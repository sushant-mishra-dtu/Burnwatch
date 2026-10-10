# BurnWatch: build plan for Saturday 10 Oct 2026

H0 = the moment you start. Write the clock time next to it: **H0 = ____**. Set phone alarms for **H8 (go/pivot)** and **H20 (PL cut)** right now.

Each step has a prompt in [PROMPTS.md](PROMPTS.md) (P0–P13). Open Claude Code in the repo root so [CLAUDE.md](CLAUDE.md) loads, then paste the prompt.

> **Auto-continue.** You don't have to paste prompts. In Claude Code (this laptop) or Codex (other device), type **`continue`**. The agent reads [PROGRESS.md](PROGRESS.md), takes its next unblocked task, runs that prompt, and updates the status, notes and log. It stops at checkpoints, gates and physical jobs for you, and says what it needs. Agents also **update this plan and PROMPTS.md** when they learn something that makes a later step wrong, logging each change under "Plan changes" in PROGRESS.md. Rows owned by `You` (U1–U3) are your physical jobs: say "U2 done" when you finish one.

---

## 1. What "done" means

**The spine (must ship).** This is the video's money shot:
> live camera → HDMI → PYNQ (ARM detector) → SUSPECT + amber LED → JPEG to S3 + event on IoT Core → Lambda → NVIDIA Nemotron (vision) → DynamoDB row + email on the phone → verdict back to the box → red LED (CONFIRMED)

**The FPGA claim (ship at whatever ladder level is verified by H20):**

| Level | What it is | Claim you can make |
|---|---|---|
| 1 | HLS C-simulation matches golden.py bit for bit on recorded clips, plus synthesis report | "Tile engine verified in simulation, X LUT / Y BRAM, II=1 at 100 MHz" |
| 2 | Custom overlay (PS + tile engine) runs on the board on recorded 720p frames from DDR, bit-exact | "On the board: PL Z fps vs ARM W fps, same integer math, bit-exact" |
| 3 *(stretch)* | Tile engine added to the base overlay, scoring live HDMI frames | "Live: every pixel at 60 fps in the PL; software sees only 3,600 numbers" |

Level 2 is the realistic target. Level 3 means a base-overlay rebuild (several hours of Vivado), so attempt it only if Level 2 is done before ~H17.

---

## 2. Changes from the brief (decisions already made)

1. **MQTT client: `paho-mqtt` instead of `aws-iot-device-sdk-python-v2`.** That SDK needs `awscrt`, which likely has no prebuilt armv7l wheel, so pip could spend a long time compiling it on the Zynq. paho-mqtt is pure Python and works with IoT Core over 8883 with X.509 certificates.
2. **Cloud verifier: NVIDIA Nemotron vision model on NVIDIA's hosted API** (OpenAI-compatible chat completions, `https://integrate.api.nvidia.com/v1`), called from Lambda with stdlib `urllib`. Changed from Claude Haiku 5.5 on Bedrock on 10 Oct (user decision). It must be a **vision** (VL) Nemotron: a text-only model cannot see the frame. Validate its JSON strictly; any parse failure falls back to Rekognition.
3. **The HLS tile engine reads frames from DDR over `m_axi`** rather than tapping the live AXI4-Stream. The same IP works at ladder Levels 2 and 3, can be debugged with plain C-sim, and has no backpressure or timing hazard on the video path.
4. **Every constant is an AXI-Lite register.** Tuning thresholds never triggers a 20–60 min rebuild.
5. **Baseline update is decimated** (`update_this_frame` flag). The ARM runs at ~3 fps and the PL at 60 fps, and both should forget the background over the same number of seconds.
6. **Use a textured, darker background**, such as a brick wall, a patterned dark cloth or foliage. With a plain background the "edge drop" cue sees nothing, because there are no edges to soften.
7. **For the AWS take, burn a small scrap of paper in a steel bowl** (outdoors, water bucket ready) rather than dhoop. The verifier will correctly call dhoop "incense", which is honest but a weak story. Use dhoop for tuning.
8. **Laptop display in Extend mode, not Duplicate.** The HDMI display carries only the full-screen camera feed. The laptop's own screen runs a viewer that draws the heat map **from the 3,600 numbers the box sends**. That is itself a demo point, and it keeps the overlay out of the HDMI feed (no feedback loop).
9. **With a team, AWS starts at H1, not H8.** The cloud owner has no dependency on the detector.

---

## 3. First 60 minutes (H0–H1): long-lead items first

