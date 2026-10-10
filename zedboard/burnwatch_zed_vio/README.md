# BurnWatch tile engine: ZedBoard + VIO hardware package (Vivado 2022.1)

This package builds the FPGA part of **BurnWatch**, the open-burning smoke detector, for a **ZedBoard
(xc7z020clg484-1)**. You can test it entirely through **VIO** in IIIT-Delhi Cloud Labs, with no switches,
buttons or other peripherals.

## 1. What is implemented

The FPGA's job in BurnWatch is the **tile engine** (spec: `detector/golden.py`; a verbatim copy is in
`model/detector/`). It turns each 1280x720 frame into 3,600 tile smoke scores. The tile engine has two parts,
and both are fully implemented in synthesizable Verilog-2001:

| | Part A: pixel feature extractor | Part B: tile scorer + baseline memory |
|---|---|---|
| Input | RGB pixels, 1 per clock (valid/ready) | tile features (mE, mY, mS), 1 tile per clock |
| Computes | luma Y, saturation S, 3x3 Sobel edge E per pixel; 16x16 tile means | edge drop, grey shift, saturation test, score 0..255, flag, changed count, frame gate, baseline update (reset frame, K_SLOW/K_FAST, frozen flagged tiles) |
| Output | 3,600 x (mE, mY, mS) per frame | 3,600 scores, gate, statistics; baselines kept in block RAM between frames |
| RTL | `rtl/bw_part_a.v` (+ frame_scan, pixel_feat, sobel_window, tile_accum) | `rtl/bw_part_b.v` (+ tile_score) |

Both parts match golden.py **bit for bit**: the testbench compares every tile's features, score and
three baselines after each test.

**On the FPGA:** Part A, Part B, a test controller and a test table. There are also two **SIMULATED INPUT**
generators, because the ZedBoard in Cloud Labs has no camera or HDMI input:
- `bw_stim_gen`: makes a synthetic 1280x720 frame (checkerboard texture + smoke box / red cloth / +40 lights),
  one pixel per clock, and feeds it into Part A through the same valid/ready port a video feed would use;
- `bw_tile_vec_gen`: makes tile-feature vectors that test Part B on its own.

**Stays in software (not on this FPGA):** camera capture and HDMI input, region grouping and the
SUSPECT/CONFIRMED state machine, MQTT/S3 upload, and the cloud verifier (Claude on Amazon Bedrock with an
NVIDIA Nemotron fallback, AWS Lambda, DynamoDB, email). In the full system the ARM writes the tile-engine
registers. Here the register values are constants in `bw_top_zed.v` (the `detector/config.py` defaults),
T_FLAG comes from the VIO, and the VIO replaces the ARM for start/stop and read-back. The Zynq PS is not used.

Details, the block diagram and one paragraph per block: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 2. Package contents

```
README.md                    this file
rtl/                         synthesizable Verilog-2001 (sources_1)
  bw_top_zed.v                 board top: GCLK, reset, VIO instance vio_0, LEDs
  bw_system.v                  integration: controller + both parts + generators + read-back
  bw_ctrl.v  bw_test_rom.v     test controller FSM, test table
  bw_part_a.v                  PART A wrapper
    bw_frame_scan.v  bw_pixel_feat.v  bw_sobel_window.v  bw_tile_accum.v
  bw_part_b.v                  PART B wrapper (baseline RAM, score RAM, statistics, gate)
    bw_tile_score.v
  bw_feat_store.v              tile-feature RAM + sums (read-back)
  bw_stim_gen.v                SIMULATED INPUT: camera frames
  bw_tile_vec_gen.v            SIMULATED INPUT: tile vectors for Part B
  bw_sdp_ram.v                 RAM template (block RAM / LUT RAM inference)
constrs/zedboard_bw.xdc      GCLK Y9 100 MHz, LEDs (constrs_1)
sim/                         testbenches (sim_1)
  tb_bw_system.v               system test: reset, all 14 demo tests, start/error/reset/timeout cases
  tb_bw_tile_score.v           Part B datapath: 4,000 random vectors with random register values
  expected/*.mem               expected data from golden.py (read by the testbenches)
scripts/
  create_project.tcl           creates the project, the VIO IP, filesets, run settings
  build.tcl                    synthesis + implementation + bitstream + reports -> output/
  run_sim.tcl                  xsim behavioural simulation (quick / full / unit)
  vio_run.tcl, bw_expected.tcl optional Hardware Manager helper: runs tests and compares with expected
  run_sim_local.sh             the same testbenches with iverilog / verilator (no Vivado)
model/bw_model.py            Python model of the two generators; writes sim/expected + docs/EXPECTED_RESULTS.md
model/detector/              golden.py + config.py (the BurnWatch spec, unchanged)
docs/ARCHITECTURE.md         block diagram, what runs where, block-by-block explanation
docs/EXPECTED_RESULTS.md     expected VIO values for every test
```

