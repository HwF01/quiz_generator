#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap: backend venv + deps, frontend deps.
# Local dev runs on SQLite + in-process cache + mock LLM (no Postgres/Redis/MinIO).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== System packages (python venv support) =="
if ! dpkg -s python3.12-venv >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y python3.12-venv
fi

echo "== Backend: venv + requirements =="
cd "$REPO_ROOT/backend"
if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
python -m pip install --upgrade pip -q
pip install -r requirements.txt

echo "== Frontend: npm ci =="
cd "$REPO_ROOT/frontend"
npm ci

echo "== Setup complete =="
