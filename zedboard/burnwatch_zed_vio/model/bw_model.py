"""Bit-exact Python model of the ZedBoard demo, and the expected-result generator.

The expected results come from the BurnWatch spec itself, detector/golden.py (a verbatim copy lives in
model/detector/). This file only re-creates the two SIMULATED inputs of the FPGA design, exactly as the
Verilog builds them:
  * stim_frame()   = rtl/bw_stim_gen.v     (synthetic camera frame, pixel by pixel)
  * vec_features() = rtl/bw_tile_vec_gen.v (tile-feature vectors for Part B on its own)
and the test table of rtl/bw_test_rom.v. Everything else (Y, S, Sobel E, tile means, scores, gate,
baseline update) is golden.py.

    python3 model/bw_model.py            # writes sim/expected/*.mem and docs/EXPECTED_RESULTS.md

Outputs
  sim/expected/full_summary.mem   one line per test: 16 x 32-bit fields (field 0 = rightmost 8 hex digits)
  sim/expected/full_tiles.mem     N_TESTS x 3600 lines: {score, mE, mY, mS, bE, bY, bS} (80 bits)
  sim/expected/quick_*.mem        the same for the small 320x192 simulation geometry
  sim/expected/score_unit.mem     random vectors for tb_bw_tile_score.v (random register values too)
  docs/EXPECTED_RESULTS.md        the table to compare against the VIO
  scripts/bw_expected.tcl         the same numbers for scripts/vio_run.tcl (Hardware Manager helper)
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from detector import golden  # noqa: E402
from detector.config import Params  # noqa: E402

FULL = dict(name="full", W=1280, H=720, TX=80, TY=45,
            smoke=(480, 800, 240, 480), cloth=(160, 320, 96, 224), patch=(30, 50, 15, 30),
            gate_tiles=1440, tile_sel=1640)
QUICK = dict(name="quick", W=320, H=192, TX=20, TY=12,
             smoke=(96, 224, 48, 144), cloth=(16, 80, 16, 48), patch=(6, 14, 3, 9),
             gate_tiles=96, tile_sel=109)

# (label, part, test, T_FLAG): the order of the testbench and of the summary files
TESTS = [
    ("A0 background", 0, 0, 40), ("A1 smoke a=2", 0, 1, 40), ("A2 lights +40", 0, 2, 40),
    ("A3 red cloth", 0, 3, 40),
    ("B0 smoke patch", 1, 0, 40), ("B1 saturation reject", 1, 1, 40),
    ("B2 lights -> gate -> snap", 1, 2, 40), ("B3 random stress", 1, 3, 40),
    ("I0 smoke grows", 2, 0, 40), ("I1 lights on", 2, 1, 40), ("I2 red cloth", 2, 2, 40),
    ("I3 static scene", 2, 3, 40), ("I4 smoke, sparse update + re-baseline", 2, 4, 40),
    ("I0 smoke grows, T_FLAG=150", 2, 0, 150),
]


# ------------------------------------------------------------------ test table (bw_test_rom.v)

def rom(part, test, fidx):
    """(n_frames, reset, update, smoke, lights, cloth) for one frame; n_frames = 0 for a bad test."""
    reset, update, smoke, lights, cloth = fidx == 0, True, 0, False, False
    if part == 0:
        if test > 3:
            return 0, reset, update, smoke, lights, cloth
        smoke, lights, cloth = (0, 2, 0, 0)[test], test == 2, test == 3
        return 1, reset, update, smoke, lights, cloth
    if part == 1:
        if test > 3:
            return 0, reset, update, smoke, lights, cloth
        if test == 3:
            reset, update = fidx in (0, 4), fidx != 2
        return (3, 2, 4, 6)[test], reset, update, smoke, lights, cloth
    if part == 2:
        if test == 0:
            return 4, reset, update, fidx, lights, cloth
        if test == 1:
            return 4, reset, update, smoke, fidx != 0, cloth
        if test == 2:
            return 3, reset, update, smoke, lights, fidx != 0
        if test == 3:
            return 3, reset, update, smoke, lights, cloth
        if test == 4:
            return 5, fidx in (0, 3), fidx != 1, (0, 1, 2, 2, 3)[fidx], lights, cloth
    return 0, reset, update, smoke, lights, cloth


# ------------------------------------------------------------------ simulated inputs

def stim_frame(cfg, smoke, lights, cloth):
    """uint8 [H, W, 3] frame, exactly as rtl/bw_stim_gen.v."""
    y, x = np.mgrid[0:cfg["H"], 0:cfg["W"]].astype(np.int32)
    light = ((x >> 3) ^ (y >> 3)) & 1
    v = np.where(light == 1, 140 + ((x >> 3) & 15), 40 + ((y >> 3) & 15))
    rgb = np.stack([v + 4, v, v - 4], axis=2)
    a = min(smoke, 4)
    x0, x1, y0, y1 = cfg["smoke"]
    box = (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
    rgb = np.where(box[..., None], ((4 - a) * rgb + a * 128) >> 2, rgb)
    if cloth:
        x0, x1, y0, y1 = cfg["cloth"]
        box = (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
        rgb = np.where(box[..., None], np.array([200, 30, 30], np.int32), rgb)
    if lights:
        rgb = np.minimum(rgb + 40, 255)
    return rgb.astype(np.uint8)


def xorshift32(v):
    v ^= (v << 13) & 0xFFFFFFFF
    v ^= v >> 17
    v ^= (v << 5) & 0xFFFFFFFF
    return v


def vec_features(cfg, case, fidx):
    """(mE, mY, mS) int32 [TY, TX] tile features, exactly as rtl/bw_tile_vec_gen.v."""
    TX, TY = cfg["TX"], cfg["TY"]
    tx0, tx1, ty0, ty1 = cfg["patch"]
    me = np.zeros((TY, TX), np.int32)
    my = np.zeros((TY, TX), np.int32)
    ms = np.zeros((TY, TX), np.int32)
    a, p = 0x2545F491, 0x9E3779B9 ^ fidx
    for ty in range(TY):
        for tx in range(TX):
            a, p = xorshift32(a), xorshift32(p)
            patch = tx0 <= tx < tx1 and ty0 <= ty < ty1
            f = (60, 70, 8)
            if case == 0 and fidx and patch:
                f = (40, 95, 10)
            elif case == 1 and fidx and patch:
                f = (40, 95, (60, 14, 12)[tx % 3])
            elif case == 2 and fidx:
                f = (60, 110, 8)
            elif case == 3:
                e0, y0, s0 = a & 0xFF, (a >> 8) & 0xFF, (a >> 16) & 0x3F
                if (p >> 30) == 0:
                    f = (e0 ^ (p & 0xFF), y0 ^ ((p >> 8) & 0xFF), s0 ^ ((p >> 16) & 0x3F))
                else:
                    f = (e0 ^ (p & 0x1F), y0 ^ ((p >> 8) & 0x1F), s0 ^ ((p >> 16) & 0x7))
            me[ty, tx], my[ty, tx], ms[ty, tx] = f
    return me, my, ms


# ------------------------------------------------------------------ running a test on golden.py

def set_geometry(cfg):
    """golden.py reads the tile grid from module globals; the small simulation geometry patches them."""
    golden.TILES_X, golden.TILES_Y = cfg["TX"], cfg["TY"]


def run_test(cfg, part, test, t_flag):
    """Run one test through golden.py. Returns a dict with the last frame's results."""
    set_geometry(cfg)
    n = rom(part, test, 0)[0]
    p = Params(T_FLAG=t_flag, GATE_TILES=cfg["gate_tiles"])
    shape = (cfg["H"], cfg["W"], 3)
    res = dict(n_frames=n, gate_hist=0, gate=0, changed=0, flagged=0, score_sum=0, max_score=0,
               max_idx=0, frame_count=0)
    if part == 0:                                   # Part A only: tile features of one frame
        _, _, _, smoke, lights, cloth = rom(part, test, 0)
        me, my, ms = golden.tile_features(stim_frame(cfg, smoke, lights, cloth), 16)
        res.update(me=me, my=my, ms=ms, scores=None, bE=None, bY=None, bS=None)
    else:
        eng = golden.TileEngine(p, tile=16)
        real_tile_features = golden.tile_features
        try:
            for f in range(n):
                _, reset, update, smoke, lights, cloth = rom(part, test, f)
                if part == 1:
                    feats = vec_features(cfg, test, f)
                    golden.tile_features = lambda rgb, tile, feats=feats: feats
                    rgb = np.zeros(shape, np.uint8)
                else:
                    rgb = stim_frame(cfg, smoke, lights, cloth)
                    feats = real_tile_features(rgb, 16)
                if reset:
                    eng.reset()
                scores, gate, changed = eng.step(rgb, update_this_frame=update)
                res["gate_hist"] |= int(gate) << f
                res["frame_count"] = 1 if reset else res["frame_count"] + 1
        finally:
            golden.tile_features = real_tile_features
        flat = scores.reshape(-1).astype(np.int64)
        res.update(gate=int(gate), changed=changed, flagged=int(np.count_nonzero(scores >= t_flag)),
                   score_sum=int(flat.sum()), max_score=int(flat.max()), max_idx=int(np.argmax(flat)),
                   me=feats[0], my=feats[1], ms=feats[2], scores=scores,
                   bE=eng.bE.copy(), bY=eng.bY.copy(), bS=eng.bS.copy())
    res["sum_e"], res["sum_y"], res["sum_s"] = (int(res[k].sum()) for k in ("me", "my", "ms"))
    return res


