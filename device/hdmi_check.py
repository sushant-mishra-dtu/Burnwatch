"""Check the HDMI ingest on the PYNQ-Z2: lock to the laptop's output, measure readframe() fps, save 3 frames.

Run on the board as root inside the PYNQ venv:
    sudo ./device/run.sh device/hdmi_check.py [--frames 100] [--out /home/xilinx/burnwatch/frames]

The laptop must already be sending 1280x720 @ 60 Hz to HDMI IN (tools/camfeed.py full screen on that output),
because hdmi_in.configure() blocks until the input locks.
"""
import argparse
import os
import threading
import time

import cv2
import numpy as np
from pynq.lib.video import PIXEL_RGB
from pynq.overlays.base import BaseOverlay


def main():
    ap = argparse.ArgumentParser(description="PYNQ-Z2 HDMI IN check")
    ap.add_argument("--frames", type=int, default=100, help="frames to time")
    ap.add_argument("--out", default="/home/xilinx/burnwatch/frames", help="where the 3 PNGs go")
    a = ap.parse_args()

    if os.geteuid() != 0:
        print("warning: not root; loading the overlay usually needs sudo (use device/run.sh)")
    os.makedirs(a.out, exist_ok=True)

    print("loading base.bit ...")
    base = BaseOverlay("base.bit")
    hdmi_in = base.video.hdmi_in

    print("configure() BLOCKS until HDMI IN locks: the laptop must already output 1280x720 @ 60 Hz.")
    done = threading.Event()

    def nag():  # configure() can't be interrupted cleanly, so at least say what to check
        while not done.wait(10):
            print("  still no lock: check cable in HDMI IN (not OUT), laptop display 1280x720 @ 60 Hz, "
                  "Extend mode, camfeed full screen on that display")

    threading.Thread(target=nag, daemon=True).start()
    try:
        hdmi_in.configure(PIXEL_RGB)
        done.set()
        hdmi_in.start()
        print("locked:", hdmi_in.mode)
        if (hdmi_in.mode.width, hdmi_in.mode.height) != (1280, 720):
            print("warning: expected 1280x720; change the laptop's display mode for this output")

        f = hdmi_in.readframe()  # first frame can be stale; don't time it
        f.freebuffer()
        save_at = {0, a.frames // 2, a.frames - 1}
        saved = []
        t0 = time.perf_counter()
        for i in range(a.frames):
            f = hdmi_in.readframe()
            if i in save_at:
                saved.append(np.array(f))  # copy out of the DMA buffer before giving it back
            f.freebuffer()
        dt = time.perf_counter() - t0
        print(f"readframe: {a.frames} frames in {dt:.2f} s = {a.frames / dt:.1f} fps "
              f"(capped by the input rate, 60 Hz)")

        stamp = time.strftime("%Y%m%d-%H%M%S")
        for k, rgb in enumerate(saved):
            path = os.path.join(a.out, f"hdmi_{stamp}_{k}.png")
            cv2.imwrite(path, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            r, g, b = (rgb[..., c].mean() for c in range(3))
            print(f"saved {path}  {rgb.shape} mean R={r:.0f} G={g:.0f} B={b:.0f}")
        print("colour check: point the phone at something red; mean R should be clearly the largest.")
    finally:
        done.set()
        hdmi_in.close()


if __name__ == "__main__":
    main()
