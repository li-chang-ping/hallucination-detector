#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
conda_python="${CONDA_PYTHON:-python}"

"$conda_python" -m venv "$repo_root/backend/.venv"
"$repo_root/backend/.venv/bin/python" -m pip install --upgrade pip
"$repo_root/backend/.venv/bin/python" -m pip install -e "$repo_root/backend[dev]"
