#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUNTIME_DIR="$ROOT_DIR/runtime"
LOG_DIR="$RUNTIME_DIR/logs"
BACKEND_HOST="0.0.0.0"
BACKEND_PORT="8000"
FRONTEND_PORT="3000"

detect_lan_ip() {
  local ip=""
  ip="$(ipconfig getifaddr en0 2>/dev/null || true)"
  if [[ -z "$ip" ]]; then
    ip="$(ipconfig getifaddr en1 2>/dev/null || true)"
  fi
  if [[ -z "$ip" ]]; then
    ip="$(route -n get default 2>/dev/null | awk '/interface:/{print $2}' | xargs -I{} ipconfig getifaddr {} 2>/dev/null || true)"
  fi
  echo "$ip"
}

LAN_IP="$(detect_lan_ip)"
if [[ -z "${LAN_IP:-}" ]]; then
  LAN_IP="127.0.0.1"
fi
API_URL="http://${LAN_IP}:${BACKEND_PORT}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Comando mancante: $1"
    echo "Installa dipendenza e rilancia lo script."
    exit 1
  fi
}

pick_python() {
  local candidates=("python3.14" "python3.13" "python3.12" "python3.11" "python3.10" "python3")
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

validate_python_version() {
  local py_bin="$1"
  local major minor
  major="$("$py_bin" -c 'import sys; print(sys.version_info.major)')"
  minor="$("$py_bin" -c 'import sys; print(sys.version_info.minor)')"
  if [[ "$major" -ne 3 || "$minor" -lt 11 ]]; then
    echo "Python non supportato: $("$py_bin" --version 2>&1)"
    echo "Installa Python 3.11+ e rilancia lo script."
    exit 1
  fi
}

venv_is_healthy() {
  local venv_python="$BACKEND_DIR/.venv/bin/python3"
  if [[ ! -x "$venv_python" ]]; then
    return 1
  fi
  if [[ -d "$BACKEND_DIR/.venv/Scripts" || -d "$BACKEND_DIR/.venv/Lib" ]]; then
    return 1
  fi
  PYTHONNOUSERSITE=1 "$venv_python" -c 'import site' >/dev/null 2>&1
}

kill_port() {
  local port="$1"
  local pids
  pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "Chiudo processi su porta ${port}..."
    kill -9 $pids >/dev/null 2>&1 || true
  fi
}

require_cmd npm
require_cmd lsof
require_cmd osascript

PYTHON_BIN="$(pick_python || true)"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "Python non trovato. Installa Python 3.11+ e rilancia."
  exit 1
fi
validate_python_version "$PYTHON_BIN"

if [[ ! -w "$ROOT_DIR" || ! -w "$BACKEND_DIR" || ! -w "$FRONTEND_DIR" ]]; then
  echo "Permessi insufficienti nella cartella progetto."
  echo "Esegui: chmod -R u+rwX \"$ROOT_DIR\""
  exit 1
fi

mkdir -p "$RUNTIME_DIR" "$LOG_DIR" "$BACKEND_DIR/data"
mkdir -p "$RUNTIME_DIR/reports" "$RUNTIME_DIR/snapshots"

GROQ_API_KEY_VALUE="${GROQ_API_KEY:-}"

cat > "$BACKEND_DIR/.env" <<EOF
DATABASE_URL=sqlite:///./data/horizonradar.db
REDIS_URL=redis://localhost:6379/0
GROQ_API_KEY=${GROQ_API_KEY_VALUE}
OPENAI_API_KEY=
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=text-embedding-3-small
SNAPSHOT_DIR=../runtime/snapshots
REPORT_DIR=../runtime/reports
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
EMAIL_FROM=noreply@horizonradar.local
APP_BASE_URL=http://localhost:${FRONTEND_PORT}
EOF

if [[ -z "$GROQ_API_KEY_VALUE" ]]; then
  echo ""
  echo "⚠  GROQ_API_KEY non trovata. Scoring LLM e estrazione topic non funzioneranno."
  echo "   Ottieni una chiave gratuita su https://console.groq.com/"
  echo "   Poi rilancia con: GROQ_API_KEY=gsk_... ./scripts/launch/start-mac.sh"
  echo ""
fi

cat > "$FRONTEND_DIR/.env.local" <<EOF
NEXT_PUBLIC_API_URL=${API_URL}
NEXT_PUBLIC_DEMO_USER_ID=demo-user
AUTH_SECRET=devsecret
AUTH_URL=http://${LAN_IP}:${FRONTEND_PORT}
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
EOF

if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  echo "Creo virtualenv backend..."
  "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv"
fi

if ! venv_is_healthy; then
  echo "Virtualenv non valido per macOS. Ricreo .venv..."
  rm -rf "$BACKEND_DIR/.venv"
  "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv"
fi

source "$BACKEND_DIR/.venv/bin/activate"
export PYTHONNOUSERSITE=1
export DATABASE_URL="sqlite:///./data/horizonradar.db"
export REDIS_URL="redis://localhost:6379/0"
export EMBEDDING_PROVIDER="local"
export OPENAI_API_KEY=""

REQ_HASH_FILE="$BACKEND_DIR/.venv/.requirements.sha256"
CURRENT_REQ_HASH="$(shasum -a 256 "$BACKEND_DIR/requirements.txt" | awk '{print $1}')"
STORED_REQ_HASH=""
if [[ -f "$REQ_HASH_FILE" ]]; then
  STORED_REQ_HASH="$(cat "$REQ_HASH_FILE" || true)"
fi

if [[ "$CURRENT_REQ_HASH" != "$STORED_REQ_HASH" ]]; then
  echo "Installo dipendenze backend..."
  python3 -m pip install --upgrade pip
  python3 -m pip install -r "$BACKEND_DIR/requirements.txt"
  printf '%s' "$CURRENT_REQ_HASH" > "$REQ_HASH_FILE"
fi

echo "Inizializzo DB e dati demo..."
(
  cd "$BACKEND_DIR"
  export DATABASE_URL="sqlite:///./data/horizonradar.db"
  export REDIS_URL="redis://localhost:6379/0"
  export EMBEDDING_PROVIDER="local"
  export OPENAI_API_KEY=""
  python3 scripts/init_db.py
  python3 scripts/load_demo_topics.py
  python3 scripts/seed_demo.py
)

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Installo dipendenze frontend..."
  (cd "$FRONTEND_DIR" && npm install)
fi
chmod -R +x "$FRONTEND_DIR/node_modules/.bin" >/dev/null 2>&1 || true

kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"

BACKEND_CMD="cd \"$BACKEND_DIR\" && source .venv/bin/activate && export PYTHONNOUSERSITE=1 && export PYTHONPATH=\"$BACKEND_DIR\" && export DATABASE_URL='sqlite:///./data/horizonradar.db' && export REDIS_URL='redis://localhost:6379/0' && export EMBEDDING_PROVIDER='local' && export OPENAI_API_KEY='' && export GROQ_API_KEY='$GROQ_API_KEY_VALUE' && python3 -m uvicorn app.main:app --host $BACKEND_HOST --port $BACKEND_PORT --reload"
FRONTEND_CMD="cd \"$FRONTEND_DIR\" && npm run dev -- -H 0.0.0.0 -p $FRONTEND_PORT"

if ! osascript <<EOF
tell application "Terminal"
  activate
  do script "bash -lc 'cd \"$BACKEND_DIR\" && source .venv/bin/activate && export PYTHONNOUSERSITE=1 && export PYTHONPATH=\"$BACKEND_DIR\" && export DATABASE_URL=\"sqlite:///./data/horizonradar.db\" && export REDIS_URL=\"redis://localhost:6379/0\" && export EMBEDDING_PROVIDER=\"local\" && export OPENAI_API_KEY=\"\" && export GROQ_API_KEY=\"$GROQ_API_KEY_VALUE\" && python3 -m uvicorn app.main:app --host $BACKEND_HOST --port $BACKEND_PORT --reload'"
  do script "bash -lc 'cd \"$FRONTEND_DIR\" && npm run dev -- -H 0.0.0.0 -p $FRONTEND_PORT'"
end tell
EOF
then
  echo "Apertura tab Terminal fallita. Avvio in background..."
  nohup bash -lc "$BACKEND_CMD" > "$LOG_DIR/backend.log" 2>&1 &
  nohup bash -lc "$FRONTEND_CMD" > "$LOG_DIR/frontend.log" 2>&1 &
fi

echo ""
echo "Avvio completato."
echo "Frontend locale: http://localhost:${FRONTEND_PORT}"
echo "Frontend rete:   http://${LAN_IP}:${FRONTEND_PORT}"
echo "Backend locale:  http://localhost:${BACKEND_PORT}/docs"
echo "Backend rete:    http://${LAN_IP}:${BACKEND_PORT}/docs"
