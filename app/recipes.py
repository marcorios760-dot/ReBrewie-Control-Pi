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
from typing import Any, Optional

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


class RecipeImportError(ValueError):
    """Raised when an uploaded recipe cannot be converted safely."""


def recipe_from_upload(data: dict[str, Any], filename: str = "") -> tuple[Recipe, str]:
    """Return a Recipe from either ReBrewie JSON or stock Brewie JSON."""
    if _looks_like_rebrewie_recipe(data):
        recipe = Recipe.model_validate(data)
        if not recipe.id:
            recipe.id = uuid.uuid4().hex[:8]
        return recipe, "rebrewie"

    if _looks_like_stock_brewie_recipe(data):
        return _stock_brewie_to_recipe(data, filename), "stock-brewie-json"

    raise RecipeImportError(
        "Unsupported recipe JSON. Expected ReBrewie fields or stock Brewie instructions/steps."
    )


def ensure_unique_recipe_id(recipe: Recipe) -> Recipe:
    """Assign a new id when the uploaded recipe would overwrite an existing file."""
    if load_recipe(recipe.id) is not None:
        recipe.id = uuid.uuid4().hex[:8]
    return recipe


def cleaning_program_from_upload(data: dict[str, Any], filename: str = "") -> tuple[Recipe, str]:
    """Convert an uploaded JSON file into a cleaning/maintenance program."""
    program, source_format = recipe_from_upload(data, filename)
    program.name = _cleaning_display_name(program.name, filename)
    program.author = program.author or "Brewie import"
    program.style = "Cleaning program"
    program.notes = _cleaning_program_notes(program)
    return program, source_format


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


def _looks_like_rebrewie_recipe(data: dict[str, Any]) -> bool:
    return "steps" in data and any(k in data for k in ("name", "batch_volume_l", "id"))


def _looks_like_stock_brewie_recipe(data: dict[str, Any]) -> bool:
    instructions = data.get("instructions")
    return isinstance(instructions, list) and all(
        isinstance(row, list) and len(row) >= 23 for row in instructions
    )


def _stock_brewie_to_recipe(data: dict[str, Any], filename: str) -> Recipe:
    instructions = data.get("instructions")
    if not isinstance(instructions, list):
        raise RecipeImportError("Stock Brewie recipe is missing instructions.")

    recipe_name = Path(filename).stem or "Imported Brewie Recipe"
    indexed_steps: list[tuple[int, RecipeStep]] = []

    for row_number, row in enumerate(instructions):
        if not isinstance(row, list) or len(row) < 23:
            raise RecipeImportError(f"Instruction {row_number} is not a valid Brewie row.")

        args = row[2:23]
        index = _int_arg(args[0], row_number)
        duration_s = _int_arg(args[16], 0)
        source_type = _int_arg(row[1], 0)
        indexed_steps.append(
            (
                index,
                RecipeStep(
                name=f"Imported step {index} (type {source_type})",
                duration_s=max(0, duration_s),
                mash_temp=_int_arg(args[4], 0),
                boil_temp=_int_arg(args[5], 0),
                water_inlet=_bool_arg(args[1]),
                mash_inlet=_bool_arg(args[2]),
                boil_inlet=_bool_arg(args[3]),
                hop1=_bool_arg(args[6]),
                hop2=_bool_arg(args[7]),
                hop3=_bool_arg(args[8]),
                hop4=_bool_arg(args[9]),
                cool_valve=_valve_arg(args[10]),
                cool_inlet=_valve_arg(args[11]),
                mash_pump=_valve_arg(args[13]),
                boil_pump=_valve_arg(args[14]),
                mash_return=_bool_arg(args[19]),
                boil_return=_bool_arg(args[20]),
                step_type=_int_arg(args[17], 1),
                step_mode=_int_arg(args[18], 0),
                ),
            ),
        )

    indexed_steps.sort(key=lambda item: item[0])
    steps = [step for _, step in indexed_steps]
    return Recipe(
        id=uuid.uuid4().hex[:8],
        name=recipe_name,
        author="Brewie import",
        style="Imported Brewie recipe",
        batch_volume_l=settings.to_liter,
        notes=_stock_recipe_notes(recipe_name, steps),
        steps=steps,
    )


