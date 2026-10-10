# BurnWatch contracts

The single source of truth for every format shared between folders and machines. Two agents build against this file in parallel, so **a change here is announced (commit message `contracts: …` plus a line under "Plan changes" in PROGRESS.md), never slipped in.** [`tools/contracts.py`](../tools/contracts.py) is the executable copy of sections 1, 3, 5 and 7 (packing): import it, don't retype constants.

Taken from CLAUDE.md and PROMPTS.md (P2–P8). Items marked **⚑F*n*** were conflicts between those sources. The user decided them on 10 Oct 2026 at 13:05 (all recommended defaults accepted), and the body below follows those decisions. Items marked **◇** are gaps the prompts left open, which this file fills.

## ⚑ Decisions (accepted 10 Oct 2026, 13:05)

| # | Conflict | Sources | Decision |
|---|---|---|---|
| F1 | The engine interface is `score_frame(rgb) -> scores, gate` in CLAUDE.md but `step(rgb, update_this_frame=True) -> (scores, gate, changed)` in P2, P6 and P9 | CLAUDE.md vs P2/P6/P9 | Use `step()`. Update the line in CLAUDE.md |
| F2 | P0b asks for "registers in the same order as Params", but P8 lists `k_slow, k_fast` first while P2 lists `K_SLOW, K_FAST` after `GATE_TILES` | P0b vs P2/P8 | Put the `Params` fields in P8's register order. This changes nothing functionally |
| F3 | Who decides CONFIRMED vs REJECTED? The Lambda sends `state` using its `CONF_THRESHOLD`, while the device's P3 rule is "is_smoke and confidence ≥ 0.6 → CONFIRMED, not is_smoke → REJECTED". With `is_smoke=true, confidence<0.6`, the Lambda says REJECTED, but P3 has no transition, so the device stays SUSPECT | P3 vs P5 | **The device obeys `verdict.state`.** The single threshold is `CONF_THRESHOLD` in the cloud. If both Bedrock and Rekognition fail, the Lambda sends no verdict and the device's 90 s timeout handles it |
| F4 | What does a **reset frame** score against? P2 lists `if reset: b = x` in the update block, after scoring, so frame 0 is scored against whatever baseline is left in memory. In csim that is zeros, but on the board it is BRAM left over from the previous run, so P9's on-board check would fail on frame 0 of every vector set after the first | P2 / P8 / P9 | **On a reset frame, set `b = x` first, then score.** That gives scores = 0, changed = 0, gate = False, prev_gate = False, whatever the previous state was |
| F5 | P7's viewer shows "the last verdict text", but P6's UDP packet carries no verdict | P6 vs P7 | Add a second UDP packet, `BWV1` + verdict JSON, which the device sends once per verdict (section 5), and add `camera`, `verifier` and `evidence` to the verdict JSON (section 2) |
| F6 | Folder ownership (BUILD_PLAN section 8): P4 (Codex) writes the stub `cloud/verify/app.py` and `cloud/verify/cameras.json`, but `cloud/verify/` belongs to Claude Code. P8 (Codex) writes `tools/dump_golden.py`, but `tools/` belongs to Claude Code | BUILD_PLAN section 8 vs P4/P8 | Codex creates the two `cloud/verify/` files in P4, and Claude Code owns them from P5 on. **Claude Code writes `tools/dump_golden.py` at the end of P2**, because it is coupled to golden.py and P8 can't start before P2 anyway. Codex only runs it |
| F7 | Spec v1 could deadlock: flagged tiles are frozen, and after a global change (lights on in a dark scene, off in a bright one) the gate shuts with 10–18 grey levels of baseline gap left, which still scores ≥ T_FLAG, so all 3,600 tiles stayed flagged forever (measured, P2) | P2 spec | Decided by the user 10 Oct 13:20. **`K_FAST` may be 0, meaning snap `b = x` after a gated frame, and 0 is the default.** The update's rounding term is written `(1 << k) >> 1`, identical to `1 << (k-1)` for k ≥ 1 and 0 for k = 0. All six lighting cases now recover in 2 frames. **Plus a caller rule: a REJECTED verdict makes the device call `eng.reset()`** (P3 emits a `rebaseline` action). Ghosts (something in view at a reset that later leaves) stay a documented limitation |