# ------------------------------------------------------------------ writers

def summary_line(part, test, t_flag, r):
    fields = [part, test, r["n_frames"], r["gate_hist"], r["gate"], r["changed"], r["flagged"],
              r["score_sum"], r["max_score"], r["max_idx"], r["frame_count"], r["sum_e"], r["sum_y"],
              r["sum_s"], t_flag, 0 if part == 0 else 1]
    return "".join(f"{v & 0xFFFFFFFF:08x}" for v in reversed(fields))


def tile_lines(r):
    me, my, ms = (r[k].reshape(-1) for k in ("me", "my", "ms"))
    zeros = np.zeros_like(me)
    sc = zeros if r["scores"] is None else r["scores"].reshape(-1)
    be, by, bs = (zeros if r[k] is None else r[k].reshape(-1) for k in ("bE", "bY", "bS"))
    return [f"{int(sc[i]):02x}{int(me[i]):02x}{int(my[i]):02x}{int(ms[i]):02x}"
            f"{int(be[i]):04x}{int(by[i]):04x}{int(bs[i]):04x}" for i in range(len(me))]


def write_expected(cfg, outdir):
    results = []
    with open(os.path.join(outdir, f"{cfg['name']}_summary.mem"), "w") as fs, \
            open(os.path.join(outdir, f"{cfg['name']}_tiles.mem"), "w") as ft:
        for label, part, test, t_flag in TESTS:
            r = run_test(cfg, part, test, t_flag)
            results.append((label, part, test, t_flag, r))
            fs.write(summary_line(part, test, t_flag, r) + "\n")
            ft.write("\n".join(tile_lines(r)) + "\n")
            print(f"  {cfg['name']:5s} {label:40s} gate_hist={r['gate_hist']:04b} changed={r['changed']:4d} "
                  f"flagged={r['flagged']:4d} sum={r['score_sum']:6d} max={r['max_score']:3d}@{r['max_idx']:4d} "
                  f"feat_sums={r['sum_e']},{r['sum_y']},{r['sum_s']}")
    return results


