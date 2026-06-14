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

from .base import BaseTransport
from ..config import settings
from ..state import brew_state


class HttpTransport(BaseTransport):
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._connected = False
        self._poll_queue: asyncio.Queue[str] = asyncio.Queue()
        self._poll_task: asyncio.Task | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.brewie_http_base, timeout=10.0
        )
        brew_state.transport_type = "http"
        try:
            resp = await self._client.get("/status")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            self._connected = False
            brew_state.connected = False
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
        await self._queue_response(resp)
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def disconnect(self) -> None:
        self._connected = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
        brew_state.connected = False
        brew_state.add_log("HTTP transport disconnected")

    async def send(self, command: str) -> None:
        if not self._client or not self._connected:
            raise RuntimeError("HTTP transport not connected or validation failed")
        try:
            resp = await self._client.post("/command", json={"cmd": command})
            resp.raise_for_status()
            brew_state.add_log(f"→ {command} ({resp.status_code})")
        except httpx.HTTPError as exc:
            brew_state.add_log(f"HTTP send error: {exc}")
            raise RuntimeError(f"HTTP send failed: {exc}") from exc

    async def receive(self) -> AsyncIterator[str]:
        while self._connected:
            try:
                line = await asyncio.wait_for(self._poll_queue.get(), timeout=2.0)
                yield line
            except asyncio.TimeoutError:
                continue

    async def _poll_loop(self) -> None:
        """Poll /status every 2 seconds and push results to the queue."""
        while self._connected and self._client:
            await asyncio.sleep(2.0)
            try:
                resp = await self._client.get("/status")
                resp.raise_for_status()
                data = resp.json()
                # Accept both a flat string or a JSON object
                if isinstance(data, str):
                    line = data
                else:
                    line = " ".join(f"{k}={v}" for k, v in data.items())
                brew_state.last_raw = line
                brew_state.last_updated = time.time()
                await self._poll_queue.put(line)
            except httpx.HTTPError as exc:
                brew_state.add_log(f"HTTP poll error: {exc}")

    async def _queue_response(self, resp: httpx.Response) -> None:
        try:
            data = resp.json()
        except ValueError:
            line = resp.text.strip()
        else:
            # Accept both a flat string or a JSON object
            if isinstance(data, str):
                line = data
            elif isinstance(data, dict):
                line = " ".join(f"{k}={v}" for k, v in data.items())
            else:
                line = str(data)
        if line:
            brew_state.last_raw = line
            brew_state.last_updated = time.time()
            await self._poll_queue.put(line)
