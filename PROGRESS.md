# BurnWatch progress (agents keep this file up to date)

## "continue" protocol

When the user says **continue** (or next / resume / go on), do this and nothing else first:

1. `git pull --rebase` if a remote exists.
2. Read this file, then the **Facts** section, then BUILD_PLAN.md if you need timing.
3. **Pick a task.** If one of *your* rows is `in progress`, resume it: reread its prompt in PROMPTS.md, check which deliverables already exist in the repo, and finish the rest. Otherwise take the **first** row you own whose status is `todo` and whose *Depends on* rows are all `done`. Your rows are the ones whose Owner matches your tool: `Claude Code` or `Codex`.
4. Set that row to `in progress (<HH:MM>)`, commit `status: <ID> started`, and push, so the other machine sees it is taken.
5. **Run the row's prompt** from PROMPTS.md exactly as written.
6. **Checkpoints.** Where the prompt says "show me…", "wait for my OK" or "ask me", set the row to `waiting: <what you need>`, commit, and stop. Show the user the thing and ask. When the user answers, continue the same row.
7. **Blocked by a physical action** (plug HDMI, record clips, confirm the SNS email, start a Vivado install): set `blocked: <exact action for the user>`, tell the user in one line, then go back to step 3 and pick the next row of yours that doesn't depend on it.
8. **Finish.** Verify the prompt's exit check, set the row to `done`, and write 1–3 lines in *Notes*: what exists now, measured numbers, any deviation. Append one line to the **Log**. Commit with the prompt ID (`P2: golden model + tests`) and push.
9. **Gates** (`GATE-H8`, `GATE-H20`): run the evaluation the gate describes in BUILD_PLAN.md section 5, write the result in Notes, set `waiting: decision`, and stop. **Never pivot or cut on your own.**
10. **Keep the plan true.** If you learn something that makes a later prompt or plan step wrong (a different region, PYNQ version, file name or API), edit that prompt in PROMPTS.md or that step in BUILD_PLAN.md, and add a line under **Plan changes**. Record discovered values under **Facts**, never secrets.
11. **Edit only your own rows.** The exceptions are Facts, Log and Plan changes, which are append-only. A row owned by `You` is done only when the user says so; then any agent may mark it.
12. Then stop and report: what you finished, what's next, and anything the user must do. One short paragraph.

Statuses: `todo` · `in progress (HH:MM)` · `waiting: …` · `blocked: …` · `done` · `skipped: reason`

## Tasks

Owners follow Case A in BUILD_PLAN.md section 8 (Vivado on the Codex machine). **If the user says Vivado is on this laptop (Case B):** change P8, P9 and P10 to `Claude Code` and P4 and P7 to `Codex`, and note it under Plan changes.

