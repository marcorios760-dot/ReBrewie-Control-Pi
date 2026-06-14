"""
app/transports/base.py – abstract transport interface.

Each concrete transport must implement:
  connect()    – open the connection to the Brewie machine
  disconnect() – close it cleanly
  send(cmd)    – send a raw command string (e.g. "P80 20.0 0 0.00000 0.00000")
  receive()    – async generator that yields raw response lines
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseTransport(ABC):
    """Abstract base for all Brewie transports."""

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection cleanly."""

    @abstractmethod
    async def send(self, command: str) -> None:
        """Send a raw command string to the machine."""

    @abstractmethod
    async def receive(self) -> AsyncIterator[str]:
        """Yield incoming raw lines from the machine."""
        # Must be implemented as an async generator
        return
        yield  # makes this an abstract async generator stub
