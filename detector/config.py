"""Every BurnWatch threshold and weight.

`Params` holds the tile-engine constants. Its first ten fields are the HLS core's AXI-Lite registers, in
register order (docs/contracts.md sections 6 and 7), so tuning never needs a rebuild. The ranges checked
here are the register widths: a value that passes validation means the same thing on the ARM and in the PL.
`Params` is frozen; change a value with `dataclasses.replace(p, T_FLAG=30)`, which validates again.

The ARM-only constants for regions and the state machine (P3) go in a separate dataclass below `Params`,
so `Params` stays 1:1 with the HLS registers.

Q8 means fixed point with 8 fractional bits: a tile mean m is stored as m << 8.
"""
from dataclasses import dataclass, fields

SPEC_VERSION = 1

# Geometry (same values as tools/contracts.py; tests/test_golden.py checks they agree).
IMG_W, IMG_H = 1280, 720           # FULL-mode frame
TILES_X, TILES_Y = 80, 45
N_TILES = TILES_X * TILES_Y        # 3600
TILE_FULL = 16                     # FULL mode: 1280x720 input, 16x16-pixel tiles
TILE_FAST = 8                      # ARM-fast mode: rgb[::2, ::2] (640x360) input, 8x8-pixel tiles

# (min, max) for each register field; None = no upper bound (caller-side fields only).
_RANGES = {
    "K_SLOW": (1, 15), "K_FAST": (0, 15),
    "W_EDGE": (0, 255), "W_GREY": (0, 255),
    "SCORE_SHIFT": (0, 31), "T_FLAG": (0, 255), "SAT_MAX": (0, 255),
    "SAT_TOL": (0, 65535), "T_GLOBAL": (0, 65535), "GATE_TILES": (0, N_TILES),
    "UPDATE_EVERY_ARM": (1, None), "UPDATE_EVERY_PL": (1, None),
}


@dataclass(frozen=True)
class Params:
    """Tile-engine constants, in HLS register order. See detector/golden.py for how each one is used."""
    K_SLOW: int = 6             # baseline update shift on normal frames: b moves 1/64 of the way to x
    K_FAST: int = 0             # shift after a gated frame; 0 snaps b = x (contracts.md F7: re-baseline at once)
    W_EDGE: int = 4             # weight of edge_drop (Q8) in the raw score
    W_GREY: int = 4             # weight of grey_shift (Q8) in the raw score
    SCORE_SHIFT: int = 8        # raw = (W_EDGE*edge_drop + W_GREY*grey_shift) >> SCORE_SHIFT
    T_FLAG: int = 40            # a tile is flagged when score >= T_FLAG (score 0..255)
    SAT_MAX: int = 40           # tiles with mean saturation mS above this score 0 (plain units, not Q8)
    SAT_TOL: int = 4 << 8       # ... and so do tiles whose saturation rose more than this above baseline (Q8)
    T_GLOBAL: int = 24 << 8     # a tile counts as changed when |xY - bY| > T_GLOBAL (Q8)
    GATE_TILES: int = 1440      # the frame is gated when more than this many tiles changed (40 %)
    UPDATE_EVERY_ARM: int = 1   # caller side, not a register: baseline update on every Nth frame (~3 fps)
    UPDATE_EVERY_PL: int = 20   # caller side: same forgetting time in seconds at ~60 fps

    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            lo, hi = _RANGES[f.name]
            if not isinstance(v, int) or isinstance(v, bool):
                raise TypeError(f"{f.name}={v!r} must be an int")
            if v < lo or (hi is not None and v > hi):
                raise ValueError(f"{f.name}={v} out of range {lo}..{hi if hi is not None else 'inf'}")

    def registers(self):
        """The ten HLS register values in register order, keyed by the lowercase register name."""
        return {f.name.lower(): getattr(self, f.name) for f in fields(self) if f.name in REGISTER_FIELDS}


REGISTER_FIELDS = ("K_SLOW", "K_FAST", "W_EDGE", "W_GREY", "SCORE_SHIFT",
                   "T_FLAG", "SAT_MAX", "SAT_TOL", "T_GLOBAL", "GATE_TILES")


@dataclass(frozen=True)
class ArmParams:
    """ARM-only constants for detector/regions.py and detector/state.py (P3). Floats are fine: never in HW.

    The region mask uses Params.T_FLAG on the smoothed scores, so one threshold serves the PL and the ARM.
    """
    SMOOTH: float = 0.4             # s = (1 - SMOOTH)*s + SMOOTH*scores, per processed frame
    MIN_TILES: int = 4              # smallest 8-connected component kept as a region
    PERSIST_S: float = 6.0          # a region must last this long before it can be a candidate
    GROW_FRAC: float = 0.25         # ... and over that window grow by this fraction of its area,
    RISE_TILES: int = 1             # ... or move its top edge up by this many tiles,
    CENTROID_RISE: float = 0.0      # ... or move its centroid row up by more than this (tiles)
    UPLOAD_COOLDOWN_S: float = 120  # CLEAR -> SUSPECT at most once per this many seconds per camera
    VERDICT_TIMEOUT_S: float = 90   # SUSPECT with no verdict this long emits verdict_timeout (once)
    IGNORE_S: float = 180           # REJECTED: the region's tiles are ignored this long
    CLEAR_AFTER_S: float = 60       # CONFIRMED -> CLEAR once the region has been gone this long

    def __post_init__(self):
        if not 0 < self.SMOOTH <= 1:
            raise ValueError(f"SMOOTH={self.SMOOTH} must be in (0, 1]")
        for f in fields(self):
            if f.name != "SMOOTH" and getattr(self, f.name) < 0:
                raise ValueError(f"{f.name}={getattr(self, f.name)} must be >= 0")
