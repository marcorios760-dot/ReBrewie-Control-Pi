# TcpTransport

Source: `app/transports/tcp.py`

## Description and Purpose

`TcpTransport` communicates with a Brewie TCP bridge. In verified setups it connects to the Brewie machine on port `9000` and uses stock Brewie binary framing.

## Methods

- `__init__()`: Initializes socket state and packet counter.
- `_set_connected(value)`: Synchronizes internal and UI connection state.
- `_connected`: Property exposing connection status.
- `mark_disconnected()`: Marks TCP disconnected.
- `_apply_socket_keepalive()`: Enables TCP keepalive when possible.
- `_next_packet_id()`: Generates valid packet ids while avoiding control bytes.
- `connect()`: Opens TCP connection.
- `disconnect()`: Closes TCP connection.
- `send(command)`: Frames and sends a command.
- `receive()`: Reads ACK frames and telemetry lines.

## Usage Example

```python
transport = TcpTransport()
await transport.connect()
await transport.send("P205 1")
```

## Design Notes

Stock Brewie framing is essential for the original controller protocol. ACK frames are logged separately from V7 telemetry to make troubleshooting easier.
