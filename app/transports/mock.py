"""
app/transports/mock.py – simulated Brewie machine.

Simulates realistic sensor readings and echoes commands so the
full UI can be exercised without hardware.
"""
from __future__ import annotations

import asyncio
import math
import random
import time
from typing import AsyncIterator

from .base import BaseTransport
from ..state import brew_state


class MockTransport(BaseTransport):
    def __init__(self) -> None:
        self._running = False
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._tick = 0

    async def connect(self) -> None:
        self._running = True
        brew_state.connected = True
        brew_state.transport_type = "mock"
        brew_state.add_log("Mock transport connected – demo mode")
        self._task = asyncio.create_task(self._simulate())

    async def disconnect(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        brew_state.connected = False
        brew_state.add_log("Mock transport disconnected")

    async def send(self, command: str) -> None:
        brew_state.add_log(f"→ {command}")
        # Echo back a synthetic response
        await self._queue.put(f"OK:{command.split()[0]}")

    async def receive(self) -> AsyncIterator[str]:
        while self._running:
            try:
                line = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield line
            except asyncio.TimeoutError:
                continue

    # ── Internal simulator ────────────────────────────────────────────────────

    async def _simulate(self) -> None:
        """Push realistic sensor data into the queue every second."""
        while self._running:
            await asyncio.sleep(1.0)
            self._tick += 1
            t = self._tick

            # Simulate slowly ramping mash temp when brewing
            if brew_state.status == "brewing":
                target = brew_state.mash_temp_target or 68.0
                actual = brew_state.mash_temp_actual
                # approach target at ~0.5 °C/s + small noise
                brew_state.mash_temp_actual = round(
                    actual + (target - actual) * 0.04 + random.uniform(-0.1, 0.1), 2
                )
                brew_state.boil_temp_actual = round(
                    brew_state.boil_temp_target * 0.97
                    + 1.5 * math.sin(t * 0.1)
                    + random.uniform(-0.2, 0.2), 2
                )
                brew_state.pressure_mbar = round(
                    1013 + random.uniform(-2, 2), 1
                )
                brew_state.weight_kg = round(
                    brew_state.weight_kg + random.uniform(-0.01, 0.01), 2
                )
                brew_state.step_elapsed_s = min(
                    brew_state.step_elapsed_s + 1,
                    brew_state.step_duration_s,
                )
                if (
                    brew_state.step_elapsed_s >= brew_state.step_duration_s
                    and brew_state.step_duration_s > 0
                ):
                    brew_state.current_step += 1
                    brew_state.step_elapsed_s = 0
                    if brew_state.current_step >= brew_state.total_steps:
                        brew_state.status = "complete"
                        brew_state.add_log("Brew complete (mock)")
                    else:
                        brew_state.step_name = f"Step {brew_state.current_step + 1}"
                        brew_state.add_log(f"Step {brew_state.current_step + 1} started")
            else:
                # Idle – slowly drift to ambient
                brew_state.mash_temp_actual = round(
                    brew_state.mash_temp_actual * 0.999 + 20.0 * 0.001, 2
                )
                brew_state.boil_temp_actual = round(
                    brew_state.boil_temp_actual * 0.999 + 20.0 * 0.001, 2
                )

            brew_state.last_updated = time.time()
            # Push status line so websocket picks it up
            await self._queue.put(
                f"STATUS mash={brew_state.mash_temp_actual} "
                f"boil={brew_state.boil_temp_actual} "
                f"state={brew_state.status}"
            )