| ID | Task | Owner | Depends on | Status | Notes |
|---|---|---|---|---|---|
| P0 | Repo bootstrap | Claude Code | none | done | Folder layout (+ `overlays/`) with READMEs, root README skeleton, MIT LICENSE, .gitignore, requirements files. Pushed to GitHub `main`. |
| P0b | `docs/contracts.md` | Claude Code | P0 | done | docs/contracts.md (8 sections) + tools/contracts.py + tests/test_contracts.py (5 pass). UDP frame packet = 3,631 bytes, ts = integer Unix seconds. User accepted all 6 flagged defaults (F1–F6) at 13:05. |
| U1 | First-hour checklist (BUILD_PLAN section 3) | You | none | todo | |
| P1 | camfeed.py + HDMI check | Claude Code | P0 | blocked: plug laptop HDMI out → PYNQ HDMI IN, set that display to 1280×720 @ 60 Hz in Extend mode, run `python tools/camfeed.py --camera 1 --monitor N`, then on the board `bash device/run.sh device/hdmi_check.py` (device/README.md) | tools/camfeed.py (camera/clip, letterbox 1280×720, full screen, q/b/space), device/hdmi_check.py, device/run.sh, device/README.md. Laptop side tested: `--list` probes OK, letterbox and clip loop verified headless. Board run pending (board not reachable yet). |
| P2 | Golden model + tests (spec v1 frozen at H5) | Claude Code | P0b | done | detector/config.py + golden.py (spec v1 with F7: K_FAST=0 snap), tests/test_golden.py 19 pass (incl. 6 lighting-recovery cases), hls/config.h via tools/gen_header.py, tools/dump_golden.py: `--synthetic` set has frame 20 gated, digest df5d3395673a5e38 (numpy 2.2.6). Laptop: FULL 57 ms/frame, ARM-fast 14 ms/frame. Known limit: a gated frame absorbs smoke present then; ghosts of objects present at reset. |
| U2 | Record the clip set + fill `testdata/labels.csv` | You | P1 | todo | |
| P4 | AWS stack + IoT thing + device IAM | Codex | P0b | waiting: approval of template + IAM policies before deployment | cloud/template.yaml, idempotent IoT/IAM scripts, MQTT smoke test, verifier stub/cameras.json and device/.env.example ready. SAM lint + Python 3.13 build pass; 14 mocked cloud tests pass. No AWS stack or credentials provisioned; need deployment approval, AlertEmail and verified BedrockRegion. |
| P5 | Lambda verifier (Claude on Bedrock, Nemotron fallback) | Claude Code | P4 | todo | |
| P3 | Regions, state machine, eval_clips, replay viewer | Claude Code | P2, U2 | todo | |
| P8 | HLS tile engine, bit-exact C-sim | Claude Code | P2 | todo | |
| GATE-H8 | Go / pivot to GaugeEye | Claude Code | P3 | todo | |
| P6 | Device runtime (A: cloud client, B: PYNQ loop) | Claude Code | P1, P3, P4, GATE-H8 | todo | |
| P7 | Live viewer + fake_device | Codex | P0b, P3 | todo | |
| P9 | Level-2 overlay + on-board bit-exact check | Claude Code | P8 | todo | |
| R1 | Citable facts → `docs/sources.md` | GPT (Omnirush) | none | in progress (13:20) | Omnirush research pass started. |
| P10 | Level-3 live integration (stretch, only if before ~H17) | Claude Code | P9 | todo | |
| GATE-H20 | PL cut decision | Claude Code | P6 | todo | Run at H20 even if P9 isn't done |
| P11 | Benchmarks + final test table | Claude Code | P6, GATE-H20 | todo | |
| P12 | README + architecture figure | Claude Code | P11, R1 | todo | |
| P13 | Video script + shot list | Claude Code | P11 | todo | |
| U3 | Record, edit (≤ 3:00), check the repo is public, submit | You | P12, P13 | todo | |
| G1 | GaugeEye pivot (only if GATE-H8 says pivot) | Claude Code | GATE-H8 | skipped: not pivoting | |
| Z1 | ZedBoard + VIO RTL package of the tile engine (pasted prompt, Cloud Labs) | Claude Code | P2 | done | `zedboard/burnwatch_zed_vio/` (+ `.zip`): Verilog-2001 Part A (pixels -> tile means) and Part B (score, gate, baselines), simulated-input generators, VIO top, xdc, create/build/sim Tcl, README. Bit-exact vs golden.py in simulation at 1280x720 (14 tests, every tile; Verilator + iverilog) and 4,000 random scorer vectors. Vivado build, timing and the board run are not done yet. |

| RTL-SIM | Native Vivado scoring-core simulation (user request) | Codex | P2 | done | Installed native RTL + golden-vector testbench in M:/Vivado Projects/Burnwatch/Burnwatch, corrected tops/testbench usage; XSim 2022.1 passed 80 full 720p synthetic frames / 288,000 scores with zero mismatches, including baseline state. Standalone core only; P8/P9 and physical FPGA validation remain pending. |

