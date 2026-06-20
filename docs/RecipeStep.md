# RecipeStep

Source: `app/recipes.py`

## Description and Purpose

`RecipeStep` models one controller-level recipe or cleaning-program step. Its fields map closely to the 21 arguments used by Brewie `P103` commands.

## Fields

- Timing: `duration_s`
- Targets: `mash_temp`, `boil_temp`
- Inlets and valves: `water_inlet`, `mash_inlet`, `boil_inlet`, `cool_valve`, `cool_inlet`, returns
- Pumps: `mash_pump`, `boil_pump`
- Hop cages: `hop1` through `hop4`
- Firmware metadata: `step_type`, `step_mode`

## Usage Example

```python
from app.recipes import RecipeStep

step = RecipeStep(name="Fill", duration_s=600, water_inlet=True, mash_inlet=True)
```

## Design Notes

The model intentionally keeps firmware-specific integer and boolean fields visible. This makes imported stock Brewie recipes inspectable and editable without hiding important controller details.
