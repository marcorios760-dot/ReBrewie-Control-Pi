# SerialTransport

Source: `app/transports/serial_transport.py`

## Description and Purpose

`SerialTransport` sends line-oriented P-commands over a local serial device. It is useful for direct USB/serial configurations or protocol experiments.

## Methods

- `__init__()`: Initializes serial handles.
- `mark_disconnected()`: Marks serial disconnected.
- `connect()`: Opens the configured serial port.
- `disconnect()`: Closes serial resources.
- `send(command)`: Writes one command line.
- `receive()`: Yields decoded serial lines.

## Usage Example

```python
transport = SerialTransport()
await transport.connect()
await transport.send("P999")
```

## Design Notes

Serial mode mirrors the TCP interface so the rest of the app does not need transport-specific branching.
