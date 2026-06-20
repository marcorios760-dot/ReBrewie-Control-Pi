"""TCP transport for the stock Brewie tty_tcp_bridge.py."""
from __future__ import annotations

import asyncio
import socket
import time
from typing import AsyncIterator

from .base import BaseTransport, TransportError, CMD_EOL
from .brewie_frame import build_frame, is_ack_frame
from ..config import settings
from ..state import brew_state

# Seconds of receive silence before we send a keep-alive P80.
# 30 s avoids bombarding the machine with polls while still detecting
# a silently-dropped connection in a reasonable time.
_HEARTBEAT_TIMEOUT = 30.0


class TcpTransport(BaseTransport):
    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.__connected = False  # backing store; use _set_connected() to mutate
        self._packet_id = 0

    # ── Connection-state management ───────────────────────────────────────────

    def _set_connected(self, value: bool) -> None:
        """Update both the internal flag and brew_state in one atomic step.

        All mutations of the connection state go through here so the two flags
        can never diverge.  ``brew_state.connected`` is the UI-facing field;
        ``__connected`` gates the receive loop.  Keeping them in sync via a
        single setter eliminates the class of bugs where one is updated and the
        other is forgotten in an error path.
        """
        self.__connected = value
        brew_state.connected = value

    @property
    def _connected(self) -> bool:
        return self.__connected

    def mark_disconnected(self) -> None:
        """Public hook for external callers (e.g. the receive loop in main.py).

        Allows main.py to mark the transport as disconnected without reaching
        directly into brew_state, keeping state mutation inside the transport.
        """
        self._set_connected(False)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _apply_socket_keepalive(self) -> None:
        """Enable OS-level TCP keepalives so a silently dropped connection is
        detected even when no application data is flowing."""
        if self._writer is None:
            return
        sock = self._writer.get_extra_info("socket")
        if sock is None:
            return
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            # Linux-specific tuning (silently ignored on other platforms).
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)
        except OSError:
            pass  # keepalive not available on this platform – harmless

    def _next_packet_id(self) -> int:
        """Return the next stock-protocol packet id.

        Avoid LF/CR as packet ids so asyncio ``readline()`` does not split an
        ACK frame in the middle of the binary header.
        """
        while True:
            self._packet_id = (self._packet_id + 1) & 0xFF
            if self._packet_id == 0:
                self._packet_id = 1
            if self._packet_id not in (0x0A, 0x0D):
                return self._packet_id

    # ── BaseTransport interface ───────────────────────────────────────────────

    async def connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(settings.brewie_host, settings.brewie_port),
                timeout=10.0,
            )
            self._set_connected(True)
            self._apply_socket_keepalive()
            brew_state.transport_type = "tcp"
            brew_state.add_log(
                f"TCP connected to {settings.brewie_host}:{settings.brewie_port}"
            )
            if settings.brewie_tcp_framing:
                brew_state.add_log("TCP stock Brewie framing enabled")
        except (OSError, asyncio.TimeoutError) as exc:
            self._set_connected(False)
            brew_state.add_log(f"TCP connect failed: {exc}")
            raise

    async def disconnect(self) -> None:
        self._set_connected(False)
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        brew_state.add_log("TCP disconnected")

    async def send(self, command: str) -> None:
        """Write a command to the socket."""
        if not self._writer or not self._connected:
            raise TransportError("TCP not connected – command not sent")
        command = command.strip()
        if settings.brewie_tcp_framing:
            packet_id = self._next_packet_id()
            try:
                payload = build_frame(command, packet_id)
            except (UnicodeEncodeError, ValueError) as exc:
                raise TransportError(f"TCP frame build failed: {exc}") from exc
        else:
            payload = (command + CMD_EOL).encode("utf-8")
        try:
            self._writer.write(payload)
            await self._writer.drain()
            brew_state.add_log(f"→ {command}")
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            self._set_connected(False)
            brew_state.add_log(f"TCP send failed ({exc}) – marking disconnected")
            raise TransportError(f"TCP send failed: {exc}") from exc

    async def receive(self) -> AsyncIterator[str]:
        if not self._reader:
            return
        while self._connected:
            try:
                raw = await asyncio.wait_for(
                    self._reader.readline(), timeout=_HEARTBEAT_TIMEOUT
                )
                if not raw:
                    brew_state.add_log("TCP connection closed by remote")
                    self._set_connected(False)
                    break
                ack, packet_id = is_ack_frame(raw)
                if ack:
                    brew_state.add_log(f"← ACK packet_id={packet_id}")
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    brew_state.last_raw = line
                    brew_state.last_updated = time.time()
                    brew_state.add_log(f"← {line}")
                    yield line
            except asyncio.TimeoutError:
                # No data for _HEARTBEAT_TIMEOUT seconds – send a keep-alive
                # so the machine keeps streaming and the OS detects dead links.
                # Delegates to settings.build_p80_command() so the format stays
                # consistent with control_start and control_resume.
                try:
                    await self.send(settings.build_p80_command())
                    brew_state.add_log("TCP heartbeat sent")
                except TransportError as exc:
                    brew_state.add_log(f"TCP heartbeat failed: {exc}")
                    self._set_connected(False)
                    break
            except Exception as exc:
                brew_state.add_log(f"TCP receive error: {exc}")
                self._set_connected(False)
                break
