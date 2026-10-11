"""Run the ARM-only pipeline offline on the labelled clips and write docs/test_table.md (P3).

Per clip: frames are letterboxed to 1280x720 (as tools/camfeed.py puts them on HDMI), decimated to ARM-fast
640x360, subsampled to --fps, then golden.TileEngine(tile=8) -> RegionTracker -> StateMachine, with verdicts
stubbed as "no verdict". So each clip raises at most one SUSPECT.

  python tools/eval_clips.py                                   # all rows of testdata/labels.csv
  python tools/eval_clips.py --only firesense                  # rows whose clip path contains this
  python tools/eval_clips.py --sweep T_FLAG=30,40,50 PERSIST_S=4,6,8

A smoke clip is detected when it reaches SUSPECT inside [smoke_start_s, smoke_end_s] (end empty = clip end).
Any SUSPECT outside that window, or on a non-smoke clip, is a false alarm.
"""
import argparse
import csv
import dataclasses
import itertools
import os
import statistics
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from detector.config import ArmParams, Params  # noqa: E402
from detector.golden import TileEngine  # noqa: E402
from detector.regions import RegionTracker  # noqa: E402
from detector.state import StateMachine  # noqa: E402
from tools import contracts  # noqa: E402
from tools.camfeed import letterbox  # noqa: E402

CLIPS = os.path.join(ROOT, "testdata", "clips")
LABELS_CSV = os.path.join(ROOT, "testdata", "labels.csv")
REVIEW_CSV = os.path.join(ROOT, "testdata", "suspect_review.csv")
TABLE_MD = os.path.join(ROOT, "docs", "test_table.md")
VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".mpg", ".flv")
EPOCH = 1_791_600_000.0    # clip time 0 maps to this Unix time, so event ts are realistic integers
CAMERA = "eval"
FIXED_MAX_PX_S = 5.0       # median camera motion below this (px/s at 720p) counts as a fixed camera


def read_labels(path=LABELS_CSV):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if tuple(r) != contracts.LABEL_COLUMNS:
            raise ValueError(f"{path}: columns {tuple(r)} != {contracts.LABEL_COLUMNS}")
        if r["label"] not in contracts.LABELS:
            raise ValueError(f"{path}: {r['clip']}: unknown label {r['label']!r}")
    return rows


def read_review(path=REVIEW_CSV):
    """{(clip, suspect_t rounded to 0.1 s): on_smoke} from the by-eye review of SUSPECT snapshots."""
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if r["on_smoke"] not in ("yes", "partly", "no"):
            raise ValueError(f"{path}: {r['clip']}: on_smoke must be yes/partly/no")
    return {(r["clip"], round(float(r["suspect_t"]), 1)): r["on_smoke"] for r in rows}


def find_clip(name, clips_dir=CLIPS):
    for ext in VIDEO_EXTS:
        p = os.path.join(clips_dir, *name.split("/")) + ext
        if os.path.exists(p):
            return p
    return None


