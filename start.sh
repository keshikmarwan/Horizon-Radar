#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS_NAME="$(uname -s)"

case "$OS_NAME" in
  Darwin)
    exec "$ROOT_DIR/scripts/launch/start-mac.sh"
    ;;
  Linux)
    echo "Su Linux usa:"
    echo "  backend: cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    echo "  frontend: cd frontend && npm install && npm run dev"
    exit 1
    ;;
  MINGW*|MSYS*|CYGWIN*)
    exec cmd.exe /c "\"%CD%\\scripts\\launch\\start-windows.bat\""
    ;;
  *)
    echo "Sistema operativo non supportato: $OS_NAME"
    exit 1
    ;;
esac
