#!/usr/bin/env bash
# Arranca API Litestar (uvicorn), panel Streamlit y opcionalmente n8n.
#
# Windows (Git Bash): desde la raíz del repo
#   bash scripts/dev-stack.sh
#
# Variables opcionales:
#   API_PORT=5000 STREAMLIT_PORT=8501 N8N_PORT=5678
#   START_N8N=0          → no intentar levantar n8n
#   START_N8N=auto       → npx si existe (sin Docker); si no, Docker (valor por defecto)
#   START_N8N=npx        → solo `npx n8n` (requiere Node.js)
#   START_N8N=docker     → solo Docker
#   DEV_BIND_HOST=0.0.0.0 → API y Streamlit accesibles en la LAN (por defecto 127.0.0.1)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-5000}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"
N8N_PORT="${N8N_PORT:-5678}"
START_N8N="${START_N8N:-auto}"
N8N_DOCKER_NAME="${N8N_DOCKER_NAME:-cherry-n8n-local}"
BIND_HOST="${DEV_BIND_HOST:-127.0.0.1}"

_activate_venv() {
  if [[ -f ".venv/Scripts/activate" ]]; then
    # shellcheck source=/dev/null
    source ".venv/Scripts/activate"
  elif [[ -f ".venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source ".venv/bin/activate"
  elif [[ -f "venv/Scripts/activate" ]]; then
    # shellcheck source=/dev/null
    source "venv/Scripts/activate"
  elif [[ -f "venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "venv/bin/activate"
  else
    echo "[error] No hay entorno virtual en .venv ni en venv" >&2
    echo "  python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt" >&2
    exit 1
  fi
}

_cleanup() {
  if [[ -n "${UV_PID:-}" ]] && kill -0 "$UV_PID" 2>/dev/null; then
    kill "$UV_PID" 2>/dev/null || true
    wait "$UV_PID" 2>/dev/null || true
  fi
  if [[ -n "${N8N_NPX_PID:-}" ]] && kill -0 "$N8N_NPX_PID" 2>/dev/null; then
    kill "$N8N_NPX_PID" 2>/dev/null || true
  fi
  if [[ "${N8N_STARTED_DOCKER:-0}" == "1" ]]; then
    docker stop "$N8N_DOCKER_NAME" >/dev/null 2>&1 || true
  fi
}

trap _cleanup EXIT INT TERM

_activate_venv

if [[ "$START_N8N" != "0" ]]; then
  N8N_STARTED_DOCKER=0
  if [[ "$START_N8N" == "docker" ]]; then
    if command -v docker >/dev/null 2>&1; then
      docker rm -f "$N8N_DOCKER_NAME" >/dev/null 2>&1 || true
      docker run -d --rm --name "$N8N_DOCKER_NAME" \
        -p "${N8N_PORT}:5678" \
        -e TZ="${TZ:-America/Bogota}" \
        n8nio/n8n:latest >/dev/null
      N8N_STARTED_DOCKER=1
      echo "[ok] n8n (Docker) → http://127.0.0.1:${N8N_PORT}"
    else
      echo "[aviso] Docker no está en PATH; define START_N8N=npx o START_N8N=0" >&2
    fi
  elif [[ "$START_N8N" == "npx" ]]; then
    if command -v npx >/dev/null 2>&1; then
      export N8N_PORT="$N8N_PORT"
      npx --yes n8n &
      N8N_NPX_PID=$!
      echo "[ok] n8n (npx) → http://127.0.0.1:${N8N_PORT}"
    else
      echo "[error] npx no encontrado (instala Node.js)" >&2
      exit 1
    fi
  elif [[ "$START_N8N" == "auto" ]]; then
    if command -v npx >/dev/null 2>&1; then
      export N8N_PORT="$N8N_PORT"
      npx --yes n8n &
      N8N_NPX_PID=$!
      echo "[ok] n8n (npx, sin Docker) → http://127.0.0.1:${N8N_PORT}"
    elif command -v docker >/dev/null 2>&1; then
      echo "[info] npx no encontrado; intentando n8n con Docker…" >&2
      docker rm -f "$N8N_DOCKER_NAME" >/dev/null 2>&1 || true
      docker run -d --rm --name "$N8N_DOCKER_NAME" \
        -p "${N8N_PORT}:5678" \
        -e TZ="${TZ:-America/Bogota}" \
        n8nio/n8n:latest >/dev/null
      N8N_STARTED_DOCKER=1
      echo "[ok] n8n (Docker) → http://127.0.0.1:${N8N_PORT}"
    else
      echo "[aviso] Sin npx ni Docker; omitiendo n8n. API y Streamlit siguen." >&2
    fi
  fi
fi

python -m uvicorn app.main:app --host "$BIND_HOST" --port "$API_PORT" &
UV_PID=$!

# Dar tiempo mínimo a que el puerto escuche (Streamlit hablará con la API al cargar)
sleep 1

echo "[ok] API Litestar → http://127.0.0.1:${API_PORT} (bind ${BIND_HOST})"
echo "[ok] Streamlit    → http://127.0.0.1:${STREAMLIT_PORT} (bind ${BIND_HOST})"
if [[ "$BIND_HOST" == "0.0.0.0" ]]; then
  echo "[info] Desde otra máquina en la LAN: http://<IP-de-esta-PC>:${STREAMLIT_PORT} (panel) y :${API_PORT} (API)" >&2
  echo "[info] El cliente Streamlit en el servidor puede seguir usando API_BASE_URL=http://127.0.0.1:${API_PORT}" >&2
fi
echo ""
echo "Cierra Streamlit (Ctrl+C) para detener también la API y el contenedor n8n (si se creó)."

python -m streamlit run streamlit_app/main.py \
  --server.address "$BIND_HOST" \
  --server.port "$STREAMLIT_PORT"
