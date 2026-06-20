"""
app/routers/discovery.py – Device discovery API endpoints.

Endpoints:
  GET  /api/discovery/devices    – list discovered devices from cache
  POST /api/discovery/scan       – run a discovery scan and return results
  POST /api/discovery/scan-async – trigger async discovery (non-blocking)
  POST /api/device/configure     – set active device config
  GET  /api/device/current       – get currently configured device
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from brewie_discovery import BrewieDiscovery

from ..config import settings
from ..state import brew_state
from ..transports.factory import get_transport

router = APIRouter(prefix="/api")

# Global discovery instance and cache.
_discovery = BrewieDiscovery(timeout=settings.discovery_timeout, verbose=False)
_discovery_lock = asyncio.Lock()
_discovery_cache: dict[str, Any] = {
    "devices": [],
    "last_scan": None,
    "scan_in_progress": False,
}


# ── Models ──────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    """Request to start a discovery scan."""

    known_ip: str | None = None
    subnet: str | None = None
    enable_subnet_scan: bool = True


class ConfigureDeviceRequest(BaseModel):
    """Request to configure the active device."""

    ip: str = Field(min_length=1)
    port: int = Field(gt=0, le=65535)
    protocol: Literal["http", "https", "tcp", "serial"] = "tcp"
    transport_type: Literal["tcp", "serial", "http", "mock"] = "tcp"


class DeviceConfigResponse(BaseModel):
    """Current device configuration."""

    ip: str
    port: int
    protocol: str
    transport_type: str
    url: str


# ── Discovery endpoints ─────────────────────────────────────────────────────

@router.get("/discovery/devices")
async def get_discovered_devices() -> dict[str, Any]:
    """Get discovered devices from the in-memory cache."""
    return {
        "devices": _discovery_cache["devices"],
        "cache_info": {
            "last_scan": _discovery_cache["last_scan"],
            "device_count": len(_discovery_cache["devices"]),
            "scan_in_progress": _discovery_cache["scan_in_progress"],
        },
    }


@router.post("/discovery/scan")
async def start_discovery_scan(body: ScanRequest) -> dict[str, Any]:
    """Run a discovery scan and return results without blocking the event loop."""
    _ensure_discovery_enabled()
    if _discovery_cache["scan_in_progress"]:
        raise HTTPException(409, "Scan already in progress")

    async with _discovery_lock:
        _discovery_cache["scan_in_progress"] = True
        try:
            result = await asyncio.to_thread(
                _discovery.discover,
                known_ip=body.known_ip,
                subnet=body.subnet or settings.discovery_subnet,
                enable_subnet_scan=body.enable_subnet_scan,
            )
            _update_discovery_cache(result)
            brew_state.add_log(
                f"Discovery scan complete: found {result['summary']['total_found']} device(s)"
            )
            return result
        finally:
            _discovery_cache["scan_in_progress"] = False


@router.post("/discovery/scan-async")
async def start_discovery_scan_async(body: ScanRequest) -> dict[str, str]:
    """Trigger a background discovery scan and cache the results."""
    _ensure_discovery_enabled()
    if _discovery_cache["scan_in_progress"]:
        raise HTTPException(409, "Scan already in progress")

    _discovery_cache["scan_in_progress"] = True
    asyncio.create_task(_run_background_scan(body))

    return {
        "status": "scan_started",
        "message": "Discovery scan running in background",
        "check_endpoint": "/api/discovery/devices",
    }


async def _run_background_scan(body: ScanRequest) -> None:
    async with _discovery_lock:
        try:
            result = await _discovery.discover_async(
                known_ip=body.known_ip,
                subnet=body.subnet or settings.discovery_subnet,
                enable_subnet_scan=body.enable_subnet_scan,
                max_concurrent=16,
            )
            _update_discovery_cache(result)
            brew_state.add_log(
                "Async discovery scan complete: found "
                f"{result['summary']['total_found']} device(s)"
            )
        except Exception as exc:
            brew_state.add_log(f"Discovery scan error: {exc}")
        finally:
            _discovery_cache["scan_in_progress"] = False


# ── Device configuration ────────────────────────────────────────────────────

@router.get("/device/current")
async def get_current_device() -> DeviceConfigResponse:
    """Get the currently configured Brewie device."""
    protocol = "http" if settings.brewie_transport == "http" else settings.brewie_transport
    return DeviceConfigResponse(
        ip=settings.brewie_host,
        port=settings.brewie_port,
        protocol=protocol,
        transport_type=settings.brewie_transport,
        url=f"{protocol}://{settings.brewie_host}:{settings.brewie_port}",
    )


@router.post("/device/configure")
async def configure_device(body: ConfigureDeviceRequest, request: Request) -> dict[str, Any]:
    """
    Configure the active Brewie device and reconnect live.

    Updates settings, then swaps the running transport instance so the
    background receive loop starts using the new device on its very next
    iteration — no service restart required.  For the new settings to
    survive a future restart, also update `.env`.
    """
    old_transport = getattr(request.app.state, "transport", None)

    settings.brewie_host = body.ip
    settings.brewie_port = body.port
    settings.brewie_transport = body.transport_type

    # Build the new transport from the settings we just updated, and store it
    # immediately so _receive_loop picks it up as soon as the old one stops.
    new_transport = get_transport()
    request.app.state.transport = new_transport
    brew_state.connected = False  # force the receive loop's reconnect path

    if old_transport is not None:
        # Flip the old transport's own connected flag FIRST, before attempting
        # the rest of its cleanup.  Every transport's receive() loop checks
        # this flag, so this guarantees the old generator will observe the
        # disconnect and self-terminate even if disconnect() raises partway
        # through (e.g. the socket/client close step itself fails) — closing
        # the gap where a partial-failure disconnect could otherwise leave the
        # old transport's receive() running for up to its own heartbeat-
        # timeout window before the swap takes effect.
        try:
            old_transport.mark_disconnected()
        except Exception as exc:
            # mark_disconnected() only flips boolean flags — it should never
            # raise.  Log it if it somehow does so the failure is visible,
            # then proceed; disconnect() below still attempts full cleanup.
            brew_state.add_log(f"mark_disconnected() raised unexpectedly: {exc}")

        try:
            await old_transport.disconnect()
        except Exception as exc:
            brew_state.add_log(f"Error disconnecting previous transport: {exc}")

    brew_state.add_log(
        f"Device configured: {body.transport_type}://{body.ip}:{body.port} "
        "(reconnecting now)"
    )

    return {
        "status": "configured",
        "config": {
            "ip": body.ip,
            "port": body.port,
            "protocol": body.protocol,
            "transport_type": body.transport_type,
            "url": f"{body.protocol}://{body.ip}:{body.port}",
        },
        "note": (
            "Now connecting to the new device live. "
            "To make this the default after a restart, also update .env."
        ),
    }


# ── Utility endpoints ──────────────────────────────────────────────────────

@router.post("/discovery/clear-cache")
async def clear_discovery_cache() -> dict[str, str]:
    """Clear the discovery device cache."""
    _discovery_cache["devices"] = []
    _discovery_cache["last_scan"] = None
    brew_state.add_log("Discovery cache cleared")
    return {"status": "cleared"}


@router.get("/discovery/status")
async def get_discovery_status() -> dict[str, Any]:
    """Get discovery module status and statistics."""
    return {
        "scan_in_progress": _discovery_cache["scan_in_progress"],
        "cached_devices": len(_discovery_cache["devices"]),
        "last_scan_time": _discovery_cache["last_scan"],
        "current_transport": settings.brewie_transport,
        "current_device": {
            "ip": settings.brewie_host,
            "port": settings.brewie_port,
        },
    }


def _ensure_discovery_enabled() -> None:
    if not settings.discovery_enabled:
        raise HTTPException(404, "Discovery endpoints are disabled")


def _update_discovery_cache(result: dict[str, Any]) -> None:
    _discovery_cache["devices"] = result.get("devices", [])
    _discovery_cache["last_scan"] = time.time()