| # | Check | Why now | Pass |
|---|---|---|---|
| 1 | On the board: `python3 -c "import pynq; print(pynq.__version__)"`. Is the **matching** Vivado + Vitis HLS installed? (PYNQ 3.0.x ↔ 2022.1, PYNQ 3.1 ↔ 2024.1; confirm in the PYNQ release notes) | A Vivado download is tens of GB. **Start it now** if it is missing | Version noted in CLAUDE.md |
| 2 | NVIDIA API key for the Nemotron vision model: put it in the git-ignored `cloud/.env` as `NVIDIA_API_KEY=...` (never in chat or a committed file). `cloud/nim_probe.py` confirms the model ID and image format | Free-tier rate limits apply | One probe call returns valid JSON for a sample frame |
| 3 | Laptop → PYNQ **HDMI IN**, laptop display set to 1280×720 @ 60 Hz, Extend mode. In Jupyter: base overlay, `hdmi_in.configure()`, `readframe()` | Everything depends on it. `configure()` hangs if there is no lock | A frame shows in Jupyter |
| 4 | PYNQ online: `date` is correct and `curl -I https://aws.amazon.com` works | **The Z2 has no RTC battery.** A wrong clock breaks TLS to IoT Core and S3 signatures with confusing errors | Both OK |
| 5 | Phone as webcam (DroidCam or Phone Link) shows up as a camera on the laptop | Ingest | Visible in the Camera app |
| 6 | New **public** GitHub repo, run **P0** | Commit history must start during the event | First commit pushed |
| 7 | Safety kit: dhoop/agarbatti, steel bowl, paper scraps, water bucket, phone stand, textured dark background | | Ready |

---

## 4. Timeline

Tracks for a team of three: **D** = detector owner, **C** = cloud and story owner, **F** = FPGA owner. Solo: run the prompts in order P0 → P13 and start F-track work only after the spine works end to end.

| Hours | D (detector) | C (cloud + story) | F (FPGA) | Exit check |
|---|---|---|---|---|
| H0–H1 | Checklist above | Checklist above | Checklist above | All 7 pass |
| H1–H3 | **P1** camfeed + HDMI check; record clips (list below) | **P4** AWS stack deployed, SNS email confirmed | Read P2 spec with D, set up HLS project skeleton | Frames on PYNQ; `sam deploy` OK |
| H3–H5 | **P2** golden.py + tests → **freeze spec v1 at H5** | **P5** Lambda verifier tested with a sample JPEG | Wait for spec v1; write the testbench harness | Golden tests pass; email received |
| H5–H7 | **P3** regions + state + eval_clips; tune | **P6a** device cloud client tested from the laptop | **P8** HLS kernel against spec v1 | Test table v1 |
| **H8** | **GATE** (criteria below) | | | Go / pivot |
| H8–H11 | **P6b** device runtime on PYNQ (ARM mode) | **P7** viewer; join D for end-to-end | **P8** C-sim bit-exact → synthesis | Spine end to end |
| H11–H13 | Tune through the real HDMI path | **R1** citations; start README (P12 skeleton) | **P9** Level-2 Vivado build (sleep during the build) | Spine stable 10/10 runs |
| H13–H20 | Re-run the test table on the real path; fix confusers | Record b-roll and the hook shot; draft the script (**P13**) | **P9** on board: bit-exact + fps. If done by H17: **P10** | Level 2 done |
| **H20** | **CUT** (criteria below) | | | |
| H20–H23 | **P11** bench + final test table | Swap in the PL (if Level 3) or prepare Level-2 footage | **P11** PL numbers | `docs/results.md` |
| H23–H25 | Review README | **P12** README + architecture figure | Review the README's PL section | Repo explains itself |
| H25–H29 | Hardware take | AWS console take; edit to ≤3:00 with big captions | Hardware take | Final cut |
| H29–H30 | Watch the full video end to end. Repo is public, links work. **Submit.** | | | Submitted |

**Sleep:** Vivado builds (P9/P10) and the overnight clip runs are natural 2–3 h sleep windows. Never sleep through the H8 or H20 gate.

### Clips to record (H1–H3, ~20 s each, phone fixed on a stand, 720p)
`empty_day`, `empty_lights_change`, `dhoop_thin` ×2, `dhoop_thick` ×2 (3–4 sticks), `paper_bowl` ×2 (outdoors), `person_walk` ×2, `grey_cloth_wave`, `kettle_steam`, `camera_bump`, `auto_exposure` (point at a window, then away). Record the label and the smoke start/end second in `testdata/labels.csv`.

---

## 5. Gates

**H8 go/pivot.** Run the ARM detector offline on the clips (P3 `eval_clips.py`).
- **GO** if ≥ 4 of 6 smoke clips reach SUSPECT within 20 s of smoke start, **and** ≤ 1 false SUSPECT across person/cloth/lights/bump/exposure. Steam is allowed to trigger; the cloud verifier is the second line of defence and steam is a documented limitation.
- **PIVOT to GaugeEye** (prompt **G1**) otherwise. Keep P1 (ingest), P4/P5 (AWS) and P7 (viewer). Only the detector changes.

**H20 PL cut.**
- If the PL is not bit-exact on the board, ship the ARM version live and present only the verified ladder level, e.g. "Sobel + tile sums verified in C-sim".
- No unverified numbers go in the video or the README.

---

## 6. Fallbacks

