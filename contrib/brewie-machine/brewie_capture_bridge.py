#!/usr/bin/env python
"""
Instrumented TCP-to-TTY bridge for short diagnostics on the Brewie machine.

It mirrors the stock tty_tcp_bridge.py behavior, but logs every byte flowing
from TCP clients to the serial device and from the serial device back to TCP.
Use it only during tests; restore the stock bridge afterward.
"""
from __future__ import print_function

import binascii
import os
import select
import socket
import sys
import time


TTY = os.environ.get("TTY", "/dev/ttyS1")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "9000"))
LOG = os.environ.get("LOG", "/tmp/rebrewie_capture_bridge.log")


def safe_text(data):
    chars = []
    for ch in data:
        if not isinstance(ch, int):
            ch = ord(ch)
        if 32 <= ch <= 126:
            chars.append(chr(ch))
        elif ch == 13:
            chars.append("\\r")
        elif ch == 10:
            chars.append("\\n")
        elif ch == 9:
            chars.append("\\t")
        else:
            chars.append("\\x%02x" % ch)
    return "".join(chars)


def hex_text(data):
    raw = binascii.hexlify(data)
    if not isinstance(raw, str):
        raw = raw.decode("ascii")
    return " ".join(raw[i:i + 2] for i in range(0, len(raw), 2))


def log_line(direction, data=None, message=None):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    if data is None:
        line = "[%s] %s %s" % (ts, direction, message or "")
    else:
        line = "[%s] %s len=%d hex=%s text=%s" % (
            ts, direction, len(data), hex_text(data), safe_text(data)
        )
    with open(LOG, "a") as f:
        f.write(line + "\n")
    try:
        print(line)
        sys.stdout.flush()
    except Exception:
        pass


def main():
    log_line("START", message="listening on %s:%d -> %s log=%s" % (HOST, PORT, TTY, LOG))

    tty_fd = os.open(TTY, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)

    clients = []
    try:
        while True:
            rlist = [srv, tty_fd] + clients
            readable, _, _ = select.select(rlist, [], [], 1.0)

            if srv in readable:
                c, addr = srv.accept()
                c.setblocking(0)
                clients.append(c)
                log_line("CLIENT", message="connected %s:%d" % addr)

            if tty_fd in readable:
                try:
                    data = os.read(tty_fd, 4096)
                except Exception as exc:
                    data = ""
                    log_line("TTY-ERR", message=str(exc))
                if data:
                    log_line("TTY->TCP", data=data)
                    dead = []
                    for c in clients:
                        try:
                            c.sendall(data)
                        except Exception:
                            dead.append(c)
                    for c in dead:
                        try:
                            c.close()
                        except Exception:
                            pass
                        if c in clients:
                            clients.remove(c)
                        log_line("CLIENT", message="dropped")

            dead = []
            for c in clients:
                if c in readable:
                    try:
                        data = c.recv(4096)
                    except Exception as exc:
                        data = ""
                        log_line("TCP-ERR", message=str(exc))
                    if not data:
                        dead.append(c)
                    else:
                        log_line("TCP->TTY", data=data)
                        try:
                            written = os.write(tty_fd, data)
                            log_line("WRITE", message="wrote %d byte(s) to %s" % (written, TTY))
                        except Exception as exc:
                            log_line("WRITE-ERR", message=str(exc))

            for c in dead:
                try:
                    c.close()
                except Exception:
                    pass
                if c in clients:
                    clients.remove(c)
                log_line("CLIENT", message="disconnected")
    except KeyboardInterrupt:
        log_line("STOP", message="keyboard interrupt")
    finally:
        for c in clients:
            try:
                c.close()
            except Exception:
                pass
        try:
            srv.close()
        except Exception:
            pass
        try:
            os.close(tty_fd)
        except Exception:
            pass


if __name__ == "__main__":
    main()
