"""
Brewie stock serial frame helpers.

The original Brewie Qt app does not write plain ``P...`` commands to the MCU.
It wraps each ASCII payload as:

    $ <packet-id> <payload-length> <payload> <check-byte> *

Captured logs and direct tests against the stock ``tty_tcp_bridge.py`` confirm
this format for P999 and P205. The check byte appears to be command-specific;
many stock logs show ``?`` (0x3f), and direct tests confirm that value is
accepted for at least P205 0.
"""
from __future__ import annotations


FRAME_START = 0x24  # $
FRAME_END = 0x2A  # *


# Check bytes captured from stock Brewie logs. Commands not listed here fall
# back to 0x3f, which is also the captured value for many commands.
CHECK_BYTES: dict[str, int] = {
    "P112": 0x46,
    "P113": 0x18,
    "P116": 0x27,
    "P117": 0x79,
    "P118": 0x38,
    "P119": 0x66,
    "P122": 0x13,
    "P123": 0x4D,
    "P126": 0x72,
    "P127": 0x2C,
    "P128": 0x6D,
    "P129": 0x33,
    "P130": 0x6B,
    "P131": 0x35,
    "P135": 0x54,
    "P150 0": 0x0F,
    "P150 1": 0x51,
    "P202": 0x66,
    "P998 0": 0x06,
    "P998 1": 0x58,
    "P999": 0x35,
}

DEFAULT_CHECK_BYTE = 0x3F


def build_frame(command: str, packet_id: int) -> bytes:
    """Return a Brewie stock frame for ``command`` and ``packet_id``."""
    payload = command.strip().encode("ascii", errors="strict")
    if len(payload) > 255:
        raise ValueError("Brewie command payload is too long for one frame")
    check = CHECK_BYTES.get(command.strip(), DEFAULT_CHECK_BYTE)
    return bytes((FRAME_START, packet_id & 0xFF, len(payload))) + payload + bytes(
        (check, FRAME_END)
    )


def is_ack_frame(raw_line: bytes) -> tuple[bool, int | None]:
    """Return ``(True, packet_id)`` for stock ACK frames like ``$\\x01!*.``"""
    line = raw_line.strip()
    if len(line) != 4:
        return False, None
    if line[0] != FRAME_START or line[1] != 0x01 or line[3] != FRAME_END:
        return False, None
    return True, line[2]
