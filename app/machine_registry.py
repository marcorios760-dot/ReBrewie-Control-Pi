"""
Persist the Brewie machine registration shown in the remote UI.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import settings
from .registration import load_owner_registration, update_owner_machine


def _registry_path() -> Path:
    return Path(settings.machine_registry_file)


def load_machine_registration() -> dict[str, str]:
    owner = load_owner_registration()
    if owner:
        return {
            "machine_id": owner["machine_id"],
            "label": owner["label"],
        }

    data: dict[str, Any] = {}
    path = _registry_path()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}

    machine_id = str(data.get("machine_id") or settings.machine_id).strip()
    label = str(data.get("label") or "Brewie").strip()
    return {"machine_id": machine_id, "label": label}


def save_machine_registration(machine_id: str, label: str) -> dict[str, str]:
    owner = update_owner_machine(machine_id, label)
    if owner:
        return {
            "machine_id": owner["machine_id"],
            "label": owner["label"],
        }

    clean = {
        "machine_id": machine_id.strip(),
        "label": label.strip() or "Brewie",
    }
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
    return clean
