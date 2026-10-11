# detector/

The integer reference model for the tile scoring core. The implemented detector code is a laptop/reference component; the planned ARM region/state runtime is not present in this checkout.

| File | Current role |
|---|---|
| `config.py` | Frozen `Params` dataclass, geometry, register defaults and range validation |
| `golden.py` | **The specification:** integer pixel features, tile means, score/gate logic, baseline updates and serialized state |
| `__init__.py` | Package marker; it does not provide the planned region/state modules yet |

`golden.py` supports:

- FULL mode: `uint8[720, 1280, 3]`, 16×16 tiles;
- ARM-fast reference mode: caller decimates to `uint8[360, 640, 3]`, 8×8 tiles;
- the same 45×80 score grid in both modes;
- reset-before-score semantics;
- `K_FAST = 0` snap re-baselining after a gated frame;
- flagged-tile baseline freeze;
- deterministic Q8 baseline state for RTL/vector comparison.

Planned but absent from this checkout:

- `regions.py` for temporal connected-component tracking;
- `state.py` for CLEAR/SUSPECT/CONFIRMED/REJECTED transitions;
- a PYNQ driver that swaps the reference engine for a live PL engine.