| If… | Then |
|---|---|
| HDMI won't lock | 1280×720 @ 60 Hz; try another cable; Extend vs Duplicate; disable HDR/variable refresh. Last resort: phone stream → ARM over Wi-Fi (weaker FPGA story) |
| The NVIDIA API is down, rate-limited or the key is rejected | Rekognition `DetectLabels` (already wired as the fallback in P5); the verdict says `verifier: rekognition` |
| `sam build` fails on Windows | The Lambda runtime must match your local Python (3.10–3.13), or use `sam build --use-container` |
| Device can't reach IoT Core | Check the clock first, then the endpoint (`iot:Data-ATS`), cert/policy attachment, and that the client ID matches the policy |
| Smoke too faint | Closer framing, more sticks, darker textured background, daylight. Lower `T_FLAG` through the register, with no rebuild |
| Vivado build fails or takes too long | Drop to ladder Level 1. ARM ships live |

---

## 7. Video (≤ 3:00): follow the brief's shot table, plus these
- **Record the AWS console take separately** and keep tabs pre-opened: IoT MQTT test client (subscribed to `burnwatch/#`), S3 bucket, CloudWatch log group of the Lambda, DynamoDB table items, phone mail app.
- Say plainly: "The laptop plays the role of a CCTV recorder's HDMI output."
- Show measured numbers only: ARM fps, PL fps (ladder level), frames sent to the cloud per event (= 1).
- Show one honest limitation (steam) and the test table.
- **Never burn plastic or real waste.** Hook footage can be dhoop or paper in a steel bowl, or existing burning filmed from a distance. Don't light anything for it.

---

## 8. Tools and devices: who runs what

GitHub is the only channel between machines. Push P0 and P0b first; the other device clones. Each tool owns its folders, and nobody edits another tool's folders.

**Case A: Vivado is on the Codex machine (preferred).**

| Tool | Runs | Owns | Prompts |
|---|---|---|---|
| Claude Code, this laptop (wired to HDMI, camera and PYNQ) | Everything that touches hardware, plus the Bedrock call | `detector/ device/ tools/ testdata/ cloud/verify/` | P0, P0b, P1, P2, P3, P5, P6, P7, P11 |
| Codex CLI, other device | Long, spec-driven jobs with a hard pass/fail test | `cloud/` except `verify/`, `hls/ overlays/` | P4 → P8 → P9 → P10 |
| GPT chat (Omnirush) | Research, second-opinion review, log debugging, writing | `docs/sources.md`, script drafts (pasted in by you) | R1, P13 draft, reviews |

**Case B: Vivado is on this laptop.** Claude Code adds P8 and P9 (run the Vivado builds while you record clips). Codex takes P4, P7 (tested with `tools/fake_device.py` on localhost) and the P12 architecture figure.

**Rules**
- **Contracts first.** P0b writes `docs/contracts.md` (topics, JSON, S3 metadata, UDP packet, HLS registers, vector file formats). Both agents code against it. A change to it is announced, not slipped in.
- **The spec freeze at H5 matters more now.** Codex builds the HLS core from `detector/golden.py`. After H5, change constants only, never formulas, unless both sides agree.
- **Clips and golden vectors are git-ignored** (too big). Move them via Google Drive or USB, then Codex runs `tools/dump_golden.py` locally. The `--synthetic` vector set needs no clips, so P8 can start before any clip arrives.
- **Cross-review across models.** GPT reviews Claude's `golden.py` against the P2 spec. Claude Code reviews Codex's HLS testbench and `cloud/` IAM policies. A different model catches different mistakes.
- **Codex cloud tasks** (ChatGPT web) can't reach Vivado, the PYNQ or your AWS credentials. Use them only for pure code with tests (e.g. unit tests, `fake_device.py`). Real builds and deploys go through Codex CLI or Claude Code.
- **You are the bottleneck, not the agents.** Queue a long agent task (HLS, SAM template, README) before each physical job (recording clips, HDMI setup, the burn take).

---

## Prompt index

| ID | When | Owner | What |
|---|---|---|---|
| P0 | H0 | any | Repo bootstrap |
| P0b | H0 | Claude Code | `docs/contracts.md`: shared formats for parallel agents |
| P1 | H1 | D | camfeed.py + PYNQ HDMI check |
| P2 | H3 | D | Golden model (the spec) + tests |
| P3 | H5 | D | Regions, state machine, clip evaluator, replay viewer |
| P4 | H1 | C | AWS stack (SAM) + IoT thing + device IAM |
| P5 | H3 | C | Lambda verifier (NVIDIA Nemotron) |
| P6 | H5/H8 | C+D | Device runtime (cloud client + capture loop) |
| P7 | H8 | C | Live viewer on the laptop |
| P8 | H5 | F | HLS tile engine + bit-exact testbench |
| P9 | H11 | F | Level-2 overlay + PYNQ driver + on-board check |
| P10 | H17 (stretch) | F | Level-3 base-overlay integration |
| P11 | H20 | all | Benchmarks + final test table |
| P12 | H23 | C | README + architecture figure |
| P13 | H13/H25 | C | Video script + shot list |
| R1 | H11 | C | Citable facts research |
| G1 | H8 (only if pivoting) | all | GaugeEye pivot |
