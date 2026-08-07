$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$chromaPath = Join-Path $repoRoot 'data\chroma'
$chroma = Join-Path $repoRoot 'backend\.venv\Scripts\chroma.exe'
New-Item -ItemType Directory -Force -Path $chromaPath | Out-Null
& $chroma run --path $chromaPath --host 127.0.0.1 --port 8001