## ◇ Gaps filled here (shout if you disagree)

- `ts` is an **integer number of Unix seconds (UTC)** everywhere it is a key (event, S3 key, S3 metadata, DynamoDB sort key, verdict, heartbeat). The 120 s upload cooldown makes it unique per camera. The device matches a verdict to its open event by `ts`.
- `bbox` is `[x1, y1, x2, y2]` in full-res pixels (1280×720), multiples of 16, with `x2, y2` **exclusive**: tile columns 30..37 give `x1=480, x2=608`.
- UDP byte order is little-endian, with no padding. State and mode are sent as indices into fixed lists.
- DynamoDB attribute names `time_ist` and `verify_ms` are added (P11 asks for the verify time separately from the latency). `bbox` is stored as a list of numbers.
- `expect.txt` also records each frame's `reset` and `update` inputs, so the testbench assumes nothing. `state_XXXX.bin` is an optional baseline dump, there to locate the first divergence.
- `params.txt` keys are the `Params` field names.
- The eval-log CSV columns and the `hls/config.h` macro names are defined here.

---

## 1. MQTT (AWS IoT Core, `ap-south-1`)

Endpoint: the account's `iot:Data-ATS` endpoint (`<prefix>-ats.iot.ap-south-1.amazonaws.com`), port **8883**, TLS with an X.509 device certificate and `AmazonRootCA1.pem`. Get it with `aws iot describe-endpoint --endpoint-type iot:Data-ATS --region ap-south-1` (it is also needed as the `IotEndpoint` SAM parameter).

| Topic | Direction | QoS | Payload |
|---|---|---|---|
| `burnwatch/<camera>/events` | device → cloud | 1 | Event JSON (section 2). Published **after** the S3 upload succeeds |
| `burnwatch/<camera>/verdict` | Lambda → device | 1 | Verdict JSON (section 2) |
| `burnwatch/<camera>/heartbeat` | device → cloud | 0 | Heartbeat JSON, every 60 s |
| `burnwatch/test` | laptop smoke test (P4) | 0 | any JSON |

- **`<camera>`** matches `^[a-z0-9][a-z0-9-]{0,31}$`. The default is `rwa-gate-2`.
- **client_id:** the device is `burnwatch-<camera>` (= `CLIENT_ID` in `device/.env`). A tool that connects at the same time (for example `cloud_selftest.py` while the board runs) uses `burnwatch-<camera>-<suffix>`. IoT Core disconnects the older session when a client id is reused. The policy grants `iot:Connect` on `client/burnwatch-*`, which covers both.
- **Policy `burnwatch-device`:** Connect `client/burnwatch-*`; Publish and Receive `topic/burnwatch/*`; Subscribe `topicfilter/burnwatch/*`.
- **On every (re)connect** the device subscribes to `burnwatch/<camera>/verdict`.
- **Payloads** are compact UTF-8 JSON. Senders send exactly the fields listed. Receivers ignore unknown fields.
- **Video setup:** the IoT MQTT test client subscribes to `burnwatch/#`.

## 2. JSON messages

### Event (device → `burnwatch/<camera>/events`)
```json
{"camera":"rwa-gate-2","state":"SUSPECT","score":0.42,"tiles":11,"bbox":[480,224,608,352],"s3_key":"frames/rwa-gate-2/1791622800.jpg","ts":1791622800}
```
| Field | Type | Meaning |
|---|---|---|
| `camera` | string | camera id |
| `state` | string | always `"SUSPECT"` (an event is only sent on CLEAR → SUSPECT) |
| `score` | number | mean tile score inside the region / 255, rounded to 2 decimals, 0–1 |
| `tiles` | integer | number of tiles in the region (16×16 px each) |
| `bbox` | [int ×4] | `[x1, y1, x2, y2]`, full-res pixels, multiples of 16, x2/y2 exclusive |
| `s3_key` | string | `frames/<camera>/<ts>.jpg` |
| `ts` | integer | Unix seconds UTC when the frame was captured. Also the event id |

