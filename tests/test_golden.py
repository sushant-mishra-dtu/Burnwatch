"""Tests for detector/golden.py (spec v1) on synthetic frames only.

Scenario frames may use floats and cv2; only the scoring path under test must be integer.
`python tests/test_golden.py` renders the test-1 heat map to docs/golden_test1.png.
"""
import dataclasses
import os
import sys

import cv2
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from detector import config  # noqa: E402
from detector.config import Params  # noqa: E402
from detector.golden import TileEngine, pixel_features, update_baseline  # noqa: E402
from tools import contracts  # noqa: E402

H, W, T = 720, 1280, 16
P = Params()

# Tile boxes (ty0, ty1, tx0, tx1), end-exclusive.
SMOKE_BOX = (10, 20, 30, 46)
DARK_BOX = (20, 27, 10, 21)
RED_BOX = (25, 33, 50, 62)


def px(box):
    ty0, ty1, tx0, tx1 = box
    return slice(ty0 * T, ty1 * T), slice(tx0 * T, tx1 * T)


def tile_mask(box, shrink=0):
    """Bool [45, 80], True inside box shrunk by `shrink` tiles on every side."""
    ty0, ty1, tx0, tx1 = box
    m = np.zeros((45, 80), bool)
    m[ty0 + shrink:ty1 - shrink, tx0 + shrink:tx1 - shrink] = True
    return m


def far_mask(box, margin=2):
    """Bool [45, 80], True at least `margin` tiles away from box."""
    ty0, ty1, tx0, tx1 = box
    m = np.ones((45, 80), bool)
    m[max(0, ty0 - margin):ty1 + margin, max(0, tx0 - margin):tx1 + margin] = False
    return m


