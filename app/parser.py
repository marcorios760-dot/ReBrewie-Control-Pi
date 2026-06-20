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


# ── V7 sensor validity ranges ────────────────────────────────────────────────
# Named so intent is documented and the limits are tunable in one place if
# hardware/firmware behaviour changes.  Disconnected NTC probes report ~280°C,
# well outside any of these windows, so out-of-range readings are dropped
# rather than corrupting brew_state with nonsense values.
#
# mash/boil/board ambient sensors share one window: all are physically
# plausible process temperatures on this machine (kettle, mash tun, PCB).
PROCESS_TEMP_MIN_C: float = -10.0
PROCESS_TEMP_MAX_C: float = 115.0
# Inlet (cold water supply) never gets hot, so it gets a tighter ceiling —
# this also catches field-offset mistakes that would otherwise silently
# masquerade as a plausible process temperature.
INLET_TEMP_MIN_C: float = -10.0
INLET_TEMP_MAX_C: float = 50.0


def _safe_float(fields: list[str], idx: int) -> float | None:
    """Parse fields[idx] as float, returning None on IndexError/ValueError.

    Module-level (not a per-call closure) so repeated calls during the
    receive loop don't allocate a new function object each time.
    """
    if idx >= len(fields):
        return None
    try:
        return float(fields[idx])
    except ValueError:
        return None


def _safe_int(fields: list[str], idx: int) -> int | None:
    """Parse fields[idx] as int via float (handles values like '0.0')."""
    v = _safe_float(fields, idx)
    return int(v) if v is not None else None

# Simple key=value token pattern
_KV_RE = re.compile(r"(\w+)=([\S]+)")


def parse_line(line: str) -> None:
    """Update brew_state in-place from one raw response line."""
    line = line.strip()
    if not line:
        return

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
    """Parse stock Brewie V7 telemetry using confirmed positional field offsets.

    Field layout verified from real Brewie+ hardware via debug-bridge hex-dumps
    (``v1_debug_bridge.py`` run on the machine, Jun 15 2026).  All offsets are
    relative to the ``V7`` marker token; ``line.split()`` collapses the
    multi-tab format the MCU emits into a clean token list.

    Confirmed field map (``fields[N]`` = token at ``v7_marker + 1 + N``):

        off[0]  step_state         MCU step index (0 = idle)
        off[1]  step_timer_s       elapsed whole seconds in current step
        off[2]  mash_temp_actual   NTC mash/vessel sensor (°C)  ← confirmed
        off[3]  boil_temp_actual   NTC boil/kettle sensor (°C)  ← confirmed
        off[4]  ~282 °C            disconnected probe, ignore
        off[5]  ~280 °C            disconnected probe, ignore
        off[6]  0.0000             disconnected / unused
        off[7]  0.0000             disconnected / unused
        off[8]  0                  integer flag
        off[9]  board_temp_a       PCB ambient sensor A (~17 °C at idle)
        off[10] 0                  integer flag
        off[11] board_temp_b       PCB ambient sensor B (~18 °C at idle)
        off[12] 0                  integer flag
        off[13] 0                  integer flag
        off[14] v7_raw_status      raw status word (260-264 idle; changes during brew)
        off[15] 0.0000             unknown
        off[16] 0.0000             unknown
        off[17] 100.00             unknown (constant in idle; purpose TBD)
        off[18] inlet_water_temp   cold-water / inlet sensor (~28 °C at idle)
        off[19] 0.0000             unknown
        off[20] 0                  last flag

    Returns True (and marks brew_state.connected = True) whenever the line is
    structurally a valid V7 telemetry line — i.e. it carries the V7 marker and
    at least the minimum required fields — regardless of whether any
    individual sensor reading happens to fall outside its plausible range at
    this exact moment.  Connection liveness reflects "did the machine send us
    a parseable line", not "did every sensor happen to be in range right now".
    """
    tokens = line.split()
    try:
        v7_idx = next(i for i, t in enumerate(tokens) if t.upper() == "V7")
    except StopIteration:
        return False

    fields = tokens[v7_idx + 1:]
    if len(fields) < 4:
        return False  # need at least step_state + timer + mash + boil

    # Past this point the line is structurally valid V7 telemetry: the
    # machine is alive and talking, independent of individual sensor ranges.
    parsed_anything = True

    # ── Step metadata (off[0], off[1]) ───────────────────────────────────────
    step = _safe_int(fields, 0)
    if step is not None:
        brew_state.step_state = step

    timer = _safe_int(fields, 1)
    if timer is not None:
        brew_state.step_timer_s = timer

    # ── Primary temperature sensors (off[2], off[3]) ─────────────────────────
    mash = _safe_float(fields, 2)
    boil = _safe_float(fields, 3)
    if mash is not None and PROCESS_TEMP_MIN_C <= mash <= PROCESS_TEMP_MAX_C:
        brew_state.mash_temp_actual = mash
    if boil is not None and PROCESS_TEMP_MIN_C <= boil <= PROCESS_TEMP_MAX_C:
        brew_state.boil_temp_actual = boil

    # ── PCB ambient sensors (off[9], off[11]) ────────────────────────────────
    ba = _safe_float(fields, 9)
    if ba is not None and PROCESS_TEMP_MIN_C <= ba <= PROCESS_TEMP_MAX_C:
        brew_state.board_temp_a = ba

    bb = _safe_float(fields, 11)
    if bb is not None and PROCESS_TEMP_MIN_C <= bb <= PROCESS_TEMP_MAX_C:
        brew_state.board_temp_b = bb

    # ── Raw status word (off[14]) ─────────────────────────────────────────────
    # Observed 260-264 during idle; individual bit meanings TBD from live brews.
    sw = _safe_int(fields, 14)
    if sw is not None:
        brew_state.v7_raw_status = sw

    # ── Cold-water / inlet sensor (off[18]) ──────────────────────────────────
    inlet = _safe_float(fields, 18)
    if inlet is not None and INLET_TEMP_MIN_C <= inlet <= INLET_TEMP_MAX_C:
        brew_state.inlet_water_temp = inlet

    # ── Connection liveness ───────────────────────────────────────────────────
    # last_updated is set by the transport's receive loop, not here, so that
    # refresh_state_from_last_raw() calls don't falsely refresh the timestamp.
    if parsed_anything:
        brew_state.connected = True
    return parsed_anything

def refresh_state_from_last_raw() -> None:
    """Re-parse the last received raw line to refresh brew_state fields.

    Called by the REST API and WebSocket routers before serving a response so
    that the freshest possible values are returned without waiting for the next
    receive-loop tick.  Safe to call even when ``last_raw`` is empty.
    """
    if brew_state.last_raw:
        parse_line(brew_state.last_raw)


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