def clip_frames(path, fps):
    """Yield (t seconds, rgb uint8 [360, 640, 3]) at about `fps` frames per second of clip time."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise OSError(f"cannot open {path}")
    native = cap.get(cv2.CAP_PROP_FPS)
    native = native if 1 <= native <= 240 else 25.0
    i, next_t = 0, 0.0
    while cap.grab():
        t = i / native
        i += 1
        if t + 1e-9 < next_t:
            continue
        next_t += 1 / fps
        ok, bgr = cap.retrieve()
        if not ok:
            break
        rgb = cv2.cvtColor(letterbox(bgr), cv2.COLOR_BGR2RGB)
        yield t, np.ascontiguousarray(rgb[::2, ::2])
    cap.release()


def camera_motion(frames):
    """Median global shift between consecutive processed frames, in pixels per second at 1280x720."""
    v, prev = [], None
    for t, rgb in frames:
        g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
        if prev is not None and t > prev[0]:
            (dx, dy), _ = cv2.phaseCorrelate(prev[1], g)
            v.append(2 * float(np.hypot(dx, dy)) / (t - prev[0]))
        prev = (t, g)
    return float(np.median(v)) if v else 0.0


def pipeline(frames, params, arm):
    """Run engine + tracker + state machine. Yields one dict per processed frame."""
    eng = TileEngine(params, tile=8)
    tr = RegionTracker(params.T_FLAG, arm)
    sm = StateMachine(CAMERA, arm)
    for frame_no, (t, rgb) in enumerate(frames):
        scores, gate, changed = eng.step(rgb, frame_no % params.UPDATE_EVERY_ARM == 0)
        region = tr.update(scores, gate, EPOCH + t)
        cand = None if gate else tr.candidate()
        actions = sm.step(EPOCH + t, cand, region is not None)
        for a in actions:
            if a["type"] == "ignore":
                tr.ignore(a["mask"], a["until"])
            elif a["type"] == "rebaseline":
                eng.reset()
        yield {"t": t, "rgb": rgb, "scores": scores, "gate": gate, "changed": changed,
               "region": region, "state": sm.state, "actions": actions}


def evaluate(row, frames, params, arm, motion, snapshots=None):
    """Score one clip. frames: list of (t, rgb); motion: camera_motion(frames).

    snapshots: a folder; the annotated frame at each SUSPECT is saved there as <clip>_<t>s.jpg, so a reviewer
    can check that the region is on the smoke (the time window alone can't tell).
    """
    uploads, gated, peak = [], 0, 0
    for f in pipeline(frames, params, arm):
        gated += f["gate"]
        if f["region"] is not None:
            peak = max(peak, f["region"].tiles)
        if any(a["type"] == "upload" for a in f["actions"]):
            uploads.append(f["t"])
            if snapshots:
                from tools.replay_viewer import render   # lazy: replay_viewer imports this module
                os.makedirs(snapshots, exist_ok=True)
                name = f"{row['clip'].replace('/', '_')}_{f['t']:.1f}s.jpg"
                cv2.imwrite(os.path.join(snapshots, name), render(f, params.T_FLAG), [cv2.IMWRITE_JPEG_QUALITY, 85])
    length = frames[-1][0] if frames else 0.0
    smoke = row["label"] == "smoke"
    start = float(row["smoke_start_s"]) if smoke else None
    end = float(row["smoke_end_s"]) if smoke and row["smoke_end_s"] else length
    hits = [t for t in uploads if smoke and start <= t <= end]
    return {"clip": row["clip"], "label": row["label"], "length": length, "frames": len(frames),
            "window": (start, end) if smoke else None, "suspect_t": uploads[0] if uploads else None,
            "detected": bool(hits), "tts": hits[0] - start if hits else None,
            "false": len(uploads) - len(hits), "gated": gated, "peak": peak, "motion": motion,
            "fixed": motion < FIXED_MAX_PX_S, "notes": row["notes"]}


def summary(results):
    """Counts for the totals line. on_smoke counts use the review of each detected clip's first SUSPECT."""
    smoke = [r for r in results if r["label"] == "smoke"]
    other = [r for r in results if r["label"] != "smoke"]
    tts = [r["tts"] for r in smoke if r["detected"]]
    fixed = [r for r in smoke if r["fixed"]]
    return {"smoke": len(smoke), "detected": sum(r["detected"] for r in smoke),
            "fixed": len(fixed), "fixed_detected": sum(r["detected"] for r in fixed),
            "on_smoke": {k: sum(r["detected"] and r.get("on_smoke", "") == k for r in smoke) for k in ("yes", "partly", "no", "")},
            "fixed_on_smoke": sum(r["detected"] and r.get("on_smoke", "") == "yes" for r in fixed),
            "other": len(other), "other_false": sum(r["false"] > 0 for r in other),
            "false": sum(r["false"] for r in results),
            "tts_median": statistics.median(tts) if tts else None}


def fmt_s(v):
    return "" if v is None else f"{v:.1f}"


def attach_review(results, review):
    for r in results:
        r["on_smoke"] = review.get((r["clip"], round(r["suspect_t"], 1)), "") if r["suspect_t"] is not None else ""


def table_md(results, params, arm, fps, cmd):
    s = summary(results)
    out = ["# Clip evaluation (ARM-only pipeline, offline)", "",
           f"Generated by `{cmd}` on {time.strftime('%Y-%m-%d %H:%M')}. Do not edit by hand.", "",
           f"Pipeline: letterbox to 1280x720, ARM-fast (640x360, 8x8 tiles), {fps} fps, `detector/golden.py` spec "
           f"v1 -> `detector/regions.py` -> `detector/state.py`, verdicts stubbed (no verdict), so at most one "
           f"SUSPECT per clip. Smoke is detected when SUSPECT falls inside the labelled smoke window; any other "
           f"SUSPECT is a false alarm.", "",
           "Non-default parameters: " + (", ".join(
               f"`{k}={v}`" for k, v in {**_diff(params, Params()), **_diff(arm, ArmParams())}.items()) or "none") + ".",
           "",
           "| Clip | Label | Length s | Frames | Camera motion px/s | Smoke window s | SUSPECT at s | "
           "Time to SUSPECT s | Result | Region on smoke (by eye) | Peak region tiles | Gated frames | Notes |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r["label"] == "smoke":
            res = "detected" if r["detected"] else "missed"
            if r["false"]:
                res += f", {r['false']} false"
        else:
            res = "false alarm" if r["false"] else "ok (no alarm)"
        win = f"{fmt_s(r['window'][0])}-{fmt_s(r['window'][1])}" if r["window"] else ""
        out.append(f"| `{r['clip']}` | {r['label']} | {r['length']:.1f} | {r['frames']} | {r['motion']:.1f} | {win} | "
                   f"{fmt_s(r['suspect_t'])} | {fmt_s(r['tts'])} | {res} | "
                   f"{r['on_smoke'] or ('not reviewed' if r['suspect_t'] is not None else '')} | {r['peak']} | "
                   f"{r['gated']} | {r['notes']} |")
    out += ["", "**Totals:** "
            f"{s['detected']} / {s['smoke']} smoke clips detected, {s['smoke'] - s['detected']} missed; "
            f"{s['other_false']} / {s['other']} non-smoke clips raised a false SUSPECT; "
            f"{s['false']} false SUSPECTs in all. Median time to SUSPECT: {fmt_s(s['tts_median']) or 'n/a'} s. "
            f"Fixed-camera smoke clips (median camera motion < {FIXED_MAX_PX_S:g} px/s at 720p, the setting the "
            f"detector is designed for): {s['fixed_detected']} / {s['fixed']} detected.", "",
            "The time window alone cannot tell whether the alarm is about the smoke, so every SUSPECT frame was saved "
            "(`--snapshots`) and checked by eye; the verdicts are in `testdata/suspect_review.csv`. "
            f"**Of the {s['detected']} detected smoke clips, the region is on the smoke in {s['on_smoke']['yes']}, "
            f"partly on it in {s['on_smoke']['partly']}, and elsewhere in {s['on_smoke']['no']}"
            + (f" ({s['on_smoke']['']} not reviewed)" if s['on_smoke'][''] else "") +
            f". Fixed-camera clips with the region on the smoke: {s['fixed_on_smoke']} / {s['fixed']}.**", "",
            "Clips under `firesense/` are from the FIRESENSE database (Dimitropoulos, Barmpoutis, Grammalidis; "
            "[Zenodo, doi:10.5281/zenodo.836749](https://doi.org/10.5281/zenodo.836749), CC-BY-4.0). "
            "They are low-resolution surveillance videos upscaled to 720p, so their scores are not those of a "
            "720p camera. The `20261011_*` clips are our own phone recordings of incense smoke.", ""]
    return "\n".join(out)


def _diff(obj, default):
    return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)
            if getattr(obj, f.name) != getattr(default, f.name)}


