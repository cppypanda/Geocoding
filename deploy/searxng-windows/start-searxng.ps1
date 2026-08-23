$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:SEARXNG_SETTINGS_PATH = Join-Path $root 'settings.yml'
$python = Join-Path $root 'bundle\searxng\venv\Scripts\python.exe'
$stdout = Join-Path $root 'searxng.stdout.log'
$stderr = Join-Path $root 'searxng.stderr.log'
$workingDirectory = Join-Path $root 'bundle\searxng'
$process = Start-Process -FilePath $python -ArgumentList '-m', 'searx.webapp' -WorkingDirectory $workingDirectory -RedirectStandardOutput $stdout -RedirectStandardError $stderr -Wait -PassThru -WindowStyle Hidden
exit $process.ExitCode
