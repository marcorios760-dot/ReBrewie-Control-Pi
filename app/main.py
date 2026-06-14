"""
app/main.py – FastAPI application entry point.

Lifecycle:
  startup  → open transport connection, start receive/parse loop
  shutdown → close transport cleanly

Routers:
  /api/*   → REST API  (api.py)
  /ws      → WebSocket (ws.py)
  /        → HTML pages (pages.py)
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import settings
from .state import brew_state
from .parser import parse_line
from .transports.factory import get_transport
from .routers import api, ws, pages, discovery


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    transport = get_transport()
    app.state.transport = transport
    recv_task: asyncio.Task | None = None

    try:
        await transport.connect()
        # Start the receive / parse loop in the background
        recv_task = asyncio.create_task(_receive_loop(transport))
        brew_state.add_log(
            f"ReBrewie Control Pi started (transport={settings.brewie_transport})"
        )
        yield
    finally:
        if recv_task:
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass
        await transport.disconnect()


async def _receive_loop(transport) -> None:
    """Continuously read lines from the transport and update brew_state."""
    try:
        async for line in transport.receive():
            parse_line(line)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        brew_state.connected = False
        brew_state.status = "error"
        brew_state.add_log(f"Receive loop stopped: {exc}")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ReBrewie Control Pi",
    description="Raspberry Pi local-only controller for Brewie+ / ReBrewie machines",
    version="1.0.0",
    lifespan=lifespan,
)

# Static files
_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static)), name="static")

# Routers
app.include_router(api.router)
app.include_router(ws.router)
app.include_router(pages.router)
app.include_router(discovery.router)
