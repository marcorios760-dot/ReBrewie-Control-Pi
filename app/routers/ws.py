"""
app/routers/ws.py – WebSocket endpoint.

Clients connect to ws://<raspberry-pi-ip>:8080/ws and receive JSON frames every
~2 seconds containing the current brew_state.  They can also send
JSON commands: {"cmd": "P150 670"} to issue raw P-commands.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..auth import current_user, request_requires_auth
from ..state import brew_state
from ..parser import refresh_state_from_last_raw
from ..transports import TransportError

# Set by the receive loop every time a new line arrives so that WebSocket
# clients get an immediate push instead of waiting the full 2-second poll.
_new_data_event: asyncio.Event = asyncio.Event()

router = APIRouter()

_clients: Set[WebSocket] = set()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    if request_requires_auth(ws) and not current_user(ws):
        await ws.close(code=1008)
        return

    await ws.accept()
    _clients.add(ws)
    transport = getattr(ws.app.state, "transport", None)
    try:
        # Send initial state immediately
        refresh_state_from_last_raw()
        await ws.send_json({"type": "state", "data": brew_state.to_dict()})

        # Run sender and receiver concurrently
        await asyncio.gather(
            _state_sender(ws),
            _command_receiver(ws, transport),
        )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        brew_state.add_log(f"WebSocket error: {exc}")
    finally:
        _clients.discard(ws)


async def _state_sender(ws: WebSocket) -> None:
    """Push brew_state to the client on new data or at least every 2 seconds.

    The receive loop calls ``notify_new_data()`` whenever a fresh line arrives
    from the machine, waking all senders immediately rather than waiting for the
    2-second fallback tick.
    """
    while True:
        try:
            await asyncio.wait_for(_new_data_event.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass  # periodic heartbeat – send anyway
        _new_data_event.clear()
        try:
            refresh_state_from_last_raw()
            payload = {
                "type": "state",
                "data": brew_state.to_dict(),
                "ts": time.time(),
            }
            await ws.send_json(payload)
        except Exception:
            break


def notify_new_data() -> None:
    """Signal all WebSocket senders that new telemetry has arrived.

    Called by the main receive loop after each parsed line so clients get an
    immediate state push rather than waiting up to 2 seconds.
    """
    _new_data_event.set()


async def _command_receiver(ws: WebSocket, transport) -> None:
    """Accept {\"cmd\": \"...\"} messages from the client and echo ack or error.

    Sends a ``{\"type\": \"ack\", \"cmd\": ...}`` frame on success or a
    ``{\"type\": \"error\", \"detail\": ...}`` frame on failure so the client
    always gets explicit feedback rather than silent drops.
    """
    async for raw in ws.iter_text():
        try:
            msg = json.loads(raw)
            cmd = msg.get("cmd", "").strip()
            if not cmd:
                continue
            if not transport:
                await ws.send_json({"type": "error", "detail": "Transport not initialised"})
                continue
            if not brew_state.connected:
                await ws.send_json({"type": "error", "detail": "Machine not connected"})
                continue
            await transport.send(cmd)
            await ws.send_json({"type": "ack", "cmd": cmd})
        except TransportError as exc:
            detail = str(exc)
            brew_state.add_log(f"WebSocket command error: {detail}")
            try:
                await ws.send_json({"type": "error", "detail": detail})
            except Exception:
                pass
        except Exception as exc:
            brew_state.add_log(f"WebSocket message error: {exc}")
