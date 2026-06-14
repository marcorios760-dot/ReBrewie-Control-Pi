#!/usr/bin/env python3
"""Check the Control Pi API for stock Brewie TCP/V7 telemetry.

This script uses only the Python standard library so it can be run from the
Raspberry Pi project folder without installing extra packages.

Examples:
  python3 scripts/check_pi_telemetry.py --base http://192.168.1.113:8080
  python3 scripts/check_pi_telemetry.py --host 192.168.1.113 --port 8080
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def fetch_json(url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object from {url}, got {type(data).__name__}")
    return data


def parse_v7_temperatures(raw: str) -> tuple[float | None, float | None]:
    tokens = raw.split()
    marker_index = next(
        (index for index, token in enumerate(tokens) if token.upper() == "V7"), None
    )
    if marker_index is None:
        return None, None

    values: list[float] = []
    for token in tokens[marker_index + 1:]:
        try:
            values.append(float(token))
        except ValueError:
            continue

    realistic = [value for value in values if 1.0 < value <= 120.0]
    mash = realistic[0] if len(realistic) >= 1 else None
    boil = realistic[1] if len(realistic) >= 2 else None
    return mash, boil


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ReBrewie Control Pi telemetry")
    parser.add_argument("--host", default="192.168.1.113", help="Control Pi host/IP")
    parser.add_argument("--port", type=int, default=8080, help="Control Pi web port")
    parser.add_argument("--base", help="Full Control Pi base URL, e.g. http://192.168.1.113:8080")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    base_url = (args.base or f"http://{args.host}:{args.port}").rstrip("/")
    try:
        status = fetch_json(f"{base_url}/api/status", args.timeout)
        log_data = fetch_json(f"{base_url}/api/log?n=20", args.timeout)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: failed to query {base_url}: {exc}", file=sys.stderr)
        return 2

    log_lines = log_data.get("log", [])
    if not isinstance(log_lines, list):
        log_lines = []

    print(f"Control Pi: {base_url}")
    print(f"connected: {status.get('connected')}")
    print(f"transport_type: {status.get('transport_type')}")
    print(f"mash_temp_actual: {status.get('mash_temp_actual')}")
    print(f"boil_temp_actual: {status.get('boil_temp_actual')}")
    print(f"last_updated: {status.get('last_updated')}")

    last_raw = str(status.get("last_raw") or "")
    if last_raw:
        print(f"last_raw: {last_raw}")
    else:
        print("last_raw: <empty>")

    v7_lines = [line for line in log_lines if "V7" in str(line)]
    if v7_lines:
        print("latest V7 log line:")
        print(v7_lines[-1])

    expected_mash, expected_boil = parse_v7_temperatures(last_raw)
    if expected_mash is not None or expected_boil is not None:
        print(
            "parsed_from_last_raw: "
            f"mash={expected_mash if expected_mash is not None else 'unknown'} "
            f"boil={expected_boil if expected_boil is not None else 'unknown'}"
        )

    connected = status.get("connected") is True
    transport_ok = status.get("transport_type") == "tcp"
    has_v7 = "V7" in last_raw or bool(v7_lines)
    temps = [status.get("mash_temp_actual"), status.get("boil_temp_actual")]
    temps_ok = any(isinstance(temp, (int, float)) and temp > 0 for temp in temps)

    if connected and transport_ok and has_v7 and temps_ok:
        print("OK: TCP bridge is connected, V7 telemetry is present, and temperatures are parsed.")
        return 0

    print("WARN: telemetry is not fully reflected in /api/status yet.")
    if not connected:
        print("- connected is not true; check service logs and Brewie network reachability.")
    if not transport_ok:
        print("- transport_type is not tcp; run sudo scripts/configure_brewie_tcp.sh 192.168.1.132 9000.")
    if not has_v7:
        print("- no V7 telemetry found yet; wait a few seconds and refresh /api/log?n=200.")
    if has_v7 and not temps_ok:
        print("- V7 telemetry is present but temperatures are zero; reinstall this update and restart rebrewie-control-pi.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
