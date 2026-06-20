# BaseTransport

Source: `app/transports/base.py`

## Description and Purpose

`BaseTransport` is the abstract interface implemented by all machine communication transports.

## Methods

### `mark_disconnected()`

Marks state disconnected after receive/send failure.

### `connect()`

Open the transport connection.

### `disconnect()`

Close the transport connection.

### `send(command)`

Send one raw P-command string.

### `receive()`

Yield incoming telemetry or response lines.

## Usage Example

```python
transport = get_transport()
await transport.connect()
await transport.send("P999")
```

## Design Notes

The abstract interface allows TCP, HTTP, serial, and mock modes to share the same router and parser logic.
