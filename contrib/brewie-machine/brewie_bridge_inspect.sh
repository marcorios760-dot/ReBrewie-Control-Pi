#!/bin/sh
# Read-only inspection for the built-in Brewie bridge process/files.
# Run on the Brewie+ machine: sh brewie_bridge_inspect.sh > /tmp/brewie_bridge_inspect.txt
set -u

echo "== Brewie bridge inspection =="
echo "date: $(date 2>/dev/null || echo unknown)"
echo

echo "== Bridge-related processes =="
ps 2>/dev/null | grep -i '[t]ty_tcp_bridge\|[b]rewie-bridge\|[B]rewieApplication\|[p]ython' || true

echo

echo "== Init/profile files =="
for f in /etc/init.d/brewie-bridge /etc/profile.d/ReBrewie.sh; do
  if [ -r "$f" ]; then
    echo "-- $f --"
    sed -n '1,220p' "$f"
  else
    echo "-- $f not readable --"
  fi
done

echo

echo "== tty_tcp_bridge.py candidates =="
for f in /usr/share/brewie/tty_tcp_bridge.py /root/tty_tcp_bridge.py /home/brewie/tty_tcp_bridge.py; do
  if [ -r "$f" ]; then
    echo "-- $f --"
    sed -n '1,260p' "$f"
  fi
done

echo

echo "== Open files for tty_tcp_bridge.py =="
for pid in $(pidof python 2>/dev/null) $(pidof python3 2>/dev/null); do
  cmdline="$(tr '\000' ' ' < /proc/$pid/cmdline 2>/dev/null || true)"
  echo "$cmdline" | grep -q 'tty_tcp_bridge.py' || continue
  echo "-- pid $pid: $cmdline --"
  if command -v lsof >/dev/null 2>&1; then
    lsof -p "$pid" 2>/dev/null || true
  fi
  for fd in /proc/$pid/fd/*; do
    [ -e "$fd" ] || continue
    ls -l "$fd" 2>/dev/null || true
  done
  echo

done

echo "== Serial settings =="
for dev in /dev/ttyS0 /dev/ttyS1 /dev/ttyS2 /dev/ttyS3; do
  [ -e "$dev" ] || continue
  echo "-- $dev --"
  stty -F "$dev" -a 2>/dev/null || true
done

echo

echo "== Listening sockets after bridge inspection =="
netstat -lntup 2>/dev/null || netstat -an 2>/dev/null || true