| RTL-SYN | Fix native Vivado synthesis configuration | Codex | RTL-SIM | done | Fixed checkpoint-path parsing by disabling automatic/manual incremental reuse; added 10 ns clock and verified synth_1 completes. Reports: 12658 LUTs, 356 FF, 7 DSP, 0 BRAM; WNS -17.202 ns and 206/125 I/O. Hardware timing/pin fit still requires pipelining + AXI wrapper; RTL unchanged, prior XSim pass retained. |

| RTL-OOC | Standalone core placement/routing analysis | Codex | RTL-SYN | done | Separate OOC module flow completed: 9114/9114 routable nets routed, 0 routing errors, 12708 LUTs / 1005 FF / 7 DSP / 0 BRAM. 100 MHz setup FAIL (WNS -20.092 ns); 21 DRC warnings. RTL unchanged; full board wrapper, boundary timing and physical test remain pending. |

## Facts
<!-- Discovered values that later prompts need. Append-only. No secrets. -->
- H0 (clock time): 12:56 IST, 10 Oct 2026 (when the user typed "start" in Claude Code; correct it if you started earlier)
- Vivado/Vitis HLS machine (Case A/B): **Case B**, this laptop (Claude Code). Vivado + Vitis HLS **2022.1** (SW Build 3526262) at `M:\amd_xilinx` (`Vivado\2022.1\bin\vivado.bat`, `Vitis_HLS\2022.1\bin\vitis_hls.bat`), not on PATH. Part `xc7z020clg400-1` present; PYNQ-Z2 board files **not installed** (needed before P9). WinPcap skipped (only for System Generator Ethernet co-sim).
- PYNQ image version / matching Vivado version: Vivado 2022.1 matches PYNQ **v3.0.x**; board image version still to confirm (`cat /etc/os-release` or `pip show pynq` on the board).
- Bedrock region serving `anthropic.claude-haiku-5-5`: 
- IoT ATS endpoint: 
- S3 bucket / DynamoDB table / SNS topic: 
- PYNQ IP address: 
- GitHub repo URL: https://github.com/sushant-mishra-dtu/Burnwatch (public, branch `main`)
- Laptop cameras: OpenCV 4.13 (pip) opens webcams via Media Foundation only (DSHOW-by-index unsupported); indices 0 and 1 both deliver 1280×720 @ 30. Monitors without the PYNQ: 0 = 2560×1440 primary, 1 = 1920×1080.
- Codex P4 tooling: Python 3.13.5; Lambda runtime python3.13; SAM CLI 1.168.0 installed in ignored cloud/.venv. AWS CLI is not currently on PATH. SAM validation/build and 14 cloud tests passed locally; no cloud deployment or real MQTT test yet.
- P4 device environment keys: IOT_ENDPOINT, CAMERA_ID, CLIENT_ID, CERT_PATH, KEY_PATH, CA_PATH, BUCKET, AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY (device/.env.example). setup_iot.py writes absolute local certificate paths; change those paths after copying to the PYNQ.
- P4 Bedrock policy: non-streaming bedrock-runtime InvokeModel requires bedrock:InvokeModel (AWS API reference verified); permission targets the configured direct foundation model. Model ID remains anthropic.claude-haiku-5-5; serving region/account access still unverified.
- Cloud verifier (from 13:56): NVIDIA Nemotron vision model on NVIDIA's hosted API (`https://integrate.api.nvidia.com/v1`). Model ID: ___ (fill after cloud/nim_probe.py). Key lives only in git-ignored `cloud/.env` and the NoEcho SAM parameter `NvidiaApiKey`. The P4 Bedrock facts above are superseded.
- Cloud verifier (from 10 Oct 16:24, user decision, supersedes the 13:56 Nemotron-only line): Claude `anthropic.claude-haiku-5-5` on the Bedrock **Mantle** endpoint in `ap-south-1` (docs list Mumbai with global routing; Mantle has no structured outputs). IAM action `bedrock-mantle:CreateInference`, currently on `Resource: '*'` because the resource ARN format could not be verified. Fallback: NVIDIA Nemotron (skipped when `NvidiaApiKey`/`NvidiaModelId` are empty), then Rekognition. Haiku 5.5 account access in ap-south-1: ___ (fill after cloud/bedrock_probe.py). `sam build` with `anthropic[bedrock]` (anthropic 1.13.0, Linux wheels) passes; build into a short path on Windows (MAX_PATH).
- ZedBoard (Cloud Labs, from 10 Oct 17:47): part xc7z020clg484-1, GCLK Y9 LVCMOS33 100 MHz, LEDs T22 T21 U22 U21 V22 W22 U19 U14 (Digilent master XDC + BoardStore 2022.1 avnet zedboard 1.4). User's Vivado: 2022.1.

