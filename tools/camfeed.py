"""Show a phone camera (or a looping clip) full screen on the HDMI output that feeds the PYNQ.

The laptop stands in for a CCTV recorder's HDMI output. The window shows the picture only,
letterboxed to exactly 1280x720: no text or overlay, ever, because the PYNQ analyses it.
Status goes to the console instead.

  python tools/camfeed.py --list                         # monitors and cameras
  python tools/camfeed.py --camera 1 --monitor 2         # DroidCam / Phone Link webcam
  python tools/camfeed.py --clip testdata/clips/burn_01.mp4 --monitor 2

Hotkeys (window focused): q quit, b toggle a black frame (tests the global gate), space pause.
"""
import argparse
import sys
import time

import cv2
import numpy as np
from screeninfo import get_monitors

OUT_W, OUT_H = 1280, 720
WINDOW = "burnwatch-feed"


def letterbox(img, w=OUT_W, h=OUT_H):
    """Scale img to fit inside w x h keeping its aspect ratio, centred on black. Returns uint8 [h, w, 3]."""
    ih, iw = img.shape[:2]
    if (iw, ih) == (w, h):
        return img
    s = min(w / iw, h / ih)
    nw, nh = max(1, round(iw * s)), max(1, round(ih * s))
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
    out = np.zeros((h, w, 3), np.uint8)
    x0, y0 = (w - nw) // 2, (h - nh) // 2
    out[y0:y0 + nh, x0:x0 + nw] = cv2.resize(img, (nw, nh), interpolation=interp)
    return out


def open_camera(index):
    """Open a webcam with OpenCV's default backend (Media Foundation on Windows), asking for 1280x720 @ 30."""
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, OUT_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, OUT_H)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


def list_sources(max_cams=5):
    for i, m in enumerate(get_monitors()):
        print(f"monitor {i}: {m.width}x{m.height} at ({m.x},{m.y}) {m.name}{' primary' if m.is_primary else ''}")
    print("probing cameras ...")
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)  # missing indices are expected here
    for i in range(max_cams):
        cap = open_camera(i)
        if cap is not None:
            ok, frame = cap.read()
            got = f"{frame.shape[1]}x{frame.shape[0]}" if ok else "opened, no frame"
            print(f"camera {i}: {got}, reported {cap.get(cv2.CAP_PROP_FPS):.0f} fps")
            cap.release()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--camera", type=int, help="webcam index (see --list)")
    src.add_argument("--clip", help="video file; loops at its own frame rate")
    ap.add_argument("--monitor", type=int, default=None, help="monitor index for the full-screen window (see --list)")
    ap.add_argument("--list", action="store_true", help="print monitors and cameras, then exit")
    a = ap.parse_args()

    if a.list:
        list_sources()
        return
    if a.camera is None and a.clip is None:
        ap.error("give --camera N or --clip PATH (or --list)")

    if a.clip:
        cap = cv2.VideoCapture(a.clip)
        if not cap.isOpened():
            sys.exit(f"cannot open clip {a.clip}")
        clip_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        print(f"clip {a.clip}: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} "
              f"at {clip_fps:.2f} fps, {int(cap.get(cv2.CAP_PROP_FRAME_COUNT))} frames (looping)")
    else:
        cap = open_camera(a.camera)
        if cap is None:
            sys.exit(f"cannot open camera {a.camera}; run --list")
        clip_fps = None
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"camera {a.camera}: got {w}x{h}, reported {cap.get(cv2.CAP_PROP_FPS):.1f} fps"
              + ("" if (w, h) == (OUT_W, OUT_H) else f" (asked for {OUT_W}x{OUT_H}; letterboxing)"))

    monitors = get_monitors()
    mon = monitors[a.monitor] if a.monitor is not None else monitors[-1]
    print(f"full screen on monitor {monitors.index(mon)} ({mon.width}x{mon.height}); keys: q quit, b black, space pause")
    if (mon.width, mon.height) != (OUT_W, OUT_H):
        print(f"warning: monitor is {mon.width}x{mon.height}; set the HDMI display to {OUT_W}x{OUT_H} @ 60 Hz")
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.moveWindow(WINDOW, mon.x, mon.y)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    black = np.zeros((OUT_H, OUT_W, 3), np.uint8)
    out, show_black, paused = black, False, False
    n, t_mark, t_next = 0, time.perf_counter(), time.perf_counter()
    try:
        while True:
            if not paused:
                ok, frame = cap.read()
                if not ok and a.clip:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = cap.read()
                if not ok:
                    print("source stopped delivering frames")
                    break
                out = letterbox(frame)
                n += 1
                now = time.perf_counter()
                if now - t_mark >= 5.0:
                    print(f"source {n / (now - t_mark):.1f} fps")
                    n, t_mark = 0, now
            cv2.imshow(WINDOW, black if show_black else out)

            wait_ms = 1
            if clip_fps and not paused:  # pace clips at their own rate; if behind, don't burst to catch up
                now = time.perf_counter()
                t_next = max(t_next + 1.0 / clip_fps, now)
                wait_ms = max(1, int((t_next - now) * 1000))
            key = cv2.waitKey(wait_ms) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("b"):
                show_black = not show_black
                print("black frame", "ON" if show_black else "OFF")
            elif key == ord(" "):
                paused = not paused
                n, t_mark = 0, time.perf_counter()
                t_next = t_mark
                print("paused" if paused else "running")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
