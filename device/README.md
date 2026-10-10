# device/

The PYNQ-Z2 runtime: HDMI capture loop, LEDs, MQTT to AWS IoT Core, S3 upload, offline queue, and `pl_engine.py` (the PL tile engine behind the same `step()` interface as `detector/golden.py`).

| File | What it does |
|---|---|
| `run.sh` | Runs any device script as root inside the PYNQ venv, from the repo root (`PYTHONPATH` set so `detector/` imports work). |
| `hdmi_check.py` | Locks to HDMI IN, prints the video mode, times 100 `readframe()` calls, saves 3 PNGs. |

## Copy the repo to the board

The board's IP is in PROGRESS.md under Facts (USB/Ethernet direct link default: `192.168.2.99`). Log in as `xilinx`.

With internet on the board:

```bash
ssh xilinx@<pynq-ip>
git clone https://github.com/sushant-mishra-dtu/Burnwatch.git ~/burnwatch
```

Without internet, copy from the laptop (PowerShell has `ssh`/`scp`):

```bash
ssh xilinx@<pynq-ip> mkdir -p /home/xilinx/burnwatch
scp -r detector device tools xilinx@<pynq-ip>:/home/xilinx/burnwatch/
```

Update later with `git pull` on the board, or run the same `scp` again.

## HDMI check

1. **Cable:** laptop HDMI out → the board's **HDMI IN** port (not HDMI OUT).
2. **Laptop display settings:** select the new display, choose **Extend these displays**, resolution **1280 × 720**, and under Advanced display a refresh rate of **60 Hz**.
3. **Laptop:** find the camera and the 1280 × 720 display, then show the feed full screen on it:
   ```bash
   python tools/camfeed.py --list
   python tools/camfeed.py --camera 1 --monitor 2
   ```
   Keys in the feed window: `q` quit, `b` black frame, `space` pause. The window never shows text, because the board analyses it.
4. **Board:** `configure()` blocks until HDMI locks, so start this only once the feed is on screen:
   ```bash
   cd ~/burnwatch && bash device/run.sh device/hdmi_check.py
   ```
   Expect `locked: VideoMode: width=1280 height=720 bpp=24`, a readframe rate near 60 fps, and 3 PNGs in `/home/xilinx/burnwatch/frames/`.
5. **Look at the frames** on the laptop:
   ```bash
   scp "xilinx@<pynq-ip>:/home/xilinx/burnwatch/frames/*.png" .
   ```

## Troubleshooting

- **Stuck at "configure() BLOCKS"**: there's no lock. The laptop output must be exactly 1280 × 720 @ 60 Hz. Press `Ctrl-C`; if that doesn't return, `sudo pkill -f hdmi_check` from a second SSH session.
- **Extend, not Duplicate.** Duplicate forces the laptop panel's mode onto HDMI and mirrors the desktop into the feed.
- **Try another cable** or another HDMI port/adapter. Turn off HDR and variable refresh rate for that display.
- **Overlay busy:** if a Jupyter notebook holds the base overlay or `hdmi_in`, shut down that kernel first.
- **Colours look wrong:** point the phone at something red. `hdmi_check` prints the mean of each channel, and R should be the largest. If B is, the pixel format isn't `PIXEL_RGB`.
- **`date` must be correct.** The board has no battery-backed clock, and a wrong date breaks TLS to AWS IoT and S3 request signing. Check with `date`, and set it with `sudo date -s "2026-10-10 14:00:00"` if NTP can't reach the internet.
