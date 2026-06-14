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

from ..state import brew_state
from ..parser import refresh_state_from_last_raw

router = APIRouter()

_clients: Set[WebSocket] = set()


def _refresh_state_from_last_raw() -> None:
    """Refresh parsed fields without requiring newer parser symbols at import time."""
    refresh = getattr(brew_parser, "refresh_state_from_last_raw", None)
    if callable(refresh):
        refresh()
        return
    if brew_state.last_raw:
        brew_parser.parse_line(brew_state.last_raw)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
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
    """Push brew_state to the client every 2 seconds as a fallback heartbeat."""
    while True:
        await asyncio.sleep(2.0)
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


async def _command_receiver(ws: WebSocket, transport) -> None:
    """Accept {"cmd": "..."} messages from the client."""
    async for raw in ws.iter_text():
        try:
            msg = json.loads(raw)
            cmd = msg.get("cmd", "").strip()
            if cmd and transport:
                await transport.send(cmd)
        except Exception as exc:
            brew_state.add_log(f"WebSocket command error: {exc}")


async def broadcast(payload: dict) -> None:
    """Broadcast a payload to all connected WebSocket clients."""
    dead: Set[WebSocket] = set()
    for ws in list(_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    _clients -= dead
