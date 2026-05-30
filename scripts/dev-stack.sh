#!/usr/bin/env bash
# Arranca API Litestar (uvicorn) y opcionalmente n8n y panel Angular.
#
#   bash scripts/dev-stack.sh
#   START_N8N=0 bash scripts/dev-stack.sh
#   START_PANEL=1 bash scripts/dev-stack.sh
#   DEV_BIND_HOST=0.0.0.0 bash scripts/dev-stack.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-5000}"
PANEL_PORT="${PANEL_PORT:-4200}"
N8N_PORT="${N8N_PORT:-5678}"
START_N8N="${START_N8N:-auto}"
N8N_DOCKER_NAME="${N8N_DOCKER_NAME:-cherry-n8n-local}"
BIND_HOST="${DEV_BIND_HOST:-127.0.0.1}"

_activate_venv() {
  if [[ -f ".venv/Scripts/activate" ]]; then source ".venv/Scripts/activate"
  elif [[ -f ".venv/bin/activate" ]]; then source ".venv/bin/activate"
  elif [[ -f "venv/Scripts/activate" ]]; then source "venv/Scripts/activate"
  elif [[ -f "venv/bin/activate" ]]; then source "venv/bin/activate"
  else
    echo "[error] No hay entorno virtual en .venv ni en venv" >&2
    exit 1
  fi
}

_cleanup() {
  if [[ -n "${UV_PID:-}" ]] && kill -0 "$UV_PID" 2>/dev/null; then
    kill "$UV_PID" 2>/dev/null || true
    wait "$UV_PID" 2>/dev/null || true
  fi
  if [[ -n "${PANEL_PID:-}" ]] && kill -0 "$PANEL_PID" 2>/dev/null; then
    kill "$PANEL_PID" 2>/dev/null || true
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
  if [[ "$START_N8N" == "docker" ]] && command -v docker >/dev/null 2>&1; then
    docker rm -f "$N8N_DOCKER_NAME" >/dev/null 2>&1 || true
    docker run -d --rm --name "$N8N_DOCKER_NAME" -p "${N8N_PORT}:5678" -e TZ="${TZ:-America/Bogota}" n8nio/n8n:latest >/dev/null
    N8N_STARTED_DOCKER=1
    echo "[ok] n8n (Docker) → http://127.0.0.1:${N8N_PORT}"
  elif [[ "$START_N8N" == "npx" ]] && command -v npx >/dev/null 2>&1; then
    export N8N_PORT="$N8N_PORT"
    npx --yes n8n &
    N8N_NPX_PID=$!
    echo "[ok] n8n (npx) → http://127.0.0.1:${N8N_PORT}"
  elif [[ "$START_N8N" == "auto" ]]; then
    if command -v npx >/dev/null 2>&1; then
      export N8N_PORT="$N8N_PORT"
      npx --yes n8n &
      N8N_NPX_PID=$!
      echo "[ok] n8n (npx) → http://127.0.0.1:${N8N_PORT}"
    elif command -v docker >/dev/null 2>&1; then
      docker rm -f "$N8N_DOCKER_NAME" >/dev/null 2>&1 || true
      docker run -d --rm --name "$N8N_DOCKER_NAME" -p "${N8N_PORT}:5678" -e TZ="${TZ:-America/Bogota}" n8nio/n8n:latest >/dev/null
      N8N_STARTED_DOCKER=1
      echo "[ok] n8n (Docker) → http://127.0.0.1:${N8N_PORT}"
    fi
  fi
fi

_resolve_panel_root() {
  if [[ -n "${CHERRY_ANGULAR_ROOT:-}" ]] && [[ -f "${CHERRY_ANGULAR_ROOT}/package.json" ]]; then
    echo "$CHERRY_ANGULAR_ROOT"
    return
  fi
  local sibling="${ROOT%/}/../cherry_tattoo_angular"
  if [[ -f "${sibling}/package.json" ]]; then
    echo "$sibling"
    return
  fi
}

if [[ "${START_PANEL:-}" =~ ^(1|true|yes|on)$ ]]; then
  PANEL_ROOT="$(_resolve_panel_root || true)"
  if [[ -n "$PANEL_ROOT" ]] && command -v npm >/dev/null 2>&1; then
    (cd "$PANEL_ROOT" && npm start) &
    PANEL_PID=$!
    echo "[ok] Panel Angular → http://127.0.0.1:${PANEL_PORT}"
  else
    echo "[aviso] START_PANEL=1 pero no se encontró proyecto Angular." >&2
  fi
fi

echo "[ok] API Litestar → http://127.0.0.1:${API_PORT} (bind ${BIND_HOST})"
if [[ -z "${PANEL_PID:-}" ]]; then
  echo "[info] Panel: cd cherry_tattoo_angular && npm start" >&2
fi
echo "[info] Ctrl+C detiene la API." >&2

python -m uvicorn app.main:app --host "$BIND_HOST" --port "$API_PORT"
