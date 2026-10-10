# Standalone core OOC placement/routing validation

Measured on 11 Oct 2026 with Vivado 2022.1, targeting `xc7z020clg400-1`.
The flow completed at 00:37 IST with exit code 0. This is isolated module
analysis; it does not implement a complete PYNQ-Z2 system.

## Reproduce

Run the installed `implement_core_ooc.tcl` with the existing `.xpr` path as its
single argument. The script uses non-project synthesis with
`-mode out_of_context`, then optimization, placement, physical optimization,
routing and reports. It uses a 10 ns clock and assumes the future parent's clock
buffer is at `BUFGCTRL_X0Y0` (`HD.CLK_SRC`). See README.md for the command.

No package pins are assigned. The normal `impl_1` run still needs an AXI/PS
wrapper: the bare core's private ports exceeded its 125 package I/O sites.
The script preserves that project/run and creates separate checkpoints.

## Measured results

| Check | Result |
|---|---|
| Placement and routing | Completed; 9,114 / 9,114 routable nets fully routed |
| Routing errors | 0 |
| LUTs | 12,708 / 53,200 (23.89%) |
| Distributed RAM LUTs | 9,372 / 17,400 (53.86%) |
| Flip-flops | 1,005 / 106,400 (0.94%) |
| DSPs | 7 / 220 (3.18%) |
| Block RAM tiles | 0 / 140 |
| Package I/O buffers | 0 (OOC boundary ports are internal module interfaces) |
| Setup WNS at 100 MHz | -20.092 ns: **FAIL** |
| Setup TNS | -311,408.031 ns; 52,834 failing endpoints |
| Hold WHS | +0.008 ns; 0 failing endpoints |
| Unconstrained internal endpoints | 0 |
| Boundary timing constraints | 117 inputs / 88 outputs lack delay constraints |
| Default DRC | 21 warnings; no error violations |

The worst reported setup path spans 33 logic levels and 29.320 ns of data-path
delay. It begins at a tile-index register, passes through baseline reads and
score arithmetic, and ends at a baseline RAM write-enable. RTL pipelining and
memory organization need work before claiming 100 MHz timing closure. The DRC
warnings include DSP input/output pipelining (19), boundary nets without routable
loads (1), and the absent PS7 block (1). They were not downgraded or suppressed.

The user's `Unisim Transformation Summary` is informational: the inferred RAM
arrays are transformed into distributed-RAM and mux primitives. It does not
establish timing closure or board readiness.

## Scope and evidence

The scoring RTL is unchanged from the 80-frame XSim pass (288,000 tile scores,
zero mismatches, persisted baseline state checked). The installed RTL SHA256
remains `0737cbfa8327c50dcb165c599a0e130f16bf1f5b7eda0607b421230c1082346f`.
The repository checkout differs only in line endings; normalized text matches.
No extra functional simulation was needed for this separate Tcl workflow.

The module-analysis flow does not route its external boundary connections without
parent-context partition-pin constraints. Its clock source location is an
assumption. The results therefore cover internal core placement/routing only;
full interface timing, actual parent clock, PS/AXI integration, board pinout,
bitstream generation, physical FPGA operation and board FPS remain unverified.
No timing exceptions, tied-off interface ports or target-device changes were
used to make this result.

The text reports are copied to `reports/` in this folder: `ooc_utilization.rpt`,
`ooc_timing_summary.rpt`, `ooc_route_status.rpt`, `ooc_drc.rpt` and `ooc_result.txt`.
The checkpoints (`tile_engine_core_synth.dcp`, `tile_engine_core_routed.dcp`) and the
Vivado log stay in `core_ooc_results/` of the local Vivado project, since the script
regenerates them.

To inspect placement, close any currently open synthesized/implemented design
in Vivado and enter this in its Tcl console:

```tcl
open_checkpoint {<Vivado project>/core_ooc_results/tile_engine_core_routed.dcp}
```

Opening this checkpoint does not convert the original project into a board top.
