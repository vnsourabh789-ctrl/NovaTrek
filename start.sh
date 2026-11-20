#!/usr/bin/env sh
# NovaTrek one-click launcher (macOS/Linux): venv + deps + server.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
echo "NovaTrek -> http://127.0.0.1:8000"
exec python -m novatrek
