#!/bin/sh
# Experimental BusyBox TCP command shim for Brewie+/ReBrewie machines.
#
# Purpose:
#   Expose a simple newline-oriented TCP port that ReBrewie Control Pi can use
#   with BREWIE_TRANSPORT=tcp. Each received line is treated as one P-command.
#
# IMPORTANT:
#   This shim cannot magically control the machine by itself. You must point one
#   of the BACKEND_* options below at the Brewie+'s real local command path
#   (serial device, FIFO pair, or vendor/community command executable).
#
# Typical Control Pi .env when this shim runs on the Brewie+ machine:
#   BREWIE_TRANSPORT=tcp
#   BREWIE_HOST=<brewie-machine-ip>
#   BREWIE_PORT=8332
#
# Examples on the Brewie+ machine:
#   LISTEN_PORT=8332 BACKEND_CMD=/usr/bin/send_brewie_command sh brewie_tcp_shim.sh
#   LISTEN_PORT=8332 SERIAL_DEV=/dev/ttyS1 sh brewie_tcp_shim.sh
#   LISTEN_PORT=8332 FIFO_IN=/tmp/brewie.in FIFO_OUT=/tmp/brewie.out sh brewie_tcp_shim.sh

set -u

LISTEN_PORT="${LISTEN_PORT:-8332}"
BACKEND_CMD="${BACKEND_CMD:-}"
SERIAL_DEV="${SERIAL_DEV:-}"
FIFO_IN="${FIFO_IN:-}"
FIFO_OUT="${FIFO_OUT:-}"
LOG_FILE="${LOG_FILE:-/tmp/rebrewie-tcp-shim.log}"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date)" "$*" >> "$LOG_FILE"
}

send_command() {
  cmd="$1"
  log "RX $cmd"

  if [ -n "$BACKEND_CMD" ]; then
    if [ ! -x "$BACKEND_CMD" ]; then
      echo "ERROR:backend_not_executable path=$BACKEND_CMD"
      log "ERR backend_not_executable $BACKEND_CMD"
      return
    fi
    "$BACKEND_CMD" "$cmd" 2>&1
    return
  fi

  if [ -n "$FIFO_IN" ]; then
    if [ ! -p "$FIFO_IN" ]; then
      echo "ERROR:fifo_in_not_found path=$FIFO_IN"
      log "ERR fifo_in_not_found $FIFO_IN"
      return
    fi
    printf '%s\n' "$cmd" > "$FIFO_IN"
    if [ -n "$FIFO_OUT" ] && [ -p "$FIFO_OUT" ]; then
      # BusyBox may not have timeout; read one immediate response if available.
      read resp < "$FIFO_OUT" && echo "$resp" || echo "OK:${cmd%% *}"
    else
      echo "OK:${cmd%% *}"
    fi
    return
  fi

  if [ -n "$SERIAL_DEV" ]; then
    if [ ! -c "$SERIAL_DEV" ]; then
      echo "ERROR:serial_not_found path=$SERIAL_DEV"
      log "ERR serial_not_found $SERIAL_DEV"
      return
    fi
    printf '%s\n' "$cmd" > "$SERIAL_DEV"
    echo "OK:${cmd%% *}"
    return
  fi

  echo "ERROR:no_backend_configured"
  log "ERR no_backend_configured"
}

serve_stdio() {
  echo "READY rebrewie_tcp_shim port=$LISTEN_PORT"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    send_command "$line"
  done
}

if [ "${1:-}" = "--stdio" ]; then
  serve_stdio
  exit 0
fi

if ! command -v nc >/dev/null 2>&1 && ! command -v netcat >/dev/null 2>&1; then
  echo "ERROR: nc/netcat not found. Run brewie_machine_probe.sh and look for available networking tools." >&2
  exit 1
fi

NC="$(command -v nc 2>/dev/null || command -v netcat)"
log "starting port=$LISTEN_PORT backend_cmd=$BACKEND_CMD serial=$SERIAL_DEV fifo_in=$FIFO_IN"
echo "Listening on TCP port $LISTEN_PORT. Log: $LOG_FILE"
echo "Stop with Ctrl-C."

# Prefer nc -e when present because it gives full duplex stdio to the handler.
if "$NC" -h 2>&1 | grep -q -- ' -e '; then
  while :; do
    "$NC" -l -p "$LISTEN_PORT" -e "$0" --stdio
  done
fi

# Portable-ish fallback for BusyBox nc builds without -e. This handles one
# command per connection and is enough for quick Control Pi send/ack testing.
while :; do
  tmp="/tmp/rebrewie-shim.$$"
  rm -f "$tmp"
  mkfifo "$tmp" || exit 1
  {
    if IFS= read -r line; then
      send_command "$line"
    fi
  } < "$tmp" | "$NC" -l -p "$LISTEN_PORT" > "$tmp"
  rm -f "$tmp"
done
