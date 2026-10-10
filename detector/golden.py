"""Integer reference of the PL tile engine. THIS FILE IS THE SPEC (spec v1).

The HLS core in hls/ must match it bit for bit in FULL mode. Integer numpy only (uint8 / int32), no floats
anywhere in the scoring path. Any change here means regenerating the HLS test vectors (tools/dump_golden.py).

A frame is cut into a 45 x 80 grid of tiles. Each tile gets a smoke score 0..255 from how far it has moved,
against a slow per-tile baseline, towards "smoke": edges fading (texture behind smoke blurs) and brightness
moving towards mid-grey, while staying unsaturated (smoke is grey; red cloth and lights are not).

Modes (same 45 x 80 grid either way):
  FULL      rgb [720, 1280, 3], TILE = 16  (the PL, and the reference for it)
  ARM-fast  rgb[::2, ::2] -> [360, 640, 3], TILE = 8  (the caller decimates)

Notation: >> is an arithmetic right shift (numpy int32 >> is arithmetic). Q8 = value << 8.
"""
import numpy as np

from detector.config import N_TILES, TILES_X, TILES_Y, Params

MID_GREY_Q8 = 128 << 8


def pixel_features(rgb):
    """Per-pixel luma Y, saturation S and edge strength E, each int32 [H, W] in 0..255.

    Y = (77*R + 150*G + 29*B) >> 8
    S = max(R, G, B) - min(R, G, B)
    E = (|Gx| + |Gy|) >> 3 with the 3x3 Sobel on Y, for interior pixels (r, c):
        Gx = (Y[r-1,c+1] + 2*Y[r,c+1] + Y[r+1,c+1]) - (Y[r-1,c-1] + 2*Y[r,c-1] + Y[r+1,c-1])
        Gy = (Y[r+1,c-1] + 2*Y[r+1,c] + Y[r+1,c+1]) - (Y[r-1,c-1] + 2*Y[r-1,c] + Y[r-1,c+1])
    E = 0 on the 1-pixel image border (first/last row and column).
    """
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)
    Y = (77 * r + 150 * g + 29 * b) >> 8
    S = rgb.max(axis=2).astype(np.int32) - rgb.min(axis=2).astype(np.int32)

    # Neighbour views for the interior pixels [1:-1, 1:-1]: u/m/d = row above/same/below, l/c/r = column.
    ul, uc, ur = Y[:-2, :-2], Y[:-2, 1:-1], Y[:-2, 2:]
    ml, mr = Y[1:-1, :-2], Y[1:-1, 2:]
    dl, dc, dr = Y[2:, :-2], Y[2:, 1:-1], Y[2:, 2:]
    gx = (ur + 2 * mr + dr) - (ul + 2 * ml + dl)
    gy = (dl + 2 * dc + dr) - (ul + 2 * uc + ur)
    E = np.zeros_like(Y)
    E[1:-1, 1:-1] = (np.abs(gx) + np.abs(gy)) >> 3
    return Y, S, E


def tile_means(a, tile):
    """Mean of each tile of an int32 [45*tile, 80*tile] array, rounded down: sum(a) >> log2(tile*tile).

    Returns int32 [45, 80]. tile is a power of two, so the division is exact as a shift.
    """
    log2n = 2 * (tile.bit_length() - 1)
    s = a.reshape(TILES_Y, tile, TILES_X, tile).sum(axis=(1, 3), dtype=np.int32)
    return s >> log2n


def tile_features(rgb, tile):
    """Tile means of E, Y and S: (mE, mY, mS), int32 [45, 80], each 0..255 (not Q8)."""
    Y, S, E = pixel_features(rgb)
    return tile_means(E, tile), tile_means(Y, tile), tile_means(S, tile)


def score_tiles(p, xE, xY, xS, mS, bE, bY, bS):
    """Per-tile score (uint8 [45, 80]) and the changed-tile count, from Q8 features x and baselines b.

    edge_drop  = max(0, bE - xE)                                   edges faded since the baseline
    grey_shift = max(0, |bY - 128<<8| - |xY - 128<<8|)             brightness moved towards mid-grey
    sat_ok     = (mS <= SAT_MAX) and (xS <= bS + SAT_TOL)          still grey, and not more colourful than before
    raw        = (W_EDGE*edge_drop + W_GREY*grey_shift) >> SCORE_SHIFT
    score      = min(raw, 255) if sat_ok else 0
    changed    = number of tiles with |xY - bY| > T_GLOBAL
    All intermediates fit int32 for every Params value that validates (contracts.md section 6).
    """
    edge_drop = np.maximum(0, bE - xE)
    grey_shift = np.maximum(0, np.abs(bY - MID_GREY_Q8) - np.abs(xY - MID_GREY_Q8))
    sat_ok = (mS <= p.SAT_MAX) & (xS <= bS + p.SAT_TOL)
    raw = (p.W_EDGE * edge_drop + p.W_GREY * grey_shift) >> p.SCORE_SHIFT
    scores = np.where(sat_ok, np.minimum(raw, 255), 0).astype(np.uint8)
    changed = int(np.count_nonzero(np.abs(xY - bY) > p.T_GLOBAL))
    return scores, changed


