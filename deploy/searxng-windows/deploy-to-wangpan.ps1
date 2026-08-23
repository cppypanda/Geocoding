$ErrorActionPreference = 'Stop'

$credentialFile = 'K:\URPA\cloud-release.local.bat'
$bundleSource = 'C:\Users\user\AppData\Local\URPA\searxng'
$remoteRoot = 'G:\urpa-agent-server\geocoding-search'

function Get-ConfigValue([string]$name) {
    $pattern = '^set "' + [regex]::Escape($name) + '=(.*)"$'
    $line = Select-String -LiteralPath $credentialFile -Pattern $pattern
    if (-not $line) { throw "Missing $name in credential file" }
    return $line.Matches[0].Groups[1].Value
}

$remoteUser = Get-ConfigValue 'URPA_INTRANET_REMOTE_USER'
$remotePassword = Get-ConfigValue 'URPA_INTRANET_REMOTE_PASSWORD'
$securePassword = ConvertTo-SecureString $remotePassword -AsPlainText -Force
$credential = [pscredential]::new($remoteUser, $securePassword)
$session = New-PSSession -ComputerName 'WANGPAN' -Credential $credential

$tempRoot = Join-Path $env:TEMP ('geocoding-searxng-' + [guid]::NewGuid().ToString('N'))
$archive = Join-Path $tempRoot 'searxng-bundle.zip'
New-Item -ItemType Directory -Path $tempRoot | Out-Null

try {
    Invoke-Command -Session $session -ScriptBlock {
        param($root)
        if (-not (Test-Path -LiteralPath $root)) {
            New-Item -ItemType Directory -Path $root | Out-Null
        }
        if (-not (Test-Path -LiteralPath 'C:\Python311\python.exe')) {
            Write-Output 'Installing the official Python NuGet runtime.'
            $package = Join-Path $env:TEMP 'python-3.11.9.nupkg.zip'
            $expanded = Join-Path $env:TEMP 'python-3.11.9-nupkg'
            Invoke-WebRequest -Uri 'https://www.nuget.org/api/v2/package/python/3.11.9' -OutFile $package -UseBasicParsing
            if (-not (Test-Path -LiteralPath $expanded)) { New-Item -ItemType Directory -Path $expanded | Out-Null }
            Expand-Archive -LiteralPath $package -DestinationPath $expanded -Force
            if (-not (Test-Path -LiteralPath 'C:\Python311')) { New-Item -ItemType Directory -Path 'C:\Python311' | Out-Null }
            Copy-Item -Path (Join-Path $expanded 'tools\*') -Destination 'C:\Python311' -Recurse -Force
        }
        if (-not (Test-Path -LiteralPath 'C:\Python311\python.exe')) { throw 'Python runtime is unavailable after bootstrap' }
        & 'C:\Python311\python.exe' --version
    } -ArgumentList $remoteRoot

    $remoteBundleReady = Invoke-Command -Session $session -ScriptBlock {
        param($root)
        Test-Path -LiteralPath (Join-Path $root 'bundle\searxng\venv\Scripts\python.exe')
    } -ArgumentList $remoteRoot
    if (-not $remoteBundleReady) {
        Write-Output 'Preparing SearXNG bundle...'
        Compress-Archive -Path (Join-Path $bundleSource '*') -DestinationPath $archive -CompressionLevel Fastest
        Copy-Item -LiteralPath $archive -Destination (Join-Path $remoteRoot 'searxng-bundle.zip') -ToSession $session -Force
    }
    foreach ($name in @('settings.yml', 'searxng_guard.py', 'start-searxng.ps1', 'start-guard.ps1')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $remoteRoot $name) -ToSession $session -Force
    }

    Invoke-Command -Session $session -ScriptBlock {
        param($root)
        $bundle = Join-Path $root 'bundle'
        $bundlePython = Join-Path $bundle 'searxng\venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $bundlePython) -and (Test-Path -LiteralPath $bundle)) {
            $resolvedBundle = [System.IO.Path]::GetFullPath($bundle)
            $resolvedRoot = [System.IO.Path]::GetFullPath($root) + [System.IO.Path]::DirectorySeparatorChar
            if (-not $resolvedBundle.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Refusing to replace bundle outside deployment root'
            }
            Remove-Item -LiteralPath $resolvedBundle -Recurse -Force
        }
        if (-not (Test-Path -LiteralPath $bundlePython)) {
            Expand-Archive -LiteralPath (Join-Path $root 'searxng-bundle.zip') -DestinationPath $bundle -Force
        }

        $bundleVersion = (Get-Content -LiteralPath (Join-Path $bundle 'VERSION') -Raw).Trim()
        $versionModule = @"