def write_score_unit(path, n=4000, seed=7):
    """Random single-tile vectors for tb_bw_tile_score.v, with random register values (golden math)."""
    rng = np.random.default_rng(seed)
    corner = [0, 255, 65280, 32768, 32767, 256]
    lines = []
    for i in range(n):
        p = Params(K_SLOW=int(rng.integers(1, 16)), K_FAST=int(rng.integers(0, 16)),
                   W_EDGE=int(rng.integers(0, 256)), W_GREY=int(rng.integers(0, 256)),
                   SCORE_SHIFT=int(rng.integers(0, 32)), T_FLAG=int(rng.integers(0, 256)),
                   SAT_MAX=int(rng.integers(0, 256)), SAT_TOL=int(rng.integers(0, 65536)),
                   T_GLOBAL=int(rng.integers(0, 65536)), GATE_TILES=1440)
        if i % 4 == 0:      # a quarter with the default registers
            p = Params(T_FLAG=int(rng.integers(0, 256)))
        reset, update, prev_gate = int(rng.random() < 0.15), int(rng.random() < 0.8), int(rng.random() < 0.3)
        m = rng.integers(0, 256, 3)
        b = [int(rng.choice(corner)) if rng.random() < 0.2 else int(rng.integers(0, 65281)) for _ in range(3)]
        x = (m.astype(np.int32) << 8).reshape(3, 1, 1)
        bb = np.array(b, np.int32).reshape(3, 1, 1)
        if reset:
            bb = x.copy()
        ms = np.full((1, 1), int(m[2]), np.int32)
        scores, changed = golden.score_tiles(p, x[0], x[1], x[2], ms, bb[0], bb[1], bb[2])
        score = int(scores[0, 0])
        if not reset and update:
            k = p.K_FAST if prev_gate else p.K_SLOW
            mask = np.array([[bool(prev_gate) or score < p.T_FLAG]])
            for j in range(3):
                golden.update_baseline(bb[j], x[j], k, mask)
        flag = int(score >= p.T_FLAG)
        # input fields, then expected outputs
        line = (f"{p.K_SLOW:01x}{p.K_FAST:01x}{p.W_EDGE:02x}{p.W_GREY:02x}{p.SCORE_SHIFT:02x}{p.T_FLAG:02x}"
                f"{p.SAT_MAX:02x}{p.SAT_TOL:04x}{p.T_GLOBAL:04x}{reset:01x}{update:01x}{prev_gate:01x}"
                f"{int(m[0]):02x}{int(m[1]):02x}{int(m[2]):02x}{b[0]:04x}{b[1]:04x}{b[2]:04x}"
                f"{score:02x}{flag:01x}{changed:01x}"
                f"{int(bb[0, 0, 0]):04x}{int(bb[1, 0, 0]):04x}{int(bb[2, 0, 0]):04x}")
        lines.append(line)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return len(lines[0]) * 4


