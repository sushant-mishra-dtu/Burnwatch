# BurnWatch: context for every Claude Code session

**What it is:** an FPGA-accelerated open-burning smoke detector. Phone camera → laptop (stands in for a CCTV DVR's HDMI output) → HDMI → PYNQ-Z2. The PL (FPGA) turns each 1280×720 frame into 3,600 tile smoke scores (80×45 tiles of 16×16 px). The ARM (Python) runs the region and state logic. AWS Lambda checks each suspect frame with an NVIDIA Nemotron vision model (NVIDIA's hosted API), logs it and sends an email alert. Only one JPEG per event leaves the box.

**Event:** Environmental Hacks 2026, build window 8–11 Oct 2026. Judges watch a video of 3 minutes or less and read the public repo. One working feature beats five half-done ones.

**Hardware:** PYNQ-Z2 (Zynq-7020, `xc7z020clg400-1`, Cortex-A9 armv7l, PYNQ image v`___`), a Windows laptop with HDMI out, and phones. No other sensors, no purchases.

## When the user says "continue"
Follow the **"continue" protocol at the top of [PROGRESS.md](PROGRESS.md)**: pick your next task there, run its prompt from PROMPTS.md, update PROGRESS.md (status, notes, facts, log), commit and push. Your owner name in PROGRESS.md is `Claude Code`. After finishing **any** prompt, even one pasted by hand, update its row in PROGRESS.md the same way.

## Repo layout
```
detector/   golden.py (integer reference = THE SPEC), config.py (all constants),
            regions.py, state.py. Runs on the laptop and on the PYNQ.
device/     PYNQ runtime: capture loop, LEDs, MQTT, S3 upload, offline queue, pl_engine.py
hls/        Vitis HLS tile engine, C testbench, run_hls.tcl, Vivado build tcl
cloud/      SAM template, Lambda verifier, IoT/IAM setup scripts, cameras.json
tools/      camfeed.py, viewer.py, eval_clips.py, dump_golden.py, bench.py, gen_header.py
testdata/   labels.csv (clips themselves are git-ignored)
docs/       architecture figure, results.md
```

## Hard rules
- `detector/golden.py` is the spec. The scoring path uses integer math only (numpy int32/uint8, no floats). The HLS core must match it bit for bit, and any change to golden.py means regenerating the HLS test vectors.
- Every shared format (topics, JSON, S3 metadata, UDP packets, HLS registers, test vectors) is defined in `docs/contracts.md`, and `tools/contracts.py` is its executable copy. Code against it, and never invent field names.
- Every threshold and weight lives in `detector/config.py`. In HLS they are runtime AXI-Lite registers, so tuning never needs a rebuild.
- Device code runs on PYNQ's Python (armv7l, inside the PYNQ venv): numpy and cv2 are available, but scipy/torch/sklearn are not. Add only pure-Python deps (paho-mqtt, boto3).
- Secrets (`*.pem`, `*.key`, `.env`, `device/certs/`) are never committed.
- Honest claims only. Do not claim "ML", "AI on the edge", "low power" or "regulatory-grade". Every number in the README comes from a script in this repo.
- The ARM-only pipeline must keep working end to end. The PL is an accelerator swapped in behind the same interface (`TileEngine.step(rgb, update_this_frame) -> (scores[45,80], gate, changed)`, see `docs/contracts.md` section 6).
- AWS region `ap-south-1` for everything. The verifier calls NVIDIA's hosted API; its key is the NoEcho SAM parameter `NvidiaApiKey` (Lambda env `NVIDIA_API_KEY`) and lives only in the git-ignored `cloud/.env`.
- Keep it small. Before adding a dependency, a service or an abstraction, ask whether the 3-minute video needs it.
