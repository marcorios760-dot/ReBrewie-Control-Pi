"""
app/transports/factory.py – return the configured transport instance.
"""
from __future__ import annotations

from ..config import settings
from .base import BaseTransport


def get_transport() -> BaseTransport:
    transport_type = settings.brewie_transport.strip().lower()
    if transport_type == "tcp":
        from .tcp import TcpTransport

        return TcpTransport()
    if transport_type == "serial":
        from .serial_transport import SerialTransport

        return SerialTransport()
    if transport_type == "http":
        from .http_transport import HttpTransport

        return HttpTransport()
    if transport_type == "mock":
        from .mock import MockTransport

        return MockTransport()
    supported = "http, mock, serial, tcp"
    raise ValueError(
        f"Unsupported BREWIE_TRANSPORT={settings.brewie_transport!r}; use {supported}"
    )
