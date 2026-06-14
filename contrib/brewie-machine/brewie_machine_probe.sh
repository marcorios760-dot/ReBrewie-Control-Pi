#!/bin/sh
# Read-only Brewie+/BusyBox diagnostics helper.
# Copy this file to the Brewie+ machine and run: sh brewie_machine_probe.sh
# It does not modify files or start services.

set -u

echo "== Brewie+ BusyBox probe =="
echo "date: $(date 2>/dev/null || echo unknown)"
echo "user: $(id 2>/dev/null || whoami 2>/dev/null || echo unknown)"
echo "host: $(hostname 2>/dev/null || echo unknown)"
echo

echo "== OS / kernel =="
uname -a 2>/dev/null || true
[ -r /etc/os-release ] && cat /etc/os-release
[ -r /etc/issue ] && cat /etc/issue
[ -r /proc/version ] && cat /proc/version

echo

echo "== Network addresses =="
if command -v ip >/dev/null 2>&1; then
  ip addr show 2>/dev/null || true
  ip route show 2>/dev/null || true
else
  ifconfig -a 2>/dev/null || true
  route -n 2>/dev/null || true
fi

echo

echo "== Listening sockets =="
netstat -lntup 2>/dev/null || netstat -an 2>/dev/null || true

echo

echo "== Useful commands available =="
for c in sh ash bash busybox nc netcat telnet wget curl httpd inetd xinetd socat python python3 lua perl awk sed grep ps netstat ss ip ifconfig route stty microcom hexdump strings; do
  if command -v "$c" >/dev/null 2>&1; then
    printf '%-10s %s\n' "$c" "$(command -v "$c")"
  fi
done

echo

echo "== BusyBox applets =="
busybox 2>/dev/null | sed -n '/Currently defined functions:/,$p' | tr ',' '\n' | sed 's/^ *//' | sed '/^$/d' | sort 2>/dev/null || true

echo

echo "== Candidate device nodes =="
for d in /dev/ttyS* /dev/ttyUSB* /dev/ttyACM* /dev/serial* /dev/i2c-* /dev/spidev*; do
  [ -e "$d" ] && ls -l "$d"
done

echo

echo "== Brewie-looking files/processes =="
ps 2>/dev/null | grep -i '[b]rew\|[r]ebrew\|[j]ava\|[n]ode\|[p]ython\|[h]ttp\|[n]c' || true
for root in / /opt /home /root /mnt /usr /var; do
  [ -d "$root" ] || continue
  find "$root" -maxdepth 3 \( -iname '*brew*' -o -iname '*reb*' -o -iname '*beer*' \) -print 2>/dev/null | head -100
done

echo

echo "== Quick local HTTP checks =="
for port in 80 8080 8332 3000 5000 22; do
  if command -v wget >/dev/null 2>&1; then
    echo "-- http://127.0.0.1:$port/ --"
    wget -q -O - "http://127.0.0.1:$port/" 2>/dev/null | head -20 || true
  fi
done

echo

echo "== Probe complete =="
echo "Share this output before installing any bridge/shim on the Brewie+ machine."