- RTL-SIM (10 Oct 2026 23:49 IST): Vivado project M:/Vivado Projects/Burnwatch/Burnwatch/Burnwatch.xpr; native standalone core/testbench sources archived in overlays/rtl_sim. XSim PASS: 80 frames, 288000 scores, 0 mismatches, 928802 simulated cycles/frame at a 10 ns testbench clock. No synthesis/timing/board-FPS claim; AXI overlay is separate. Originals backed up in codex_backup_20261010_233428.

- RTL-SYN (11 Oct 2026 00:20 IST): native synthesis completed after removing incremental DCP reuse; reports in M:/Vivado Projects/Burnwatch/Burnwatch/synthesis_results. LUT 12658/53200, FF 356, DSP 7, BRAM 0; target 100 MHz NOT met (WNS -17.202 ns); bare-top I/O 206/125, so no board-ready claim. RTL-SIM code/hash unchanged.

- RTL-OOC (11 Oct 2026 00:37 IST): separate Vivado 2022.1 module analysis in core_ooc_results completed placement/routing with 9114/9114 routable nets, 0 routing errors, LUT 12708, FF 1005, DSP 7, BRAM 0. 10 ns setup WNS -20.092 ns / TNS -311408.031 ns: timing NOT met. 21 default-DRC warnings; parent clock assumed BUFGCTRL_X0Y0; external boundary timing/PS integration/pinout/board test are not validated. Scoring RTL unchanged.

