$ErrorActionPreference = 'Stop'

$credentialFile = 'K:\URPA\cloud-release.local.bat'
$remoteRoot = 'G:\urpa-agent-server\geocoding-search'

function Get-ConfigValue([string]$name) {
    $pattern = '^set "' + [regex]::Escape($name) + '=(.*)"$'
    $line = Select-String -LiteralPath $credentialFile -Pattern $pattern
    if (-not $line) { throw "Missing $name in credential file" }
    return $line.Matches[0].Groups[1].Value
}

$securePassword = ConvertTo-SecureString (Get-ConfigValue 'URPA_INTRANET_REMOTE_PASSWORD') -AsPlainText -Force
$credential = [pscredential]::new((Get-ConfigValue 'URPA_INTRANET_REMOTE_USER'), $securePassword)
$session = New-PSSession -ComputerName 'WANGPAN' -Credential $credential

try {
    Invoke-Command -Session $session -ScriptBlock {
        param($root)
        foreach ($taskName in @('Geocoding SearXNG', 'Geocoding SearXNG Guard')) {
            $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            $info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
            [pscustomobject]@{ Task = $taskName; State = $task.State; LastResult = $info.LastTaskResult }
        }

        Get-NetTCPConnection -LocalPort 8888, 8889 -State Listen -ErrorAction SilentlyContinue |
            Select-Object LocalAddress, LocalPort, OwningProcess

        $searxLog = Join-Path $root 'searxng.stderr.log'
        if (Test-Path -LiteralPath $searxLog) {
            [pscustomobject]@{ Check = 'SearXNG log'; Output = ((Get-Content -LiteralPath $searxLog -Tail 40) -join "`n") }
        }
        $guardLog = Join-Path $root 'guard.stdout.log'
        if (Test-Path -LiteralPath $guardLog) {
            [pscustomobject]@{ Check = 'Guard log'; Output = ((Get-Content -LiteralPath $guardLog -Tail 20) -join "`n") }
        }

        $python = Join-Path $root 'bundle\searxng\venv\Scripts\python.exe'
        $importOutput = & $python -c 'import searx; print(1)' 2>&1
        [pscustomobject]@{ Check = 'Python import'; ExitCode = $LASTEXITCODE; Output = ($importOutput -join "`n") }

        if (-not (Get-NetTCPConnection -LocalPort 8888 -State Listen -ErrorAction SilentlyContinue)) {
            $env:SEARXNG_SETTINGS_PATH = Join-Path $root 'settings.yml'
            $workingDirectory = Join-Path $root 'bundle\searxng'
            $stdout = Join-Path $root 'diagnostic.stdout.log'
            $stderr = Join-Path $root 'diagnostic.stderr.log'
            $process = Start-Process -FilePath $python -ArgumentList '-m', 'searx.webapp' -WorkingDirectory $workingDirectory -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
            Start-Sleep -Seconds 5
            $wasRunning = -not $process.HasExited
            if ($wasRunning) { Stop-Process -Id $process.Id -Force }
            [pscustomobject]@{
                Check = 'SearXNG diagnostic start'
                WasRunning = $wasRunning
                ExitCode = $(if ($wasRunning) { $null } else { $process.ExitCode })
                Stdout = $(if (Test-Path -LiteralPath $stdout) { (Get-Content -LiteralPath $stdout -Tail 80) -join "`n" })
                Stderr = $(if (Test-Path -LiteralPath $stderr) { (Get-Content -LiteralPath $stderr -Tail 80) -join "`n" })
            }
        }

        try {
            $direct = Invoke-RestMethod -Uri 'http://127.0.0.1:8888/search?q=%E5%8C%97%E4%BA%AC&format=json' -TimeoutSec 20
            [pscustomobject]@{ Check = 'Direct search'; ResultCount = @($direct.results).Count }
        } catch {
            [pscustomobject]@{ Check = 'Direct search'; Error = $_.Exception.Message }
        }

        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8889/healthz' -TimeoutSec 10
            [pscustomobject]@{ Check = 'Guard health'; Status = $health.status }
        } catch {
            [pscustomobject]@{ Check = 'Guard health'; Error = $_.Exception.Message }
        }

        try {
            Invoke-WebRequest -Uri 'http://127.0.0.1:8889/search?q=test&format=json' -UseBasicParsing -TimeoutSec 10 | Out-Null
            [pscustomobject]@{ Check = 'Guard unauthenticated'; Status = 'UNEXPECTEDLY_ALLOWED' }
        } catch {
            [pscustomobject]@{ Check = 'Guard unauthenticated'; StatusCode = [int]$_.Exception.Response.StatusCode }
        }

        $token = (Get-Content -LiteralPath (Join-Path $root 'api-token.txt') -Raw).Trim()
        try {
            $secured = Invoke-RestMethod -Uri 'http://127.0.0.1:8889/search?q=%E5%8C%97%E4%BA%AC&format=json' -Headers @{ 'X-SearXNG-Token' = $token } -TimeoutSec 20
            [pscustomobject]@{ Check = 'Guard authenticated'; ResultCount = @($secured.results).Count }
        } catch {
            $responseBody = ''
            if ($_.Exception.Response) {
                $reader = [IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
                $responseBody = $reader.ReadToEnd()
                $reader.Dispose()
            }
            [pscustomobject]@{ Check = 'Guard authenticated'; Error = $_.Exception.Message; Body = $responseBody }
        }

        try {
            $public = Invoke-RestMethod -Uri 'https://geosearch.luwug.top/search?q=%E5%8C%97%E4%BA%AC&format=json' -Headers @{ 'X-SearXNG-Token' = $token } -TimeoutSec 30
            [pscustomobject]@{ Check = 'Public tunnel authenticated'; ResultCount = @($public.results).Count }
        } catch {
            [pscustomobject]@{ Check = 'Public tunnel authenticated'; Error = $_.Exception.Message }
        }
    } -ArgumentList $remoteRoot | Format-List
} finally {
    Remove-PSSession $session
}
