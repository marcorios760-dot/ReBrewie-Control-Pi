# StartRequest

Source: `app/routers/api.py`

## Description and Purpose

`StartRequest` carries an optional recipe id for `/api/control/start`.

## Fields

- `recipe_id`: Optional id of the recipe to start. If omitted, manual mode is initialized.

## Usage Example

```json
{ "recipe_id": "demo-ipa1" }
```

## Design Notes

The endpoint sends startup commands before mutating UI state so the app does not claim brewing if the machine did not receive initialization.
