#!/usr/bin/env bash

set -euo pipefail

# 参考 us_stock_screener/scripts/dev_server.sh 的 start/stop/restart/status 模式。
# 本项目差异：后端是 Flask+SocketIO（run.py 读 PORT 环境变量），前端 Vite 的
# proxy 在 vite.config.ts 里硬编码指向 127.0.0.1:5000 —— 因此后端端口覆盖
# 只对绕过 Vite 直连后端的场景有效，默认保持 5000 以配合前端代理。

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${DEV_SERVER_RUN_DIR:-$ROOT_DIR/.run}"
BACKEND_DIR="${DEV_SERVER_BACKEND_DIR:-$ROOT_DIR}"
FRONTEND_DIR="${DEV_SERVER_FRONTEND_DIR:-$ROOT_DIR/frontend}"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG_FILE="$RUN_DIR/backend.log"
FRONTEND_LOG_FILE="$RUN_DIR/frontend.log"

BACKEND_PORT="${DEV_SERVER_BACKEND_PORT:-5000}"
# Vite 占用时级联到下一个空闲端口，清一小段范围；随 FRONTEND_PORT 联动。
FRONTEND_PORT="${DEV_SERVER_FRONTEND_PORT:-5180}"
FRONTEND_CLEANUP_MAX_PORT="${DEV_SERVER_FRONTEND_CLEANUP_MAX_PORT:-$((FRONTEND_PORT + 18))}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"

if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  DEFAULT_BACKEND_CMD="source .venv/bin/activate && PORT=${BACKEND_PORT} python run.py"
else
  DEFAULT_BACKEND_CMD="PORT=${BACKEND_PORT} python run.py"
fi
DEFAULT_FRONTEND_CMD="npm run dev -- --host 127.0.0.1 --port ${FRONTEND_PORT}"

BACKEND_CMD="${DEV_SERVER_BACKEND_CMD:-$DEFAULT_BACKEND_CMD}"
FRONTEND_CMD="${DEV_SERVER_FRONTEND_CMD:-$DEFAULT_FRONTEND_CMD}"
SKIP_CHECKS="${DEV_SERVER_SKIP_CHECKS:-0}"


usage() {
  cat <<'EOF'
Usage: bash scripts/dev_server.sh <start|stop|restart|status>

Ports default to backend 5000 / frontend 5180. Backend port override only
takes effect for direct backend access: the Vite proxy in
frontend/vite.config.ts hardcodes 127.0.0.1:5000.

  DEV_SERVER_BACKEND_PORT            backend port            (default 5000)
  DEV_SERVER_FRONTEND_PORT           frontend port           (default 5180)
  DEV_SERVER_FRONTEND_CLEANUP_MAX_PORT  kill range end       (default FRONTEND_PORT+18)
  DEV_SERVER_RUN_DIR                 pid/log dir             (default .run)
  DEV_SERVER_BACKEND_DIR             backend working dir     (default repo root)
  DEV_SERVER_FRONTEND_DIR            frontend working dir    (default frontend)
  DEV_SERVER_BACKEND_CMD             command override
  DEV_SERVER_FRONTEND_CMD            command override
  DEV_SERVER_SKIP_CHECKS            1 = skip dependency check
EOF
}


ensure_run_dir() {
  mkdir -p "$RUN_DIR"
}


load_backend_env() {
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ROOT_DIR/.env"
    set +a
  fi
}


require_dependencies() {
  if [[ "$SKIP_CHECKS" == "1" ]]; then
    return 0
  fi

  if [[ ! -f "$ROOT_DIR/.venv/bin/activate" ]] && ! command -v python >/dev/null 2>&1; then
    echo "missing backend runtime: create $ROOT_DIR/.venv or install python on PATH" >&2
    exit 1
  fi

  if [[ ! -f "$BACKEND_DIR/run.py" ]]; then
    echo "missing backend entrypoint: $BACKEND_DIR/run.py" >&2
    exit 1
  fi

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "missing frontend dependencies: $FRONTEND_DIR/node_modules" >&2
    exit 1
  fi
}


read_pid() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi
  tr -d '[:space:]' <"$pid_file"
}


is_running() {
  local pid_file="$1"
  local pid

  if ! pid="$(read_pid "$pid_file")"; then
    return 1
  fi

  if [[ -z "$pid" ]]; then
    rm -f "$pid_file"
    return 1
  fi

  if kill -0 "$pid" 2>/dev/null; then
    return 0
  fi

  rm -f "$pid_file"
  return 1
}


