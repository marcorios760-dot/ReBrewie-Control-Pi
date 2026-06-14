"""
app/state.py – in-memory brew state shared across all requests.

The state is updated by the polling loop (transport → parse → here)
and read by the API / WebSocket router.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class BrewState:
    # Connection
    connected: bool = False
    transport_type: str = "mock"

    # Brew status
    status: str = "idle"          # idle | brewing | paused | complete | error
    current_step: int = 0
    total_steps: int = 0
    step_name: str = ""
    step_elapsed_s: int = 0
    step_duration_s: int = 0

    # Temperatures (°C)
    mash_temp_actual: float = 0.0
    mash_temp_target: float = 0.0
    boil_temp_actual: float = 0.0
    boil_temp_target: float = 0.0

    # Valves / actuators  (True = open/on)
    water_inlet:   bool = False
    mash_inlet:    bool = False
    boil_inlet:    bool = False
    cool_inlet:    bool = False
    cool_valve:    bool = False
    outlet_valve:  bool = False
    mash_return:   bool = False
    boil_return:   bool = False
    mash_pump:     bool = False
    boil_pump:     bool = False
    fan:           bool = False
    hop1:          bool = False
    hop2:          bool = False
    hop3:          bool = False
    hop4:          bool = False

    # Pressure / weight (raw, unit depends on firmware)
    pressure_mbar: float = 0.0
    weight_kg: float = 0.0

    # Raw last line received from the machine
    last_raw: str = ""
    last_updated: float = field(default_factory=time.time)

    # Log ring-buffer (last 200 lines)
    log: list = field(default_factory=list)

    # Active recipe id (not display name), so resume can reload its steps
    active_recipe: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("log")          # log is streamed separately
        return d

    def add_log(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {line}")
        if len(self.log) > 200:
            self.log = self.log[-200:]


brew_state = BrewState()
