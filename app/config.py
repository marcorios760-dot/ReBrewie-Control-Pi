"""
app/config.py – settings and Brewie command map.

All environment variables are loaded from .env (via pydantic-settings).
The COMMAND_MAP contains the canonical P-command strings the firmware
understands.  Update the values here if your firmware revision uses
different strings.
"""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Transport selection: mock | tcp | http | serial
    brewie_transport: str = Field("tcp", alias="BREWIE_TRANSPORT")

    # TCP
    brewie_host: str = Field("192.168.1.132", alias="BREWIE_HOST")
    brewie_port: int = Field(9000, alias="BREWIE_PORT")
    brewie_tcp_framing: bool = Field(True, alias="BREWIE_TCP_FRAMING")

    # HTTP bridge
    brewie_http_base: str = Field("http://192.168.1.113:8080", alias="BREWIE_HTTP_BASE")

    # Serial / USB
    brewie_serial_port: str = Field("/dev/ttyUSB0", alias="BREWIE_SERIAL_PORT")
    brewie_serial_baud: int = Field(115200, alias="BREWIE_SERIAL_BAUD")

    # Web server
    local_bind: str = Field("0.0.0.0", alias="LOCAL_BIND")
    local_port: int = Field(8080, alias="LOCAL_PORT")

    # Recipes storage directory
    recipe_dir: str = Field("recipes", alias="RECIPE_DIR")

    # Discovery
    discovery_enabled: bool = Field(True, alias="DISCOVERY_ENABLED")
    discovery_subnet: str = Field("192.168.1", alias="DISCOVERY_SUBNET")
    discovery_timeout: float = Field(3.0, alias="DISCOVERY_TIMEOUT")

    # P80 parameters
    to_liter: float = Field(20.0, alias="TO_LITER")
    mash_temp_delta: float = Field(0.0, alias="MASH_TEMP_DELTA")
    boil_temp_delta: float = Field(0.0, alias="BOIL_TEMP_DELTA")

    @property
    def recipe_path(self) -> Path:
        p = Path(self.recipe_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def build_p80_command(self, volume_l: float | None = None) -> str:
        """Return a fully-parameterised P80 init/session command string.

        ``volume_l`` overrides ``to_liter`` when the recipe specifies a
        different batch volume (e.g. in ``control_start``).  When omitted the
        configured default is used (heartbeat, resume, and manual-mode start).

        Keeping this construction in one place means a protocol change only
        needs to be made here rather than in tcp.py, api.py, and anywhere else
        a P80 is built.
        """
        vol = volume_l if volume_l is not None else self.to_liter
        return (
            f"P80 {vol:.1f} 0 "
            f"{self.mash_temp_delta:.5f} {self.boil_temp_delta:.5f}"
        )


settings = Settings()


# ── Brewie P-Command map ────────────────────────────────────────────────────────
# Keys are human-readable names used in the API.
# Values are the raw command strings sent over the transport.
# Reference: commands.md in the project repository.
COMMAND_MAP: dict[str, str] = {
    # Initialise/session-open command. The firmware expects the full P80
    # payload; a bare P80 may not arm manual actuator commands.
    "init": settings.build_p80_command(),
    # Enqueue a step
    "enqueue_step": "P103",
    # Brewing program control
    "brew_run": "P200",
    # Water / valve controls
    "water_inlet_open":   "P110",
    "water_inlet_close":  "P111",
    "mash_inlet_open":    "P112",
    "mash_inlet_close":   "P113",
    "boil_inlet_open":    "P114",
    "boil_inlet_close":   "P115",
    "hop1_open":          "P116",
    "hop1_close":         "P117",
    "hop2_open":          "P118",
    "hop2_close":         "P119",
    "hop3_open":          "P120",
    "hop3_close":         "P121",
    "hop4_open":          "P122",
    "hop4_close":         "P123",
    "mash_pump_start":    "P124",
    "mash_pump_stop":     "P125",
    "boil_pump_start":    "P126",
    "boil_pump_stop":     "P127",
    "cool_inlet_open":    "P128",
    "cool_inlet_close":   "P129",
    "cool_valve_open":    "P130",
    "cool_valve_close":   "P131",
    "outlet_valve_open":  "P132",
    "outlet_valve_close": "P133",
    "mash_return_open":   "P134",
    "mash_return_close":  "P135",
    "boil_return_open":   "P136",
    "boil_return_close":  "P137",
    # Heaters
    "mash_heater_set": "P150",
    "boil_heater_set": "P151",
    # Fan / IO logging
    "fan_off": "P205 0",
    "fan_on":  "P205 1",
    # Safety
    "close_all_valves": "P999",
}
