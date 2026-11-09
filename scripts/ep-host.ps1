<# Local CLI launcher only; does not install services or edit host settings. #>
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot 'api\.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $taskPython -PathType Leaf) {
    & $taskPython (Join-Path $PSScriptRoot 'ep-host.py') @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.11 (Join-Path $PSScriptRoot 'ep-host.py') @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $PSScriptRoot 'ep-host.py') @args
} else {
    Write-Error 'Python 3.11+ is required. No configuration was changed.'
    exit 2
}
exit $LASTEXITCODE
