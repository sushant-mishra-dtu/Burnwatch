"""Play a clip through the ARM-only pipeline with the tile heat map, the region box and the state badge (P3).

Used for tuning: the same frames, parameters and code path as tools/eval_clips.py.

  python tools/replay_viewer.py testdata/clips/20261011_102913.mp4
  python tools/replay_viewer.py firesense/pos/testpos02.818 --set T_FLAG=30 PERSIST_S=4
  python tools/replay_viewer.py firesense/pos/testpos02.818 --save docs/images/replay.mp4   # no window

Keys: space pause/play, left/right arrow step one processed frame back/forward (pauses), q or Esc quit.
Only tiles with score >= T_FLAG are coloured. Badge colours: CLEAR green, SUSPECT amber, CONFIRMED red.
"""
import argparse
import collections
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools.eval_clips import clip_frames, find_clip, pipeline, split_params  # noqa: E402

W, H = 1280, 720
BADGE = {"CLEAR": (60, 170, 60), "SUSPECT": (0, 170, 255), "CONFIRMED": (40, 40, 220), "REJECTED": (140, 140, 140)}
KEYS_LEFT = {2424832, 65361, 81}
KEYS_RIGHT = {2555904, 65363, 83}
MAX_HISTORY = 600   # processed frames kept for stepping back (~0.7 MB each)


def render(f, t_flag):
    """BGR uint8 [720, 1280, 3] for one pipeline frame dict."""
    img = cv2.resize(cv2.cvtColor(f["rgb"], cv2.COLOR_RGB2BGR), (W, H), interpolation=cv2.INTER_NEAREST)
    scores = f["scores"]
    flagged = cv2.resize((scores >= t_flag).astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST).astype(bool)
    heat = cv2.applyColorMap(cv2.resize(scores, (W, H), interpolation=cv2.INTER_NEAREST), cv2.COLORMAP_JET)
    img[flagged] = (0.55 * img[flagged] + 0.45 * heat[flagged]).astype(np.uint8)
    if f["region"] is not None:
        x1, y1, x2, y2 = f["region"].bbox
        cv2.rectangle(img, (x1, y1), (x2 - 1, y2 - 1), (0, 255, 255), 2)
        cv2.putText(img, f"{f['region'].tiles} tiles", (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 255, 255), 1, cv2.LINE_AA)
    cv2.rectangle(img, (10, 10), (190, 46), BADGE[f["state"]], -1)
    cv2.putText(img, f["state"], (20, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    info = f"t {f['t']:6.1f} s   flagged {int((scores >= t_flag).sum())}   changed {f['changed']}" + \
           ("   GATED" if f["gate"] else "")
    cv2.putText(img, info, (10, H - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", help="a video path, or a labels.csv clip name such as firesense/pos/testpos02.818")
    ap.add_argument("--fps", type=float, default=3.0)
    ap.add_argument("--set", nargs="*", default=[], metavar="NAME=VALUE", help="override Params/ArmParams fields")
    ap.add_argument("--save", help="write the annotated video here instead of opening a window")
    args = ap.parse_args()

    path = args.clip if os.path.exists(args.clip) else find_clip(args.clip)
    if path is None:
        sys.exit(f"no clip {args.clip!r}")
    params, arm = split_params({k: float(v) for k, v in (s.split("=", 1) for s in args.set)})
    frames = pipeline(clip_frames(path, args.fps), params, arm)

    if args.save:
        out = cv2.VideoWriter(args.save, cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (W, H))
        n = 0
        for f in frames:
            out.write(render(f, params.T_FLAG))
            n += 1
        out.release()
        print(f"wrote {args.save}: {n} frames")
        return

    history = collections.deque(maxlen=MAX_HISTORY)   # pipeline frames already shown, for stepping back
    pos = -1

    def forward():
        """Index of the next frame, decoding one more if needed; None at the end of the clip."""
        if pos + 1 < len(history):
            return pos + 1
        f = next(frames, None)
        if f is None:
            return None
        full = len(history) == MAX_HISTORY
        history.append(f)
        return len(history) - 1 if full else pos + 1

    win = "burnwatch-replay"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    playing = True
    pos = forward()
    if pos is None:
        sys.exit(f"{path}: no frames")
    cv2.imshow(win, render(history[pos], params.T_FLAG))
    while cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) >= 1:
        key = cv2.waitKeyEx(max(1, int(1000 / args.fps)) if playing else 0)
        if key in (ord("q"), 27):
            break
        if key == ord(" "):
            playing = not playing
            continue
        if key in KEYS_LEFT:
            playing, new = False, max(0, pos - 1)
        elif key in KEYS_RIGHT or (key == -1 and playing):
            playing = playing and key == -1
            new = forward()
            if new is None:
                playing = False
                continue
        else:
            continue
        pos = new
        cv2.imshow(win, render(history[pos], params.T_FLAG))
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
