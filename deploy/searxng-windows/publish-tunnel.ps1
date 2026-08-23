$ErrorActionPreference = 'Stop'

$credentialFile = 'K:\URPA\cloud-release.local.bat'
$hostname = 'geosearch.luwug.top'
$tunnelId = 'f38ab496-deec-401f-a076-8aa55979dba6'

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
        param($hostName, $id)
        $cloudflaredRoot = 'G:\urpa-agent-server\cloudflared'
        $configPath = Join-Path $cloudflaredRoot 'config.yml'
        $executable = Join-Path $cloudflaredRoot 'cloudflared.exe'
        $certificate = 'C:\Users\wangpan\.cloudflared\cert.pem'
        foreach ($required in @($configPath, $executable, $certificate)) {
            if (-not (Test-Path -LiteralPath $required)) { throw "Required Cloudflare file is missing: $required" }
        }

        $config = Get-Content -LiteralPath $configPath -Raw
        if ($config -notmatch ('(?m)^\s*- hostname:\s*' + [regex]::Escape($hostName) + '\s*$')) {
            $fallback = '(?m)^(\s*)- service:\s*http_status:404\s*$'
            if ($config -notmatch $fallback) { throw 'Cloudflare fallback ingress rule was not found' }
            $indent = $Matches[1]
            $newRule = $indent + '- hostname: ' + $hostName + "`r`n" + $indent + '  service: http://127.0.0.1:8889' + "`r`n" + $indent + '- service: http_status:404'
            $backupPath = Join-Path $cloudflaredRoot ('config.yml.backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
            Copy-Item -LiteralPath $configPath -Destination $backupPath
            $updated = [regex]::Replace($config, $fallback, $newRule, 1)
            [IO.File]::WriteAllText($configPath, $updated, [Text.UTF8Encoding]::new($false))
        }

        & $executable --config $configPath tunnel ingress validate
        if ($LASTEXITCODE -ne 0) { throw 'Cloudflare ingress validation failed' }

        $dnsOutput = & $executable --origincert $certificate tunnel route dns $id $hostName 2>&1
        if ($LASTEXITCODE -ne 0 -and ($dnsOutput -join "`n") -notmatch 'already exists') {
            throw "Cloudflare DNS route failed: $($dnsOutput -join ' ')"
        }

        Restart-Service -Name 'Cloudflared'
        $service = Get-Service -Name 'Cloudflared'
        [pscustomobject]@{ Hostname = $hostName; Tunnel = $id; ServiceState = $service.Status; IngressValidated = $true }
    } -ArgumentList $hostname, $tunnelId | Format-List
} finally {
    Remove-PSSession $session
}
