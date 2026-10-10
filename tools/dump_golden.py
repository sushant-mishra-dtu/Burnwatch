"""Write HLS test vectors from detector/golden.py (FULL mode). Format: docs/contracts.md section 8.

    python tools/dump_golden.py --synthetic                       # testdata/golden/synthetic/ (no clips needed)
    python tools/dump_golden.py --clip testdata/clips/dhoop_01.mp4 [--start-s 2] [--step 2]
    python tools/dump_golden.py --pngs some/folder [--name myset]
    python tools/dump_golden.py --synthetic --update-every 3 --reset-at 0,30 --name synthetic-u3   # optional extra set

Every set: frame 0 is a reset frame, frame 20 is the source frame + 40 brightness (must come out gated), and by
default update_this_frame = 1 on every frame. Frames are resized to 1280x720. The printed digest covers every
frame and expected output, so two machines can confirm they generated the same synthetic set.
"""
import argparse
import glob
import hashlib
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from detector import config  # noqa: E402
from detector.config import REGISTER_FIELDS, Params  # noqa: E402
from detector.golden import TileEngine  # noqa: E402
from tools.contracts import pack_rgb_words  # noqa: E402

W, H = config.IMG_W, config.IMG_H
BRIGHT_FRAME, BRIGHT_ADD = 20, 40


# ------------------------------------------------------------------ sources

def blur121(a, passes=3):
    """Integer [1 2 1]/4 blur along both axes, repeated; edges replicated. int32 in, int32 out."""
    for _ in range(passes):
        p = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode="edge")
        a = (p[:-2] + 2 * p[1:-1] + p[2:]) >> 2
        a = (a[:, :-2] + 2 * a[:, 1:-1] + a[:, 2:]) >> 2
    return a