def split_params(overrides):
    """{'T_FLAG': 30, 'PERSIST_S': 4.0} -> (Params, ArmParams)."""
    p_names = {f.name for f in dataclasses.fields(Params)}
    a_names = {f.name: f.type for f in dataclasses.fields(ArmParams)}
    p_kw = {k: int(v) for k, v in overrides.items() if k in p_names}
    a_kw = {k: (float(v) if a_names[k] in (float, "float") else int(v)) for k, v in overrides.items() if k in a_names}
    unknown = set(overrides) - p_names - set(a_names)
    if unknown:
        raise SystemExit(f"unknown parameter(s): {', '.join(sorted(unknown))}")
    return Params(**p_kw), ArmParams(**a_kw)


def parse_sweep(items):
    grid = {}
    for it in items:
        name, _, vals = it.partition("=")
        grid[name] = [float(v) for v in vals.split(",") if v]
    keys = list(grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(grid[k] for k in keys))]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", default=LABELS_CSV)
    ap.add_argument("--clips", default=CLIPS)
    ap.add_argument("--fps", type=float, default=3.0)
    ap.add_argument("--only", help="evaluate only clips whose path contains this text")
    ap.add_argument("--set", nargs="*", default=[], metavar="NAME=VALUE", help="override Params/ArmParams fields")
    ap.add_argument("--sweep", nargs="+", metavar="NAME=V1,V2", help="grid of overrides; prints a summary per combination")
    ap.add_argument("--out", default=TABLE_MD)
    ap.add_argument("--snapshots", metavar="DIR", help="save the annotated frame at every SUSPECT here")
    args = ap.parse_args()

    rows = [r for r in read_labels(args.labels) if not args.only or args.only in r["clip"]]
    base = {k: float(v) for k, v in (s.split("=", 1) for s in args.set)}
    combos = [{**base, **c} for c in parse_sweep(args.sweep)] if args.sweep else [base]
    configs = [split_params(c) for c in combos]
    results = [[] for _ in configs]

    for row in rows:
        path = find_clip(row["clip"], args.clips)
        if path is None:
            print(f"skip {row['clip']}: no video file under {args.clips}", file=sys.stderr)
            continue
        t0 = time.time()
        frames = list(clip_frames(path, args.fps))
        motion = camera_motion(frames)
        for res, (p, a) in zip(results, configs):
            res.append(evaluate(row, frames, p, a, motion, None if args.sweep else args.snapshots))
        r = results[0][-1]
        print(f"{row['clip']}: {r['label']}, {len(frames)} frames, SUSPECT at {fmt_s(r['suspect_t']) or '-'} "
              f"({time.time() - t0:.1f} s)", file=sys.stderr)

    if args.sweep:
        print("| " + " | ".join(combos[0]) + " | detected | fixed-camera detected | false SUSPECTs | "
              "non-smoke clips with a false SUSPECT | median time to SUSPECT s |")
        print("|" + "---|" * (len(combos[0]) + 5))
        for c, res in zip(combos, results):
            s = summary(res)
            vals = " | ".join(f"{v:g}" for v in c.values())
            print(f"| {vals} | {s['detected']}/{s['smoke']} | {s['fixed_detected']}/{s['fixed']} | {s['false']} | "
                  f"{s['other_false']}/{s['other']} | "
                  f"{fmt_s(s['tts_median'])} |")
        return

    attach_review(results[0], read_review())
    cmd = "python tools/eval_clips.py" + "".join(f" {a}" for a in sys.argv[1:])
    md = table_md(results[0], *configs[0], args.fps, cmd)
    if not args.only:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
        print(f"wrote {os.path.relpath(args.out, ROOT)}", file=sys.stderr)
    print(md)


if __name__ == "__main__":
    main()
