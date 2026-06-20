# CommandRequest

Source: `app/routers/api.py`

## Description and Purpose

`CommandRequest` validates low-level `/api/command` requests containing a single `cmd` string.

## Fields

- `cmd`: Non-empty command string such as `P999`.

## Usage Example

```json
{ "cmd": "P205 1" }
```

## Design Notes

This request model is for controlled API access to the same command path used by the UI.
