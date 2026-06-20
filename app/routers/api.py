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

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from ..config import settings, COMMAND_MAP
from ..state import brew_state
from ..parser import refresh_state_from_last_raw
from ..recipes import (
    RecipeImportError,
    Recipe,
    cleaning_program_from_upload,
    ensure_unique_recipe_id,
    list_cleaning_programs, list_recipes,
    load_cleaning_program, load_recipe,
    save_cleaning_program, save_recipe, delete_recipe,
    recipe_from_upload,
)

router = APIRouter(prefix="/api")

STARTUP_COMMAND_DELAY_S = 0.12


# ── Transport accessor ────────────────────────────────────────────────────────

def _transport(request: Request):
    transport = getattr(request.app.state, "transport", None)
    if transport is None:
        raise HTTPException(503, "Transport not initialised")
    return transport


async def _send_and_record(transport: Any, cmd: str, *, delay: float = 0.0) -> None:
    await transport.send(cmd)
    brew_state.apply_sent_command(cmd)
    if delay > 0:
        await asyncio.sleep(delay)


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
    brew_state.apply_sent_command(cmd)
    return {"sent": cmd, "ts": time.time()}


# ── Brew control ──────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    recipe_id: str | None = None


async def _start_program(program: Recipe, request: Request, label: str) -> None:
    transport = _transport(request)
    init_cmd = settings.build_p80_command(program.batch_volume_l)
    await _send_and_record(transport, init_cmd, delay=STARTUP_COMMAND_DELAY_S)

    for i in range(min(2, len(program.steps))):
        step_args = program.to_p103_args(i)
        step_cmd = f"P103 {step_args}"
        await _send_and_record(transport, step_cmd, delay=STARTUP_COMMAND_DELAY_S)

    run_cmd = COMMAND_MAP["brew_run"]
    await _send_and_record(transport, run_cmd)

    brew_state.status = "brewing"
    brew_state.current_step = 0
    brew_state.step_elapsed_s = 0
    brew_state.active_recipe = f"{label}: {program.name}"
    brew_state.active_recipe_id = program.id
    brew_state.total_steps = len(program.steps)
    if program.steps:
        brew_state.step_name = program.steps[0].name or "Step 1"
        brew_state.step_duration_s = program.steps[0].duration_s
    else:
        brew_state.step_name = label
        brew_state.step_duration_s = 0
    brew_state.add_log(f"{label} started. Program: {program.name}")


@router.post("/control/start")
async def control_start(body: StartRequest, request: Request) -> dict:
    recipe: Recipe | None = None
    if body.recipe_id:
        recipe = load_recipe(body.recipe_id)
        if not recipe:
            raise HTTPException(404, f"Recipe {body.recipe_id!r} not found")

    if brew_state.status == "brewing":
        raise HTTPException(409, "Already brewing")

    # Send the startup commands BEFORE mutating brew_state.  If any send
    # raises (TransportError -> 503), status is left unchanged so the UI
    # never claims "brewing" when the machine never actually received P80.
    if recipe and recipe.steps:
        await _start_program(recipe, request, "Brew")
    else:
        transport = _transport(request)
        init_cmd = settings.build_p80_command()
        await _send_and_record(transport, init_cmd)
        brew_state.status = "brewing"
        brew_state.current_step = 0
        brew_state.step_elapsed_s = 0
        brew_state.active_recipe = None
        brew_state.active_recipe_id = None
        brew_state.total_steps = 0
        brew_state.step_name = "Manual"
        brew_state.step_duration_s = 0
        brew_state.add_log("Brew started. Recipe: none")

    return {"status": brew_state.status}


@router.post("/control/pause")
async def control_pause(request: Request) -> dict:
    transport = _transport(request)
    if brew_state.status != "brewing":
        raise HTTPException(409, "Not currently brewing")
    # Send the safety-critical command BEFORE updating state.  If this raises
    # (TransportError -> 503), brew_state.status is left unchanged so the UI
    # never claims "paused" while the valves may still be open.
    close_cmd = COMMAND_MAP["close_all_valves"]
    await transport.send(close_cmd)
    brew_state.apply_sent_command(close_cmd)
    brew_state.status = "paused"
    brew_state.add_log("Brew paused")
    return {"status": brew_state.status}


