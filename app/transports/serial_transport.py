"""
app/transports/serial_transport.py – USB serial line transport.

The Raspberry Pi connects to the Brewie IO board via a USB-to-serial
adapter.  Commands and responses are newline-terminated UTF-8 strings
at 115 200 baud (configurable via BREWIE_SERIAL_BAUD).
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

from .base import BaseTransport, TransportError, CMD_EOL
from ..config import settings
from ..state import brew_state


class SerialTransport(BaseTransport):
    def __init__(self) -> None:
        self._serial = None
        self._connected = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def mark_disconnected(self) -> None:
        """Keep internal flag and brew_state in sync (mirrors TcpTransport)."""
        self._connected = False
        super().mark_disconnected()

    async def connect(self) -> None:
        try:
            import serial  # pyserial – optional dep

            self._loop = asyncio.get_running_loop()
            self._serial = serial.Serial(
                port=settings.brewie_serial_port,
                baudrate=settings.brewie_serial_baud,
                # 1-second read timeout so the executor thread unblocks quickly
                # and we can check self._connected without an additional cancel.
                timeout=1.0,
            )
            self._connected = True
            brew_state.connected = True
            brew_state.transport_type = "serial"
            brew_state.add_log(
                f"Serial connected: {settings.brewie_serial_port} @ {settings.brewie_serial_baud}"
            )
        except Exception as exc:
            self.mark_disconnected()
            brew_state.add_log(f"Serial connect failed: {exc}")
            raise

    async def disconnect(self) -> None:
        self.mark_disconnected()
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        brew_state.add_log("Serial disconnected")

    async def send(self, command: str) -> None:
        if not self._serial or not self._connected:
            raise TransportError("Serial not connected – command not sent")
        line = (command.strip() + CMD_EOL).encode("utf-8")
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._serial.write, line)
            brew_state.add_log(f"→ {command}")
        except OSError as exc:
            self.mark_disconnected()
            brew_state.add_log(f"Serial send failed ({exc}) – marking disconnected")
            raise TransportError(f"Serial send failed: {exc}") from exc

    async def receive(self) -> AsyncIterator[str]:
        """Yield decoded lines from the serial port.

        The serial port is opened with ``timeout=1.0`` so each
        ``readline()`` call in the thread executor unblocks within one second
        even when no data arrives.  This avoids wrapping the executor future
        in ``asyncio.wait_for``, which cannot cancel the underlying thread and
        would leave a blocking ``readline`` stranded in the thread pool.
        """
        loop = asyncio.get_running_loop()
        while self._connected and self._serial:
            try:
                # The 1-second serial timeout means this returns at most 1 s late
                # when the port is idle — no asyncio.wait_for needed.
                raw = await loop.run_in_executor(None, self._serial.readline)
                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        brew_state.last_raw = line
                        brew_state.last_updated = time.time()
                        brew_state.add_log(f"← {line}")
                        yield line
            except Exception as exc:
                brew_state.add_log(f"Serial receive error: {exc}")
                self.mark_disconnected()
                break
