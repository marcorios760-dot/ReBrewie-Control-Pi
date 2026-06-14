"""
app/routers/api.py – REST API endpoints.

Endpoints:
  GET  /api/status          – current BrewState (JSON)
  GET  /api/log             – last N log lines
  POST /api/command         – send a raw command string
  POST /api/control/start   – start brew with a recipe
  POST /api/control/pause   – pause
  POST /api/control/resume  – resume
  POST /api/control/stop    – stop / abort
  POST /api/control/step    – enqueue next step manually
  POST /api/developer/raw   – send any raw P-command (developer mode)
  GET  /api/recipes         – list recipes
  POST /api/recipes         – create recipe
  GET  /api/recipes/{id}    – get recipe
  PUT  /api/recipes/{id}    – update recipe
  DELETE /api/recipes/{id}  – delete recipe
"""
from __future__ import annotations

import time
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import settings, COMMAND_MAP
from ..state import brew_state
from ..parser import refresh_state_from_last_raw
from ..recipes import (
    Recipe,
    list_recipes, load_recipe, save_recipe, delete_recipe,
)

router = APIRouter(prefix="/api")


def _refresh_state_from_last_raw() -> None:
    """Refresh parsed fields without requiring newer parser symbols at import time."""
    refresh = getattr(brew_parser, "refresh_state_from_last_raw", None)
    if callable(refresh):
        refresh()
        return
    if brew_state.last_raw:
        brew_parser.parse_line(brew_state.last_raw)


# ── Transport accessor ────────────────────────────────────────────────────────

def _transport(request: Request):
    transport = getattr(request.app.state, "transport", None)
    if transport is None:
        raise HTTPException(503, "Transport not initialised")
    return transport


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_status() -> dict:
    refresh_state_from_last_raw()
    return brew_state.to_dict()


@router.get("/log")
async def get_log(n: int = 100) -> dict:
    n = max(1, min(n, 200))
    return {"log": brew_state.log[-n:]}


# ── Low-level command ─────────────────────────────────────────────────────────

class CommandRequest(BaseModel):
    cmd: str = Field(min_length=1)


@router.post("/command")
async def send_command(body: CommandRequest, request: Request) -> dict:
    transport = _transport(request)
    cmd = body.cmd.strip()
    if not cmd:
        raise HTTPException(400, "Empty command")
    await transport.send(cmd)
    return {"sent": cmd, "ts": time.time()}


# ── Brew control ──────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    recipe_id: str | None = None


@router.post("/control/start")
async def control_start(body: StartRequest, request: Request) -> dict:
    transport = _transport(request)

    recipe: Recipe | None = None
    if body.recipe_id:
        recipe = load_recipe(body.recipe_id)
        if not recipe:
            raise HTTPException(404, f"Recipe {body.recipe_id!r} not found")

    if brew_state.status == "brewing":
        raise HTTPException(409, "Already brewing")

    brew_state.status = "brewing"
    brew_state.current_step = 0
    brew_state.step_elapsed_s = 0
    brew_state.active_recipe = recipe.id if recipe else None

    if recipe and recipe.steps:
        brew_state.total_steps = len(recipe.steps)
        brew_state.step_name = recipe.steps[0].name or "Step 1"
        brew_state.step_duration_s = recipe.steps[0].duration_s

        # Send P80 initialise
        init_cmd = (
            f"P80 {recipe.batch_volume_l:.1f} 0 "
            f"{settings.mash_temp_delta:.5f} {settings.boil_temp_delta:.5f}"
        )
        await transport.send(init_cmd)

        # Enqueue first two steps (firmware expects two ahead)
        for i in range(min(2, len(recipe.steps))):
            step_args = recipe.to_p103_args(i)
            await transport.send(f"P103 {step_args}")
    else:
        brew_state.total_steps = 0
        brew_state.step_name = "Manual"
        brew_state.step_duration_s = 0
        await transport.send(
            f"P80 {settings.to_liter:.1f} 0 "
            f"{settings.mash_temp_delta:.5f} {settings.boil_temp_delta:.5f}"
        )

    recipe_label = (recipe.name if recipe else None) or "none"
    brew_state.add_log(f"Brew started. Recipe: {recipe_label}")
    return {"status": brew_state.status}


