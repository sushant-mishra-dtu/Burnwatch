# BurnWatch: build prompts

Paste each prompt into Claude Code opened at the repo root, where [CLAUDE.md](CLAUDE.md) gives it the shared context. Timing and owners are in [BUILD_PLAN.md](BUILD_PLAN.md). Fill in `<…>` placeholders before pasting.

> **You usually don't paste these.** Type `continue` in Claude Code or Codex. The agent picks its next task from [PROGRESS.md](PROGRESS.md), runs the matching prompt below, and updates its status. **Agents keep this file current:** if a fact learned during the build (region, version, file name, API) makes a later prompt wrong, the agent edits that prompt here and logs the change under "Plan changes" in PROGRESS.md. Paste a prompt by hand only to redo or jump to a specific step. The agent still updates PROGRESS.md afterwards.

Tips:
- One prompt per session, or `/clear` between prompts. Each prompt stands alone, and `continue` works after a `/clear` because the state lives in PROGRESS.md.
- When a prompt says "show me X before continuing", stop and check it. Those are the places where a silent mistake costs hours.
- Commit after every prompt (`git add -A && git commit`). Small commits also show the judges a real build history.

---

## P0: Repo bootstrap (H0)

````text
Bootstrap the BurnWatch repo in this folder (read CLAUDE.md first).

1. Create the directory layout from CLAUDE.md with a short README.md in each folder saying what goes there.
2. Root README.md skeleton with these headings and one placeholder line each: Problem, What BurnWatch does, Architecture, PL/PS split, AWS, Results, Limitations, How to run, Credits and licences, "Built 8–11 October 2026 for Environmental Hacks 2026".
   The Credits section lists: Xilinx/PYNQ (BSD-3-Clause), paho-mqtt (EPL-2.0/EDL-1.0), boto3 (Apache-2.0), anthropic Python SDK (MIT), NumPy (BSD-3-Clause), OpenCV (Apache-2.0), AWS SAM CLI (Apache-2.0).
3. LICENSE: MIT, copyright 2026 the BurnWatch team.
4. .gitignore: Python, Vivado/HLS build outputs (*.jou, *.log, .Xil/, hls/proj*/, vivado/proj*/, *.runs/, *.cache/), testdata/clips/, testdata/golden/, *.npy, *.pem, *.key, *.crt, .env, device/certs/, .aws-sam/, __pycache__/.
   Keep the final *.bit and *.hwh files trackable under overlays/.
5. requirements-laptop.txt (numpy, opencv-python, mss, screeninfo, boto3, paho-mqtt, pytest) and requirements-device.txt (paho-mqtt, boto3; numpy and cv2 already ship with PYNQ).
6. git init if needed, and make the first commit "Bootstrap BurnWatch repo".

Don't write any feature code yet.
````

---

## P0b: Contracts for parallel agents (H0, Claude Code)

````text
Write docs/contracts.md: the single source of truth for every format shared between folders, because two coding agents on two machines will build against it in parallel. Take the details from PROMPTS.md (P2, P4, P5, P6, P7, P8) and CLAUDE.md. Where those disagree, flag it to me rather than picking one.

Sections, each with an exact example:
1. MQTT topics: burnwatch/<camera>/events | verdict | heartbeat, QoS, the client_id rule.
2. Event JSON (device → IoT Core) and verdict JSON (Lambda → device): every field, its type and units.
3. S3: bucket key pattern, x-amz-meta-* keys and their encoding (bbox as a JSON string).
4. DynamoDB item: keys and attributes.
5. UDP viewer packet: struct format string, byte order, field list, total size.
6. Golden model API (TileEngine.step signature, output shapes and dtypes) and Params field names.
7. HLS: top-function arguments, register names in the same order as Params, frame word packing (R | G<<8 | B<<16), score layout.
8. Test-vector files: directory layout, file names, binary formats, params.txt / expect.txt syntax.
Also create tools/contracts.py with the UDP struct format and topic helpers, so code imports them instead of copying.
Commit as "P0b: shared contracts".
````

---

## P1: Camera feed + PYNQ HDMI check (H1, D)

````text
Two small tools for the camera → laptop → HDMI → PYNQ ingest path.

A) tools/camfeed.py (runs on the Windows laptop)
- Source: --camera N (DroidCam / Phone Link camera shows up as a webcam) or --clip path.mp4 (loops; used later to replay test clips through the real HDMI path).
- Shows the source borderless and full screen on a chosen monitor (--monitor N, enumerate with screeninfo, and print the list when started with --list). Resize/letterbox to exactly 1280x720. No text or overlay on this window, ever: the PYNQ analyses it.
- Hotkeys: q quit, b toggle a black frame (to test the global gate), space pause.
- Request 1280x720 from the camera, and print the resolution and fps it actually got.

B) device/hdmi_check.py (runs on the PYNQ as root inside the PYNQ venv)
- Load BaseOverlay("base.bit"), configure hdmi_in with PIXEL_RGB, start it, and print hdmi_in.mode.
- Warn first that configure() blocks until HDMI locks, so the laptop must already be outputting 1280x720 @ 60 Hz.
- Read 100 frames and report readframe fps. Save 3 frames as PNG to /home/xilinx/burnwatch/frames/ (convert RGB→BGR for cv2.imwrite), free/close the buffers properly, and close hdmi_in on exit (try/finally).
- Also write device/run.sh, which runs any device script as root inside the PYNQ venv (source /etc/profile.d/pynq_venv.sh; check that this path exists on the image and adapt if not).

