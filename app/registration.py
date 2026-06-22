"""
Owner account and machine registration storage.
"""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

from .config import settings


def registration_path() -> Path:
    return Path(settings.auth_registration_file)


def load_owner_registration() -> dict[str, str] | None:
    path = registration_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    username = str(data.get("username") or "").strip()
    password_hash = str(data.get("password_hash") or "").strip()
    machine_id = str(data.get("machine_id") or "").strip()
    if not username or not password_hash or not machine_id:
        return None

    return {
        "username": username,
        "password_hash": password_hash,
        "machine_id": machine_id,
        "label": str(data.get("label") or "Brewie").strip() or "Brewie",
        "session_secret": str(data.get("session_secret") or "").strip(),
        "created_at": str(data.get("created_at") or ""),
    }


def has_owner_registration() -> bool:
    return load_owner_registration() is not None


def create_owner_registration(
    *,
    username: str,
    password_hash: str,
    machine_id: str,
    label: str,
) -> dict[str, str]:
    clean = {
        "username": username.strip(),
        "password_hash": password_hash.strip(),
        "machine_id": machine_id.strip(),
        "label": label.strip() or "Brewie",
        "session_secret": secrets.token_urlsafe(32),
        "created_at": str(int(time.time())),
    }
    if not clean["username"]:
        raise ValueError("Username is required")
    if not clean["password_hash"]:
        raise ValueError("Password hash is required")
    if not clean["machine_id"]:
        raise ValueError("Machine ID / Serial # is required")

    path = registration_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
    return clean


def update_owner_machine(machine_id: str, label: str) -> dict[str, str] | None:
    current = load_owner_registration()
    if current is None:
        return None
    current["machine_id"] = machine_id.strip()
    current["label"] = label.strip() or "Brewie"
    path = registration_path()
    path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return current


def registration_summary() -> dict[str, str]:
    owner = load_owner_registration()
    if owner:
        return {
            "username": owner["username"],
            "machine_id": owner["machine_id"],
            "label": owner["label"],
        }
    return {
        "username": settings.auth_username,
        "machine_id": settings.machine_id,
        "label": "Brewie",
    }
