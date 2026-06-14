"""
app/transports/tcp.py – raw line-oriented TCP transport.

The stock Brewie tty_tcp_bridge.py listens on a TCP socket (default port 9000).
Commands are sent as newline-terminated UTF-8 strings.
Responses are similarly newline-terminated lines.
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

from .base import BaseTransport
from ..config import settings
from ..state import brew_state


class TcpTransport(BaseTransport):
    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._stopping = False

    async def connect(self) -> None:
        self._stopping = False
        await self._open_connection()

    async def _open_connection(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(settings.brewie_host, settings.brewie_port),
                timeout=10.0,
            )
            self._connected = True
            brew_state.connected = True
            brew_state.transport_type = "tcp"
            brew_state.add_log(
                f"TCP connected to {settings.brewie_host}:{settings.brewie_port}"
            )
        except (OSError, asyncio.TimeoutError) as exc:
            self._connected = False
            brew_state.connected = False
            brew_state.add_log(f"TCP connect failed: {exc}")
            raise

    async def _close_writer(self) -> None:
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None

    def _poll_command(self) -> str:
        return (
            f"P80 {settings.to_liter:.1f} 0 "
            f"{settings.mash_temp_delta:.5f} {settings.boil_temp_delta:.5f}"
        )

    async def disconnect(self) -> None:
        self._stopping = True
        self._connected = False
        await self._close_writer()
        brew_state.connected = False
        brew_state.add_log("TCP disconnected")

    async def send(self, command: str) -> None:
        if not self._writer or not self._connected:
            raise RuntimeError("TCP not connected")
        line = command.strip() + "\n"
        self._writer.write(line.encode("utf-8"))
        await self._writer.drain()
        brew_state.add_log(f"→ {command}")

    async def receive(self) -> AsyncIterator[str]:
        backoff = 1.0
        while not self._stopping:
            if not self._reader or not self._connected:
                try:
                    await self._open_connection()
                    backoff = 1.0
                except Exception:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    continue

            try:
                raw = await asyncio.wait_for(self._reader.readline(), timeout=10.0)
                if not raw:
                    brew_state.add_log("TCP connection closed by remote; reconnecting")
                    self._connected = False
                    brew_state.connected = False
                    await self._close_writer()
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    brew_state.connected = True
                    brew_state.last_raw = line
                    brew_state.last_updated = time.time()
                    brew_state.add_log(f"← {line}")
                    yield line
            except asyncio.TimeoutError:
                # Poll telemetry using the full P80 command shape expected by the
                # stock bridge/firmware instead of a bare, potentially malformed P80.
                try:
                    await self.send(self._poll_command())
                except Exception as exc:
                    brew_state.add_log(f"TCP poll failed; reconnecting: {exc}")
                    self._connected = False
                    brew_state.connected = False
                    await self._close_writer()
            except Exception as exc:
                brew_state.add_log(f"TCP receive error; reconnecting: {exc}")
                self._connected = False
                brew_state.connected = False
                await self._close_writer()