## Plan changes
<!-- One line each: date-time, what changed in PROMPTS.md / BUILD_PLAN.md, and why. -->
- 10 Oct 13:05, contracts F1–F6 (accepted by user): CLAUDE.md interface line → `step()` (F1); P2 Params in register order + range checks (F2), reset frame sets b = x before scoring (F4), and P2 now also writes tools/dump_golden.py (F6, moved from P8); P3 device obeys verdict.state (F3); P5 verdict adds camera/verifier/evidence, DynamoDB adds time_ist/verify_ms (F5); P6/P7 use tools/contracts.py + BWV1 verdict packet (F5); P4 may create the cloud/verify stub + cameras.json (F6).
- 10 Oct 13:23, contracts F7 (decided by user 13:20): spec v1 now has K_FAST = 0 (snap b = x after a gated frame, range 0–15) and the update rounding term `(1 << k) >> 1`; contracts.md sections 6–8 updated. PROMPTS.md P2 (spec + constants), P8 (rounding note), P3 (REJECTED emits `rebaseline`) and P6 (rebaseline → engine.reset()) edited to match. Why: v1 left all 3,600 tiles flagged forever after a lighting change.
- 10 Oct 13:23, contracts section 8 (◇ additive): optional extra vector sets `<set>-u<N>` (`dump_golden.py --update-every N --reset-at 0,30`) cover update=0 frames and a mid-sequence reset; same format.
- 10 Oct 13:43, P4 CodeUri in PROMPTS.md corrected to verify/ relative to cloud/template.yaml (resolves to cloud/verify/). SAM's relative-path handling otherwise looks for cloud/cloud/verify/; local build confirmed the corrected path.
- 10 Oct 13:56, verifier switched from Claude Haiku 5.5 on Bedrock to an NVIDIA Nemotron vision model (user decision). PROMPTS.md P4 (template params/env: NvidiaApiKey NoEcho, VerifierModelId, NimBaseUrl; Bedrock IAM removed), P5 (urllib call, probe first, strict JSON parse, verifier="nemotron"), P12/P13 wording; BUILD_PLAN sections 1, 2, 3, 5, 6, 8; CLAUDE.md; contracts.md verifier enum; tests/test_contracts.py. .gitignore now ignores samconfig.toml (it would hold AlertEmail and the key). **Codex: P4's template.yaml and cloud/README.md need reworking to match before deployment.**
- 10 Oct 16:24, verifier is Claude on Bedrock again, with NVIDIA Nemotron as fallback (user decision): chain Claude → Nemotron → Rekognition, `verifier` enum now `claude`/`nemotron`/`rekognition`. Edited cloud/template.yaml (BedrockRegion removed, region = stack region; BedrockModelId, NvidiaApiKey NoEcho default "", NvidiaModelId default "", NimBaseUrl; IAM `bedrock-mantle:CreateInference` replaces `bedrock:InvokeModel`; timeout 60 → 90 s), cloud/README.md, cloud/verify/requirements.txt (anthropic[bedrock]), PROMPTS.md P4/P5/P12/P13, BUILD_PLAN sections 1, 2, 3, 6, 8, CLAUDE.md, contracts.md (verdict example/enum, verify_ms, F3), tests/test_contracts.py. The P4 template/IAM still needs the user's approval before deploying.
- 10 Oct 17:47, user: PYNQ-Z2 is not used for now. Added row Z1 and `zedboard/`, a hand-written Verilog version of the tile engine with VIO control for a ZedBoard in IIIT-Delhi Cloud Labs (synthetic on-chip frames, no HDMI). P8/P9 (HLS + PYNQ overlay, Codex) are unchanged; Z1 matches the same spec, golden.py.
- 10 Oct 17:50, Case B (user: Vivado installed on this laptop): P8, P9, P10 → Claude Code; P7 → Codex; P4 stays Codex (already its row).

## Log
<!-- One line per finished task: HH:MM, ID, tool, one-line result. -->
- 13:00, P0, Claude Code: repo bootstrapped, first commit on `main`, pushed to GitHub.
- 13:05, P0b, Claude Code: docs/contracts.md + tools/contracts.py, 6 conflicts resolved by the user.
- 13:23, P2, Claude Code: golden model + 19 tests, gen_header, dump_golden (synthetic set ready for Codex P8); F7 deadlock found and fixed (K_FAST=0 snap).
- 13:43, P4 checkpoint, Codex: AWS template/setup scripts prepared; SAM lint/build and 14 mocked tests pass. Waiting for the prompt's required template/IAM approval before deploying, provisioning credentials or running live MQTT verification.
- 17:47, Z1, Claude Code: ZedBoard VIO RTL package; bit-exact with golden.py in simulation (1280x720, all tiles); Vivado/board not run here.
- 23:49, RTL-SIM, Codex: requested native Vivado project completed; 80 full-resolution synthetic frames bit-exact (scores + persisted state), 24 Python reference/contract tests pass, local report saved.
- 00:20, RTL-SYN, Codex: fixed Common 17-165 configuration error, synth_1 Complete; saved resource/timing reports and documented clock/pin limitations.
- 00:30, RTL-SYN files, Claude Code: copied Codex's finished synthesis results from the Vivado project into overlays/rtl_sim (SYNTHESIS_VALIDATION.md, reports/, implement_core_ooc.tcl). The OOC place-and-route was still running, so none of its results are included.
- 00:40, RTL-OOC, Codex: saved reproducible OOC workflow and routed checkpoint/reports; internal routing complete, 100 MHz timing failure and full-system limits documented in overlays/rtl_sim/OOC_VALIDATION.md.