def textured_bg(seed=0, dark=(30, 91), light=(150, 216)):
    """Random grey checkerboard: 8x8-pixel cells alternating a random dark and a random light grey,
    so every cell boundary has contrast and every tile has strong edges."""
    rng = np.random.default_rng(seed)
    cy, cx = np.mgrid[0:H // 8, 0:W // 8]
    is_light = (cy + cx) % 2 == 0
    cells = np.where(is_light, rng.integers(*light, is_light.shape), rng.integers(*dark, is_light.shape))
    grey = np.repeat(np.repeat(cells, 8, axis=0), 8, axis=1)
    return np.repeat(grey[..., None], 3, axis=2).astype(np.uint8)


def jitter(img, rng, amp=2):
    """Small per-frame sensor noise."""
    return np.clip(img.astype(np.int16) + rng.integers(-amp, amp + 1, img.shape), 0, 255).astype(np.uint8)


def add_smoke(img, box, alpha=0.6, grey=150, sigma=6):
    """Smoke-like patch: blur what is behind it, then blend towards grey."""
    out = img.copy()
    ys, xs = px(box)
    blurred = cv2.GaussianBlur(img[ys, xs], (0, 0), sigma).astype(np.float32)
    out[ys, xs] = np.clip((1 - alpha) * blurred + alpha * grey, 0, 255).astype(np.uint8)
    return out


def scenario_smoke(n_bg=10, n_smoke=30):
    """Test 1 frames: textured background, then a blurred grey patch over SMOKE_BOX."""
    rng = np.random.default_rng(1)
    bg = textured_bg()
    frames = [jitter(bg, rng) for _ in range(n_bg)]
    frames += [jitter(add_smoke(bg, SMOKE_BOX), rng) for _ in range(n_smoke)]
    return frames


def run(engine, frames, update=True):
    return [engine.step(f, update) for f in frames]


# ---------------------------------------------------------------- spec tests 1-7

def test_1_smoke_patch_flags_patch_only():
    eng = TileEngine(P)
    out = run(eng, scenario_smoke())
    for scores, gate, _ in out[:10]:
        assert not gate and scores.max() < P.T_FLAG          # background alone: nothing flagged
    for scores, gate, _ in out[10:]:
        flagged = scores >= P.T_FLAG
        assert not gate
        assert flagged[tile_mask(SMOKE_BOX, shrink=1)].all()  # patch interior flagged on every frame
        assert not flagged[far_mask(SMOKE_BOX)].any()         # nothing flagged away from it


def test_2_grey_overlay_on_dark_flat_scores_from_grey_shift():
    dark = np.full((H, W, 3), 30, np.uint8)
    over = dark.copy()
    ys, xs = px(DARK_BOX)
    over[ys, xs] = (0.5 * 30 + 0.5 * 180)                     # semi-transparent grey: 30 -> 105
    eng = TileEngine(P)
    run(eng, [dark] * 5)
    assert not eng.bE.any()                                   # flat: no edges, so edge_drop can't contribute
    scores, gate, _ = eng.step(over)
    inner = tile_mask(DARK_BOX, shrink=1)
    assert not gate
    assert (scores[inner] == 255).all()                       # grey_shift = 98 - 23 = 75 levels -> raw 300 -> 255
    assert not scores[far_mask(DARK_BOX, 1)].any()
    no_grey = TileEngine(dataclasses.replace(P, W_GREY=0))
    run(no_grey, [dark] * 5)
    assert not no_grey.step(over)[0][inner].any()             # without W_GREY the same overlay scores 0


def test_3_saturated_patch_scores_zero():
    rng = np.random.default_rng(3)
    bg = textured_bg()
    red = bg.copy()
    ys, xs = px(RED_BOX)
    red[ys, xs] = (220, 30, 30)                               # flat red: edges vanish, mS = 190 > SAT_MAX
    inner = tile_mask(RED_BOX, shrink=1)
    eng = TileEngine(P)
    run(eng, [jitter(bg, rng) for _ in range(5)])
    assert not eng.step(red)[0][inner].any()
    no_sat = TileEngine(dataclasses.replace(P, SAT_MAX=255, SAT_TOL=65535))
    run(no_sat, [jitter(bg, rng) for _ in range(5)])
    assert (no_sat.step(red)[0][inner] >= P.T_FLAG).all()     # control: without the sat gate it would flag


def test_4_global_brightness_gates_then_rebaselines_fast():
    rng = np.random.default_rng(4)
    bg = textured_bg()
    bright = np.clip(bg.astype(np.int16) + 40, 0, 255).astype(np.uint8)
    eng = TileEngine(P)
    run(eng, [jitter(bg, rng) for _ in range(5)])
    _, gate, changed = eng.step(jitter(bright, rng))
    assert gate and changed > P.GATE_TILES
    gaps = []
    for _ in range(6):                                        # scene stays bright
        before = eng.bY.copy()
        prev_gate = eng.prev_gate
        f = jitter(bright, rng)
        _, gate, _ = eng.step(f)
        gaps.append(gate)
        if prev_gate:                                         # after a gated frame every tile moves 1/4 of the way
            xY = (pixel_features(f)[0].reshape(45, T, 80, T).sum(axis=(1, 3)) >> 8) << 8
            assert np.array_equal(eng.bY, before + ((xY - before + 2) >> 2))
    assert gaps[-1] is False                                  # the gate releases within a few frames


def test_5_flagged_tiles_baselines_frozen():
    eng = TileEngine(P)
    frames = scenario_smoke()
    run(eng, frames[:10])
    for f in frames[10:]:
        before = (eng.bE.copy(), eng.bY.copy(), eng.bS.copy())
        prev_gate = eng.prev_gate
        scores, _, _ = eng.step(f)
        frozen = scores >= P.T_FLAG
        assert frozen.any() and not prev_gate
        for b0, b1 in zip(before, (eng.bE, eng.bY, eng.bS)):
            assert np.array_equal(b0[frozen], b1[frozen])


def test_6_full_and_fast_mode_shapes():
    frames = scenario_smoke(n_bg=5, n_smoke=3)
    full, fast = TileEngine(P, tile=16), TileEngine(P, tile=8)
    for f in frames:
        for eng, img in ((full, f), (fast, f[::2, ::2])):
            scores, gate, changed = eng.step(img)
            assert scores.shape == (45, 80) and scores.dtype == np.uint8
            assert isinstance(gate, bool) and isinstance(changed, int)
    assert (scores >= P.T_FLAG)[tile_mask(SMOKE_BOX, shrink=1)].all()   # fast mode sees the patch too
    with pytest.raises(ValueError):
        full.step(frames[0][::2, ::2])


def test_7_deterministic():
    frames = scenario_smoke(n_bg=5, n_smoke=10)
    a, b = TileEngine(P), TileEngine(P)
    for f in frames:
        sa, ga, ca = a.step(f)
        sb, gb, cb = b.step(f)
        assert np.array_equal(sa, sb) and ga == gb and ca == cb
    assert a.state_bytes() == b.state_bytes()


# ---------------------------------------------------------------- spec details

def test_reset_frame_scores_zero_whatever_the_state():
    eng = TileEngine(P)
    frames = scenario_smoke(n_bg=5, n_smoke=5)
    scores, gate, changed = eng.step(frames[-1])              # a new engine starts with a reset pending
    assert not scores.any() and not gate and changed == 0
    run(eng, frames)
    eng.reset()
    bright = np.clip(frames[0].astype(np.int16) + 60, 0, 255).astype(np.uint8)
    scores, gate, changed = eng.step(bright)
    assert not scores.any() and not gate and changed == 0 and eng.prev_gate is False
    assert (eng.bY & 0xFF == 0).all() and (eng.bE & 0xFF == 0).all()   # b = x exactly (Q8, no update after)


def test_no_update_frame_keeps_baselines_but_tracks_gate():
    rng = np.random.default_rng(8)
    bg = textured_bg()
    eng = TileEngine(P)
    run(eng, [jitter(bg, rng) for _ in range(3)])
    before = eng.state_bytes()[:-1]
    bright = np.clip(bg.astype(np.int16) + 40, 0, 255).astype(np.uint8)
    _, gate, _ = eng.step(bright, update_this_frame=False)
    assert gate and eng.prev_gate and eng.state_bytes()[:-1] == before


def test_update_rounding_and_arithmetic_shift():
    cases = [  # (b, x, k, expected new b)
        (0, 256, 6, 4),          # (256 + 32) >> 6 = 4
        (256, 0, 6, 252),        # (-256 + 32) >> 6 = -224 >> 6 = -4 (floor of -3.5)
        (10, 0, 2, 8),           # (-10 + 2) >> 2 = -2
        (9, 0, 2, 7),            # (-9 + 2) >> 2 = floor(-1.75) = -2
        (100, 102, 2, 101),      # (2 + 2) >> 2 = 1
        (101, 100, 2, 101),      # (-1 + 2) >> 2 = 0: stops 1 above x (round half up)
        (65280, 0, 1, 32640),    # (-65280 + 1) >> 1 = -32640
    ]
    for b, x, k, want in cases:
        arr = np.array([[b]], np.int32)
        update_baseline(arr, np.array([[x]], np.int32), k, np.array([[True]]))
        assert arr[0, 0] == want, (b, x, k)
    arr = np.array([[5]], np.int32)
    update_baseline(arr, np.array([[200]], np.int32), 3, np.array([[False]]))
    assert arr[0, 0] == 5                                     # masked tiles don't move


def test_pixel_features_match_scalar_formulas():
    rgb = np.random.default_rng(5).integers(0, 256, (9, 11, 3)).astype(np.uint8)
    Y, S, E = pixel_features(rgb)
    h, w = rgb.shape[:2]
    y = [[(77 * int(rgb[r, c, 0]) + 150 * int(rgb[r, c, 1]) + 29 * int(rgb[r, c, 2])) >> 8 for c in range(w)]
         for r in range(h)]
    for r in range(h):
        for c in range(w):
            assert Y[r, c] == y[r][c]
            assert S[r, c] == int(rgb[r, c].max()) - int(rgb[r, c].min())
            if r in (0, h - 1) or c in (0, w - 1):
                assert E[r, c] == 0
                continue
            gx = (y[r-1][c+1] + 2*y[r][c+1] + y[r+1][c+1]) - (y[r-1][c-1] + 2*y[r][c-1] + y[r+1][c-1])
            gy = (y[r+1][c-1] + 2*y[r+1][c] + y[r+1][c+1]) - (y[r-1][c-1] + 2*y[r-1][c] + y[r-1][c+1])
            assert E[r, c] == (abs(gx) + abs(gy)) >> 3
    white = np.full((5, 5, 3), 255, np.uint8)
    assert pixel_features(white)[0].max() == 255              # 77 + 150 + 29 = 256: Y spans 0..255


def test_params_validate_ranges_and_register_order():
    assert list(P.registers()) == [f.lower() for f in config.REGISTER_FIELDS]
    assert P.registers()["sat_tol"] == 1024 and P.registers()["t_global"] == 6144
    for bad in (dict(K_SLOW=0), dict(K_FAST=16), dict(W_EDGE=256), dict(SCORE_SHIFT=32),
                dict(SAT_TOL=65536), dict(GATE_TILES=3601), dict(UPDATE_EVERY_PL=0)):
        with pytest.raises(ValueError):
            Params(**bad)
    with pytest.raises(TypeError):
        Params(T_FLAG=40.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        P.T_FLAG = 30


def test_geometry_matches_contracts():
    assert (config.IMG_W, config.IMG_H) == (contracts.IMG_W, contracts.IMG_H)
    assert (config.TILES_X, config.TILES_Y, config.N_TILES) == (contracts.TILES_X, contracts.TILES_Y, contracts.N_TILES)


@pytest.mark.xfail(strict=True, reason="spec v1 deadlock: after a global change the gate releases with a residual "
                                       "gap that keeps tiles flagged, and flagged tiles are frozen (F7)")
def test_global_change_recovers():
    """'Lights on' in a dark scene: after a few frames the scene should score clean again."""
    rng = np.random.default_rng(6)
    dark = textured_bg(dark=(10, 31), light=(50, 71))
    lit = np.clip(dark.astype(np.int16) + 40, 0, 255).astype(np.uint8)
    eng = TileEngine(P)
    run(eng, [jitter(dark, rng) for _ in range(5)])
    out = run(eng, [jitter(lit, rng) for _ in range(30)])
    assert (out[-1][0] >= P.T_FLAG).sum() == 0


# ---------------------------------------------------------------- heat map for docs/

def render_test1(path=os.path.join(ROOT, "docs", "golden_test1.png")):
    eng = TileEngine(P)
    frames = scenario_smoke()
    for f in frames:
        scores, gate, changed = eng.step(f)
    rgb = frames[-1]
    heat = cv2.applyColorMap(cv2.resize(scores, (W, H), interpolation=cv2.INTER_NEAREST), cv2.COLORMAP_INFERNO)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    flagged = cv2.resize((scores >= P.T_FLAG).astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST)
    overlay = np.where(flagged[..., None] > 0, cv2.addWeighted(bgr, 0.35, heat, 0.65, 0), bgr // 2)
    left = cv2.resize(bgr, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    right = cv2.resize(overlay, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    img = np.hstack([left, np.full((H // 2, 8, 3), 255, np.uint8), right])
    cap = np.full((40, img.shape[1], 3), 255, np.uint8)
    n = int((scores >= P.T_FLAG).sum())
    cv2.putText(cap, f"golden.py test 1, frame {len(frames) - 1}: input (left) | tile scores >= T_FLAG={P.T_FLAG} "
                     f"(right, {n} tiles flagged, max {scores.max()})", (10, 27),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.imwrite(path, np.vstack([cap, img]))
    print(f"wrote {path}: {n} flagged tiles, max score {scores.max()}, gate {gate}, changed {changed}")


if __name__ == "__main__":
    render_test1()
