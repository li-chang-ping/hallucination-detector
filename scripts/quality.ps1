$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'

function Invoke-Checked {
    param([string]$FilePath, [string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    throw 'backend/.venv is missing. Run scripts/setup.ps1 first.'
}

Push-Location (Join-Path $repoRoot 'backend')
try {
    Invoke-Checked $python @('-m', 'ruff', 'check', 'app', 'tests')
    Invoke-Checked $python @('-m', 'ruff', 'format', '--check', 'app', 'tests')
    Invoke-Checked $python @('-m', 'mypy', 'app')
    Invoke-Checked $python @('-m', 'pytest')
} finally { Pop-Location }

$node = Get-Command node -ErrorAction SilentlyContinue
$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if (-not $node -or -not $pnpm) {
    throw 'Node.js or pnpm is missing.'
}
$env:Path = "$(Split-Path -Parent $node.Source);$env:Path"

Push-Location (Join-Path $repoRoot 'frontend')
try {
    Invoke-Checked $pnpm.Source @('lint')
    Invoke-Checked $pnpm.Source @('format:check')
    Invoke-Checked $pnpm.Source @('test')
    Invoke-Checked $pnpm.Source @('build')
} finally { Pop-Location }