def update_baseline(b, x, k, mask):
    """b += (x - b + ((1 << k) >> 1)) >> k on the tiles in mask, in place. Rounds half up; b stays in 0..65280.

    The rounding term (1 << k) >> 1 is 1 << (k-1) for k >= 1, and 0 for k = 0, where the update snaps b = x
    (K_FAST = 0, docs/contracts.md F7).
    """
    delta = (x - b + ((1 << k) >> 1)) >> k
    b += np.where(mask, delta, 0)


class TileEngine:
    """The tile engine with its state carried between frames.

    State: baselines bE, bY, bS (int32 [45, 80], Q8, 0..65280; uint16 in HW) and prev_gate (the previous
    frame's gate). A new engine starts with a reset pending.

    step(rgb, update_this_frame), in order:
      1. xE, xY, xS = tile means << 8.
      2. Reset frame (docs/contracts.md F4): if a reset is pending, b = x for all three features first, so
         the frame scores 0 with changed = 0 and gate = False, whatever state was left over.
      3. Score every tile (score_tiles). flagged = score >= T_FLAG. gate = changed > GATE_TILES.
      4. Baseline update, unless this was a reset frame:
           if update_this_frame:
               k = K_FAST if prev_gate else K_SLOW
               on tiles where (prev_gate or not flagged): b += (x - b + ((1 << k) >> 1)) >> k
         Flagged tiles are frozen so smoke isn't absorbed into the baseline. After a gated frame (a global
         change: lights, exposure, camera bump) every tile re-baselines with K_FAST; the default 0 snaps b = x,
         because a partial re-baseline can leave the whole frame flagged and frozen for good (F7).
      5. prev_gate = gate.
    The caller decides update_this_frame (frame_no % UPDATE_EVERY == 0), ignores gated frames, and calls
    reset() when a verdict says REJECTED (F7). Known limitation: anything in view at a reset frame that later
    moves away leaves a "ghost" of frozen flagged tiles if the background is nearer mid-grey than it was.
    """

    def __init__(self, params=None, tile=16):
        if tile not in (8, 16):
            raise ValueError("tile must be 16 (FULL) or 8 (ARM-fast)")
        self.p = params if params is not None else Params()
        self.tile = tile
        self.shape = (TILES_Y * tile, TILES_X * tile, 3)
        self.bE = np.zeros((TILES_Y, TILES_X), np.int32)
        self.bY = np.zeros((TILES_Y, TILES_X), np.int32)
        self.bS = np.zeros((TILES_Y, TILES_X), np.int32)
        self.prev_gate = False
        self.reset_pending = True

    def reset(self):
        """Make the next step() a reset frame."""
        self.reset_pending = True

    def step(self, rgb, update_this_frame=True):
        """Score one frame. Returns (scores uint8 [45, 80], gate bool, changed int 0..3600)."""
        if rgb.shape != self.shape or rgb.dtype != np.uint8:
            raise ValueError(f"rgb must be uint8 {self.shape}, got {rgb.dtype} {rgb.shape}")
        p = self.p
        mE, mY, mS = tile_features(rgb, self.tile)
        xE, xY, xS = mE << 8, mY << 8, mS << 8

        reset = self.reset_pending
        if reset:
            self.bE, self.bY, self.bS = xE.copy(), xY.copy(), xS.copy()
            self.reset_pending = False

        scores, changed = score_tiles(p, xE, xY, xS, mS, self.bE, self.bY, self.bS)
        gate = changed > p.GATE_TILES

        if not reset and update_this_frame:
            k = p.K_FAST if self.prev_gate else p.K_SLOW
            mask = self.prev_gate | (scores < p.T_FLAG)
            update_baseline(self.bE, xE, k, mask)
            update_baseline(self.bY, xY, k, mask)
            update_baseline(self.bS, xS, k, mask)
        self.prev_gate = gate
        return scores, gate, changed

    def state_bytes(self):
        """State as in the test vectors: bE, bY, bS as 3 x 3600 uint16 LE, then 1 byte prev_gate (21,601 bytes)."""
        b = np.stack([self.bE, self.bY, self.bS]).reshape(3, N_TILES).astype("<u2")
        return b.tobytes() + bytes([int(self.prev_gate)])