@router.post("/control/pause")
async def control_pause(request: Request) -> dict:
    transport = _transport(request)
    if brew_state.status != "brewing":
        raise HTTPException(409, "Not currently brewing")
    brew_state.status = "paused"
    # P999 closes all valves as a safe pause action
    await transport.send(COMMAND_MAP["close_all_valves"])
    brew_state.add_log("Brew paused")
    return {"status": brew_state.status}


@router.post("/control/resume")
async def control_resume(request: Request) -> dict:
    transport = _transport(request)
    if brew_state.status != "paused":
        raise HTTPException(409, "Not paused")

    recipe = load_recipe(brew_state.active_recipe) if brew_state.active_recipe else None
    volume = recipe.batch_volume_l if recipe else settings.to_liter
    await transport.send(
        f"P80 {volume:.1f} 0 "
        f"{settings.mash_temp_delta:.5f} {settings.boil_temp_delta:.5f}"
    )

    if recipe and recipe.steps:
        start_index = max(0, min(brew_state.current_step, len(recipe.steps) - 1))
        for i in range(start_index, min(start_index + 2, len(recipe.steps))):
            await transport.send(f"P103 {recipe.to_p103_args(i)}")

    brew_state.status = "brewing"
    brew_state.add_log("Brew resumed and command queue refreshed")
    return {"status": brew_state.status}


@router.post("/control/stop")
async def control_stop(request: Request) -> dict:
    transport = _transport(request)
    brew_state.status = "idle"
    brew_state.active_recipe = None
    await transport.send(COMMAND_MAP["close_all_valves"])
    await transport.send(COMMAND_MAP["mash_pump_stop"])
    await transport.send(COMMAND_MAP["boil_pump_stop"])
    await transport.send("P150 0")   # heater off
    await transport.send("P151 0")
    brew_state.add_log("Brew stopped / aborted")
    return {"status": brew_state.status}


class StepRequest(BaseModel):
    recipe_id: str
    step_index: int = Field(ge=0)


@router.post("/control/step")
async def control_step(body: StepRequest, request: Request) -> dict:
    transport = _transport(request)
    recipe = load_recipe(body.recipe_id)
    if not recipe:
        raise HTTPException(404, "Recipe not found")
    try:
        args = recipe.to_p103_args(body.step_index)
    except IndexError as exc:
        raise HTTPException(400, "Step index out of range") from exc
    await transport.send(f"P103 {args}")
    brew_state.add_log(f"Enqueued step {body.step_index}")
    return {"enqueued": body.step_index}


# ── Developer mode ────────────────────────────────────────────────────────────

class RawRequest(BaseModel):
    raw: str


@router.post("/developer/raw")
async def developer_raw(body: RawRequest, request: Request) -> dict:
    transport = _transport(request)
    cmd = body.raw.strip()
    if not cmd:
        raise HTTPException(400, "Empty command")
    await transport.send(cmd)
    return {"sent": cmd, "ts": time.time()}


@router.get("/developer/commands")
async def developer_commands() -> dict:
    return {"commands": COMMAND_MAP}


# ── Recipes ───────────────────────────────────────────────────────────────────

@router.get("/recipes")
async def api_list_recipes() -> dict:
    recipes = list_recipes()
    return {"recipes": [r.model_dump() for r in recipes]}


@router.post("/recipes", status_code=201)
async def api_create_recipe(recipe: Recipe) -> dict:
    path = save_recipe(recipe)
    return {"id": recipe.id, "path": str(path)}


@router.get("/recipes/{recipe_id}")
async def api_get_recipe(recipe_id: str) -> dict:
    r = load_recipe(recipe_id)
    if not r:
        raise HTTPException(404, "Recipe not found")
    return r.model_dump()


@router.put("/recipes/{recipe_id}")
async def api_update_recipe(recipe_id: str, recipe: Recipe) -> dict:
    recipe.id = recipe_id
    path = save_recipe(recipe)
    return {"id": recipe.id, "path": str(path)}


@router.delete("/recipes/{recipe_id}")
async def api_delete_recipe(recipe_id: str) -> dict:
    ok = delete_recipe(recipe_id)
    if not ok:
        raise HTTPException(404, "Recipe not found")
    return {"deleted": recipe_id}
