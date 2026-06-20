# RawRequest

Source: `app/routers/api.py`

## Description and Purpose

`RawRequest` validates Developer Mode raw command requests.

## Fields

- `raw`: Raw P-command string.

## Usage Example

```json
{ "raw": "P999" }
```

## Design Notes

Developer Mode intentionally exposes powerful command injection for troubleshooting. It should stay local-network only.
