# BrewState

Source: `app/state.py`

## Description and Purpose

`BrewState` is the shared in-memory state object used by routes, transports, parser, and WebSocket updates. It holds live telemetry, actuator command echoes, current program progress, and an event log.

## Methods

### `to_dict()`

Returns the state as a serializable dictionary for APIs and WebSockets.

### `add_log(line)`

Adds a timestamped message to the in-memory rolling log.

### `clear_brew_progress()`

Resets progress fields after stop/abort.

### `_mark_commanded_actuator(...)`

Records the last commanded actuator state.

### `apply_sent_command(command)`

Updates command echo fields after sending a recognized P-command.

## Usage Example

```python
from app.state import brew_state

brew_state.add_log("Manual check started")
print(brew_state.to_dict())
```

## Design Notes

The app distinguishes commanded actuator state from telemetry-confirmed state because the Brewie V7 stream often echoes recent commands rather than proving hardware position electrically.
