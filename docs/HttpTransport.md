# HttpTransport

Source: `app/transports/http_transport.py`

## Description and Purpose

`HttpTransport` talks to an HTTP bridge that exposes Brewie status and command endpoints.

## Methods

- `__init__()`: Initializes HTTP client state.
- `mark_disconnected()`: Marks bridge disconnected.
- `connect()`: Validates bridge status endpoint.
- `disconnect()`: Closes HTTP client and polling task.
- `send(command)`: Posts a command to the bridge.
- `receive()`: Yields status lines from polling.
- `_poll_loop()`: Background status poller.

## Usage Example

```python
transport = HttpTransport()
await transport.connect()
await transport.send("P80 20.0 0 0.00000 0.00000")
```

## Design Notes

HTTP mode is less direct than TCP but useful when an intermediate bridge already exists.
