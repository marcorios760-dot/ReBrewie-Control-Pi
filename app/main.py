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

from fastapi import FastAPI, Request as _Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .state import brew_state
from .parser import parse_line
from .transports.factory import get_transport
from .transports import TransportError
from .routers import api, ws, pages, discovery
from .routers.ws import notify_new_data

# Reconnect back-off schedule (seconds).  Caps at the last value.
_RECONNECT_DELAYS = [2, 4, 8, 16, 30]


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.transport = get_transport()
    recv_task: asyncio.Task | None = None

    try:
        try:
            await app.state.transport.connect()
        except Exception as exc:
            # Don't let a machine that's offline/unreachable at boot prevent
            # the web app itself from starting.  _receive_loop's reconnect
            # logic (below) will keep retrying with back-off once it's running.
            brew_state.add_log(f"Initial connect failed, will retry: {exc}")

        # Start the receive / parse loop in the background.  It is given the
        # app instance (not a fixed transport reference) so that it always
        # reads app.state.transport fresh on every outer-loop iteration —
        # this lets discovery.configure_device() swap in a new transport and
        # have it picked up without restarting the service.
        recv_task = asyncio.create_task(_receive_loop(app))
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
        transport = getattr(app.state, "transport", None)
        if transport is not None:
            await transport.disconnect()


async def _receive_loop(app: FastAPI) -> None:
    """Continuously read lines from app.state.transport, parse them, and push
    real-time WebSocket notifications.

    Reads ``app.state.transport`` fresh at the top of every outer-loop
    iteration (rather than capturing a single transport reference once) so
    that swapping in a new transport — e.g. via
    ``POST /api/device/configure`` — takes effect on the very next iteration
    instead of requiring a full service restart.

    On disconnect the loop waits with exponential back-off and then
    re-connects automatically so a brief network hiccup does not permanently
    kill telemetry or command delivery.
    """
    attempt = 0

    while True:
        transport = getattr(app.state, "transport", None)
        if transport is None:
            # Defensive guard: app.state.transport should always be set by
            # lifespan() before this loop starts, and configure_device()
            # always swaps in a new (non-None) transport rather than clearing
            # it.  This should not happen in practice, but failing loudly
            # with a short retry is safer than letting an AttributeError
            # propagate out of the background task and silently kill it.
            brew_state.connected = False
            brew_state.add_log("No transport configured – retrying in 2s")
            await asyncio.sleep(2)
            continue

        # ── If the transport is not connected, attempt reconnection ──────────
        if not brew_state.connected:
            delay = _RECONNECT_DELAYS[min(attempt, len(_RECONNECT_DELAYS) - 1)]
            brew_state.add_log(
                f"Transport disconnected – reconnecting in {delay}s "
                f"(attempt {attempt + 1})"
            )
            try:
                await asyncio.sleep(delay)
                # Re-read in case configure_device() swapped the transport
                # in while we were sleeping.
                transport = getattr(app.state, "transport", None)
                if transport is None:
                    # Transport was cleared or not yet swapped in while we
                    # were sleeping.  Log it so the condition is visible,
                    # then fall through to the outer-loop None guard which
                    # applies its own 2-second sleep before the next retry.
                    brew_state.add_log(
                        "Transport is None after reconnect sleep – waiting for a new one"
                    )
                    attempt += 1
                    continue
                await transport.connect()
                attempt = 0
                brew_state.add_log("Reconnection successful")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                brew_state.add_log(f"Reconnect failed: {exc}")
                attempt += 1
                continue

        # ── Consume lines until the transport drops ──────────────────────────
        try:
            async for line in transport.receive():
                parse_line(line)
                # Wake WebSocket senders so clients get an immediate update
                # rather than waiting for the next 2-second poll tick.
                notify_new_data()
                attempt = 0  # reset back-off on any successful receive
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            transport.mark_disconnected()
            brew_state.add_log(f"Receive loop error: {exc}")
            attempt += 1
            continue

        # receive() returned cleanly → transport disconnected
        if not brew_state.connected:
            # Back-off and retry handled at the top of the outer while loop.
            continue
        # If connected is still True after receive() ends something odd happened;
        # mark disconnected so we don't spin without a delay.
        transport.mark_disconnected()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ReBrewie Control Pi",
    description="Raspberry Pi local-only controller for Brewie+ / ReBrewie machines",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(TransportError)
async def _transport_error_handler(_req: _Request, exc: TransportError) -> JSONResponse:
    """Convert TransportError to an HTTP 503 with a readable message.

    Without this handler FastAPI would return a generic 500.  A 503 is more
    accurate (the service is available but the upstream machine is not) and
    lets the dashboard distinguish a connection failure from a code bug.
    """
    return JSONResponse(status_code=503, content={"detail": str(exc)})

# Static files
_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static)), name="static")

# Routers
app.include_router(api.router)
app.include_router(ws.router)
app.include_router(pages.router)
app.include_router(discovery.router)