The Lambda is triggered by S3, not by this message. The event exists for the IoT console and the logs.

### Verdict (Lambda → `burnwatch/<camera>/verdict`)
```json
{"camera":"rwa-gate-2","ts":1791622800,"is_smoke":true,"confidence":0.86,"likely_source":"leaf or biomass burning","state":"CONFIRMED","verifier":"nemotron","evidence":"A grey plume rises from a pile of leaves at the left of the box."}
```
| Field | Type | Meaning |
|---|---|---|
| `camera` | string | ⚑F5 addition |
| `ts` | integer | the event's `ts`. The device ignores a verdict whose `ts` isn't its open SUSPECT event |
| `is_smoke` | boolean | |
| `confidence` | number | 0–1, 2 decimals |
| `likely_source` | string | one of: `open waste burning`, `leaf or biomass burning`, `incense or small flame`, `cooking or tandoor`, `vehicle exhaust`, `steam or fog`, `dust`, `not smoke`, `unclear` |
| `state` | string | `"CONFIRMED"` if `is_smoke and confidence >= CONF_THRESHOLD`, else `"REJECTED"`. **The device obeys this field** (⚑F3) |
| `verifier` | string | `"nemotron"` or `"rekognition"` (⚑F5 addition; was `"claude"` until 10 Oct 13:56) |
| `evidence` | string | one sentence, as stored in DynamoDB (⚑F5 addition; the viewer shows it) |

`complaint_text` is **not** sent to the device. It only goes to DynamoDB and the email.

### Heartbeat (device → `burnwatch/<camera>/heartbeat`, every 60 s)
```json
{"ts":1791622860,"state":"CLEAR","fps":3.1,"mode":"arm","queue_len":0}
```
`ts` integer Unix seconds · `state` one of the four states · `fps` processed frames/s over the last 60 s, 1 decimal · `mode` `"arm"`, `"pl"` or `"pl-live"` · `queue_len` number of events waiting in the offline queue.

## 3. S3 frames

- **Bucket:** the SAM output (Facts in PROGRESS.md). Public access is blocked. A lifecycle rule deletes `frames/` after 7 days.
- **Key:** `frames/<camera>/<ts>.jpg`, for example `frames/rwa-gate-2/1791622800.jpg`. The S3 notification filter is prefix `frames/`, suffix `.jpg`.
- **Body:** a JPEG of the full-res 1280×720 frame, `cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])` (RGB → BGR first). `ContentType: image/jpeg`.
- **User metadata** (boto3 `Metadata={...}`; S3 stores it as `x-amz-meta-<key>`). All values are ASCII strings:

| Key | Example | Encoding |
|---|---|---|
| `camera` | `rwa-gate-2` | as is |
| `ts` | `1791622800` | integer as a string |
| `score` | `0.42` | 2 decimals |
| `tiles` | `11` | integer as a string |
| `bbox` | `[480,224,608,352]` | compact JSON array string |

`tools.contracts.s3_metadata(event)` builds this dict. The Lambda parses it back with `int()`, `float()` and `json.loads()`.
- **Device credentials:** IAM user `burnwatch-device`, which can only `s3:PutObject` on `arn:aws:s3:::<bucket>/frames/*`. This is a hackathon shortcut; production would use the IoT credentials provider.

## 4. DynamoDB item (table `burnwatch-events`, on-demand)

