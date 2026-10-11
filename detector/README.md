# detector/

The integer reference model for the tile scoring core, plus the ARM-side region tracker and alert state machine that turn its scores into events. The device loop that runs them on the PYNQ is not written yet.

| File | Current role |
|---|---|
| `config.py` | Frozen `Params` dataclass (the HLS registers), geometry, range validation, and `ArmParams` for regions/state |
| `golden.py` | **The specification:** integer pixel features, tile means, score/gate logic, baseline updates and serialized state |
| `regions.py` | `RegionTracker`: smooths scores, keeps the largest 8-connected flagged component, tracks it, and reports a candidate when it persists and rises or spreads |
| `state.py` | `StateMachine`: CLEAR / SUSPECT / CONFIRMED / REJECTED; returns actions (upload, ignore, rebaseline, verdict_timeout) and never executes them |
| `__init__.py` | Package marker |

`golden.py` supports:

- FULL mode: `uint8[720, 1280, 3]`, 16×16 tiles;
- ARM-fast reference mode: caller decimates to `uint8[360, 640, 3]`, 8×8 tiles;
- the same 45×80 score grid in both modes;
- reset-before-score semantics;
- `K_FAST = 0` snap re-baselining after a gated frame;
- flagged-tile baseline freeze;
- deterministic Q8 baseline state for RTL/vector comparison.

`regions.py` and `state.py` use floats; they never go to hardware. Time is always passed in, so tests drive them with a fake clock.

Planned but absent from this checkout: a PYNQ driver that swaps the reference engine for a live PL engine, and the device loop that runs all three.
