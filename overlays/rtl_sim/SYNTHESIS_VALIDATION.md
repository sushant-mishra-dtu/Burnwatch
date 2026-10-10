# Native RTL synthesis verification

Verified 11 Oct 2026 00:20 IST using Vivado 2022.1, target xc7z020clg400-1.

The reported Common 17-165 error occurred before synth_design, in an unquoted incremental-checkpoint path containing spaces. AUTO_INCREMENTAL_CHECKPOINT is now false and INCREMENTAL_CHECKPOINT is empty. The failed run was reset, a 10 ns ap_clk constraint was added, and synth_1 completed successfully. No scoring RTL changes were made; its SHA256 remains 0737cbfa8327c50dcb165c599a0e130f16bf1f5b7eda0607b421230c1082346f.

| Metric | Post-synthesis result |
|---|---|
| Slice LUTs | 12658 / 53200 (23.79%) |
| LUTs used as distributed RAM | 9372 / 17400 (53.86%) |
| Flip-flops | 356 / 106400 |
| DSPs | 7 / 220 |
| Block RAM tiles | 0 / 140 |
| Bonded I/O | 206 / 125 (164.80%) |
| Clock target | 10 ns (100 MHz) |
| Worst setup slack | -17.202 ns |
| Timing status | Constraints NOT met |

Successful synthesis does not establish physical fit or timing closure. The scoring core is a standalone simulation top: its private data/control ports must be connected inside an AXI/PS wrapper rather than mapped individually to board pins. The datapath/memory access needs pipelining before the 100 MHz target can be claimed. There are also 117 inputs and 88 outputs without interface delay constraints; real interface constraints belong with that wrapper. No bitstream, implementation success, board FPS or power result is claimed.

Source reports: copied to `reports/synth_utilization.rpt` and `reports/synth_timing_summary.rpt` (from `synthesis_results/` in the Vivado project). XSim pass line: `reports/xsim_rtl_result.txt`. Reproduce with synthesize_project.tcl. Previous XSim verification remains 80 frames / 288000 scores / zero mismatches because the RTL is unchanged.