| Attribute | Type | Example / meaning |
|---|---|---|
| `camera` | S, **partition key** | `rwa-gate-2` |
| `ts` | N, **sort key** | `1791622800` |
| `time_ist` | S | `2026-10-10T14:30:00+05:30` (◇) |
| `score` | N | `0.42` |
| `tiles` | N | `11` |
| `bbox` | L of N | `[480, 224, 608, 352]` |
| `s3_key` | S | `frames/rwa-gate-2/1791622800.jpg` |
| `is_smoke` | BOOL | `true` |
| `confidence` | N | `0.86` |
| `likely_source` | S | one of the enum values |
| `evidence` | S | one sentence |
| `complaint_text` | S | draft complaint, or `""` |
| `verifier` | S | `nemotron` or `rekognition` |
| `latency_ms` | N | Lambda "now" just before PutItem, minus the S3 event record's `eventTime` |
| `verify_ms` | N | the Nemotron (or Rekognition) call alone (◇) |

With boto3's resource API, numbers must be `Decimal` (`Decimal(str(x))`), not float.

## 5. UDP viewer packets (device → laptop `<viewer-ip>:9999`)

**Frame packet `BW01`**, one per processed frame, never video:

```python
UDP_HEADER_FMT = "<4sIdBBfB4H"      # little-endian, no padding
# magic b"BW01", frame_no u32, ts f64, state u8, gate u8, fps f32, mode u8, x1 y1 x2 y2 u16
UDP_HEADER_SIZE = 31
UDP_PACKET_SIZE = 31 + 3600 = 3631  # + 3600 uint8 scores, row-major 45x80
```

| Field | Type | Meaning |
|---|---|---|
| magic | 4s | `b"BW01"` |
| frame_no | u32 | processed frames since the device started (wraps) |
| ts | f64 | device Unix time in seconds, float |
| state | u8 | index in `("CLEAR", "SUSPECT", "CONFIRMED", "REJECTED")` |
| gate | u8 | 1 if this frame was gated |
| fps | f32 | processing fps (rolling) |
| mode | u8 | index in `("arm", "pl", "pl-live")` |
| x1 y1 x2 y2 | 4 × u16 | the tracked region's bbox (section 2 convention), all 0 if there is none |
| scores | 3600 × u8 | the engine's raw tile scores for this frame |

**Verdict packet `BWV1`** (⚑F5): `b"BWV1"` + the verdict JSON exactly as received on MQTT, sent once when a verdict reaches the device.

Use `tools.contracts.pack_viewer_packet`, `pack_verdict_packet` and `unpack_viewer_packet`.

## 6. Golden model API (`detector/`)

```python
from detector.config import Params
from detector.golden import TileEngine

eng = TileEngine(Params(), tile=16)   # FULL mode: rgb uint8 [720, 1280, 3]
eng = TileEngine(Params(), tile=8)    # ARM-fast: the caller passes rgb[::2, ::2] -> [360, 640, 3]
eng.reset()                           # the next step() is a reset frame (⚑F4); a new engine starts this way
scores, gate, changed = eng.step(rgb, update_this_frame=True)
#   scores  np.ndarray uint8, shape (45, 80), row-major
#   gate    bool    (this frame's gate; the caller ignores gated frames)
#   changed int     0..3600
eng.bE, eng.bY, eng.bS                # np.ndarray int32 (45, 80), Q8, 0..65280, after this step's update
eng.prev_gate                         # bool, = gate after the step
```

- `step()` requires `rgb.shape == (45*tile, 80*tile, 3)` and dtype uint8. The caller decimates for ARM-fast mode. The same `step()` is implemented by `device/pl_engine.PLTileEngine` (FULL-mode input) (⚑F1).
- **Reset frame (⚑F4):** `bE, bY, bS = xE, xY, xS` **before** scoring. So scores = 0, changed = 0, gate = False, then prev_gate = False.
- **`update_this_frame`** is computed by the caller: `frame_no % UPDATE_EVERY == 0`, where frame_no counts processed frames from 0 (`UPDATE_EVERY_ARM` or `UPDATE_EVERY_PL`).