def cycles_expected(cfg, part, n):
    """Clocks from Start to done (the `cycles` probe); per-frame counts measured in RTL simulation."""
    slots = (cfg["H"] + 1) * (cfg["W"] + 1)
    per_frame = {0: slots + 7, 1: cfg["TX"] * cfg["TY"] + 8, 2: slots + 13}[part]
    return 1 + n * per_frame


def fmt_hist(h, n):
    return "".join(str((h >> i) & 1) for i in range(n)) if n else "-"


def write_doc(results, cfg, path):
    ts = cfg["tile_sel"]
    ty, tx = divmod(ts, cfg["TX"])
    out = ["# Expected VIO results (1280x720, default registers)", "",
           "Generated by `python3 model/bw_model.py` from `model/detector/golden.py` (the BurnWatch spec, "
           "unchanged). The simulation testbench checks the hardware against exactly these numbers, plus every "
           "tile's features, score and baselines.", "",
           "Read `gate_hist` as frame 0, frame 1, ... from left to right here. **In the VIO (binary radix) the "
           "same value shows MSB first**, i.e. reversed, padded to 8 bits.", "",
           "## Status and frame results", "",
           "| # | part_sel | test_sel | T_FLAG | Test | frames | gate per frame | gate | changed | flagged | "
           "score_sum | max_score | max_idx | frame_count | sum_e | sum_y | sum_s | cycles |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, (label, part, test, t_flag, r) in enumerate(results):
        pb = part != 0
        out.append(f"| {i} | {part} | {test} | {t_flag} | {label} | {r['n_frames']} | "
                   f"{fmt_hist(r['gate_hist'], r['n_frames']) if pb else '-'} | {r['gate']} | {r['changed']} | "
                   f"{r['flagged']} | {r['score_sum']} | {r['max_score']} | {r['max_idx']} | "
                   f"{r['frame_count'] if pb else '(unchanged)'} | {r['sum_e']} | {r['sum_y']} | {r['sum_s']} | "
                   f"{cycles_expected(cfg, part, r['n_frames'])} |")
    out += ["", "`cycles` = clocks from Start to done at 100 MHz (divide by 100,000 for ms), as measured in the RTL "
            "simulation; the testbench prints the same values.", "",
            "In Part A tests (part_sel = 0) Part B does not run: gate, changed, flagged, score_sum, max_score "
            "and max_idx read 0 (cleared at the start of the test), frame_count, rd_score and rd_bE/bY/bS keep "
            "whatever the previous Part B test left.", "",
            f"## Read-back of tile_sel = {ts} (tile row {ty}, column {tx}; inside the smoke box and the vector "
            "patch)", "",
            "| # | Test | rd_me | rd_my | rd_ms | rd_score | rd_be | rd_by | rd_bs |",
            "|---|---|---|---|---|---|---|---|---|"]
    for i, (label, part, test, t_flag, r) in enumerate(results):
        me, my, ms = (int(r[k].reshape(-1)[ts]) for k in ("me", "my", "ms"))
        if part == 0:
            rest = "(not run) | (unchanged) | (unchanged) | (unchanged)"
        else:
            rest = " | ".join(str(int(r[k].reshape(-1)[ts])) for k in ("scores", "bE", "bY", "bS"))
        out.append(f"| {i} | {label} | {me} | {my} | {ms} | {rest} |")
    out += ["", "Error checks (no expected data needed): part_sel = 3 gives error = 1, err_code = 1; "
            "an unknown test_sel (Part A 4-7, Part B 4-7, Integrated 5-7) gives error = 1, err_code = 2; "
            "tile_sel >= 3600 gives rd_err = 1 and all rd_* = 0.", ""]
    with open(path, "w") as f:
        f.write("\n".join(out))


def write_tcl(results, cfg, path):
    """Expected VIO values per (part, test, T_FLAG) for scripts/vio_run.tcl."""
    ts = cfg["tile_sel"]
    out = ["# Generated by model/bw_model.py from golden.py. Do not edit; rerun the script.",
           f"# Expected VIO input-probe values after each demo test (1280x720), read-back tile = {ts}.",
           f"set bw_expected_tile {ts}", "set bw_expected [dict create]"]
    for label, part, test, t_flag, r in results:
        f = [("frames_run", r["n_frames"]), ("cycles", cycles_expected(cfg, part, r["n_frames"])),
             ("sum_e", r["sum_e"]), ("sum_y", r["sum_y"]), ("sum_s", r["sum_s"])]
        f += [(k, int(r[k].reshape(-1)[ts])) for k in ("me", "my", "ms")]
        f = [("rd_" + k if k in ("me", "my", "ms") else k, v) for k, v in f]
        if part == 0:
            f += [("gate", 0), ("changed", 0), ("flagged", 0), ("score_sum", 0), ("max_score", 0), ("max_idx", 0)]
        else:
            f += [(k, r[k]) for k in ("gate_hist", "gate", "changed", "flagged", "score_sum", "max_score",
                                       "max_idx", "frame_count")]
            f += [("rd_score", int(r["scores"].reshape(-1)[ts]))]
            f += [("rd_b" + k[1:].lower(), int(r[k].reshape(-1)[ts]))
                  for k in ("bE", "bY", "bS")]
        body = " ".join(f"{k} {v}" for k, v in f)
        out.append(f"dict set bw_expected {part},{test},{t_flag} {{label {{{label}}} {body}}}")
    with open(path, "w") as fh:
        fh.write("\n".join(out) + "\n")


def main():
    outdir = os.path.join(PKG, "sim", "expected")
    os.makedirs(outdir, exist_ok=True)
    for cfg in (QUICK, FULL):
        res = write_expected(cfg, outdir)
        if cfg is FULL:
            write_doc(res, cfg, os.path.join(PKG, "docs", "EXPECTED_RESULTS.md"))
            write_tcl(res, cfg, os.path.join(PKG, "scripts", "bw_expected.tcl"))
    set_geometry(FULL)
    bits = write_score_unit(os.path.join(outdir, "score_unit.mem"))
    print(f"wrote {outdir} (score_unit line = {bits} bits) and docs/EXPECTED_RESULTS.md")


if __name__ == "__main__":
    main()
