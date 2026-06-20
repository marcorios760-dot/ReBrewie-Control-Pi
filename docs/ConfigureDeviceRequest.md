# ConfigureDeviceRequest

Source: `app/routers/discovery.py`

## Description and Purpose

`ConfigureDeviceRequest` accepts user-selected device details and updates runtime transport configuration.

## Fields

Includes IP, port, and transport type.

## Usage Example

```json
{ "ip": "192.168.1.132", "port": 9000, "transport_type": "tcp" }
```

## Design Notes

The app can swap transport configuration without a full service restart, which helps during setup and troubleshooting.