## 3. Clock and constraints

- **GCLK = 100 MHz on pin Y9, LVCMOS33.** Checked against the Digilent `Zedboard-Master.xdc` ("Clock Source -
  Bank 13", Y9; bank 13 is fixed at 3.3 V) and the Xilinx BoardStore 2022.1 Avnet `zedboard/1.4` files
  (`sys_clk loc="Y9" iostandard="LVCMOS33"`, "System Clock, 100 MHz").
- The design runs directly on GCLK, so **no Clocking Wizard is needed** and there is no MMCM lock to wait for.
  Reset = 16-clock power-on reset (FPGA initial values) OR the VIO reset probe, synchronous, active high.
- LEDs LD0..LD7 (T22 T21 U22 U21 V22 W22 U19 U14, LVCMOS33, same sources) mirror the status: LD0 heartbeat,
  LD1 busy, LD2 done, LD3 result_valid, LD4 error, LD5 gate, LD6 any tile flagged, LD7 rd_err. They are optional.

## 4. Build in Vivado 2022.1

1. Extract the ZIP to a path **without spaces**, e.g. `C:\bw\burnwatch_zed_vio` or `~/bw/burnwatch_zed_vio`.
2. Start Vivado 2022.1. In the **Tcl Console** at the bottom:
   ```tcl
   cd C:/bw/burnwatch_zed_vio          ;# forward slashes, also on Windows
   source scripts/create_project.tcl
   ```
   This creates `vivado/burnwatch_zed_vio.xpr`, sets the part xc7z020clg484-1, adds `rtl/` to Design Sources,
   the XDC to Constraints and `sim/` to Simulation Sources, **creates and configures the VIO IP `vio_0`**
   (28 input probes, 6 output probes with initial values), generates its output products and creates its
   out-of-context synthesis run. The project opens in the GUI.
   (Batch alternative: `vivado -mode batch -source scripts/create_project.tcl` from the package folder.)
3. Bitstream:
   ```tcl
   source scripts/build.tcl
   ```
   This runs synthesis (the VIO OOC run goes first), implementation and write_bitstream, then writes to
   `output/`: **`bw_top_zed.bit`**, **`bw_top_zed.ltx`**, `timing_summary.rpt`, `utilization.rpt` and
   `build_summary.txt`. It prints the setup WNS and hold WHS. **Both must be >= 0** before you trust the
   board results. (Build time was not measured here; for a design this size it is usually several minutes.)
   (GUI alternative: Flow Navigator -> Generate Bitstream; then the files are in
   `vivado/burnwatch_zed_vio.runs/impl_1/bw_top_zed.bit` and `.ltx`.)

## 5. Simulation

In the Vivado Tcl console (project open):
```tcl
source scripts/run_sim.tcl                          ;# system test, small 320x192 geometry (~2 M clocks)
set bw_sim unit; source scripts/run_sim.tcl         ;# Part B datapath, 4,000 random vectors, seconds
set bw_sim full; source scripts/run_sim.tcl         ;# system test at 1280x720 (~32 M clocks; slow in xsim, not timed here)
```
GUI alternative: Flow Navigator -> Run Simulation -> Run Behavioral Simulation (sim top `tb_bw_system`,
define `QUICK` is preset). The result is printed in the Tcl console. Each check prints a PASS/FAIL line, and the run
ends with **`TB_BW_SYSTEM PASS: all checks passed`** (or `TB_TILE_SCORE PASS: 4000 vectors bit-exact`).
The `.mem` files are copied into `vivado/burnwatch_zed_vio.sim/sim_1/behav/xsim/` by the scripts. If you see
"cannot read quick_summary.mem", copy `sim/expected/*.mem` there by hand.

What the system testbench checks:
- **T0** reset state, and that Start held high through reset does not launch a test
- **T1** all 14 demo tests: every status/result probe, then **every tile** read back through the VIO
  read-back port (features; plus score and baselines when Part B ran) against golden.py
- **T2** a repeated test gives identical results and run_id + 1
- **T3** Start held high: exactly one run; a new 0->1 edge runs again
- **T4** Start edges while busy are ignored
- **T5/T6** part_sel = 3 -> err_code 1; unknown test_sel -> err_code 2
- **T7** tile_sel >= 3600 -> rd_err = 1 and read-back forced to 0
- **T8** reset in the middle of a run -> idle, then a correct run
- **T9** stalled input stream -> frame timeout, err_code 3, then a correct run without a reset

Without Vivado: `bash scripts/run_sim_local.sh` (iverilog), or `bash scripts/run_sim_local.sh full`
(adds the 1280x720 run with Verilator, ~20 s).

## 6. Files to use on the board

Use **`output/bw_top_zed.bit`** and **`output/bw_top_zed.ltx` from the same build**. The .ltx file holds the VIO
probe names; a .ltx from an older build will not match the bitstream. build.tcl deletes the old pair
before each build, so `output/` never holds a mixed pair.

## 7. VIO probes

VIO **output** probes drive the FPGA logic. VIO **input** probes observe it.

| Probe | Net (name in VIO) | Dir | Width | Purpose | Initial | Radix |
|---|---|---|---|---|---|---|
| probe_out0 | `vio_rst` | out | 1 | Reset: 1 = hold the design in reset, then back to 0 | 0 | Binary |
| probe_out1 | `vio_start` | out | 1 | Start: a test starts on a **0 -> 1** edge | 0 | Binary |
| probe_out2 | `vio_part_sel` | out | 2 | 0 = Part A only, 1 = Part B only, 2 = integrated A->B (3 = invalid, gives error 1) | 0 | Unsigned |
| probe_out3 | `vio_test_sel` | out | 3 | test number inside the part (A: 0-3, B: 0-3, integrated: 0-4) | 0 | Unsigned |
| probe_out4 | `vio_tile_sel` | out | 12 | tile to read back, 0..3599 = row*80 + column | 1640 (0x668) | Unsigned |
| probe_out5 | `vio_t_flag` | out | 8 | T_FLAG register (flag threshold) | 40 (0x28) | Unsigned |
| probe_in0 | `busy` | in | 1 | a test is running | - | Binary |
| probe_in1 | `done` | in | 1 | test finished; held until the next Start or reset | - | Binary |
| probe_in2 | `result_valid` | in | 1 | done and no error | - | Binary |
| probe_in3 | `error` | in | 1 | test ended with an error | - | Binary |
| probe_in4 | `err_code` | in | 4 | 0 ok, 1 bad part_sel, 2 bad test_sel, 3 frame timeout | - | Unsigned |
| probe_in5 | `run_id` | in | 8 | +1 for every accepted Start (shows a new run happened) | - | Unsigned |
| probe_in6 | `frames_run` | in | 4 | frames finished in this test | - | Unsigned |
| probe_in7 | `gate_hist` | in | 8 | bit i = gate of frame i | - | Binary |
| probe_in8 | `gate` | in | 1 | gate of the last frame | - | Binary |
| probe_in9 | `changed` | in | 12 | changed tiles in the last frame | - | Unsigned |
| probe_in10 | `flagged` | in | 12 | tiles with score >= T_FLAG in the last frame | - | Unsigned |
| probe_in11 | `score_sum` | in | 20 | sum of the 3,600 scores | - | Unsigned |
| probe_in12 | `max_score` | in | 8 | highest score | - | Unsigned |
| probe_in13 | `max_idx` | in | 12 | first tile with the highest score | - | Unsigned |
| probe_in14 | `frame_count` | in | 16 | frames since the last reset frame (reset frame = 1) | - | Unsigned |
| probe_in15 | `sum_e` | in | 20 | sum of mE over all tiles (last frame) | - | Unsigned |
| probe_in16 | `sum_y` | in | 20 | sum of mY | - | Unsigned |
| probe_in17 | `sum_s` | in | 20 | sum of mS | - | Unsigned |
| probe_in18 | `rd_err` | in | 1 | tile_sel >= 3600 (read-back forced to 0) | - | Binary |
| probe_in19 | `rd_me` | in | 8 | mE of tile tile_sel | - | Unsigned |
| probe_in20 | `rd_my` | in | 8 | mY of tile tile_sel | - | Unsigned |
| probe_in21 | `rd_ms` | in | 8 | mS of tile tile_sel | - | Unsigned |
| probe_in22 | `rd_score` | in | 8 | score of tile tile_sel | - | Unsigned |
| probe_in23 | `rd_be` | in | 16 | baseline bE of tile tile_sel (Q8) | - | Unsigned |
| probe_in24 | `rd_by` | in | 16 | baseline bY (Q8) | - | Unsigned |
| probe_in25 | `rd_bs` | in | 16 | baseline bS (Q8) | - | Unsigned |
| probe_in26 | `cycles` | in | 32 | clocks from Start to done (100 per microsecond) | - | Unsigned |
| probe_in27 | `heartbeat` | in | 1 | toggles every ~0.67 s: the clock runs | - | Binary |

(If Vivado shows a probe with a hierarchical prefix, e.g. `u_sys/busy`, it is the same signal.)

### Start: how to trigger a test reliably
- A test starts **only on a 0 -> 1 change of `vio_start`**, and only while the design is idle or done.
- **Holding Start at 1 does not start more runs.** You do not have to put it back to 0 straight away, but you
  **must set it to 0 before the next run** (a new 0 -> 1 is needed). Easiest: right-click `vio_start` ->
  set it as an *Active-High Button* and click it once, or type 1, then 0.
- Start changes while `busy` = 1 are ignored, and so is a Start held high through a reset.
- After `done` = 1, **every result stays latched** until the next accepted Start or a reset, so you can read
  it at leisure. `run_id` goes up by 1 on every accepted Start, so you can see that a repeated test really ran again.
- Read-back (`rd_*`) follows `vio_tile_sel` at any time when the design is not busy (one clock of latency).

## 8. Cloud Labs: program and test

The Cloud Labs portal details (how you reserve, upload, and which host/port the hardware server uses) come
from IIIT-Delhi's instructions. This README cannot verify them. The Vivado side is the same either way:

1. **Before the slot:** build (section 4) and check `output/build_summary.txt` (timing met = YES). Have
   `output/bw_top_zed.bit`, `output/bw_top_zed.ltx` and [docs/EXPECTED_RESULTS.md](docs/EXPECTED_RESULTS.md) ready.
2. **Connect:** Flow Navigator -> **Open Hardware Manager** -> **Open Target**. Use **Auto Connect** if the
   board's hardware server runs on the machine you are using. For a remote server, use **Open New Target** ->
   *Remote server*, with the host name and port (usually 3121) your Cloud Labs session gives you. The chain shows
   **`xc7z020_1`** (the FPGA) and `arm_dap_0` (the ARM debug port; ignore it).
   If the portal programs the board from an uploaded file instead, upload `bw_top_zed.bit` there, then still
   connect the Hardware Manager to see the VIO, and give it the `.ltx` as described in step 3 (*Refresh Device*).
3. **Program:** right-click `xc7z020_1` -> **Program Device**. Bitstream file = `output/bw_top_zed.bit`;
   Debug probes file = `output/bw_top_zed.ltx` -> **Program**. After programming, the hardware tree shows
   **`hw_vio_1`**. If it does not, select the device, set the Debug probes file in its Properties, and click
   **Refresh Device**.
4. **Open the VIO dashboard:** double-click `hw_vio_1` (or it opens as *hw_vios* / *dashboard_1*). Click
   **"+"** in the dashboard and add **all** probes.
5. **Set radix:** select the probes, right-click -> **Radix**: *Unsigned (Decimal)* for multi-bit probes and
   *Binary* for 1-bit probes and `gate_hist` (see the table). Optional: right-click `vio_start` -> *Active-High Button*.
   Check that `heartbeat` toggles.
6. **Reset:** set `vio_rst` = 1, then 0. Now `busy` = 0, `done` = 0, `error` = 0 and `run_id` = 0.
7. **Select a test:** set `vio_part_sel` and `vio_test_sel` (and `vio_t_flag`, normally 40).
8. **Start:** set `vio_start` = 1, then back to 0. Tests with a Part A frame take 9-46 ms, so the result is
   there by the next VIO refresh.
9. **Inspect:** `done` = 1, `result_valid` = 1, then compare `frames_run`, `gate_hist`, `changed`, `flagged`,
   `score_sum`, `max_score`, `max_idx`, `frame_count`, `sum_e/y/s`, `cycles` with
   [docs/EXPECTED_RESULTS.md](docs/EXPECTED_RESULTS.md). Leave `vio_tile_sel` = 1640 and compare
   `rd_me ... rd_bs` with the read-back table. Try other tiles: `max_idx` gives the hottest tile.

**Faster option (Tcl):** after step 3, in the Tcl console:
```tcl
source C:/bw/burnwatch_zed_vio/scripts/vio_run.tcl
bw_setup ; bw_reset ; bw_all
```
`bw_all` runs the 14 demo tests through the VIO and prints `PASS`/`FAIL` for each against the expected
values (`bw_run 2 0` runs one test, `bw_tile 1312` reads one tile, `bw_show` prints every probe). This helper
was tested only against a mock of the Vivado commands, not on a board. If any command errors, use the GUI steps.

### Key expected results (full table: docs/EXPECTED_RESULTS.md)

| part_sel, test_sel | Test | What it shows | Expected (after done) |
|---|---|---|---|
| 0, 0 | A0 background | Part A on a textured frame | sum_e 76127, sum_y 348600, sum_s 28800; tile 1640: rd_me 20, rd_my 94, rd_ms 8 |
| 0, 1 | A1 smoke a=2 | smoke fades edges, moves luma to grey | sum_e 72810, sum_y 353200, sum_s 27600; tile 1640: 10, 111, 4 |
| 1, 0 | B0 smoke patch | Part B scores a smoke patch | changed 300, flagged 300, score_sum 54000, max_score 180, max_idx 1230; tile 1640: rd_score 180 |
| 1, 1 | B1 saturation reject | colourful tiles score 0 (incl. the exact SAT_TOL limit) | flagged 90, score_sum 16200 |
| 1, 2 | B2 lights -> gate -> snap | global change gates, then K_FAST = 0 re-baselines | gate_hist 0110 per frame = **00000110** in VIO binary (6); final changed 0, flagged 0 |
| 2, 0 | I0 smoke grows (integrated) | the full detector path | flagged 300, changed 78, score_sum 47138, max_score 176 @ 1312, frame_count 4; tile 1640: rd_score 164 |
| 2, 1 | I1 lights on | lighting change is gated, not alarmed | gate_hist 00000110, final flagged 0 |
| 2, 2 | I2 red cloth | saturated object is not smoke | flagged 0, score_sum 136, max_score 7 |
| 2, 0, T_FLAG = 150 | I0 with a higher threshold | runtime register | flagged 180, score_sum 46238 |

### Screenshots to take (they show both parts working)
1. The Hardware Manager after programming: `xc7z020_1` programmed, `hw_vio_1` present.
2. **Part A:** VIO after **A1** (part 0, test 1): done = 1, result_valid = 1, sum_e/y/s, tile 1640 features.
3. **Part B:** VIO after **B0** (part 1, test 0): changed 300, flagged 300, score_sum 54000, rd_score 180.
4. **Part B gate:** VIO after **B2** (part 1, test 2): gate_hist = 00000110.
5. **Integrated:** VIO after **I0** (part 2, test 0): flagged 300, max_score 176, max_idx 1312, cycles 3694457.
6. **Errors:** VIO after part_sel = 3: error = 1, err_code = 1.
7. Optional: the Tcl console after `bw_all` (14 of 14 PASS), and `output/build_summary.txt` / timing summary.

## 9. 15-minute hardware checklist

Prepare before the slot: the bitstream built, timing met, EXPECTED_RESULTS.md open, the screenshot tool ready.

| Minute | Step |
|---|---|
| 0-3 | Connect the Hardware Manager, Program Device with the .bit + .ltx, open the VIO dashboard, add all probes |
| 3-5 | Set the radix (or `source scripts/vio_run.tcl; bw_setup`); heartbeat toggles; reset 1 -> 0 |
| 5-7 | Part A: run A0 and A1, compare, screenshot A1 |
| 7-9 | Part B: run B0 and B2, compare, screenshot both |
| 9-12 | Integrated: run I0, I1, I2, compare, screenshot I0; set T_FLAG = 150, run I0 again (flagged 180) |
| 12-13 | Error: part_sel = 3 -> error/err_code 1, screenshot; set part_sel back |
| 13-15 | Optional `bw_all`; reserve time to save screenshots |

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| No `hw_vio_1` / "no debug cores" / probes missing | The .ltx was not loaded, or it is from another build. Select `xc7z020_1`, set *Debug probes file* = `output/bw_top_zed.ltx` (same build as the .bit), **Refresh Device**. |
| "Debug probes file does not match" / strange probe names / stale values | Stale .ltx or .bit: rebuild with build.tcl (it deletes the old pair) and use both files from `output/`. |
| "The debug hub core was not detected" | The FPGA is not programmed (or was reprogrammed by someone else): Program Device again. The 100 MHz GCLK must be running: `heartbeat` should toggle. |
| Start does nothing | Start was already 1: set `vio_start` = 0, then 1. Or `busy` = 1: wait for done. Or it was held through a reset: set 0 then 1. Check that `run_id` increments. |
| `done` = 1 but `error` = 1 | `err_code` 1: part_sel = 3; 2: test_sel not in the table (A 0-3, B 0-3, integrated 0-4); 3: frame timeout (should not happen on the board; reset and retry). |
| Values differ from the table | Check `vio_t_flag` = 40 (the table assumes it, except the T_FLAG = 150 row); `vio_tile_sel` = 1640 for the read-back table; radix = unsigned decimal; read after `done` = 1. In Part A tests, rd_score/rd_b* show the previous Part B test (expected). |
| `gate_hist` looks reversed | VIO binary shows MSB first: 00000110 means frames 1 and 2 were gated. |
| Outputs look random after a build with timing not met | WNS < 0 in `output/build_summary.txt`. Do not trust the results; see the timing note below. |
| Simulation: "cannot read ... .mem" | Copy `sim/expected/*.mem` into `vivado/burnwatch_zed_vio.sim/sim_1/behav/xsim/`. |
| `create_ip` fails for VIO | Check that Vivado 2022.1 (with Zynq-7000 device support) is used; rerun create_project.tcl (it recreates the project with -force). |

## 11. Verification status (be precise about what ran)

| Check | Status |
|---|---|
| Part B datapath, 4,000 random vectors with random register values (iverilog) | **ran, PASS**, bit-exact with golden.py |
| System testbench, 320x192 geometry: T0-T9, 14 demo tests, every tile (iverilog and Verilator) | **ran, PASS** |
| System testbench, **1280x720**: T0-T9, 14 demo tests, every tile (Verilator) | **ran, PASS** |
| System testbench, 1280x720 (iverilog, event-driven) | see the note in the delivery message |
| Testbench sensitivity: 5 injected RTL bugs (Sobel border, rounding, prev_gate mask, luma weight, gate compare) | each one **detected** (FAIL) |
| Lint (Verilator -Wall) | clean except intentionally unused bits |
| Yosys `synth_xilinx` synthesis (xc7) | **ran**: synthesizes, no latches; ~1,320 LUT, 1,225 FF, 10 RAMB36 + 3 RAMB18, 3 DSP48 (estimate) |
| Vivado 2022.1 project creation, VIO IP generation, synthesis, implementation, bitstream | **not run here** (no Vivado available) |
| Timing closure at 100 MHz | **not verified**; check WNS/WHS in `output/build_summary.txt` |
| xsim simulation | **not run here**; same testbench as above |
| Hardware test on a ZedBoard | **not run** |
| `vio_run.tcl` | logic tested against a mock of the hw_* commands only |

**Timing note.** The data paths are pipelined: Part B has 3 arithmetic stages, and the multiplies are 8x16 bits.
The longest expected paths are the baseline-update arithmetic (subtract, variable shift, add) and the
stimulus generator's pattern logic, both a few adders deep. This is believed to close at 100 MHz on a -1
part, but that has not been checked. If WNS < 0, report the worst path from `output/timing_summary.rpt`.
The fix is one extra register stage at that point; it does not need a slower clock.

## 12. Limitations
- Frames come from the on-chip **simulated** generator, not from a camera: the ZedBoard has no video input in
  Cloud Labs. The real system's HDMI/DDR front end is not part of this package.
- 9 of the 10 tile-engine registers are fixed at the `detector/config.py` defaults in `bw_top_zed.v`. Only
  T_FLAG is on the VIO. They are module inputs of `bw_system`, so wiring more of them to VIO probes needs no other changes.
- Frame geometry is fixed at build time (1280x720, 16x16 tiles; parameters of `bw_system`).
- The read-back shows one tile at a time; the full 3,600-tile score map is checked in simulation, not on the VIO.
- The ARM-side region/state logic and the cloud verification are software and are not implemented here.

## 13. Regenerating the expected values
`python3 model/bw_model.py` (needs Python 3 + numpy) rewrites `sim/expected/*.mem`, `docs/EXPECTED_RESULTS.md`
and `scripts/bw_expected.tcl` from golden.py. Do this after any change to the generators, the test table or
golden.py, then rerun the simulations.
