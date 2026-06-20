"""
app/transports/http_transport.py – HTTP/JSON bridge transport.

Some ReBrewie firmware builds expose an HTTP endpoint for command
injection.  This transport wraps that REST bridge using httpx.
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import httpx

from .base import BaseTransport, TransportError
from ..config import settings
from ..state import brew_state


class HttpTransport(BaseTransport):
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._connected = False
        self._poll_queue: asyncio.Queue[str] = asyncio.Queue()
        self._poll_task: asyncio.Task | None = None

    def mark_disconnected(self) -> None:
        """Keep internal flag and brew_state in sync (mirrors TcpTransport)."""
        self._connected = False
        super().mark_disconnected()

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.brewie_http_base, timeout=10.0
        )
        brew_state.transport_type = "http"
        try:
            resp = await self._client.get("/status")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            self.mark_disconnected()
            brew_state.add_log(
                "HTTP transport validation failed for "
                f"{settings.brewie_http_base}/status: {exc}. "
                "If your Brewie+ stock TCP bridge test succeeds on port 9000, "
                "set BREWIE_TRANSPORT=tcp, BREWIE_HOST=<brewie-ip>, "
                "BREWIE_PORT=9000 and restart the service."
            )
            return

        self._connected = True
        brew_state.connected = True
        brew_state.add_log(f"HTTP transport connected to {settings.brewie_http_base}")
        # Seed the receive queue with the validated response so browser status/logs
        # show data immediately instead of waiting for the next poll interval.
        line = _response_to_line(resp)
        if line:
            brew_state.last_raw = line
            brew_state.last_updated = time.time()
            await self._poll_queue.put(line)
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def disconnect(self) -> None:
        self.mark_disconnected()
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
        brew_state.add_log("HTTP transport disconnected")

    async def send(self, command: str) -> None:
        if not self._client or not self._connected:
            raise TransportError("HTTP transport not connected or validation failed")
        try:
            resp = await self._client.post("/command", json={"cmd": command})
            resp.raise_for_status()
            brew_state.add_log(f"→ {command} ({resp.status_code})")
        except httpx.HTTPError as exc:
            brew_state.add_log(f"HTTP send error: {exc}")
            raise TransportError(f"HTTP send failed: {exc}") from exc

    async def receive(self) -> AsyncIterator[str]:
        while self._connected:
            try:
                line = await asyncio.wait_for(self._poll_queue.get(), timeout=2.0)
                yield line
            except asyncio.TimeoutError:
                continue

    async def _poll_loop(self) -> None:
        """Poll /status every 2 seconds and push results to the queue.

        Consecutive failures increment an error counter; after 3 consecutive
        failures the transport marks itself disconnected so the reconnection
        logic in ``_receive_loop`` can kick in.
        """
        consecutive_errors = 0
        while self._connected and self._client:
            await asyncio.sleep(2.0)
            try:
                resp = await self._client.get("/status")
                resp.raise_for_status()
                consecutive_errors = 0
                line = _response_to_line(resp)
                if line:
                    brew_state.last_raw = line
                    brew_state.last_updated = time.time()
                    await self._poll_queue.put(line)
            except httpx.HTTPError as exc:
                consecutive_errors += 1
                brew_state.add_log(
                    f"HTTP poll error ({consecutive_errors}): {exc}"
                )
                if consecutive_errors >= 3:
                    brew_state.add_log(
                        "HTTP poll: 3 consecutive failures – marking disconnected"
                    )
                    self.mark_disconnected()
                    break


def _response_to_line(resp: httpx.Response) -> str:
    """Convert an HTTP response body to a single parseable line.

    Centralises the JSON-vs-string detection that was previously duplicated
    between ``_poll_loop`` and ``_queue_response``.
    """
    try:
        data = resp.json()
    except ValueError:
        return resp.text.strip()
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return " ".join(f"{k}={v}" for k, v in data.items())
    return str(data)
