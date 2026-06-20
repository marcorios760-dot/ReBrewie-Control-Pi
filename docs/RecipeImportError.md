# RecipeImportError

Source: `app/recipes.py`

## Description and Purpose

`RecipeImportError` is raised when an uploaded recipe or cleaning program cannot be safely parsed or converted.

## Usage Example

```python
from app.recipes import RecipeImportError, recipe_from_upload

try:
    recipe, source = recipe_from_upload(data, "recipe.json")
except RecipeImportError as exc:
    print(f"Import failed: {exc}")
```

## Design Notes

Using a specific exception type lets API routes return user-friendly `400 Bad Request` messages while allowing unexpected errors to surface normally during development.
