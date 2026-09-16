#!/usr/bin/env bash
set -euo pipefail

# Unified remote stack entrypoint. Override RDS_STACK_CONFIG when needed.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${RDS_STACK_CONFIG:-$ROOT_DIR/config/remote-stack.env}"
STACK="${ROOT_DIR}/remote-stack.sh"

[[ -f "$CONFIG_FILE" ]] || { echo "missing config: $CONFIG_FILE" >&2; exit 1; }
[[ -x "$STACK" ]] || { echo "missing executable: $STACK" >&2; exit 1; }

export RDS_STACK_CONFIG="$CONFIG_FILE"

case "${1:-status}" in
  setup|start|stop|restart|status|logs)
    exec "$STACK" "$1"
    ;;
  *)
    echo "usage: $0 {setup|start|stop|restart|status|logs}" >&2
    exit 2
    ;;
esac
