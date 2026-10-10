# Native RTL simulation for BurnWatch

This is a standalone SystemVerilog implementation of the **scoring core** in
`detector/golden.py` (spec v1), running directly in Vivado/XSim 2022.1. It operates
on full 1280x720 RGB frames and emits 3,600 scores in row-major order. It retains
per-tile Q8 baselines across calls, uses runtime scoring parameters from the
contract's `params.txt`, and implements reset-before-score, previous-frame gate
updates, K_FAST=0, flagged-tile freeze, and update decimation.

The core reads RGB words packed as `R | G<<8 | B<<16`. Its private asynchronous
frame address/data port and score address/valid port are only the local harness
interface. They are **not** the AXI-Lite/m_axi register and bus interface in
contracts section 7. No shared register map or contract is changed. The planned
P8 HLS/AXI overlay and P9 board verification remain separate work.

The native datapath reads one pixel per clock, uses three rotating luma line
buffers, and computes the previous row's Sobel edges concurrently. Borders have
zero edge strength. Integer feature sums and Q8 baselines are scored after the
frame. Actual clock timing and throughput still require hardware validation.
The design contains no initial data, file I/O, delays or simulation-only golden
calculation; those exist only in the testbench. FPGA synthesis/resource fit and
timing closure have to be verified before making any deployment claim.

The testbench loads the binary vectors and text parameters defined in
`docs/contracts.md` section 8. It verifies score count/order, every score,
gate, changed, frame_count, and (when available) every baseline and prev_gate.
It exercises two 40-frame sets: `synthetic` and `synthetic-u3` (update every
third frame, resets on frames 0 and 30). A missing file, timeout, mismatch or
incomplete score stream produces `$fatal`; passing produces `BURNWATCH RTL PASS`.

## Set up from the repository

```powershell
.\.venv\Scripts\python.exe tools/dump_golden.py --synthetic
.\.venv\Scripts\python.exe tools/dump_golden.py --synthetic --update-every 3 --reset-at 0,30 --name synthetic-u3
.\.venv\Scripts\python.exe overlays/rtl_sim/install_project.py --project "M:\Vivado Projects\Burnwatch\Burnwatch\Burnwatch.xpr" --vectors testdata/golden
```

The installer copies only these sources and generated vectors into the chosen
project. It backs up the original source files and `.xpr` under a timestamped
`codex_backup_*` folder. No original file is deleted. It generates a local include
file with vector/report paths and a Tcl script configuring the correct tops.

## Run the installed project

Close and reopen the project if it was open while sources were installed.
The batch runner also configures `tile_engine` as the synthesis top and
`tb_tile_engine` as the simulation top, with testbench use restricted to simulation.

```powershell
& "M:\Vivado Projects\Burnwatch\Burnwatch\run_local_sim.ps1"
```

Alternatively, in Vivado select Run Behavioral Simulation, then **Run All**.
The default 1 us GUI run is much shorter than one 720p frame, so do not treat an
initial paused waveform as a completed test. Runtime is configured to `all` by
the supplied Tcl. A full run checks 80 frames / 288,000 tile scores. Inspect
`simulation_results/rtl_result.txt` for the pass summary and the Vivado log for
per-frame results. Simulated clock cycles are **not** physical board FPS.

No HDMI capture, ARM/Linux execution, AWS communication or physical FPGA
validation is included in this standalone scoring-core simulation.
