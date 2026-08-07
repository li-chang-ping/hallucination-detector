$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repoRoot 'backend'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
Push-Location $backendRoot
try {
    & $python -m alembic upgrade head
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
} finally { Pop-Location }

