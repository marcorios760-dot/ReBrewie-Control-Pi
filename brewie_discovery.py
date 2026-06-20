"""
Brewie+ network discovery helpers.

The discovery layer probes likely HTTP/HTTPS endpoints on a known host or /24
subnet and looks for ReBrewie/Brewie signatures in the response body.  It uses
httpx so the project does not need a second HTTP client dependency.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)


class BrewieDiscovery:
    """Discover and validate Brewie+/ReBrewie devices on the local network."""

    COMMON_PORTS = [8332, 80, 8080, 443, 8443, 3000, 5000, 22]
    BREWIE_SIGNATURES = ["brewie", "brewie+", "brewie_plus", "brewieplus", "rebrewie"]
    COMMON_ENDPOINTS = [
        "/",
        "/api",
        "/api/status",
        "/api/info",
        "/api/brew/status",
        "/api/v1/status",
        "/system/info",
    ]

    def __init__(self, timeout: float = 3.0, verbose: bool = False) -> None:
        self.timeout = timeout
        self.verbose = verbose
        self.found_device: dict[str, Any] | None = None

    def scan_ip(self, ip: str, port: int = 8332) -> dict[str, Any] | None:
        """Check a specific IP/port for a Brewie-like HTTP endpoint."""
        with httpx.Client(timeout=self.timeout, verify=False, follow_redirects=True) as client:
            return self._scan_ip_with_client(client, ip, port)

    async def scan_ip_async(self, ip: str, port: int = 8332) -> dict[str, Any] | None:
        """Async variant of :meth:`scan_ip`."""
        async with httpx.AsyncClient(
            timeout=self.timeout, verify=False, follow_redirects=True
        ) as client:
            return await self._scan_ip_with_async_client(client, ip, port)

    def scan_subnet(self, subnet: str = "192.168.1", port: int = 8332) -> list[dict[str, Any]]:
        """Scan all hosts in a /24 subnet for Brewie-like devices."""
        devices: list[dict[str, Any]] = []
        with httpx.Client(timeout=self.timeout, verify=False, follow_redirects=True) as client:
            for ip in _iter_subnet_hosts(subnet):
                device = self._scan_ip_with_client(client, ip, port)
                if device:
                    devices.append(device)
        return devices

    async def scan_subnet_async(
        self, subnet: str = "192.168.1", port: int = 8332, max_concurrent: int = 16
    ) -> list[dict[str, Any]]:
        """Scan all hosts in a /24 subnet concurrently."""
        semaphore = asyncio.Semaphore(max(1, max_concurrent))
        async with httpx.AsyncClient(
            timeout=self.timeout, verify=False, follow_redirects=True
        ) as client:
            async def probe(ip: str) -> dict[str, Any] | None:
                async with semaphore:
                    return await self._scan_ip_with_async_client(client, ip, port)

            results = await asyncio.gather(
                *(probe(ip) for ip in _iter_subnet_hosts(subnet)), return_exceptions=True
            )
        return [r for r in results if isinstance(r, dict)]

    def discover(
        self,
        known_ip: str | None = None,
        subnet: str | None = None,
        enable_subnet_scan: bool = True,
    ) -> dict[str, Any]:
        """Run discovery and return a stable API response for the router."""
        devices: list[dict[str, Any]] = []
        if known_ip:
            devices.extend(self._scan_known_ip(known_ip))
        elif enable_subnet_scan:
            devices.extend(self._scan_all_common_ports(subnet or _default_subnet()))

        self.found_device = devices[0] if devices else None
        return _result(devices, known_ip=known_ip, subnet=subnet, enable_subnet_scan=enable_subnet_scan)

    async def discover_async(
        self,
        known_ip: str | None = None,
        subnet: str | None = None,
        enable_subnet_scan: bool = True,
        max_concurrent: int = 16,
    ) -> dict[str, Any]:
        """Async discovery variant for background API scans."""
        devices: list[dict[str, Any]] = []
        if known_ip:
            for port in self.COMMON_PORTS:
                device = await self.scan_ip_async(known_ip, port)
                if device:
                    devices.append(device)
        elif enable_subnet_scan:
            scan_subnet = subnet or _default_subnet()
            for port in self.COMMON_PORTS:
                devices.extend(
                    await self.scan_subnet_async(
                        scan_subnet, port=port, max_concurrent=max_concurrent
                    )
                )

        self.found_device = devices[0] if devices else None
        return _result(devices, known_ip=known_ip, subnet=subnet, enable_subnet_scan=enable_subnet_scan)

    def try_known_endpoints(self, base_url: str) -> dict[str, Any]:
        """Probe common endpoints on a discovered HTTP device."""
        results: dict[str, Any] = {}
        with httpx.Client(timeout=self.timeout, verify=False, follow_redirects=True) as client:
            for endpoint in self.COMMON_ENDPOINTS:
                url = urljoin(base_url + "/", endpoint.lstrip("/"))
                try:
                    resp = client.get(url)
                except httpx.HTTPError as exc:
                    if self.verbose:
                        logger.debug("%s -> %s", endpoint, exc)
                    continue
                if resp.status_code != 404:
                    results[endpoint] = {
                        "status": resp.status_code,
                        "content_type": resp.headers.get("Content-Type", ""),
                        "body": resp.text[:1000],
                    }
        return results

    def _scan_known_ip(self, known_ip: str) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        for port in self.COMMON_PORTS:
            device = self.scan_ip(known_ip, port)
            if device:
                devices.append(device)
        return devices

    def _scan_all_common_ports(self, subnet: str) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        for port in self.COMMON_PORTS:
            devices.extend(self.scan_subnet(subnet, port))
        return devices

    def _scan_ip_with_client(
        self, client: httpx.Client, ip: str, port: int
    ) -> dict[str, Any] | None:
        for protocol in ("http", "https"):
            device = self._device_from_response(client, protocol, ip, port)
            if device:
                return device
        return None

    async def _scan_ip_with_async_client(
        self, client: httpx.AsyncClient, ip: str, port: int
    ) -> dict[str, Any] | None:
        for protocol in ("http", "https"):
            device = await self._device_from_async_response(client, protocol, ip, port)
            if device:
                return device
        return None

    def _device_from_response(
        self, client: httpx.Client, protocol: str, ip: str, port: int
    ) -> dict[str, Any] | None:
        base_url = f"{protocol}://{ip}:{port}"
        try:
            resp = client.get(base_url)
        except httpx.HTTPError:
            return None
        return _device_from_http_response(resp, ip=ip, port=port, protocol=protocol, url=base_url)

    async def _device_from_async_response(
        self, client: httpx.AsyncClient, protocol: str, ip: str, port: int
    ) -> dict[str, Any] | None:
        base_url = f"{protocol}://{ip}:{port}"
        try:
            resp = await client.get(base_url)
        except httpx.HTTPError:
            return None
        return _device_from_http_response(resp, ip=ip, port=port, protocol=protocol, url=base_url)


def _device_from_http_response(
    resp: httpx.Response, *, ip: str, port: int, protocol: str, url: str
) -> dict[str, Any] | None:
    body = resp.text.lower()
    matched = [sig for sig in BrewieDiscovery.BREWIE_SIGNATURES if sig in body]
    if not matched:
        return None
    return {
        "ip": ip,
        "port": port,
        "protocol": protocol,
        "transport_type": "http",
        "url": url,
        "status_code": resp.status_code,
        "matched_signatures": matched,
        "response_snippet": resp.text[:500],
    }


def _iter_subnet_hosts(subnet: str):
    network = subnet if "/" in subnet else f"{subnet}.0/24"
    for ip in ipaddress.ip_network(network, strict=False).hosts():
        yield str(ip)


def _default_subnet() -> str:
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        return "192.168.1"
    parts = ip.split(".")
    if len(parts) == 4 and not ip.startswith("127."):
        return ".".join(parts[:3])
    return "192.168.1"


def _result(
    devices: list[dict[str, Any]], *, known_ip: str | None, subnet: str | None, enable_subnet_scan: bool
) -> dict[str, Any]:
    unique: dict[tuple[str, int, str], dict[str, Any]] = {}
    for device in devices:
        unique[(device["ip"], device["port"], device["protocol"])] = device
    deduped = list(unique.values())
    return {
        "devices": deduped,
        "summary": {
            "total_found": len(deduped),
            "known_ip": known_ip,
            "subnet": subnet,
            "subnet_scan_enabled": enable_subnet_scan,
        },
    }


if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(level=logging.INFO)
    disc = BrewieDiscovery(verbose=True)
    known = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(disc.discover(known_ip=known), indent=2))
