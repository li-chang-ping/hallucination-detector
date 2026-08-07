$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$condaPython = 'C:\ProgramData\anaconda3\python.exe'
$backendRoot = Join-Path $repoRoot 'backend'
$venvPython = Join-Path $backendRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $condaPython)) {
    throw "未找到 Conda Python: $condaPython"
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $condaPython -m venv (Join-Path $backendRoot '.venv')
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e "${backendRoot}[dev]"

Write-Host 'Python venv 已就绪：backend/.venv'
