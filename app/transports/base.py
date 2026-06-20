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

# Command line terminator confirmed from Brewie MCU debug session (Jun 2026).
# The MCU firmware expects \r (CR) to end each command.  The stock
# tty_tcp_bridge.py opens /dev/ttyS1 with -opost (raw TTY output, no
# character translation), so bytes are delivered verbatim.
# We send \r\n so that:
#   • the MCU sees \r and executes the command, and
#   • bridge variants that wrap input in readline() get a clean line boundary.
CMD_EOL: str = "\r\n"


class TransportError(Exception):
    """Raised by transport implementations when a send or connect operation fails.

    Carries the original OS/network exception as ``__cause__`` so callers that
    need to distinguish failure modes (e.g. connection refused vs broken pipe)
    can inspect ``exc.__cause__`` without having to parse an error string.

    Example::

        try:
            await transport.send(cmd)
        except TransportError as exc:
            logger.error("send failed: %s (caused by %r)", exc, exc.__cause__)
    """


class BaseTransport(ABC):
    """Abstract base for all Brewie transports."""

    def mark_disconnected(self) -> None:
        """Mark this transport as disconnected and update brew_state.

        The default implementation sets ``brew_state.connected = False``.
        Subclasses that maintain their own ``_connected`` flag (e.g.
        ``TcpTransport``) override this to keep their internal flag in sync
        via ``_set_connected(False)``.

        Called by ``_receive_loop`` in ``main.py`` when it catches an error
        outside the transport's own receive generator, ensuring the flag is
        always updated through the transport rather than by reaching into
        ``brew_state`` directly.
        """
        # Import here to avoid a module-level circular dependency.
        from ..state import brew_state  # noqa: PLC0415
        brew_state.connected = False

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