def synthetic_frames(n, seed=2026):
    """A deterministic test clip, integer numpy only: textured grey checkerboard, a smooth gradient band,
    coloured blocks, clipped white/black areas, per-frame noise, a rising and spreading grey 'smoke' plume
    (blur + blend to grey), a saturated red block that slides in, and a dark 'person' walking across."""
    rng = np.random.default_rng(seed)
    cy, cx = np.mgrid[0:H // 8, 0:W // 8]
    light = (cy + cx) % 2 == 0
    cells = np.where(light, rng.integers(140, 230, light.shape), rng.integers(20, 100, light.shape))
    grey = np.repeat(np.repeat(cells, 8, axis=0), 8, axis=1)
    bg = np.repeat(grey[..., None], 3, axis=2).astype(np.int32)
    bg[560:720, :, :] = (np.arange(W) * 255 // (W - 1))[None, :, None]          # smooth band: few edges
    bg[40:200, 1000:1240] = rng.integers(0, 256, (1, 1, 3)) // 2 + (90, 40, 10)  # coloured blocks
    bg[300:420, 1040:1200] = (30, 160, 60)
    bg[0:48, 0:160] = 255                                                       # clipped areas at the border
    bg[672:720, 1120:1280] = 0
    bg = bg + rng.integers(-6, 7, bg.shape)                                     # fine texture
    frames = []
    for i in range(n):
        f = bg + rng.integers(-2, 3, bg.shape)                                  # sensor noise
        if i >= 4:                                                              # smoke: grows and rises
            g = min(i - 4, 30)
            y0, y1, x0, x1 = 360 - 6 * g, 520, 320 - 4 * g, 520 + 4 * g
            alpha = min(32 + 6 * g, 200)                                        # /256
            patch = blur121(f[y0:y1, x0:x1])
            f[y0:y1, x0:x1] = ((256 - alpha) * patch + alpha * 150) >> 8
        if i >= 8:                                                              # saturated red block slides in
            x = 700 + 6 * (i - 8)
            f[100:228, x:x + 128] = (225, 25, 30)
        px = 40 + 28 * i                                                        # person walks left to right
        f[250:530, px:px + 70] = (f[250:530, px:px + 70] >> 2) + (40, 30, 25)
        frames.append(np.clip(f, 0, 255).astype(np.uint8))
    return frames


def clip_frames(path, n, start_s=0.0, step=1):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        sys.exit(f"cannot open {path}")
    cap.set(cv2.CAP_PROP_POS_MSEC, start_s * 1000)
    frames, k = [], 0
    while len(frames) < n:
        ok, bgr = cap.read()
        if not ok:
            sys.exit(f"{path}: only {len(frames)} frames after {start_s}s with step {step}, need {n}")
        if k % step == 0:
            frames.append(to_rgb720(bgr))
        k += 1
    cap.release()
    return frames


def png_frames(folder, n):
    paths = sorted(glob.glob(os.path.join(folder, "*.png")) + glob.glob(os.path.join(folder, "*.jpg")))
    if len(paths) < n:
        sys.exit(f"{folder}: {len(paths)} images, need {n}")
    return [to_rgb720(cv2.imread(p)) for p in paths[:n]]


def to_rgb720(bgr):
    if bgr.shape[:2] != (H, W):
        bgr = cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


# ------------------------------------------------------------------ vectors

def dump(frames, out_dir, params, update_every=1, reset_at=(0,)):
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "*_[0-9][0-9][0-9][0-9].bin")):
        os.remove(old)
    frames = list(frames)
    frames[BRIGHT_FRAME] = np.clip(frames[BRIGHT_FRAME].astype(np.int16) + BRIGHT_ADD, 0, 255).astype(np.uint8)

    eng = TileEngine(params, tile=config.TILE_FULL)
    digest = hashlib.sha256()
    rows = ["# frame reset update gate changed"]
    print(f"{'frame':>5} reset update gate changed flagged max")
    for i, rgb in enumerate(frames):
        reset, update = int(i in reset_at), int(i % update_every == 0)
        if reset:
            eng.reset()
        scores, gate, changed = eng.step(rgb, bool(update))
        words = pack_rgb_words(rgb).astype("<u4").tobytes()
        state = eng.state_bytes()
        for name, data in (("frame", words), ("scores", scores.tobytes()), ("state", state)):
            with open(os.path.join(out_dir, f"{name}_{i:04d}.bin"), "wb") as fh:
                fh.write(data)
            digest.update(data)
        rows.append(f"{i:04d} {reset} {update} {int(gate)} {changed}")
        print(f"{i:5d} {reset:5d} {update:6d} {int(gate):4d} {changed:7d} {int((scores >= params.T_FLAG).sum()):7d} "
              f"{int(scores.max()):3d}")
        if i == BRIGHT_FRAME and not gate:
            print(f"WARNING: frame {i} (+{BRIGHT_ADD} brightness) is not gated; the gate path is untested in this set")

    with open(os.path.join(out_dir, "expect.txt"), "w", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
    lines = [f"# BurnWatch golden vectors, spec v{config.SPEC_VERSION}", f"SPEC {config.SPEC_VERSION}",
             f"IMG_W {W}", f"IMG_H {H}", f"TILE {config.TILE_FULL}", f"FRAMES {len(frames)}"]
    lines += [f"{k} {getattr(params, k)}" for k in REGISTER_FIELDS]
    with open(os.path.join(out_dir, "params.txt"), "w", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {len(frames)} frames to {out_dir}  digest sha256:{digest.hexdigest()[:16]}")


def main():
    ap = argparse.ArgumentParser(description="write HLS test vectors from detector/golden.py")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--synthetic", action="store_true", help="built-in deterministic test clip")
    src.add_argument("--clip", help="video file")
    src.add_argument("--pngs", help="folder of .png/.jpg frames (sorted by name)")
    ap.add_argument("--name", help="set name (default: synthetic, clip basename or folder name)")
    ap.add_argument("--frames", type=int, default=40, help="frames in the set (>= 40)")
    ap.add_argument("--start-s", type=float, default=0.0, help="clip: start time in seconds")
    ap.add_argument("--step", type=int, default=1, help="clip: keep every Nth frame")
    ap.add_argument("--update-every", type=int, default=1, help="update_this_frame on frames where i %% N == 0")
    ap.add_argument("--reset-at", default="0", help="comma-separated reset frames (must include 0)")
    ap.add_argument("--out", default=os.path.join(ROOT, "testdata", "golden"), help="output root")
    a = ap.parse_args()

    if a.frames < 40:
        ap.error("--frames must be >= 40 (contracts.md section 8)")
    reset_at = tuple(int(x) for x in a.reset_at.split(","))
    if 0 not in reset_at:
        ap.error("--reset-at must include frame 0")
    if a.synthetic:
        name, frames = a.name or "synthetic", synthetic_frames(a.frames)
    elif a.clip:
        name = a.name or os.path.splitext(os.path.basename(a.clip))[0]
        frames = clip_frames(a.clip, a.frames, a.start_s, a.step)
    else:
        name, frames = a.name or os.path.basename(os.path.normpath(a.pngs)), png_frames(a.pngs, a.frames)
    dump(frames, os.path.join(a.out, name), Params(), a.update_every, reset_at)


if __name__ == "__main__":
    main()
