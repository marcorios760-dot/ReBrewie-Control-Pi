#!/usr/bin/env python3
"""Quick stdlib-only TCP smoke test for the Brewie tty_tcp_bridge.

Examples:
  python3 scripts/test_brewie_tcp_bridge.py --host 192.168.1.XXX --port 9000
  python3 scripts/test_brewie_tcp_bridge.py --host 192.168.1.XXX --port 9000 --cmd P80
  python3 scripts/test_brewie_tcp_bridge.py --host 192.168.1.XXX --port 9000 --cmd STATUS --line-ending cr
  python3 scripts/test_brewie_tcp_bridge.py --host 192.168.1.XXX --port 9000 --cmd STATUS --try-line-endings
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

# Keep the order stable for --try-line-endings so output is easy to compare
# between test runs. Build the lookup dict from this single source of truth.
LINE_ENDINGS: tuple[tuple[str, bytes], ...] = (
    ("none", b""),
    ("lf", b"\n"),
    ("cr", b"\r"),
    ("crlf", b"\r\n"),
)
LINE_ENDING_VALUES = dict(LINE_ENDINGS)
LINE_ENDING_NAMES = tuple(name for name, _ in LINE_ENDINGS)

# Short pauses give BusyBox-era bridges/MCUs a moment to flush responses without
# making normal smoke tests slow; expose them as CLI options for slower systems.
DEFAULT_RESPONSE_SETTLE_DELAY = 0.05
DEFAULT_RETRY_DELAY = 0.2


def hexdump(data: bytes) -> str:
    """Return a compact hex dump that works on old Raspberry Pi terminals."""
    if not data:
        return "<empty>"
    return " ".join(f"{byte:02x}" for byte in data)


def printable(data: bytes) -> str:
    if not data:
        return "<empty>"
    return repr(data.decode("utf-8", "replace"))


def send_once(
    host: str,
    port: int,
    payload: bytes,
    timeout: float,
    response_settle_delay: float,
) -> bytes:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload)
        if response_settle_delay > 0:
            time.sleep(response_settle_delay)
        deadline = time.time() + timeout
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
        return b"".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Brewie TCP bridge connectivity")
    parser.add_argument("--host", default="192.168.1.XXX")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--cmd", default="", help="optional command to send after connecting")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument(
        "--line-ending",
        choices=LINE_ENDING_NAMES,
        default="lf",
        help="line ending appended to --cmd (default: lf)",
    )
    parser.add_argument(
        "--try-line-endings",
        action="store_true",
        help="send --cmd once for each supported line ending, in test order",
    )
    parser.add_argument(
        "--response-settle-delay",
        type=float,
        default=DEFAULT_RESPONSE_SETTLE_DELAY,
        help=(
            "seconds to wait after sending before reading "
            f"(default: {DEFAULT_RESPONSE_SETTLE_DELAY})"
        ),
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=DEFAULT_RETRY_DELAY,
        help=(
            "seconds to wait between --try-line-endings sends "
            f"(default: {DEFAULT_RETRY_DELAY})"
        ),
    )
    args = parser.parse_args()

    command = args.cmd.strip()
    print(f"Target: {args.host}:{args.port}")
    if not command:
        print("Connecting without sending a command ...")
        try:
            with socket.create_connection((args.host, args.port), timeout=args.timeout):
                print("Connected. Use --cmd P80 or --cmd STATUS for a command/response test.")
                return 0
        except OSError as exc:
            print(f"ERROR: connection failed: {exc}", file=sys.stderr)
            print("Check that tty_tcp_bridge.py is running and listening on this host/port.", file=sys.stderr)
            return 1

    ending_names = LINE_ENDING_NAMES if args.try_line_endings else (args.line_ending,)
    exit_code = 0
    for name in ending_names:
        payload = command.encode("utf-8") + LINE_ENDING_VALUES[name]
        print("----")
        print(f"Sending {command!r} with {name.upper()} ending")
        print(f"TX hex: {hexdump(payload)}")
        print(f"TX printable: {printable(payload)}")
        try:
            response = send_once(
                args.host,
                args.port,
                payload,
                args.timeout,
                args.response_settle_delay,
            )
        except OSError as exc:
            print(f"ERROR: connection/send failed: {exc}", file=sys.stderr)
            print("If this is 'Connection refused', no bridge is listening on that port.", file=sys.stderr)
            return 1
        print(f"RX hex: {hexdump(response)}")
        print(f"RX printable: {printable(response)}")
        if not response:
            exit_code = 2
        if args.retry_delay > 0:
            time.sleep(args.retry_delay)

    if exit_code == 2:
        print("No response for at least one send. The bridge may still have accepted the command.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