**`Params`** (dataclass in `detector/config.py`): the field names, in register order (⚑F2), with defaults and the ranges that `Params` validates, because the HLS registers are only this wide:

| Field | Default | Range | Units |
|---|---|---|---|
| `K_SLOW` | 6 | 1–15 | baseline shift (slow) |
| `K_FAST` | 0 | 0–15 | baseline shift after a gated frame; 0 = snap `b = x` (⚑F7) |
| `W_EDGE` | 4 | 0–255 | weight |
| `W_GREY` | 4 | 0–255 | weight |
| `SCORE_SHIFT` | 8 | 0–31 | shift |
| `T_FLAG` | 40 | 0–255 | score units |
| `SAT_MAX` | 40 | 0–255 | mean saturation (not Q8) |
| `SAT_TOL` | 1024 (= 4<<8) | 0–65535 | Q8 |
| `T_GLOBAL` | 6144 (= 24<<8) | 0–65535 | Q8 |
| `GATE_TILES` | 1440 | 0–3600 | tiles |
| `UPDATE_EVERY_ARM` | 1 | ≥ 1 | frames (caller side, not a register) |
| `UPDATE_EVERY_PL` | 20 | ≥ 1 | frames (caller side, not a register) |

**Baseline update** (after scoring, not on a reset frame, only when `update_this_frame`): `k = K_FAST if prev_gate else K_SLOW`; on tiles where `prev_gate or score < T_FLAG`: `b += (x - b + ((1 << k) >> 1)) >> k`, with `>>` an arithmetic shift (⚑F7).

**Caller rule (⚑F7):** when a verdict with `state` `"REJECTED"` arrives, the device calls `eng.reset()`, so the next frame re-baselines everything the verifier judged not to be smoke.

With these ranges every intermediate fits in int32: `raw ≤ 255·65280·2 < 2²⁵`, and `bS + SAT_TOL ≤ 130815` (18 bits).

The ARM-only constants for regions and the state machine (P3: `MIN_TILES`, `PERSIST_S`, smoothing, growth, cooldowns) live in a **separate** dataclass in `config.py`, so `Params` stays 1:1 with the HLS registers.

## 7. HLS tile engine (`hls/`)

```cpp
void tile_engine(
    const ap_uint<32> *frame,      // m_axi bundle=gmem0 offset=slave depth=921600
    ap_uint<8>        *scores,     // m_axi bundle=gmem1 offset=slave depth=3600
    ap_uint<1>  reset,             // s_axilite bundle=control, this order:
    ap_uint<1>  update_this_frame,
    ap_uint<4>  k_slow,      ap_uint<4>  k_fast,
    ap_uint<8>  w_edge,      ap_uint<8>  w_grey,
    ap_uint<5>  score_shift, ap_uint<8>  t_flag,
    ap_uint<8>  sat_max,     ap_uint<16> sat_tol,
    ap_uint<16> t_global,    ap_uint<12> gate_tiles,
    ap_uint<1>  *gate_out,         // s_axilite outputs
    ap_uint<12> *changed_out,
    ap_uint<32> *frame_count);     // + s_axilite port=return (ap_ctrl_hs)
```