VERSION_STRING = '$bundleVersion'
VERSION_TAG = '$bundleVersion'
DOCKER_TAG = '$($bundleVersion.Replace('+', '-'))'
GIT_URL = 'https://github.com/searxng/searxng'
GIT_BRANCH = 'master'
"@
        $versionPath = Join-Path $bundle 'searxng\venv\Lib\site-packages\searx\version_frozen.py'
        [IO.File]::WriteAllText($versionPath, $versionModule, [Text.UTF8Encoding]::new($false))

        $secretBytes = [byte[]]::new(48)
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        $rng.GetBytes($secretBytes)
        $searxngSecret = [Convert]::ToBase64String($secretBytes)
        $settingsPath = Join-Path $root 'settings.yml'
        $settings = Get-Content -LiteralPath $settingsPath -Raw
        if (-not $settings.Contains('__SEARXNG_SECRET__')) { throw 'SearXNG secret placeholder is missing' }
        [IO.File]::WriteAllText($settingsPath, $settings.Replace('__SEARXNG_SECRET__', $searxngSecret), [Text.UTF8Encoding]::new($false))

        $tokenPath = Join-Path $root 'api-token.txt'
        if (-not (Test-Path -LiteralPath $tokenPath) -or [string]::IsNullOrWhiteSpace((Get-Content -LiteralPath $tokenPath -Raw))) {
            $tokenBytes = [byte[]]::new(48)
            $rng.GetBytes($tokenBytes)
            $apiToken = [Convert]::ToBase64String($tokenBytes)
            [IO.File]::WriteAllText($tokenPath, $apiToken, [Text.UTF8Encoding]::new($false))
        }
        $rng.Dispose()
        & icacls.exe $tokenPath /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' | Out-Null

        $python = Join-Path $root 'bundle\searxng\venv\Scripts\python.exe'
        & $python -c 'import searx; print(1)'

        $settings = New-ScheduledTaskSettingsSet -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

        $searxAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $root 'start-searxng.ps1') + '"')
        Register-ScheduledTask -TaskName 'Geocoding SearXNG' -Action $searxAction -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

        $guardAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $root 'start-guard.ps1') + '"')
        Register-ScheduledTask -TaskName 'Geocoding SearXNG Guard' -Action $guardAction -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

        Stop-ScheduledTask -TaskName 'Geocoding SearXNG' -ErrorAction SilentlyContinue
        Stop-ScheduledTask -TaskName 'Geocoding SearXNG Guard' -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            $listenerPids = @(Get-NetTCPConnection -LocalPort 8888, 8889 -State Listen -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique)
            if ($listenerPids.Count -eq 0) { break }
            $listenerPids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Milliseconds 250
        }
        if (Get-NetTCPConnection -LocalPort 8888, 8889 -State Listen -ErrorAction SilentlyContinue) {
            throw 'Could not release SearXNG listener ports before restart'
        }
        Start-ScheduledTask -TaskName 'Geocoding SearXNG'
        Start-ScheduledTask -TaskName 'Geocoding SearXNG Guard'
        Write-Output 'REMOTE_SERVICES_STARTED'
    } -ArgumentList $remoteRoot
} finally {
    if ($session) { Remove-PSSession $session }
    if (Test-Path -LiteralPath $tempRoot) {
        $resolvedTemp = [System.IO.Path]::GetFullPath($tempRoot)
        $resolvedBase = [System.IO.Path]::GetFullPath($env:TEMP) + [System.IO.Path]::DirectorySeparatorChar
        if ($resolvedTemp.StartsWith($resolvedBase, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
    }
}
