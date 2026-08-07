$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$condaPython = 'C:\ProgramData\anaconda3\python.exe'
$backendRoot = Join-Path $repoRoot 'backend'
$venvPython = Join-Path $backendRoot '.venv\Scripts\python.exe'

function Invoke-Checked {
    param([string]$FilePath, [string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

if (-not (Test-Path -LiteralPath $condaPython)) {
    throw "Conda Python not found: $condaPython"
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Invoke-Checked $condaPython @('-m', 'venv', (Join-Path $backendRoot '.venv'))
}

Invoke-Checked $venvPython @('-m', 'pip', 'install', '--upgrade', 'pip')
Invoke-Checked $venvPython @('-m', 'pip', 'install', '-e', "${backendRoot}[dev]")

Write-Host 'Python venv is ready: backend/.venv'
