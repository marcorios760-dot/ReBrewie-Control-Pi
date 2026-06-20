# ScanRequest

Source: `app/routers/discovery.py`

## Description and Purpose

`ScanRequest` configures a device discovery scan.

## Fields

Includes subnet, ports, known IPs, and scan behavior options used by the discovery router.

## Usage Example

```json
{ "subnet": "192.168.1", "ports": [8332, 9000] }
```

## Design Notes

The model keeps discovery parameters explicit and avoids hard-coding one network layout.
