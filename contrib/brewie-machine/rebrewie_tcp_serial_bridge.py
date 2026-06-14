#!/usr/bin/env python3
"""Small stdlib-only TCP-to-serial bridge for Brewie+/BusyBox systems.

This is intended for Brewie machines that have Python but no nc/socat. It listens
for newline-delimited P-commands on a TCP port and forwards them to a configured
serial device. Use only after confirming which serial device/baud the Brewie MCU
uses; opening the wrong device can interfere with the stock UI.
"""
from __future__ import print_function

import argparse
import errno
import os
import select
import socket
import sys
import termios
import threading
import time

BAUDS = {
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
}


def log(message):
    sys.stderr.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + message + "\n")
    sys.stderr.flush()


class SerialBackend(object):
    def __init__(self, device, baud, read_timeout):
        if baud not in BAUDS:
            raise SystemExit("Unsupported baud rate: %s" % baud)
        self.device = device
        self.baud = baud
        self.read_timeout = read_timeout
        self.lock = threading.Lock()
        self.fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self._configure()
        log("opened serial device=%s baud=%s" % (device, baud))

    def _configure(self):
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = 0  # iflag
        attrs[1] = 0  # oflag
        attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[3] = 0  # lflag
        attrs[4] = BAUDS[self.baud]
        attrs[5] = BAUDS[self.baud]
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def transact(self, command):
        line = command.strip()
        if not line:
            return "ERROR:empty_command\n"
        payload = (line + "\n").encode("ascii", "replace")
        with self.lock:
            log("TX %s" % line)
            try:
                os.write(self.fd, payload)
            except OSError as exc:
                log("serial write error: %s" % exc)
                return "ERROR:serial_write_failed %s\n" % exc
            return self._read_response(line)

    def _read_response(self, line):
        deadline = time.time() + self.read_timeout
        chunks = []
        while time.time() < deadline:
            remaining = max(0.0, deadline - time.time())
            readable, _, _ = select.select([self.fd], [], [], min(0.2, remaining))
            if not readable:
                continue
            try:
                data = os.read(self.fd, 4096)
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    continue
                log("serial read error: %s" % exc)
                return "ERROR:serial_read_failed %s\n" % exc
            if not data:
                continue
            chunks.append(data)
            if b"\n" in data:
                break
        if chunks:
            response = b"".join(chunks).decode("utf-8", "replace")
            log("RX %s" % response.strip())
            return response if response.endswith("\n") else response + "\n"
        # Some firmware builds are silent for commands; give the Pi a visible ack.
        log("RX timeout; returning synthetic ack for %s" % line.split()[0])
        return "OK:%s\n" % line.split()[0]


def handle_client(conn, addr, backend):
    log("client connected %s:%s" % addr)
    try:
        conn.sendall(b"READY rebrewie_tcp_serial_bridge\n")
        buffer = b""
        while True:
            data = conn.recv(4096)
            if not data:
                break
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                command = line.decode("utf-8", "replace").strip()
                if not command:
                    continue
                response = backend.transact(command)
                conn.sendall(response.encode("utf-8", "replace"))
    except Exception as exc:
        log("client error %s:%s %s" % (addr[0], addr[1], exc))
    finally:
        try:
            conn.close()
        except Exception:
            pass
        log("client disconnected %s:%s" % addr)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Brewie TCP-to-serial bridge")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8332)
    parser.add_argument("--serial", default="/dev/ttyS1")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--read-timeout", type=float, default=1.0)
    args = parser.parse_args(argv)

    backend = SerialBackend(args.serial, args.baud, args.read_timeout)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    sock.listen(5)
    log("listening on %s:%s" % (args.host, args.port))
    while True:
        conn, addr = sock.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr, backend))
        thread.daemon = True
        thread.start()


if __name__ == "__main__":
    main()