def _stock_recipe_notes(recipe_name: str, steps: list[RecipeStep]) -> str:
    total_s = sum(max(0, step.duration_s) for step in steps)
    mash_temps = sorted({step.mash_temp / 10 for step in steps if step.mash_temp})
    boil_steps = sum(1 for step in steps if step.boil_temp or step.step_mode == 3)
    details: list[str] = [
        f"Imported Brewie recipe with {len(steps)} controller step(s)"
    ]
    if total_s:
        details.append(f"estimated runtime {_format_duration(total_s)}")
    if mash_temps:
        details.append(
            "mash targets " + ", ".join(f"{temp:g}C" for temp in mash_temps[:4])
        )
    if boil_steps:
        details.append(f"{boil_steps} boil-related step(s)")
    return "; ".join(details) + ". Review volume and step labels before brewing."


def _format_duration(seconds: int) -> str:
    minutes = max(0, int(round(seconds / 60)))
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} hr {mins} min"
    if hours:
        return f"{hours} hr"
    return f"{mins} min"


def _stock_instruction_durations(stock_steps: Any) -> dict[int, int]:
    durations: dict[int, int] = {}

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if not isinstance(node, dict):
            return
        refs = node.get("steps")
        time_value = node.get("time")
        if isinstance(refs, list) and all(isinstance(ref, int) for ref in refs):
            try:
                duration = int(round(float(time_value)))
            except (TypeError, ValueError):
                duration = 0
            for ref in refs:
                durations.setdefault(ref, duration)
        walk(refs)

    walk(stock_steps)
    return durations


def _int_arg(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _bool_arg(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _valve_arg(value: Any) -> int:
    if isinstance(value, bool):
        return 255 if value else 0
    return _int_arg(value, 0)


def _recipe_files(base: Path) -> Iterable[Path]:
    return sorted(p for p in base.glob("*.json") if p.is_file())


def _cleaning_path() -> Path:
    base = settings.recipe_path.parent / "cleaning_programs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _path_for(recipe_id: str, name: str = "") -> Path:
    base = settings.recipe_path.resolve()
    return _path_for_base(base, recipe_id, name)


def _path_for_cleaning_program(program_id: str, name: str = "") -> Path:
    base = _cleaning_path().resolve()
    return _path_for_base(base, program_id, name)


def _path_for_base(base: Path, recipe_id: str, name: str = "") -> Path:
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


def _cleaning_display_name(current_name: str, filename: str) -> str:
    raw = (Path(filename).stem or current_name or "").lower()
    if "short" in raw:
        return "Short Clean"
    if "full" in raw:
        return "Full Clean"
    if "sanit" in raw:
        return "Sanitizing Clean"
    return current_name or "Cleaning Program"


def _cleaning_program_notes(program: Recipe) -> str:
    runtime_s = _phase_runtime_estimate_s(program.steps)
    return (
        f"Maintenance cleaning program with {len(program.steps)} controller step(s)"
        f" and approx phase runtime {_format_duration(runtime_s)}. "
        "Use before or after brewing as appropriate."
    )


def _phase_runtime_estimate_s(steps: list[RecipeStep]) -> int:
    """Estimate wall-clock runtime without double-counting repeated phase rows."""
    total = 0
    previous: int | None = None
    for step in steps:
        duration = max(0, step.duration_s)
        if duration != previous:
            total += duration
            previous = duration
    return total


def list_recipes() -> list[Recipe]:
    out: list[Recipe] = []
    for p in _recipe_files(settings.recipe_path):
        try:
            out.append(Recipe.model_validate(json.loads(p.read_text())))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return out


def list_cleaning_programs() -> list[Recipe]:
    out: list[Recipe] = []
    for p in _recipe_files(_cleaning_path()):
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


def load_cleaning_program(program_id: str) -> Optional[Recipe]:
    try:
        p = _path_for_cleaning_program(program_id)
    except ValueError:
        return None
    if not p.exists():
        return None
    return Recipe.model_validate(json.loads(p.read_text()))


def save_recipe(recipe: Recipe) -> Path:
    p = _path_for(recipe.id, recipe.name)
    p.write_text(recipe.model_dump_json(indent=2), encoding="utf-8")
    return p


def save_cleaning_program(program: Recipe) -> Path:
    if load_cleaning_program(program.id) is not None:
        program.id = uuid.uuid4().hex[:8]
    p = _path_for_cleaning_program(program.id, program.name)
    p.write_text(program.model_dump_json(indent=2), encoding="utf-8")
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
