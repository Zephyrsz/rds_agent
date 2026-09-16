#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${RDS_STACK_CONFIG:-/app/rds_agent/config/remote-stack.env}"
SECRETS_FILE="${RDS_STACK_SECRETS:-/app/rds_agent/config/remote-secrets.env}"
[[ -f "$CONFIG_FILE" ]] || { echo "missing config: $CONFIG_FILE" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
source "$CONFIG_FILE"
if [[ -f "$SECRETS_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$SECRETS_FILE"
fi
set +a

DUCK_SERVICE="$DUCKDB_TOOLS_ROOT/remote-service.sh"
OVERLAY="$RDS_AGENT_ROOT/integration/deepseek-harness.remote.cordis.yml"
RUN_DIR="$RDS_AGENT_ROOT/.run/remote"
LOG_DIR="$RDS_AGENT_ROOT/logs/remote"
HARNESS_PID_FILE="$RUN_DIR/harness.pid"
HARNESS_LOG="$LOG_DIR/harness.log"
mkdir -p "$RUN_DIR" "$LOG_DIR" "$RDS_AGENT_ROOT/data"

pid_alive() {
  local file="$1" pid
  [[ -f "$file" ]] || return 1
  pid="$(tr -cd '0-9' < "$file")"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

port_free() {
  ! ss -ltn | awk '{print $4}' | grep -qE ":${1}$"
}

harness_ready() {
  local code
  code="$(curl -sS --max-time 1 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$HARNESS_PORT/" 2>/dev/null || true)"
  [[ "$code" != "000" && "$code" =~ ^[0-9]{3}$ ]]
}

setup() {
  "$RDS_AGENT_PYTHON" -m pip install -r "$RDS_AGENT_ROOT/requirements.txt"
  "$DUCK_SERVICE" setup
}

start_harness() {
  if pid_alive "$HARNESS_PID_FILE"; then
    echo "DeepSeek Harness already running (PID $(cat "$HARNESS_PID_FILE"))"
    return
  fi
  [[ -f "$RDS_DB_PATH" ]] || { echo "shared DuckDB was not created: $RDS_DB_PATH" >&2; exit 1; }
  [[ -f "$RDS_METADATA_DB_PATH" ]] || { echo "shared metadata was not created: $RDS_METADATA_DB_PATH" >&2; exit 1; }
  port_free "$HARNESS_PORT" || { echo "Harness port $HARNESS_PORT is busy" >&2; exit 1; }
  cd "$HARNESS_ROOT"
  local args=(run dsh -- --profile web --patch "$OVERLAY" --no-open --host "$HARNESS_HOST" --port "$HARNESS_PORT")
  if [[ -n "${HARNESS_TRUSTED_HOST:-}" ]]; then
    args+=(--trusted-host "$HARNESS_TRUSTED_HOST")
  fi
  nohup setsid npm "${args[@]}" >"$HARNESS_LOG" 2>&1 </dev/null &
  echo "$!" > "$HARNESS_PID_FILE"
  for _ in {1..120}; do
    kill -0 "$!" 2>/dev/null || { tail -n 60 "$HARNESS_LOG" >&2 || true; exit 1; }
    harness_ready && {
      echo "DeepSeek Harness started on port $HARNESS_PORT"
      return
    }
    sleep 0.5
  done
  tail -n 60 "$HARNESS_LOG" >&2 || true
  exit 1
}

stop_harness() {
  local pid
  if ! pid_alive "$HARNESS_PID_FILE"; then
    rm -f "$HARNESS_PID_FILE"
    echo "DeepSeek Harness is not running"
    return
  fi
  pid="$(cat "$HARNESS_PID_FILE")"
  kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
  for _ in {1..40}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
  rm -f "$HARNESS_PID_FILE"
  echo "DeepSeek Harness stopped"
}

status() {
  "$DUCK_SERVICE" status
  if pid_alive "$HARNESS_PID_FILE"; then echo "harness: running PID $(cat "$HARNESS_PID_FILE") port $HARNESS_PORT"; else echo "harness: stopped"; fi
}

case "${1:-}" in
  setup) setup ;;
  start) "$DUCK_SERVICE" start; start_harness; status ;;
  stop) stop_harness; "$DUCK_SERVICE" stop ;;
  restart) "$0" stop; "$0" start ;;
  status) status ;;
  logs) tail -n 100 "$DUCKDB_TOOLS_ROOT/logs/remote/backend.log" "$DUCKDB_TOOLS_ROOT/logs/remote/frontend.log" "$HARNESS_LOG" ;;
  *) echo "usage: $0 {setup|start|stop|restart|status|logs}" >&2; exit 2 ;;
esac
