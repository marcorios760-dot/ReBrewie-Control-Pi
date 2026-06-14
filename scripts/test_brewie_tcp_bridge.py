#!/usr/bin/env python3
"""Quick stdlib-only TCP smoke test for the Brewie tty_tcp_bridge.

Example:
  python3 scripts/test_brewie_tcp_bridge.py --host 192.168.1.132 --port 9000
  python3 scripts/test_brewie_tcp_bridge.py --host 192.168.1.132 --port 9000 --cmd P80
"""
from __future__ import annotations

import argparse
import socket
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Brewie TCP bridge connectivity")
    parser.add_argument("--host", default="192.168.1.132")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--cmd", default="", help="optional command to send after connecting")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    command = args.cmd.strip()
    print(f"Connecting to {args.host}:{args.port} ...")
    with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
        sock.settimeout(args.timeout)
        print("Connected.")
        if not command:
            print("No command sent; use --cmd P80 for an optional command/response test.")
            return
        payload = command.encode("utf-8") + b"\n"
        print(f"Sending {payload!r}")
        sock.sendall(payload)
        deadline = time.time() + args.timeout
        chunks: list[bytes] = []
        while time.time() < deadline:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                break
            if not data:
                break
            chunks.append(data)
            if b"\n" in data:
                break

    if chunks:
        print("Received:")
        print(b"".join(chunks).decode("utf-8", "replace"))
    else:
        print("No response before timeout. The bridge may still have accepted the command.")


if __name__ == "__main__":
    main()
