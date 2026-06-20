"""
app/routers/pages.py – HTML page routes rendered with Jinja2.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from ..state import brew_state
from ..recipes import list_cleaning_programs, list_recipes
from ..config import settings, COMMAND_MAP

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "state": brew_state,
            "transport": settings.brewie_transport,
        },
    )


@router.get("/progress", response_class=HTMLResponse)
async def page_progress(request: Request):
    return templates.TemplateResponse(
        "progress.html",
        {"request": request, "state": brew_state},
    )


@router.get("/preparation", response_class=HTMLResponse)
async def page_preparation(request: Request):
    return templates.TemplateResponse(
        "preparation.html",
        {"request": request, "state": brew_state, "commands": COMMAND_MAP},
    )


@router.get("/cleaning", response_class=HTMLResponse)
async def page_cleaning(request: Request):
    programs = list_cleaning_programs()
    return templates.TemplateResponse(
        "cleaning.html",
        {"request": request, "programs": programs, "state": brew_state},
    )


@router.get("/developer", response_class=HTMLResponse)
async def page_developer(request: Request):
    return templates.TemplateResponse(
        "developer.html",
        {"request": request, "state": brew_state, "commands": COMMAND_MAP},
    )


@router.get("/recipes", response_class=HTMLResponse)
async def page_recipes(request: Request):
    recipes = list_recipes()
    return templates.TemplateResponse(
        "recipes.html",
        {"request": request, "recipes": recipes, "state": brew_state},
    )


@router.get("/recipes/new", response_class=HTMLResponse)
async def page_recipe_new(request: Request):
    return templates.TemplateResponse(
        "recipe_editor.html",
        {"request": request, "recipe": None, "recipe_data": None, "state": brew_state},
    )


@router.get("/recipes/{recipe_id}/edit", response_class=HTMLResponse)
async def page_recipe_edit(recipe_id: str, request: Request):
    from ..recipes import load_recipe
    recipe = load_recipe(recipe_id)
    recipe_data = recipe.model_dump() if recipe else None
    return templates.TemplateResponse(
        "recipe_editor.html",
        {
            "request": request,
            "recipe": recipe,
            "recipe_data": recipe_data,
            "state": brew_state,
        },
    )
