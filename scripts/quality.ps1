$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'

Push-Location (Join-Path $repoRoot 'backend')
try {
    & $python -m ruff check app tests
    & $python -m mypy app
    & $python -m pytest
} finally { Pop-Location }

Push-Location (Join-Path $repoRoot 'frontend')
try {
    pnpm lint
    pnpm format:check
    pnpm test
    pnpm build
} finally { Pop-Location }

