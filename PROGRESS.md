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
| P2 | Golden model + tests (spec v1 frozen at H5) | Claude Code | P0b | waiting: user OK on docs/golden_test1.png + decision on F7 (flagged tiles can stay frozen forever) | detector/config.py + golden.py (spec v1 exactly), tests/test_golden.py 18 pass + 1 strict xfail (F7), tools/gen_header.py → hls/config.h, tools/dump_golden.py (--synthetic set OK: frame 20 gated, digest b860f0ecbc50c466). Laptop: FULL 57 ms/frame, ARM-fast 14 ms/frame. |
| U2 | Record the clip set + fill `testdata/labels.csv` | You | P1 | todo | |
| P4 | AWS stack + IoT thing + device IAM | Codex | P0b | todo | |
| P5 | Lambda verifier (Claude on Bedrock) | Claude Code | P4 | todo | |
| P3 | Regions, state machine, eval_clips, replay viewer | Claude Code | P2, U2 | todo | |
| P8 | HLS tile engine, bit-exact C-sim | Codex | P2 | todo | |
| GATE-H8 | Go / pivot to GaugeEye | Claude Code | P3 | todo | |
| P6 | Device runtime (A: cloud client, B: PYNQ loop) | Claude Code | P1, P3, P4, GATE-H8 | todo | |
| P7 | Live viewer + fake_device | Claude Code | P0b, P3 | todo | |
| P9 | Level-2 overlay + on-board bit-exact check | Codex | P8 | todo | |
| R1 | Citable facts → `docs/sources.md` | GPT (Omnirush) | none | todo | |
| P10 | Level-3 live integration (stretch, only if before ~H17) | Codex | P9 | todo | |
| GATE-H20 | PL cut decision | Claude Code | P6 | todo | Run at H20 even if P9 isn't done |
| P11 | Benchmarks + final test table | Claude Code | P6, GATE-H20 | todo | |
| P12 | README + architecture figure | Claude Code | P11, R1 | todo | |
| P13 | Video script + shot list | Claude Code | P11 | todo | |
| U3 | Record, edit (≤ 3:00), check the repo is public, submit | You | P12, P13 | todo | |
| G1 | GaugeEye pivot (only if GATE-H8 says pivot) | Claude Code | GATE-H8 | skipped: not pivoting | |

## Facts
<!-- Discovered values that later prompts need. Append-only. No secrets. -->
- H0 (clock time): 12:56 IST, 10 Oct 2026 (when the user typed "start" in Claude Code; correct it if you started earlier)
- Vivado/Vitis HLS machine (Case A/B): 
- PYNQ image version / matching Vivado version: 
- Bedrock region serving `anthropic.claude-haiku-5-5`: 
- IoT ATS endpoint: 
- S3 bucket / DynamoDB table / SNS topic: 
- PYNQ IP address: 
- GitHub repo URL: https://github.com/sushant-mishra-dtu/Burnwatch (public, branch `main`)
- Laptop cameras: OpenCV 4.13 (pip) opens webcams via Media Foundation only (DSHOW-by-index unsupported); indices 0 and 1 both deliver 1280×720 @ 30. Monitors without the PYNQ: 0 = 2560×1440 primary, 1 = 1920×1080.

## Plan changes
<!-- One line each: date-time, what changed in PROMPTS.md / BUILD_PLAN.md, and why. -->
- 10 Oct 13:05, contracts F1–F6 (accepted by user): CLAUDE.md interface line → `step()` (F1); P2 Params in register order + range checks (F2), reset frame sets b = x before scoring (F4), and P2 now also writes tools/dump_golden.py (F6, moved from P8); P3 device obeys verdict.state (F3); P5 verdict adds camera/verifier/evidence, DynamoDB adds time_ist/verify_ms (F5); P6/P7 use tools/contracts.py + BWV1 verdict packet (F5); P4 may create the cloud/verify stub + cameras.json (F6).

## Log
<!-- One line per finished task: HH:MM, ID, tool, one-line result. -->
- 13:00, P0, Claude Code: repo bootstrapped, first commit on `main`, pushed to GitHub.
- 13:05, P0b, Claude Code: docs/contracts.md + tools/contracts.py, 6 conflicts resolved by the user.
