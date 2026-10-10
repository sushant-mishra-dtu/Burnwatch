# BurnWatch tile engine on the ZedBoard: architecture

## The two hardware parts

In BurnWatch, the FPGA's job is the **tile engine** (`detector/golden.py` is its spec). It turns every
1280x720 frame into 3,600 tile smoke scores (80x45 tiles of 16x16 pixels). The tile engine splits
naturally into the two parts this package implements:

| Part | What it computes | golden.py functions | RTL |
|---|---|---|---|
| **A: pixel feature extractor** | per pixel: luma Y, saturation S, Sobel edge E; per tile: means mE, mY, mS | `pixel_features()`, `tile_means()` | `bw_part_a.v` = `bw_frame_scan` + `bw_pixel_feat` + `bw_sobel_window` + `bw_tile_accum` |
| **B: tile scorer + baseline memory** | per tile: score 0..255, flag, changed; per frame: gate; per tile state: baselines bE, bY, bS updated across frames | `score_tiles()`, `update_baseline()`, `TileEngine.step()` (reset frame, prev_gate, K_FAST/K_SLOW) | `bw_part_b.v` = `bw_tile_score` + baseline RAM + score RAM + statistics |

Both parts use only integer math and match golden.py bit for bit. The testbench checks every tile's
features, score and baselines.

## What runs where

| Function | Where |
|---|---|
| Part A and Part B (the tile engine) | **FPGA (this package)** |
| Demo frames and tile vectors | **FPGA, SIMULATED INPUT** (`bw_stim_gen`, `bw_tile_vec_gen`): the ZedBoard in Cloud Labs has no camera/HDMI input |
| Start/stop, test selection, result read-back | FPGA controller (`bw_ctrl`, `bw_test_rom`) driven from the **VIO** (stands in for the ARM driver) |
| Register values (K_SLOW ... GATE_TILES) | constants in `bw_top_zed.v` (detector/config.py defaults); T_FLAG from the VIO |
| Camera capture, HDMI input, DDR frame buffers | not in this package (the real system: laptop/phone -> HDMI -> board) |
| Region grouping, SUSPECT/CONFIRMED state machine, LEDs, MQTT, S3 upload | **software** (ARM/Python, `detector/regions.py`, `state.py`, `device/`), not on the FPGA |
| Cloud verification (Claude on Amazon Bedrock, NVIDIA Nemotron fallback), DynamoDB, email | **software** (AWS Lambda), not on the FPGA |

The Zynq PS (ARM) is not used in this package. The design is PL-only: one clock pin, eight LEDs, and the VIO over JTAG.

## Block diagram

```
                      GCLK 100 MHz (Y9)            VIO (JTAG)
                            |                 outputs: rst start part_sel test_sel tile_sel t_flag
                            v                 inputs : status, results, read-back (28 probes)
 bw_top_zed  +--------------------------------------------------------------------------------+
             | power-on reset + VIO reset  |  heartbeat  |  LEDs                              |
             |                                                                                |
             |  bw_system                                                                     |
             |   +----------+   +------------+                                                |
             |   | bw_ctrl  |<--| bw_test_rom|  start edge, busy/done/error, frame sequencing |
             |   +----------+   +------------+                                                |
             |      | frame_start, frame settings                                             |
             |      v                                                                         |
             |  +-------------+  RGB    +================ PART A ================+            |
             |  | bw_stim_gen |-------->| bw_frame_scan -> bw_pixel_feat ->      |  tiles     |
             |  | SIMULATED   | valid/  | bw_sobel_window -> bw_tile_accum       |--+         |
             |  | camera      | ready   +========================================+  |         |
             |  +-------------+                                                     v         |
             |  +-----------------+     tiles (mE, mY, mS)                    [source mux]    |
             |  | bw_tile_vec_gen |------------------------------------------->   |          |
             |  | SIMULATED tiles |                                               |          |
             |  +-----------------+          +================ PART B ===========v======+   |
             |                               | baseline RAM -> bw_tile_score (3 stages)  |   |
             |                               |   -> baseline write-back, score RAM,      |   |
             |  bw_feat_store <-- tiles      |   -> changed/flagged/sum/max, gate        |   |
             |  (feature RAM, sums)          +===========================================+   |
             |                                                                                |
             +--------------------------------------------------------------------------------+
```

`part_sel` picks the data path: 0 = stimulus -> Part A; 1 = tile vectors -> Part B; 2 = stimulus -> Part A -> Part B (the real detector path).

## Blocks (one paragraph each, for a viva)

