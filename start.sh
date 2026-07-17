#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  echo "Crie .env a partir de .env.example e preencha as credenciais." >&2
  exit 1
fi
set -a
. ./.env
set +a
python3 -m pip install -r requirements.txt
exec python3 main.py