C) device/README.md: how to copy the repo to the board (scp or git clone), how to run hdmi_check, and the troubleshooting list: display mode 1280x720 @ 60, Extend vs Duplicate, try another cable, `date` must be correct.

Keep both scripts under ~150 lines. Show me how to run each.
````

---

## P2: Golden model, which is the spec (H3, D)

````text
Implement detector/config.py and detector/golden.py: the integer reference of the PL tile engine. Later an HLS core must match this bit for bit, so follow the spec exactly, keep it simple, and document every formula in docstrings. Integer numpy only (uint8/int32), no floats anywhere in the scoring path.

SPEC v1
Input: rgb uint8 [H, W, 3]. Full mode: H=720, W=1280, TILE=16. ARM-fast mode: rgb[::2, ::2] (360x640) with TILE=8. Both give the same 45 x 80 tile grid.

Per pixel:
  Y = (77*R + 150*G + 29*B) >> 8
  S = max(R,G,B) - min(R,G,B)
  Sobel on Y, interior pixels only:
    Gx = (Y[r-1,c+1] + 2*Y[r,c+1] + Y[r+1,c+1]) - (Y[r-1,c-1] + 2*Y[r,c-1] + Y[r+1,c-1])
    Gy = (Y[r+1,c-1] + 2*Y[r+1,c] + Y[r+1,c+1]) - (Y[r-1,c-1] + 2*Y[r-1,c] + Y[r-1,c+1])
    E  = (|Gx| + |Gy|) >> 3          # 0..255
  E = 0 on the 1-pixel image border.

Per tile (N = TILE*TILE pixels, LOG2N = log2(N)):
  mE = sum(E) >> LOG2N ; mY = sum(Y) >> LOG2N ; mS = sum(S) >> LOG2N
  xE, xY, xS = mE << 8, mY << 8, mS << 8          # Q8 fixed point

Per-tile baselines bE, bY, bS: Q8 int32 arrays, range 0..65280 (fits uint16 in HW).

Score per tile:
  edge_drop  = max(0, bE - xE)
  grey_shift = max(0, |bY - (128<<8)| - |xY - (128<<8)|)      # moved toward mid-grey
  sat_ok     = (mS <= SAT_MAX) and (xS <= bS + SAT_TOL)
  raw        = (W_EDGE*edge_drop + W_GREY*grey_shift) >> SCORE_SHIFT
  score      = min(raw, 255) if sat_ok else 0                  # uint8
  flagged    = score >= T_FLAG

Global gate:
  changed = number of tiles with |xY - bY| > T_GLOBAL
  gate    = changed > GATE_TILES        # reported with THIS frame's scores; the caller ignores gated frames

Reset frame (docs/contracts.md F4): when reset is set, b = x for all three features BEFORE scoring, so that frame
scores 0 with changed = 0 and gate = False, whatever state was left over. A new engine starts with reset pending.

Baseline update (state carried between frames; prev_gate = gate of the previous frame):
  if reset:                 nothing more (b was already set before scoring)
  elif update_this_frame:
      k = K_FAST if prev_gate else K_SLOW
      for tiles where (prev_gate or not flagged):     # flagged tiles are frozen so smoke isn't absorbed
          b += (x - b + ((1 << k) >> 1)) >> k          # numpy >> on int32 is an arithmetic shift; k = 0 snaps b = x (F7)
  then prev_gate = gate

Starting constants (config.py, one dataclass Params with these defaults; fields in HLS register order per
docs/contracts.md F2: K_SLOW, K_FAST, W_EDGE, W_GREY, SCORE_SHIFT, T_FLAG, SAT_MAX, SAT_TOL, T_GLOBAL, GATE_TILES,
UPDATE_EVERY_ARM, UPDATE_EVERY_PL; Params validates the ranges in contracts.md section 6; P3's ARM-only constants
go in a separate dataclass):
  W_EDGE=4, W_GREY=4, SCORE_SHIFT=8, T_FLAG=40, SAT_MAX=40, SAT_TOL=4<<8,
  T_GLOBAL=24<<8, GATE_TILES=1440, K_SLOW=6, K_FAST=0 (snap after a gated frame, contracts.md F7; range 0-15),
  UPDATE_EVERY_ARM=1, UPDATE_EVERY_PL=20   (same forgetting time in seconds at ~3 fps vs 60 fps)

API:
  class TileEngine:  __init__(params, tile=16); reset(); step(rgb, update_this_frame=True) -> (scores uint8[45,80], gate bool, changed int)
  It also exposes the internal state (bE, bY, bS, prev_gate) so the HLS test vectors can include it.
  Vectorise with reshape(45, TILE, 80, TILE).sum(axis=(1,3)); no Python loops over pixels.

Tests (tests/test_golden.py, pytest, synthetic frames only):
  1. Textured background (random grey checkerboard), then a Gaussian-blurred grey patch over one region for 30 frames → tiles in the patch flagged, others not.
  2. Dark flat background, then a semi-transparent grey overlay → grey_shift drives the score.
  3. Saturated red patch → score 0 (sat gate).
  4. Whole frame +40 brightness → gate=True; the next frames re-baseline fast.
  5. Flagged tiles' baselines don't move while flagged.
  6. Full mode and ARM-fast mode both return shape (45, 80).
  7. Determinism: same input sequence → identical outputs.

