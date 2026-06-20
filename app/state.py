"""
app/state.py – in-memory brew state shared across all requests.

The state is updated by the polling loop (transport → parse → here)
and read by the API / WebSocket router.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Optional


ACTUATOR_FIELDS: tuple[str, ...] = (
    "water_inlet", "mash_inlet", "boil_inlet", "cool_inlet",
    "cool_valve", "outlet_valve", "mash_return", "boil_return",
    "mash_pump", "boil_pump", "fan", "hop1", "hop2", "hop3", "hop4",
)


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

    # Temperatures (°C) — live NTC sensor readings
    mash_temp_actual: float = 0.0
    mash_temp_target: float = 0.0
    boil_temp_actual: float = 0.0
    boil_temp_target: float = 0.0

    # Additional V7 telemetry decoded from confirmed field positions.
    # Fields are 0/None until the first V7 line is parsed.
    step_state: int = 0            # MCU step index (0 = idle)
    step_timer_s: int = 0          # elapsed whole seconds in current step (V7 off[1])
    board_temp_a: float = 0.0      # PCB ambient sensor A (~17 °C at idle)
    board_temp_b: float = 0.0      # PCB ambient sensor B (~18 °C at idle)
    inlet_water_temp: float = 0.0  # cold-water inlet sensor (~28 °C at idle)
    v7_raw_status: int = 0         # raw status bitmask (260-264 during idle)

    # Valves / actuators (True = open/on). These are commanded values for
    # manual P-commands unless actuator_state_verified is true.
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

    actuator_state_source: str = "commanded"
    actuator_state_verified: bool = False
    last_commanded_actuator: Optional[str] = None
    last_commanded_value: Optional[bool] = None
    last_commanded_command: Optional[str] = None
    last_commanded_at: float = 0.0

    # Pressure / weight (raw, unit depends on firmware)
    pressure_mbar: float = 0.0
    weight_kg: float = 0.0

    # Raw last line received from the machine
    last_raw: str = ""
    last_updated: float = field(default_factory=time.time)

    # Log ring-buffer (last 200 lines)
    log: list = field(default_factory=list)

    # Active recipe (display name + id stored separately so resume can reload it)
    active_recipe: Optional[str] = None
    active_recipe_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("log")          # log is streamed separately
        return d

    def add_log(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {line}")
        if len(self.log) > 200:
            self.log = self.log[-200:]

    def clear_brew_progress(self) -> None:
        self.status = "idle"
        self.current_step = 0
        self.total_steps = 0
        self.step_name = ""
        self.step_elapsed_s = 0
        self.step_duration_s = 0
        self.active_recipe = None
        self.active_recipe_id = None

    def _mark_commanded_actuator(
        self,
        attr: str,
        value: bool,
        command: str,
    ) -> None:
        setattr(self, attr, value)
        self.actuator_state_source = "commanded"
        self.actuator_state_verified = False
        self.last_commanded_actuator = attr
        self.last_commanded_value = value
        self.last_commanded_command = command
        self.last_commanded_at = time.time()

    def apply_sent_command(self, command: str) -> None:
        """Reflect last-commanded actuator state when telemetry lacks bit detail."""
        cmd = command.strip().upper()
        if not cmd:
            return

        effects = {
            "P110": ("water_inlet", True),
            "P111": ("water_inlet", False),
            "P112": ("mash_inlet", True),
            "P113": ("mash_inlet", False),
            "P114": ("boil_inlet", True),
            "P115": ("boil_inlet", False),
            "P116": ("hop1", True),
            "P117": ("hop1", False),
            "P118": ("hop2", True),
            "P119": ("hop2", False),
            "P120": ("hop3", True),
            "P121": ("hop3", False),
            "P122": ("hop4", True),
            "P123": ("hop4", False),
            "P124": ("mash_pump", True),
            "P125": ("mash_pump", False),
            "P126": ("boil_pump", True),
            "P127": ("boil_pump", False),
            "P128": ("cool_inlet", True),
            "P129": ("cool_inlet", False),
            "P130": ("cool_valve", True),
            "P131": ("cool_valve", False),
            "P132": ("outlet_valve", True),
            "P133": ("outlet_valve", False),
            "P134": ("mash_return", True),
            "P135": ("mash_return", False),
            "P136": ("boil_return", True),
            "P137": ("boil_return", False),
            "P205 1": ("fan", True),
            "P205 0": ("fan", False),
        }

        if cmd == "P999":
            for attr in ACTUATOR_FIELDS:
                if attr in ("mash_pump", "boil_pump", "fan"):
                    continue
                self._mark_commanded_actuator(attr, False, cmd)
            return

        if cmd.startswith("P150 "):
            self.mash_temp_target = _target_from_command(cmd)
            return

        if cmd.startswith("P151 "):
            self.boil_temp_target = _target_from_command(cmd)
            return

        effect = effects.get(cmd)
        if effect:
            self._mark_commanded_actuator(effect[0], effect[1], cmd)


def _target_from_command(command: str) -> float:
    try:
        raw = float(command.split()[1])
    except (IndexError, ValueError):
        return 0.0
    return raw / 10.0 if raw > 0 else 0.0


brew_state = BrewState()
