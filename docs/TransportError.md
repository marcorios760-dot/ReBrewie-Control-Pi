# TransportError

Source: `app/transports/base.py`

## Description and Purpose

`TransportError` represents failures in the command transport layer. FastAPI converts it to HTTP 503 so users see a machine connectivity problem rather than a generic server bug.

## Usage Example

```python
from app.transports import TransportError

raise TransportError("TCP not connected - command not sent")
```

## Design Notes

Transport failures are expected operational conditions when a Brewie is off, disconnected, or rebooting. A dedicated exception keeps that distinction clear.