Also write tools/gen_header.py, which writes hls/config.h (#define for each constant) from config.py.
Then write tools/dump_golden.py (moved here from P8, docs/contracts.md F6): spec in the P8 "Test vectors" paragraph
and contracts.md section 8. Generate the --synthetic set first (no clips needed) so Codex can start P8.

Finally, time step() on this laptop for full and fast mode and print ms/frame. After the tests pass, show me a heat map of test 1 rendered with cv2 (save to docs/golden_test1.png).
````

---

## P3: Regions, state machine, clip evaluator (H5, D)

````text
Build the ARM-side logic on top of detector/golden.py. Read detector/golden.py and detector/config.py first. Floats are fine here: this part never goes to HW.

1. detector/regions.py: RegionTracker
   - Input per frame: scores [45,80], gate, timestamp (seconds, injected; never call time.time() inside).
   - Gated frames: skip and keep state.
   - Temporal smoothing: s = 0.6*s + 0.4*scores; mask = s >= T_FLAG.
   - Connected components (8-connected) on the mask with cv2.connectedComponentsWithStats. Keep the largest component with >= MIN_TILES (default 4).
   - Track it across frames (bbox overlap with the previous one). Keep a history of (t, area, top_row, centroid_row).
   - candidate() returns a region only if it has persisted >= PERSIST_S (default 6 s, configurable) AND over that window it grew >= 25% in area OR its top edge moved up >= 1 tile OR centroid_row decreased. Rising or spreading is the smoke cue.
   - Supports ignore masks (tile sets ignored until time T) for the REJECTED cooldown.
   - The bbox is returned in full-res pixel coordinates (tiles * 16).

2. detector/state.py: StateMachine with states CLEAR, SUSPECT, CONFIRMED, REJECTED
   - CLEAR → SUSPECT when there is a candidate AND >= 120 s since the last upload for this camera. It emits an "upload" action with the event dict:
     {camera, state, score (mean score in region / 255, 2 decimals), tiles, bbox, s3_key "frames/<camera>/<ts>.jpg", ts}
   - SUSPECT → CONFIRMED on a verdict whose state is "CONFIRMED" (the cloud applies CONF_THRESHOLD; docs/contracts.md F3).
   - SUSPECT → REJECTED on a verdict whose state is "REJECTED": add the region's tiles to the ignore mask for 180 s, emit a "rebaseline" action (the caller calls engine.reset(), contracts.md F7), then CLEAR.
   - Ignore a verdict whose ts isn't the open event's ts. Event/verdict fields: docs/contracts.md section 2 (ts = integer Unix seconds).
   - CONFIRMED → CLEAR after the region has been gone for 60 s.
   - SUSPECT with no verdict for 90 s stays SUSPECT (amber) and emits "verdict_timeout" once.
   - Pure logic: actions are returned, never executed (no network, no LEDs). Unit tests drive it with fake clocks and verdicts.

3. tools/eval_clips.py
   - Reads testdata/labels.csv (columns: clip, label in {smoke, person, cloth, lights, bump, exposure, steam, empty}, smoke_start_s, smoke_end_s, notes).
   - Runs golden (ARM-fast mode, frames resized to 1280x720 first) + RegionTracker + StateMachine with verdicts stubbed as "no verdict" on every clip at its native fps, subsampled to --fps (default 3) to mimic the ARM.
   - Per clip: detected (reached SUSPECT), time-to-SUSPECT after smoke_start, false SUSPECTs (SUSPECT outside the smoke window or on a non-smoke clip).
   - Writes docs/test_table.md (one row per clip + totals: detected / missed / false alarms) and prints it.
   - --sweep T_FLAG=30,40,50 PERSIST_S=4,6,8 runs a small grid and prints the summary per combination.

4. tools/replay_viewer.py: plays a clip with the tile heat map (only tiles with score >= T_FLAG, alpha-blended, colormap), the region bbox, the state badge and the frame time. Keys: space pause, ←/→ step, q quit. Used for tuning.

Create testdata/labels.csv with a header and example rows matching the clip names in BUILD_PLAN.md section 4.
Tests: tests/test_regions.py and tests/test_state.py.
Then run eval_clips.py on whatever clips are in testdata/clips/ and show me the table.
````

---

## P4: AWS stack (H1, C)

````text
Create the AWS infrastructure for BurnWatch in cloud/ using AWS SAM (template.yaml) plus small Python setup scripts (the laptop runs Windows: no bash-only scripts). Region ap-south-1.

template.yaml (parameters: AlertEmail, NvidiaApiKey (NoEcho: pass it with --parameter-overrides at deploy time and never save it in samconfig.toml), VerifierModelId (the Nemotron vision model ID recorded in PROGRESS.md Facts), NimBaseUrl default "https://integrate.api.nvidia.com/v1", ConfidenceThreshold default 0.6):
- S3 bucket for frames. Lifecycle rule deletes frames/ after 7 days. Block all public access. ObjectCreated notification on prefix frames/ suffix .jpg → VerifyFunction.
- DynamoDB table burnwatch-events: PK camera (S), SK ts (N), on-demand billing.
- SNS topic burnwatch-alerts with an email subscription to AlertEmail.
- VerifyFunction (Python; runtime must match the local Python version used by `sam build` — check `python --version`), timeout 60 s, memory 512 MB, CodeUri verify/ relative to cloud/template.yaml (resolves to cloud/verify/; handler only stubbed here; P5 fills it in).
  Env: TABLE, TOPIC_ARN, NVIDIA_API_KEY, NIM_BASE_URL, MODEL_ID, CONF_THRESHOLD, IOT_ENDPOINT (parameter), BUCKET.
  IAM: s3:GetObject on the bucket, dynamodb:PutItem on the table, sns:Publish on the topic, iot:Publish on topic/burnwatch/*/verdict, rekognition:DetectLabels. No Bedrock permission: the verifier calls NVIDIA's hosted API over HTTPS.
- Outputs: bucket name, table name, topic ARN.

cloud/setup_iot.py (boto3; idempotent, safe to re-run):
- Get the ATS endpoint (describe_endpoint endpointType iot:Data-ATS) and print it.
- Create thing burnwatch-<camera> (arg --camera, default rwa-gate-2).
- create_keys_and_certificate(setAsActive=True); save cert/private key to device/certs/ (git-ignored); download AmazonRootCA1.pem there too.
- Policy burnwatch-device: iot:Connect on client/burnwatch-*; iot:Publish on topic/burnwatch/*; iot:Subscribe on topicfilter/burnwatch/*; iot:Receive on topic/burnwatch/*.
- Attach the policy to the cert and the cert to the thing.
- Write device/.env with IOT_ENDPOINT, CAMERA_ID, CLIENT_ID=burnwatch-<camera>, cert paths, BUCKET, AWS_REGION.

cloud/setup_device_iam.py:
- IAM user burnwatch-device whose only permission is s3:PutObject on arn:aws:s3:::<bucket>/frames/*.
- Create an access key and append AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY to device/.env.
- Print a warning that this is a hackathon shortcut and that production should use the IoT credentials provider (role alias), and add the same note to cloud/README.md.

cloud/verify/cameras.json (inside CodeUri so the Lambda bundles it): {"rwa-gate-2": {"name": "RWA Gate 2", "address": "<area>, New Delhi", "timezone": "Asia/Kolkata"}}.

device/.env.example: same keys as device/.env with placeholder values (committed; the real .env never is).

cloud/README.md: exact deploy commands (sam build; sam deploy --guided first time), then the setup scripts, then "confirm the SNS email". Also the IoT MQTT test client steps for the video (subscribe to burnwatch/#).

Formats (topics, policy, S3 keys/metadata, DynamoDB): docs/contracts.md sections 1–4. You may create cloud/verify/app.py
(stub) and cloud/verify/cameras.json; Claude Code owns cloud/verify/ from P5 on (contracts.md F6).
Before deploying: show me the template and the IAM policies and wait for my OK. Then deploy, run the setup scripts, and verify: publish a test message to burnwatch/test from the laptop using device/.env (small paho-mqtt script cloud/mqtt_smoke_test.py) and confirm it appears in the IoT test client.
````

---

## P5: Lambda verifier with NVIDIA Nemotron (H3, C)

````text
Implement cloud/verify/app.py, the S3-triggered verifier. Read cloud/template.yaml and cloud/README.md first.

Flow per S3 ObjectCreated event (key frames/<camera>/<ts>.jpg):
1. head_object → metadata set by the device (x-amz-meta-): camera, ts, score, tiles, bbox (JSON string). get_object → JPEG bytes.
2. Call the NVIDIA Nemotron vision model on NVIDIA's hosted API: OpenAI-compatible chat completions at NIM_BASE_URL, model MODEL_ID (recorded in PROGRESS.md Facts), key NVIDIA_API_KEY. Use stdlib urllib (no SDK), timeout 30 s, temperature 0, max_tokens 1024.
   - First, cloud/nim_probe.py makes one call from the laptop (key read from the git-ignored cloud/.env, never printed or logged) to confirm: the model accepts a base64 JPEG and in which form (OpenAI image_url data URL or an inline <img> tag), and whether it honours response_format json_schema. Record the answers under Facts.
   - Image first, then the text prompt below.
   - Ask for JSON (response_format json_schema if the probe showed it works, otherwise a JSON-only instruction) with exactly these required fields, no others:
       is_smoke (boolean), confidence (number 0–1),
       likely_source (enum: "open waste burning", "leaf or biomass burning", "incense or small flame", "cooking or tandoor", "vehicle exhaust", "steam or fog", "dust", "not smoke", "unclear"),
       evidence (string, one sentence), complaint_text (string)
   - Parse strictly: strip any <think>...</think> block and ``` fences, then reject missing or extra fields, wrong types, confidence outside 0-1 and unknown likely_source values. A finish_reason other than "stop", an HTTP error or a parse failure all count as a failed verification.
3. If the Nemotron call fails: fall back to Rekognition DetectLabels (MinConfidence 60). is_smoke = any label named Smoke; confidence = that label's confidence/100; likely_source "unclear"; evidence lists the top labels; complaint_text "". Record verifier="rekognition" vs "nemotron".
4. PutItem to DynamoDB: camera, ts, time_ist, score, tiles, bbox, s3_key, is_smoke, confidence, likely_source, evidence, complaint_text, verifier, latency_ms, verify_ms (types and definitions: docs/contracts.md section 4).
5. If is_smoke and confidence >= CONF_THRESHOLD: SNS publish.
   Subject: "BurnWatch: possible open burning at <camera name>".
   Body: time (IST), camera name + address (cameras.json), likely source, evidence, a presigned GET URL for the photo (expires in 12 h), and the complaint draft under the heading "DRAFT – review before you submit it to your RWA or municipal helpline. Nothing has been sent automatically."
6. Publish the verdict to IoT topic burnwatch/<camera>/verdict via boto3 iot-data (endpoint_url https://IOT_ENDPOINT), QoS 1: {camera, ts, is_smoke, confidence, likely_source, state: "CONFIRMED" if is_smoke and confidence >= CONF_THRESHOLD else "REJECTED", verifier, evidence} (docs/contracts.md section 2, F3/F5). If both Nemotron and Rekognition fail, publish nothing; the device times out.
7. Log one line of JSON with the full verdict (this is filmed in CloudWatch for the video).

Prompt text for the verifier (keep it in a constant, inject camera name, local time, bbox):
"You are checking one CCTV frame that an on-device detector flagged as possible smoke. The flagged region is the box [x1, y1, x2, y2] in a 1280x720 image: <bbox>. Camera: <name>, <address>. Local time: <time IST>.
Decide whether smoke is actually visible in or near that region and what is most likely producing it. Be skeptical: steam from kettles or vents, fog, dust, clouds, grey walls or cloth, motion blur and people are common false triggers. Set is_smoke true only if you can see smoke in the image. confidence is your probability that smoke is present. evidence is one sentence naming what you see that supports the verdict.
Write complaint_text only if is_smoke is true and the source looks like open burning of waste, leaves or biomass. Make it a factual 3–4 sentence complaint to the local RWA or municipal helpline stating the place, the time and what is visible. Do not guess who is responsible. Otherwise complaint_text is an empty string."

Also:
- No extra Lambda dependencies: urllib from the standard library, boto3 from the Lambda runtime.
- cloud/test_verify.py: uploads a local JPEG with the right metadata to the bucket (laptop credentials), then polls DynamoDB until the row appears, then prints the row. Add 3 sample images to testdata/samples/ (I will drop them in: smoke, steam, empty). Run it on each and show me the verdicts.
- Unit-test the pure parts (metadata parsing, message formatting, Rekognition mapping) with pytest and no AWS calls.
````

---

## P6: Device runtime (P6a at H5 on the laptop, P6b at H8 on the PYNQ; C+D)

````text
Build the PYNQ runtime in device/. Read CLAUDE.md, detector/*.py and device/.env.example first. It must run on PYNQ's Python (armv7l): only numpy, cv2, paho-mqtt, boto3 and the pynq library.

PART A: device/cloud.py (test it from the laptop first, with a JPEG from testdata/samples/)
- MQTT with paho-mqtt to IOT_ENDPOINT:8883 with TLS (CA, cert, key from .env), client_id CLIENT_ID. paho-mqtt 2.x requires mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=...). Pin the version in requirements-device.txt and code for that version.
- Auto-reconnect; subscribe to burnwatch/<camera>/verdict on every (re)connect; verdicts go onto a thread-safe queue.
- publish_event(event): topic burnwatch/<camera>/events, QoS 1.
- heartbeat(): burnwatch/<camera>/heartbeat every 60 s with {ts, state, fps, mode, queue_len}.
- upload_frame(jpeg_bytes, event): boto3 put_object to BUCKET/frames/<camera>/<ts>.jpg with Metadata {camera, ts, score, tiles, bbox(json)} and ContentType image/jpeg, using the scoped keys from .env.
  Upload first, then publish the event.
- Offline queue: if either fails, write event.json + frame.jpg under /home/xilinx/burnwatch/queue/<ts>/ (on the laptop: ./queue/) and retry oldest-first every 30 s once connected. Survives restarts.
- On startup, check that the system clock is plausible (year >= 2026). If not, log a loud error explaining that TLS will fail and how to fix it (NTP, or `sudo date -s` from an HTTP Date header).
- cloud_selftest.py (client_id burnwatch-<camera>-selftest so it can run while the board is connected): connect, publish a test event, upload a sample JPEG, wait up to 60 s for the verdict, and print it.

PART B: device/main.py (on the PYNQ)
- Args: --mode arm|pl (pl imports device/pl_engine.py, which comes later; ARM is the default), --camera, --viewer-ip, --fps-cap, --eval-log path.csv.
- Load BaseOverlay, hdmi_in.configure(PIXEL_RGB), start. Loop: readframe → copy what's needed → free the buffer.
  ARM mode: golden TileEngine in ARM-fast mode (frame[::2, ::2], TILE=8, UPDATE_EVERY_ARM). PL mode: same step() interface.
- RegionTracker + StateMachine from detector/. Execute the returned actions:
  upload → cv2.imencode JPEG quality 80 of the full-res frame (RGB→BGR) → cloud.upload_frame + publish_event.
  rebaseline → engine.reset() (a REJECTED verdict; contracts.md F7).
  Verdicts from the queue go to the state machine.
- LEDs (base.rgbleds[4] and [5], check the indices on the board): CLEAR green, SUSPECT yellow, CONFIRMED red, REJECTED blue, gated frame = brief white blink on LED 5.
- UDP to --viewer-ip:9999 every processed frame: struct header (magic b"BW01", frame_no u32, ts f64, state u8, gate u8, fps f32, mode u8, bbox 4×u16) + 3600 uint8 scores. Never video.
  Build it with tools/contracts.py (pack_viewer_packet; docs/contracts.md section 5). When a verdict arrives, also send one BWV1 verdict packet (pack_verdict_packet, contracts.md F5).
- Logs one line per state change; heartbeat every 60 s.
- --eval-log writes per-frame (ts, state, gate, region_tiles) for the real-path test table (P11).
- Ctrl-C closes hdmi_in and turns the LEDs off (try/finally).
- device/burnwatch.service: systemd unit running main.py through run.sh, for a clean demo boot. Install instructions in device/README.md.

Do Part A first and show me cloud_selftest.py output from the laptop. Part B: keep main.py readable (< 250 lines) and keep the logic in detector/.
````

---

## P7: Live viewer on the laptop (H8, C)

````text
Write tools/viewer.py, the laptop-side live view that is filmed for the video. It must make clear that the overlay is drawn from the 3,600 numbers the box sends, not from video sent by the box.

- Laptop display setup: Extend mode. The HDMI display (going to the PYNQ) shows tools/camfeed.py full screen; the viewer runs on the laptop's own screen.
- Capture the HDMI monitor with mss (--monitor N; reuse the same enumeration as camfeed.py --list), downscale to 960x540 for display.
- Receive UDP packets on :9999 in a background thread (format in docs/contracts.md section 5; use tools/contracts.unpack_viewer_packet, which also decodes BWV1 verdict packets).
- Draw: tiles with score >= T_FLAG as a translucent heat map (cv2 colormap) on a 45x80 grid, the region bbox, a big state badge (CLEAR green / SUSPECT amber / CONFIRMED red / REJECTED blue), "GATED" when gate=1.
  A side panel shows: device fps, mode (ARM or PL), "bytes received per frame: 3,6xx", "frames sent to cloud: N" (count SUSPECT transitions), the last verdict text (likely_source, confidence and evidence from the latest BWV1 packet).
- If no packet arrives for 3 s, show "NO SIGNAL FROM DEVICE".
- Hotkeys: r start/stop recording the viewer window to an mp4 in recordings/, q quit.
- Also test it without hardware: tools/fake_device.py replays a clip through golden + regions + state and sends the same UDP packets to localhost.
````

---

## P8: HLS tile engine with a bit-exact testbench (H5, F)

````text
Implement the PL tile engine in Vitis HLS in hls/, matching detector/golden.py (spec v1) bit for bit in FULL mode (1280x720, TILE=16). Read detector/golden.py, detector/config.py and hls/config.h first. Part xc7z020clg400-1, clock 10 ns.

Interface (top function tile_engine; exact signature, register order and widths: docs/contracts.md section 7; reset frames follow contracts.md F4, b = x before scoring):
- frame: const ap_uint<32>*, m_axi bundle=gmem0, offset=slave, depth 921600. One pixel per 32-bit word, packed R | G<<8 | B<<16 (bits 31:24 ignored). Row-major.
- scores: ap_uint<8>*, m_axi bundle=gmem1, offset=slave, depth 3600. Row-major 45x80.
- s_axilite (bundle=control) scalars: reset, update_this_frame, k_slow, k_fast, w_edge, w_grey, score_shift, t_flag, sat_max, sat_tol, t_global, gate_tiles.
  Outputs: gate_out, changed_out, frame_count. Plus return.
  Everything tunable at runtime, no constants baked in except image size and TILE.
- Persistent state as static arrays: bE, bY, bS (uint16, 3600 each, BRAM) and prev_gate.

Implementation notes:
- Target II=1 on the pixel loop and >= 60 fps at 100 MHz (<= 1.66M cycles per frame). Make sure frame reads become AXI bursts (check the burst section of the synthesis report).
- Sobel with two line buffers plus a 3x3 window. Watch the 1-pixel latency: E for pixel (r,c) is only known after row r+1 / column c+1 arrive. Assign it to the tile of (r,c), not of the newest pixel. Border E = 0 exactly as in golden.
- Per tile-row: 80 x 3 accumulators. When a tile row is complete, run a short loop over its 80 tiles: means, score, flag, changed count, baseline update (with the PREVIOUS frame's gate), write 80 scores.
- Signed arithmetic: compute edge_drop, grey_shift and the baseline delta in ap_int with enough bits. The baseline update rounds with + ((1 << k) >> 1) and then an arithmetic right shift, exactly like numpy. k_fast may be 0 (snap b = x, contracts.md F7), so never write 1 << (k-1).
- gate is decided at the end of the frame from changed and becomes prev_gate for the next call.

Test vectors: tools/dump_golden.py (written by Claude Code at the end of P2, contracts.md F6; Codex runs it and reports problems instead of editing it)
- Takes a clip (or a folder of PNGs), resizes to 1280x720, runs golden FULL mode for a sequence of >= 40 frames (including a gated frame: insert a +40 brightness frame at index 20, and use update_this_frame on every frame), and writes testdata/golden/<name>/:
  frame_XXXX.bin (uint32 packed words), scores_XXXX.bin (3600 bytes), expect.txt (per frame: gate changed), params.txt (key value per line).
- Generate vectors for at least: one dhoop clip, the person_walk clip and a synthetic textured clip.

Testbench hls/tb_tile_engine.cpp: for each vector set, reset on frame 0, run all frames, compare scores/gate/changed exactly. Print the first 10 mismatches with (frame, tile_row, tile_col, expected, got) and return non-zero on any mismatch.

hls/run_hls.tcl: csim, csynth, export_design -format ip_catalog. Check which HLS command-line tool is installed (vitis_hls vs vitis-run) and document the exact command in hls/README.md.

Order of work: csim bit-exact first, then synthesis. Show me the csim result, then the synthesis report (latency, II, LUT/FF/BRAM/DSP).
````

---

## P9: Level-2 overlay + PYNQ driver + on-board check (H11, F)

````text
Build a minimal Vivado design around the exported tile_engine IP and a PYNQ driver, then verify bit-exactness on the board. Read hls/README.md and the synthesis report first.

1. hls/build_overlay.tcl (batch mode, same Vivado version as HLS and matching the board's PYNQ image):
   - Project for xc7z020clg400-1. Check that the PYNQ-Z2 board files are installed. If they aren't, stop and tell me: the PS7 DDR/MIO preset must be correct or the board hangs when the bitstream loads.
   - Block design: processing_system7 (board preset), FCLK_CLK0 100 MHz, M_AXI_GP0 → tile_engine s_axi_control, gmem0/gmem1 → S_AXI_HP0 via SmartConnect/interconnect, processor system reset, address map auto-assigned.
   - Validate, generate the wrapper, synthesize and implement, write the bitstream.
   - Copy outputs to overlays/burnwatch_pl.bit and overlays/burnwatch_pl.hwh (same basename; PYNQ needs both).
   - Print the timing summary (WNS must be >= 0) and utilization.
2. device/pl_engine.py: class PLTileEngine with the same API as golden.TileEngine (reset(), step(rgb, update_this_frame) -> scores, gate, changed).
   - Loads the overlay. pynq.allocate buffers: frame (921600 uint32), scores (3600 uint8).
   - Writes registers from Params using the offsets in the HLS-generated driver header (xtile_engine_hw.h), or the overlay's register_map if it's populated. Sets ap_start, polls ap_done.
   - Packs RGB→uint32 with numpy, vectorised. Times the PL call separately from packing.
3. device/pl_check.py (on the board): loads the testdata/golden vector sets (copy them over), runs them through PLTileEngine, compares bit-exact with the expected files, and reports mismatches plus PL ms/frame (preload frames into allocated buffers to measure pure PL time) and pack ms/frame.
   It also runs golden.py FULL mode on the ARM on the same frames and reports ARM ms/frame. These are the numbers for the video.

Be explicit about which numbers mean what. PL time = the tile engine alone, reading a frame from DDR. This level does not include live HDMI: the base overlay is not loaded here, and the README must say so.
````

---

## P10 (stretch, only if P9 is done by ~H17): Level-3 live integration

````text
Goal: run tile_engine on LIVE HDMI frames by adding it to the PYNQ base overlay. Read hls/README.md, device/pl_engine.py and device/main.py first.

1. Find the base overlay sources for our PYNQ version (Xilinx/PYNQ repo, boards/Pynq-Z2/base) and the exact Vivado version they need. Tell me the expected build time, and whether a free HP port (or a port on the existing interconnect) is available for the tile engine's m_axi masters, before changing anything.
2. Plan: add tile_engine to the base block design as a DDR reader (do not insert it into the video stream), connected to a free AXI GP master for control and to an HP port for memory. Keep every existing IP and address unchanged so BaseOverlay and hdmi_in keep working.
3. Rebuild into overlays/base_bw.bit/.hwh. In device/main.py --mode pl-live: hdmi_in writes frames to DDR as usual (configure PIXEL_RGBA so each pixel is one 32-bit word); pass the physical address of the frame hdmi_in just returned straight to tile_engine. No ARM-side copy or pack.
   Verify the byte order of PIXEL_RGBA against our R | G<<8 | B<<16 packing with a solid red / green / blue test frame from camfeed.py. If it differs, add a channel-order register to the HLS core rather than packing on the ARM.
4. Check: the scores from pl-live match golden FULL mode on the same frame (save a few frames + scores and compare offline).
Stop and report if the rebuild fails twice. The ARM version is the shipping version.
````

---

## P11: Benchmarks + final test table (H20, all)

````text
Produce the measured numbers for the video and README. Write tools/bench.py and update tools/eval_clips.py; the results go to docs/results.md.

1. Throughput table, each measured over >= 100 frames with median and p90:
   - ARM full res, golden.py FULL mode (same math as the PL)
   - ARM fast mode (what the live ARM detector runs)
   - PL Level 2: tile engine only, from device/pl_check.py output; plus pack time
   - PL Level 3 live (if done)
   - End-to-end device loop fps in ARM mode (from main.py logs)
   - Per event: bytes uploaded (JPEG size), MQTT bytes; Lambda latency_ms and verify time from DynamoDB (median of the last N events)
   Note the clock speeds and the measurement method under the table.
2. Real-path test table: replay every labelled clip through camfeed.py --clip → HDMI → PYNQ main.py --eval-log, then score the logs with eval_clips.py --from-logs. Write a markdown table: clip, label, detected, time-to-SUSPECT, false alarms, final cloud verdict. Totals row: detected / missed / false alarms.
   Keep the offline (laptop) table next to it, clearly labelled.
3. Limitations section, from what we actually observed (steam, thin smoke, night, wind), each with one sentence on how we would address it.
Don't round numbers up, and every number names the script that produced it.
````

---

## P12: README + architecture figure (H23, C)

````text
Write the final README.md. Read every folder's README, docs/results.md, docs/test_table.md, cloud/README.md and hls/README.md first. Audience: hackathon judges who are not FPGA experts and give the repo ~3 minutes.

Structure:
1. One-line pitch + a GIF or screenshot of the viewer (docs/demo.gif; I'll add it).
2. Problem: open burning in Delhi. Use ONLY the figures and sources in docs/sources.md, with links. If a figure isn't sourced there, leave it out.
3. What it does, in 4 bullets: detects, verifies, alerts, keeps video private ("only one frame per event leaves the box").
4. Architecture figure: docs/architecture.svg, hand-written SVG matching the brief's diagram (camera → laptop/DVR stand-in → HDMI → PL tile engine → ARM state machine → IoT Core / S3 → Lambda → Nemotron (NVIDIA API) → DynamoDB / SNS → verdict back). Readable in light and dark GitHub themes.
5. PL/PS split: the spec table (stage, what it does, resource use from the actual synthesis report), the bit-exact verification story (golden model → HLS testbench → on-board check), and which ladder level we reached, stated precisely.
6. AWS: each service, what it does here and why. Event and verdict JSON examples copied from real logs.
7. Results: throughput table + test table from docs/results.md.
8. Limitations and honest claims: what we do NOT claim (no ML on the FPGA, not regulatory-grade, no low-power claim; the laptop stands in for a DVR; the device S3 key is a hackathon shortcut).
9. How to run: laptop, AWS, PYNQ, HLS/Vivado. Exact commands, tested.
10. Credits and licences; "Built 8–11 October 2026 for Environmental Hacks 2026".
Keep it under ~250 lines. Check that every link and path exists.
````

---

## P13: Video script + shot list (draft at H13, final at H25; C)

````text
Write docs/video_script.md for a video of 3:00 or less (target 2:50). Read docs/results.md, the README and BUILD_PLAN.md section 7.

Format: a table with columns time | what's on screen | narration (spoken, short sentences) | caption (big on-screen text, <= 6 words).
Follow this structure:
0:00–0:12 hook (burning footage) · 0:12–0:32 setup (phone → laptop as DVR stand-in → HDMI → PYNQ) · 0:32–1:00 live detection (heat map, CLEAR → SUSPECT, LED) · 1:00–1:15 confuser stays CLEAR · 1:15–1:50 AWS on screen (IoT test client → S3 object → Lambda log with the Nemotron verdict JSON → DynamoDB row → email arriving on the phone → CONFIRMED + red LED) · 1:50–2:15 architecture with measured numbers · 2:15–2:40 test table + one honest limitation (steam) · 2:40–3:00 who uses it + repo link + "Built 8–11 October 2026".
Use only numbers from docs/results.md. Mark any number not yet measured as [TBD].
Then add:
- A shot checklist: hardware take vs AWS console take, which tabs are open, phone screen recording for the email, camera angles, LED close-up.
- Pre-flight: clock synced on the PYNQ, SNS confirmed, IoT test client subscribed to burnwatch/#, Lambda log group open, safety kit (water bucket), no plastic burned.
- Narration word count per section (≈150 words/min) to prove it fits.
````

---

## R1: Citable facts research (H11, C)

````text
Find citable sources for the BurnWatch README and video. Write docs/sources.md: one entry per claim with the exact figure, source title, publisher, date, URL, and a quoted sentence of 25 words or fewer supporting it. Mark anything you can't verify as UNVERIFIED and leave it out of the README.
Claims to source:
1. Open burning of garbage/biomass is prohibited in Delhi and is part of winter air-pollution action: Delhi Winter Action Plan, CAQM directions, GRAP measures, NGT/DPCC fines.
2. Any official or peer-reviewed figure for open burning's contribution to Delhi's PM2.5 or to the number of burning incidents/complaints (e.g. Green Delhi app complaint statistics).
3. How enforcement currently works (field teams, complaint apps), to support "monitors say how bad the air is, not where the burn is".
4. Töreyin et al., EUSIPCO 2005, wavelet-based real-time smoke detection: full citation.
5. AWS: SNS SMS to Indian numbers requires DLT registration (one sentence, AWS docs link).
Prefer government, CAQM, CPCB, peer-reviewed and AWS-doc sources over news, and news over blogs.
````

---

## G1: GaugeEye pivot (only if the H8 gate fails)

````text
We are pivoting from BurnWatch to GaugeEye (water-depth gauge reader). Read CLAUDE.md, then update it for GaugeEye; keep the ingest, AWS and viewer rules.
Reuse: tools/camfeed.py, device/hdmi_check.py, device/cloud.py (MQTT/S3/offline queue), the AWS stack (rename topics to gaugeeye/<site>/...), tools/viewer.py (overlay changes).

Build:
1. gauge/calibrate.py: show one frame, I click two calibration marks (known cm apart) and the pole's left/right edges → saves gauge/calib.json (ROI strip, rows-per-cm, zero row).
2. gauge/waterline.py: per frame in the ROI strip, a per-row band-contrast profile (horizontal edge energy / alternating-band periodicity). Waterline = the last row from the top where the periodic band pattern is present. Depth in cm from calibration. Median of 5 frames, reject jumps > 3 cm per frame, quality 0–1.
3. gauge/state.py: depth + rise rate (cm/min over 30–60 s) → GREEN/AMBER/RED with hysteresis on the way down. Thresholds in config (site-specific, documented as such). Local alarm (LEDs + laptop beep) works offline.
4. Device loop: telemetry {site, depth_cm, rise_cm_per_min, state, quality, ts} every 10 s on MQTT. IoT Rule → DynamoDB (depth series). On RED, Lambda → SNS email (+ optional S3 snapshot).
5. tests + tools/eval_gauge.py over recorded pour clips (opaque water: add soil/tea/turmeric; matte tape on the gauge).
Show me the waterline overlay on a recorded clip before wiring AWS.
````
