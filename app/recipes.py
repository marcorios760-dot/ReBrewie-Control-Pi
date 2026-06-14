"""
app/recipes.py – recipe model and JSON file helpers.

Recipes are stored as individual JSON files in the recipes/ directory.
The schema mirrors the structure needed to build P103 step commands.
"""
from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .config import settings


# ── Data models ───────────────────────────────────────────────────────────────

class RecipeStep(BaseModel):
    name: str = ""
    duration_s: int = 3600          # step time in seconds
    mash_temp: int = 0              # mash tank target × 10 (e.g. 670 = 67.0 °C)
    boil_temp: int = 0              # boil tank target × 10
    water_inlet: bool = False
    mash_inlet: bool = False
    boil_inlet: bool = False
    hop1: bool = False
    hop2: bool = False
    hop3: bool = False
    hop4: bool = False
    cool_valve: int = 0             # 0 = close, 255 = open
    cool_inlet: int = 0
    mash_pump: int = 0              # 0 = off, 255 = on
    boil_pump: int = 0
    mash_return: bool = False
    boil_return: bool = False
    step_type: int = 1              # completion type (1–10, firmware-specific)
    step_mode: int = 0              # 0=normal, 2=sparge, 3=boil


class Recipe(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "New Recipe"
    author: str = ""
    style: str = ""
    batch_volume_l: float = 20.0
    notes: str = ""
    steps: list[RecipeStep] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()
        if not _SAFE_ID_RE.fullmatch(value):
            raise ValueError(
                "Recipe id may contain only letters, numbers, dots, underscores, and hyphens"
            )
        return value

    def to_p103_args(self, step_index: int) -> str:
        """Return the argument string for a P103 enqueue command for this step."""
        if step_index < 0 or step_index >= len(self.steps):
            raise IndexError(f"Step {step_index} out of range")
        s = self.steps[step_index]
        args = [
            str(step_index),
            "1" if s.water_inlet  else "0",
            "1" if s.mash_inlet   else "0",
            "1" if s.boil_inlet   else "0",
            str(s.mash_temp),
            str(s.boil_temp),
            "1" if s.hop1 else "0",
            "1" if s.hop2 else "0",
            "1" if s.hop3 else "0",
            "1" if s.hop4 else "0",
            str(s.cool_valve),
            str(s.cool_inlet),
            "0",                          # reserved / always 0
            str(s.mash_pump),
            str(s.boil_pump),
            "0",                          # water intake (unknown)
            str(s.duration_s),
            str(s.step_type),
            str(s.step_mode),
            "1" if s.mash_return else "0",
            "1" if s.boil_return else "0",
        ]
        return " ".join(args)


# ── File I/O helpers ──────────────────────────────────────────────────────────

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def _safe_recipe_id(recipe_id: str) -> str:
    recipe_id = recipe_id.strip()
    if not _SAFE_ID_RE.fullmatch(recipe_id):
        raise ValueError("Invalid recipe id")
    return recipe_id


def _slug(name: str) -> str:
    slug = re.sub(r"[^\w-]", "_", name.lower()).strip("_")[:40]
    return slug or "recipe"


def _recipe_files(base: Path) -> Iterable[Path]:
    return sorted(p for p in base.glob("*.json") if p.is_file())


def _path_for(recipe_id: str, name: str = "") -> Path:
    base = settings.recipe_path.resolve()
    safe_id = _safe_recipe_id(recipe_id)
    # Try to find existing file by exact id suffix/prefix only.
    for f in _recipe_files(base):
        stem = f.stem
        if (
            stem == safe_id
            or stem.endswith(f"_{safe_id}")
            or stem.startswith(f"{safe_id}_")
        ):
            return f
    slug = _slug(name) if name else safe_id
    path = (base / f"{slug}_{safe_id}.json").resolve()
    if base != path.parent:
        raise ValueError("Invalid recipe path")
    return path


def list_recipes() -> list[Recipe]:
    out: list[Recipe] = []
    for p in _recipe_files(settings.recipe_path):
        try:
            out.append(Recipe.model_validate(json.loads(p.read_text())))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return out


def load_recipe(recipe_id: str) -> Optional[Recipe]:
    try:
        p = _path_for(recipe_id)
    except ValueError:
        return None
    if not p.exists():
        return None
    return Recipe.model_validate(json.loads(p.read_text()))


def save_recipe(recipe: Recipe) -> Path:
    p = _path_for(recipe.id, recipe.name)
    p.write_text(recipe.model_dump_json(indent=2), encoding="utf-8")
    return p


def delete_recipe(recipe_id: str) -> bool:
    try:
        p = _path_for(recipe_id)
    except ValueError:
        return False
    if p.exists():
        p.unlink()
        return True
    return False
