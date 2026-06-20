# StepRequest

Source: `app/routers/api.py`

## Description and Purpose

`StepRequest` identifies a recipe and step index to enqueue manually.

## Fields

- `recipe_id`: Recipe identifier.
- `step_index`: Zero-based step index.

## Usage Example

```json
{ "recipe_id": "demo-ipa1", "step_index": 2 }
```

## Design Notes

Manual enqueue is useful for advanced testing but should be used carefully with physical hardware.
