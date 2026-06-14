"""
app/parser.py – parse raw Brewie response lines into brew_state updates.

The Brewie IO board responds to commands with lines like:
  OK:P80
  STATUS mash=67.4 boil=99.1 state=brewing
  ERROR:P103 reason=queue_full
  R<sensor_id>=<value>

This module handles all known formats observed from the original APK
and the community ReBrewie captures.  Unknown lines are logged as-is.
"""
from __future__ import annotations

import re
from .state import brew_state


# Simple key=value token pattern
_KV_RE = re.compile(r"(\w+)=([\S]+)")


def parse_line(line: str) -> None:
    """Update brew_state in-place from one raw response line."""
    line = line.strip()
    if not line:
        return

    # Any parseable/non-empty machine line proves the transport is alive.
    brew_state.connected = True

    upper = line.upper()

    # ── OK acknowledgement ────────────────────────────────────────────────────
    if upper.startswith("OK:"):
        return  # nothing to update

    # ── Error from firmware ───────────────────────────────────────────────────
    if upper.startswith("ERROR:"):
        brew_state.add_log(f"⚠ {line}")
        return

    # ── STATUS line (mock and some firmware builds) ───────────────────────────
    if upper.startswith("STATUS"):
        kv = dict(_KV_RE.findall(line))
        if "mash" in kv:
            try:
                brew_state.mash_temp_actual = float(kv["mash"])
            except ValueError:
                pass
        if "boil" in kv:
            try:
                brew_state.boil_temp_actual = float(kv["boil"])
            except ValueError:
                pass
        if "state" in kv:
            brew_state.status = kv["state"].lower()
        if "step" in kv:
            try:
                brew_state.current_step = int(kv["step"])
            except ValueError:
                pass
        return

    # ── Stock Brewie V7 telemetry from tty_tcp_bridge.py / P80 ────────────────
    # Example observed from a Brewie+ over TCP port 9000:
    #   -1 0 V7 0 0.0000 25.187 24.937 255.13 ...
    # The stock bridge uses tab/space-delimited fields and reports the first two
    # plausible temperature readings after the V7 marker as mash and boil actuals.
    if _parse_v7_telemetry(line):
        return

    # ── Register-style lines: R<id>=<value> ───────────────────────────────────
    m = re.match(r"^R(\d+)=([\S]+)$", line)
    if m:
        reg_id = int(m.group(1))
        raw_val = m.group(2)
        _apply_register(reg_id, raw_val)
        return

    # ── Comma-separated telemetry (original APK format) ───────────────────────
    # e.g.  "67.40,99.10,1013,20.0,1,3,600,300"
    parts = line.split(",")
    if len(parts) >= 4:
        try:
            brew_state.mash_temp_actual = float(parts[0])
            brew_state.boil_temp_actual = float(parts[1])
            brew_state.pressure_mbar    = float(parts[2])
            brew_state.weight_kg        = float(parts[3])
            if len(parts) > 4:
                brew_state.step_elapsed_s  = int(parts[4])
            if len(parts) > 5:
                brew_state.step_duration_s = int(parts[5])
            return
        except (ValueError, IndexError):
            pass

    # Unknown line – already logged by the transport layer
    brew_state.last_raw = line


def _parse_v7_telemetry(line: str) -> bool:
    """Parse stock Brewie V7 whitespace-delimited telemetry lines.

    The Brewie+ stock ``tty_tcp_bridge.py`` returns a tab-delimited row for P80
    where the token ``V7`` identifies the firmware payload. The exact complete
    field map is firmware-specific, but observed stock units place the mash and
    boil actual temperatures in the first two realistic Celsius fields after the
    header values. Disconnected sensors commonly report around 255, so those are
    intentionally ignored for live dashboard temperatures.
    """
    tokens = line.split()
    try:
        marker_index = next(i for i, token in enumerate(tokens) if token.upper() == "V7")
    except StopIteration:
        return False

    numeric_values: list[float] = []
    for token in tokens[marker_index + 1:]:
        try:
            numeric_values.append(float(token))
        except ValueError:
            continue

    plausible_temps = [value for value in numeric_values if -20.0 <= value <= 120.0]
    # Observed V7 rows start with status/flag/zero fields after V7. Use the first
    # plausible Celsius values above ambient zero noise as actual mash/boil temps.
    actual_temps = [value for value in plausible_temps if value > 1.0]
    if len(actual_temps) >= 1:
        brew_state.mash_temp_actual = actual_temps[0]
    if len(actual_temps) >= 2:
        brew_state.boil_temp_actual = actual_temps[1]
    if len(actual_temps) >= 1:
        return True

    return bool(numeric_values)

def _apply_register(reg_id: int, raw_val: str) -> None:
    """Map firmware register IDs to state fields."""
    try:
        val = float(raw_val)
    except ValueError:
        return

    mapping = {
        1:  "mash_temp_actual",
        2:  "boil_temp_actual",
        3:  "mash_temp_target",
        4:  "boil_temp_target",
        5:  "pressure_mbar",
        6:  "weight_kg",
        10: "step_elapsed_s",
        11: "step_duration_s",
        12: "current_step",
        13: "total_steps",
    }
    attr = mapping.get(reg_id)
    if attr:
        if attr in ("step_elapsed_s", "step_duration_s", "current_step", "total_steps"):
            setattr(brew_state, attr, int(val))
        else:
            setattr(brew_state, attr, val)