- The register names are the lowercase `Params` names. Each scalar has its own 32-bit AXI-Lite register. **Offsets come from the generated `xtile_engine_hw.h`**, never hard-coded from this file.
- Zynq-7000 addresses are 32-bit. Turn off 64-bit m_axi addresses in `run_hls.tcl` (`config_interface -m_axi_addr64`) so each pointer is one register. If they stay 64-bit, the PYNQ driver writes 0 to the high word.
- **Frame:** 1280×720 = 921600 words, row-major, one pixel per word: `R | G<<8 | B<<16`, bits 31:24 written as 0 and ignored by the core. Use `tools.contracts.pack_rgb_words`.
- **Scores:** 3600 bytes, row-major: `scores[ty*80 + tx]`, ty 0..44, tx 0..79.
- **State:** `static` arrays `bE, bY, bS` (uint16 ×3600, BRAM) and `prev_gate`. A reset call follows ⚑F4.
- **Baseline update:** exactly section 6. `k_fast` may be 0 (snap, ⚑F7): the rounding term is `(1 << k) >> 1`, never `1 << (k-1)`.
- **Outputs:** `gate_out` = this frame's gate. `changed_out` = this frame's changed count. `frame_count` = calls since the last reset, counting the reset call as 1.
- **`hls/config.h`** (from `tools/gen_header.py`): geometry `IMG_W 1280`, `IMG_H 720`, `TILE 16`, `TILES_X 80`, `TILES_Y 45`, `N_TILES 3600`, and the defaults `CFG_<FIELD>` (for example `CFG_K_SLOW 6`). The core takes every tunable at run time. The defaults are for the testbench only.

## 8. Test vectors and test data

### Golden vectors (`tools/dump_golden.py` → `testdata/golden/`, git-ignored)
```
testdata/golden/<set>/        # <set> = clip basename, or "synthetic"
  params.txt
  expect.txt
  frame_0000.bin  ...         # 921600 x uint32 little-endian (3,686,400 bytes), packed as in section 7
  scores_0000.bin ...         # 3600 x uint8, row-major 45x80
  state_0000.bin  ...         # optional: bE, bY, bS as 3x3600 uint16 LE, then 1 byte prev_gate (21,601 bytes), after the update
```
`XXXX` is 4 digits, zero-padded, from 0000. Each set has ≥ 40 frames: frame 0 is a reset frame, frame 20 is the +40 brightness (gated) frame, and `update_this_frame` = 1 on every frame. FULL mode only.

Optional extra sets (◇, added in P2): `dump_golden.py --update-every N --reset-at 0,30 --name <set>-u<N>` writes a set with `update_this_frame = 0` on frames where `i % N != 0` and extra reset frames, to cover the PL's `UPDATE_EVERY_PL` cadence and a reset with state left over. Same format; the testbench needs nothing new because `expect.txt` carries `reset` and `update` per frame.

**params.txt**: one `KEY value` per line, decimal integers, `#` starts a comment. The keys are the `Params` field names plus the geometry:
```
# BurnWatch golden vectors, spec v1
SPEC 1
IMG_W 1280
IMG_H 720
TILE 16
FRAMES 40
K_SLOW 6
K_FAST 0
W_EDGE 4
W_GREY 4
SCORE_SHIFT 8
T_FLAG 40
SAT_MAX 40
SAT_TOL 1024
T_GLOBAL 6144
GATE_TILES 1440
```

**expect.txt**: one line per frame, in order, space-separated: the inputs that frame used, then the expected outputs:
```
# frame reset update gate changed
0000 1 1 0 0
0001 0 1 0 3
0020 0 1 1 3600
```
(Example values. Real values come from dump_golden.py.)

The testbench resets on the frames where `reset` = 1, compares scores, gate and changed exactly, prints the first 10 mismatches as `(frame, tile_row, tile_col, expected, got)`, and returns non-zero on any mismatch.

### Clip labels (`testdata/labels.csv`, tracked)
Columns: `clip,label,smoke_start_s,smoke_end_s,notes`. `clip` is the file basename without `.mp4`, from `testdata/clips/`. `label` is one of `smoke, person, cloth, lights, bump, exposure, steam, empty`. The smoke times are seconds from the clip start, left empty for non-smoke clips.

### Device eval log (`main.py --eval-log path.csv`, read by `eval_clips.py --from-logs`)
Header row, then one row per processed frame: `ts,frame_no,state,gate,region_tiles` (ts float Unix seconds on the device clock; state name; gate 0/1; region_tiles = tiles in the tracked region, 0 if none).
