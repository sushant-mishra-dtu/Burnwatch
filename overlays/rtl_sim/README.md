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

## Synthesis and timing reports

Vivado 2022.1 can generate an unquoted incremental-checkpoint path when the
project directory contains spaces. If `[Common 17-165]` mentions the checkpoint
path, disable both automatic and manual incremental reuse on `synth_1`, reset
that failed run, and synthesize again. The installer now saves those settings.
Do not change or relocate the scoring source to address this configuration error.

The supplied synthesis script also adds a 10 ns clock constraint and writes
resource and timing reports. Run it from PowerShell:

```powershell
& "M:\amd_xilinx\Vivado\2022.1\bin\vivado.bat" -mode batch -source "M:\Vivado Projects\Burnwatch\Burnwatch\synthesize_project.tcl" -tclargs "M:\Vivado Projects\Burnwatch\Burnwatch\Burnwatch.xpr"
```

Inspect `synthesis_results/utilization.rpt` and `timing_summary.rpt`. This is
post-synthesis timing, not post-route timing closure. The standalone memory and
parameter ports are not a board pinout: physical deployment requires the planned
AXI/PS wrapper and appropriate interface constraints. The reports must be assessed
before claiming the complete design fits or runs at 100 MHz on the board.

Synthesis results from the Vivado project are summarised in
[SYNTHESIS_VALIDATION.md](SYNTHESIS_VALIDATION.md), with the raw reports in `reports/`.
Measured core placement/routing results and remaining timing limits are in
[OOC_VALIDATION.md](OOC_VALIDATION.md).

## Core-only placement and routing

The normal `impl_1` run treats every private frame/data/parameter connection as a
package pin. That cannot fit this bare top: the reported 205 unplaced ports exceed
125 available package sites. Assigning arbitrary pin locations cannot resolve it.
A complete board design must connect these ports internally through the AXI/PS
wrapper before ordinary top-level implementation can succeed.

For isolated core analysis, use the documented Vivado UG905 module-analysis flow:

```powershell
& "M:\amd_xilinx\Vivado\2022.1\bin\vivado.bat" -mode batch -source "M:\Vivado Projects\Burnwatch\Burnwatch\implement_core_ooc.tcl" -tclargs "M:\Vivado Projects\Burnwatch\Burnwatch\Burnwatch.xpr"
```

This runs non-project synthesis with `-mode out_of_context`, then optimization,
placement, physical optimization, routing and reports. It keeps the 10 ns target
clock, assumes an external parent clock buffer at `BUFGCTRL_X0Y0`, and tags the
module as an HD partition. Source RTL and algorithm parameters are unchanged.
No I/O buffers, package pin constraints, bitstream or fake external tie-offs are
added. This separate flow preserves the existing project and failed board-top
run as evidence; it does not turn `impl_1` into a complete PYNQ overlay.

Reports and reusable checkpoints are in `core_ooc_results`. Open
`tile_engine_core_routed.dcp` in Vivado to inspect physical placement. In the
Vivado Tcl console use `open_checkpoint {<absolute path to that file>}` after
closing any currently open synthesized/implemented design. The module's
boundary nets are intentionally not routed in the module-analysis flow unless
parent-context partition-pin constraints are supplied. Therefore this analysis
checks internal core placement/routing, not external interface timing or board
connectivity. Check `timing_summary.rpt` separately: completing routing does not
mean the 100 MHz target was met. Full-system integration needs the AXI wrapper,
actual parent clock/interface constraints, pinout and a new implementation run.
