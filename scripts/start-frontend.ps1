$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $repoRoot 'frontend')
$node = Get-Command node -ErrorAction SilentlyContinue
$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if (-not $node -or -not $pnpm) {
    throw 'Node.js or pnpm is missing.'
}
$env:Path = "$(Split-Path -Parent $node.Source);$env:Path"
& $pnpm.Source dev
if ($LASTEXITCODE -ne 0) {
    throw "Vite exited with code $LASTEXITCODE"
}