port_is_listening() {
  local port="$1"
  [[ -n "$(lsof -ti tcp:"$port" 2>/dev/null)" ]]
}


# Kill all processes (including children) listening on a given port.
kill_port() {
  local port="$1"
  local pids
  pids="$(lsof -ti tcp:"$port" 2>/dev/null)" || true
  if [[ -z "$pids" ]]; then
    return 0
  fi
  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
  done
  # Wait briefly for graceful shutdown
  for _ in {1..10}; do
    pids="$(lsof -ti tcp:"$port" 2>/dev/null)" || true
    [[ -z "$pids" ]] && return 0
    sleep 0.3
  done
  # Force kill stragglers
  pids="$(lsof -ti tcp:"$port" 2>/dev/null)" || true
  for pid in $pids; do
    kill -9 "$pid" 2>/dev/null || true
  done
}


kill_port_range() {
  local start_port="$1"
  local end_port="$2"
  local port

  for port in $(seq "$start_port" "$end_port"); do
    kill_port "$port"
  done
}


cleanup_frontend_ports() {
  # Old Vite dev servers can linger on a cascade of local ports after
  # repeated restarts. Clear the whole range before starting again.
  kill_port_range "$FRONTEND_PORT" "$FRONTEND_CLEANUP_MAX_PORT"
}


start_service() {
  local name="$1"
  local service_dir="$2"
  local command="$3"
  local pid_file="$4"
  local log_file="$5"

  if is_running "$pid_file"; then
    echo "$name already running (pid $(read_pid "$pid_file"))"
    return 0
  fi

  (
    cd "$service_dir"
    nohup bash -lc "$command" >>"$log_file" 2>&1 &
    echo $! >"$pid_file"
  )

  sleep 1

  if ! is_running "$pid_file"; then
    echo "failed to start $name; see $log_file" >&2
    exit 1
  fi

  echo "started $name (pid $(read_pid "$pid_file"))"
}


stop_service() {
  local name="$1"
  local pid_file="$2"
  local port="$3"

  # First, try graceful stop via PID file
  if is_running "$pid_file"; then
    local pid
    pid="$(read_pid "$pid_file")"
    # Kill the process group (negative PID) to catch child processes
    kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true

    for _ in {1..20}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.25
    done

    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi

  rm -f "$pid_file"

  # Nuclear option: kill anything still listening on the port.
  # This catches orphaned children from the Flask dev server.
  kill_port "$port"

  echo "stopped $name"
}


status_service() {
  local name="$1"
  local pid_file="$2"
  local url="$3"
  local port="${4:-}"

  if is_running "$pid_file"; then
    echo "$name: running (pid $(read_pid "$pid_file")) $url"
    return 0
  fi

  if [[ -n "$port" ]] && port_is_listening "$port"; then
    echo "$name: running (port $port) $url"
    return 0
  fi

  echo "$name: stopped"
  return 1
}


start_all() {
  ensure_run_dir
  load_backend_env
  require_dependencies

  # Clear previous logs for cleaner output
  : > "$BACKEND_LOG_FILE"
  : > "$FRONTEND_LOG_FILE"

  start_service "backend" "$BACKEND_DIR" "$BACKEND_CMD" "$BACKEND_PID_FILE" "$BACKEND_LOG_FILE"
  cleanup_frontend_ports
  start_service "frontend" "$FRONTEND_DIR" "$FRONTEND_CMD" "$FRONTEND_PID_FILE" "$FRONTEND_LOG_FILE"
  echo "backend url: $BACKEND_URL"
  echo "frontend url: $FRONTEND_URL"
}


stop_all() {
  ensure_run_dir
  stop_service "backend" "$BACKEND_PID_FILE" "$BACKEND_PORT"
  stop_service "frontend" "$FRONTEND_PID_FILE" "$FRONTEND_PORT"
  cleanup_frontend_ports
}


status_all() {
  ensure_run_dir
  local result=0
  status_service "backend" "$BACKEND_PID_FILE" "$BACKEND_URL" "$BACKEND_PORT" || result=1
  status_service "frontend" "$FRONTEND_PID_FILE" "$FRONTEND_URL" "$FRONTEND_PORT" || result=1
  return "$result"
}


main() {
  local command="${1:-}"

  case "$command" in
    start)
      start_all
      ;;
    stop)
      stop_all
      ;;
    restart)
      stop_all
      start_all
      ;;
    status)
      status_all
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}


main "$@"
