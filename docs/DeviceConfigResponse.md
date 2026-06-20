# DeviceConfigResponse

Source: `app/routers/discovery.py`

## Description and Purpose

`DeviceConfigResponse` describes the currently selected Brewie/ReBrewie connection details.

## Fields

Includes IP, port, protocol/transport type, URL, and status metadata.

## Usage Example

```python
# Returned by discovery/configuration API routes.
```

## Design Notes

A typed response gives the UI enough information to explain which machine endpoint is active.
