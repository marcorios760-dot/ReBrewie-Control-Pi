# MockTransport

Source: `app/transports/mock.py`

## Description and Purpose

`MockTransport` simulates machine responses for UI development without Brewie hardware.

## Methods

- `__init__()`: Initializes simulation state.
- `connect()`: Marks mock connected.
- `disconnect()`: Stops mock simulation.
- `send(command)`: Logs a command and updates command echo state.
- `receive()`: Yields simulated status messages.
- `_simulate()`: Background telemetry simulation.

## Usage Example

```bash
BREWIE_TRANSPORT=mock uvicorn app.main:app --host 127.0.0.1 --port 8080
```

## Design Notes

Mock mode allows contributors to work on layout, API flow, and basic state transitions without touching physical pumps, valves, or heaters.