- **bw_top_zed**: board top. GCLK runs the whole design at 100 MHz (Vivado adds IBUF+BUFG). A 16-clock power-on reset (register initial values) is ORed with the VIO reset into one synchronous, active-high reset. It holds the register defaults, the VIO instance, a heartbeat counter and the LED mirror.
- **bw_ctrl** (FSM IDLE -> LOAD -> FSTART -> FWAIT -> DONE): edge-detects Start, latches part/test, checks them (error codes 1/2), sends each frame of the test with a one-clock `frame_start`, waits for the frame to finish (or times out: error 3), records the gate of each frame in `gate_hist`, counts clocks, and holds `done` and every result until the next accepted Start or reset.
- **bw_test_rom**: combinational table: for (part, test, frame) it gives the number of frames, reset/update flags and the scene (smoke strength, lights, cloth).
- **bw_stim_gen** (SIMULATED INPUT): makes a 1280x720 RGB frame on the fly, one pixel per clock over valid/ready: a grey checkerboard texture, an optional smoke box (blend towards grey 128), a red cloth box, and a +40 lighting change. Pure integer function of (x, y), so Python rebuilds the same frame.
- **bw_frame_scan** (Part A stage 1): row/column counters. It walks (H+1)x(W+1) slots; the extra row and column are padding that flush the 3x3 window, so each output pixel is aligned to its own (r, c).
- **bw_pixel_feat** (Part A, combinational): Y = (77R + 150G + 29B) >> 8 and S = max - min.
- **bw_sobel_window** (Part A stages 2-4): a two-line buffer in block RAM (one word per column = {Y row r, S row r, Y row r-1}) and a 3x3 window of registers. It computes |Gx| + |Gy| >> 3, forces 0 on the image border, and emits the centre pixel's Y, S and E.
- **bw_tile_accum** (Part A stage 5): a running sum over each 16-pixel row segment, then a per-tile-column partial sum in a small RAM (80 x 48 bits). On the last pixel of a tile it outputs the means (sum >> 8) and the tile index.
- **bw_tile_vec_gen** (SIMULATED INPUT): tile features for testing Part B alone: background, a smoke patch, saturation edge cases, a lighting change, and a random stress set from two xorshift32 generators.
- **bw_tile_score** (Part B datapath, 3 stages, 1 tile/clock): Q1 = reset rule (b = x), edge drop, grey shift, saturation test, changed test, baseline-update candidate `b + ((x - b + ((1<<k)>>1)) >>> k)`; Q2 = weighted sum W_EDGE*edge_drop + W_GREY*grey_shift; Q3 = >> SCORE_SHIFT, clamp to 255, zero if not sat_ok, flag = score >= T_FLAG, and choose the baseline to write back (x on a reset frame, updated if update_this_frame and (prev_gate or not flagged), else unchanged).
- **bw_part_b**: reads the tile's baselines from RAM, runs bw_tile_score, writes the baselines and the score back, and counts changed/flagged/score sum/max per frame. After the last tile: gate = changed > GATE_TILES, and prev_gate = gate for the next frame. Its RAM read ports are free between frames for the VIO read-back.
- **bw_feat_store**: keeps the last frame's features of every tile (feature RAM) and their sums, for Part-A-only tests and read-back.
- **bw_sdp_ram**: one simple dual-port RAM template (synchronous write, registered read) used for all memories.

## Timing of one frame

- Part A: (720+1) x (1280+1) = 923,601 clocks per frame (one pixel per clock plus the padding row/column) = 9.24 ms at 100 MHz. Measured in simulation: 923,608 clocks per Part-A-only frame and 923,614 per integrated frame (pipeline latency included).
- Part B: one tile per clock; from the vector generator, 3,600 + 8 clocks per frame. In the integrated path Part B is idle most of the time, because Part A delivers a tile every 16 clocks during the last pixel row of each tile row.
- These are clock counts of the RTL in simulation. Throughput on the board depends on timing closure at 100 MHz, which has not been checked in Vivado (see README).

## Memories (Yosys `synth_xilinx` estimate, not Vivado)

| Memory | Size | Maps to |
|---|---|---|
| line buffer | 2048 x 24 | block RAM |
| tile-column partial sums | 128 x 48 | LUT RAM |
| baseline RAM {bE, bY, bS} | 4096 x 48 | block RAM |
| score RAM | 4096 x 8 | block RAM |
| feature RAM {mE, mY, mS} | 4096 x 24 | block RAM |

Yosys estimate for the whole design without the VIO: about 1,320 LUTs, 1,225 flip-flops, 48 RAM128X1S LUT-RAM cells, 10 RAMB36 + 3 RAMB18 and 3 DSP48. No latches. The Zynq-7020 has 53,200 LUTs, 140 RAMB36 and 220 DSP48. Vivado's own numbers will be in `output/utilization.rpt` after the build.
