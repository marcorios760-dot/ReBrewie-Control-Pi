# Settings

Source: `app/config.py`

## Description and Purpose

`Settings` is the central configuration model for ReBrewie-Pi-Control. It loads environment variables from `.env` using `pydantic-settings` and exposes typed values for transport selection, Brewie addressing, serial settings, web server binding, recipe storage, discovery, and P80 session parameters.

## Fields

- `brewie_transport`: Selects `tcp`, `http`, `serial`, or `mock`.
- `brewie_host` / `brewie_port`: TCP target for the Brewie bridge.
- `brewie_tcp_framing`: Enables stock Brewie command framing.
- `brewie_http_base`: Base URL for HTTP bridge mode.
- `brewie_serial_port` / `brewie_serial_baud`: Serial transport settings.
- `local_bind` / `local_port`: Web server bind configuration.
- `recipe_dir`: Directory where recipe JSON files are stored.
- `discovery_*`: Discovery helper options.
- `to_liter`, `mash_temp_delta`, `boil_temp_delta`: P80 command parameters.

## Methods

### `recipe_path`

Creates and returns the configured recipe directory as a `Path`.

### `build_p80_command(volume_l=None)`

Builds the full `P80` initialization/session command using either the provided volume or the configured default.

## Usage Example

```python
from app.config import settings

print(settings.brewie_host)
print(settings.build_p80_command(20.0))
```

## Design Notes

Keeping P80 construction centralized prevents multiple parts of the app from drifting when the initialization command format changes.
