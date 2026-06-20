# Recipe

Source: `app/recipes.py`

## Description and Purpose

`Recipe` represents a complete brewing recipe or controller program. It includes user-facing metadata and a list of `RecipeStep` objects.

## Fields

- `id`: Safe stable identifier used in file names and API routes.
- `name`, `author`, `style`, `notes`: Display metadata.
- `batch_volume_l`: Volume used when building `P80`.
- `steps`: Controller steps.

## Methods

### `validate_id(value)`

Ensures ids contain only safe filename and URL characters.

### `to_p103_args(step_index)`

Converts a step into the argument payload for a `P103` command.

## Usage Example

```python
from app.recipes import load_recipe

recipe = load_recipe("demo-ipa1")
cmd = "P103 " + recipe.to_p103_args(0)
```

## Design Notes

Recipes and cleaning programs share the same controller-level structure so both can use the same safe start sequence: `P80`, queued `P103`, then `P200`.
