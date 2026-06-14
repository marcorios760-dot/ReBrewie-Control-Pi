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

from .base import BaseTransport
from ..config import settings
from ..state import brew_state


class SerialTransport(BaseTransport):
    def __init__(self) -> None:
        self._serial = None
        self._connected = False
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self) -> None:
        try:
            import serial  # pyserial – optional dep

            self._loop = asyncio.get_running_loop()
            self._serial = serial.Serial(
                port=settings.brewie_serial_port,
                baudrate=settings.brewie_serial_baud,
                timeout=1.0,
            )
            self._connected = True
            brew_state.connected = True
            brew_state.transport_type = "serial"
            brew_state.add_log(
                f"Serial connected: {settings.brewie_serial_port} @ {settings.brewie_serial_baud}"
            )
        except Exception as exc:
            brew_state.connected = False
            brew_state.add_log(f"Serial connect failed: {exc}")
            raise

    async def disconnect(self) -> None:
        self._connected = False
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        brew_state.connected = False
        brew_state.add_log("Serial disconnected")

    async def send(self, command: str) -> None:
        if not self._serial:
            raise RuntimeError("Serial not connected")
        line = (command.strip() + "\n").encode("utf-8")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._serial.write, line)
        brew_state.add_log(f"→ {command}")

    async def receive(self) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        while self._connected and self._serial:
            try:
                raw = await asyncio.wait_for(
                    loop.run_in_executor(None, self._serial.readline),
                    timeout=5.0,
                )
                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        brew_state.last_raw = line
                        brew_state.last_updated = time.time()
                        brew_state.add_log(f"← {line}")
                        yield line
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                brew_state.add_log(f"Serial receive error: {exc}")
                self._connected = False
                brew_state.connected = False
                break
