$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:SEARXNG_API_TOKEN = (Get-Content -LiteralPath (Join-Path $root 'api-token.txt') -Raw).Trim()
$python = 'C:\Python311\python.exe'
$stdout = Join-Path $root 'guard.stdout.log'
$stderr = Join-Path $root 'guard.stderr.log'
$process = Start-Process -FilePath $python -ArgumentList (Join-Path $root 'searxng_guard.py') -WorkingDirectory $root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -Wait -PassThru -WindowStyle Hidden
exit $process.ExitCode