@router.post("/control/resume")
async def control_resume(request: Request) -> dict:
    transport = _transport(request)
    if brew_state.status != "paused":
        raise HTTPException(409, "Not paused")

    # Re-initialise the machine (P80 wakes up the IO board after a valve-close pause).
    # Sent BEFORE flipping status so a failed send (TransportError -> 503)
    # leaves brew_state.status as "paused" — accurate, since the machine
    # never actually received the resume command.
    init_cmd = settings.build_p80_command()
    await _send_and_record(transport, init_cmd, delay=STARTUP_COMMAND_DELAY_S)

    # Re-enqueue the current step so the firmware picks up where it left off.
    requeued_step: int | None = None
    if brew_state.active_recipe_id:
        recipe = load_recipe(brew_state.active_recipe_id)
        if recipe and 0 <= brew_state.current_step < len(recipe.steps):
            step_args = recipe.to_p103_args(brew_state.current_step)
            step_cmd = f"P103 {step_args}"
            await _send_and_record(transport, step_cmd, delay=STARTUP_COMMAND_DELAY_S)
            requeued_step = brew_state.current_step

    run_cmd = COMMAND_MAP["brew_run"]
    await _send_and_record(transport, run_cmd)

    brew_state.status = "brewing"
    if requeued_step is not None:
        brew_state.add_log(f"Brew resumed – re-queued step {requeued_step}")
    elif brew_state.active_recipe_id:
        brew_state.add_log("Brew resumed (no step re-queued – recipe unavailable)")
    else:
        brew_state.add_log("Brew resumed (manual mode – re-queue steps as needed)")

    return {"status": brew_state.status}


@router.post("/control/stop")
async def control_stop(request: Request) -> dict:
    transport = _transport(request)
    # Send all shutdown commands BEFORE updating state.  If any of these
    # raises (TransportError -> 503), the exception propagates and brew_state
    # is left unchanged — the UI must never report "stopped" when the
    # valves/pumps/heater may not actually have received the command.
    shutdown_commands = (
        COMMAND_MAP["close_all_valves"],
        COMMAND_MAP["mash_pump_stop"],
        COMMAND_MAP["boil_pump_stop"],
        "P150 0",
        "P151 0",
    )
    for cmd in shutdown_commands:
        await transport.send(cmd)
        brew_state.apply_sent_command(cmd)

    brew_state.clear_brew_progress()
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
    cmd = f"P103 {args}"
    await transport.send(cmd)
    brew_state.apply_sent_command(cmd)
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
    brew_state.apply_sent_command(cmd)
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


@router.post("/recipes/upload", status_code=201)
async def api_upload_recipe(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "recipe.json"
    if not filename.lower().endswith(".json"):
        raise HTTPException(400, "Only .json recipe uploads are currently supported")

    raw = await file.read()
    if len(raw) > 1024 * 1024:
        raise HTTPException(400, "Recipe file is too large")

    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Recipe file is not valid JSON") from exc

    if not isinstance(data, dict):
        raise HTTPException(400, "Recipe JSON must be an object")

    try:
        recipe, source_format = recipe_from_upload(data, filename)
        recipe = ensure_unique_recipe_id(recipe)
        path = save_recipe(recipe)
    except (RecipeImportError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "id": recipe.id,
        "name": recipe.name,
        "steps": len(recipe.steps),
        "source_format": source_format,
        "path": str(path),
    }


@router.get("/cleaning")
async def api_list_cleaning_programs() -> dict:
    programs = list_cleaning_programs()
    return {"programs": [p.model_dump() for p in programs]}


@router.post("/cleaning/upload", status_code=201)
async def api_upload_cleaning_program(file: UploadFile = File(...)) -> dict:
    filename = file.filename or "cleaning-program.json"
    if not filename.lower().endswith(".json"):
        raise HTTPException(400, "Only .json cleaning program uploads are currently supported")

    raw = await file.read()
    if len(raw) > 1024 * 1024:
        raise HTTPException(400, "Cleaning program file is too large")

    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Cleaning program file is not valid JSON") from exc

    if not isinstance(data, dict):
        raise HTTPException(400, "Cleaning program JSON must be an object")

    try:
        program, source_format = cleaning_program_from_upload(data, filename)
        path = save_cleaning_program(program)
    except (RecipeImportError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "id": program.id,
        "name": program.name,
        "steps": len(program.steps),
        "source_format": source_format,
        "path": str(path),
    }


@router.post("/cleaning/{program_id}/start")
async def api_start_cleaning_program(program_id: str, request: Request) -> dict:
    if brew_state.status == "brewing":
        raise HTTPException(409, "Already running a program")

    program = load_cleaning_program(program_id)
    if not program:
        raise HTTPException(404, "Cleaning program not found")
    if not program.steps:
        raise HTTPException(400, "Cleaning program has no steps")

    await _start_program(program, request, "Cleaning")
    return {"status": brew_state.status, "program": program.name}


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
