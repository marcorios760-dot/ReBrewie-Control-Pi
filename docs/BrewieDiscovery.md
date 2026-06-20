# BrewieDiscovery

Source: `brewie_discovery.py`

## Description and Purpose

`BrewieDiscovery` scans a local subnet for likely Brewie/ReBrewie endpoints and probes known status URLs.

## Methods

- `__init__(timeout, verbose)`: Configures probe behavior.
- `scan_ip(ip, port)`: Synchronously scan one IP/port.
- `scan_ip_async(ip, port)`: Asynchronously scan one IP/port.
- `scan_subnet(subnet, port)`: Scan a class-C style subnet.
- `scan_subnet_async(...)`: Async subnet scan.
- `discover(...)`: Higher-level discovery routine.
- `discover_async(...)`: Async discovery routine.
- `try_known_endpoints(base_url)`: Probe common Brewie endpoints.
- Private helpers build response-derived device records.

## Usage Example

```python
from brewie_discovery import BrewieDiscovery

scanner = BrewieDiscovery(timeout=2.0)
for device in scanner.scan_subnet("192.168.1"):
    print(device)
```

## Design Notes

Discovery is intentionally local-network only. It is a convenience helper, not an internet discovery mechanism.
