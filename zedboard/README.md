# zedboard/

The BurnWatch tile engine (spec: `detector/golden.py`) as hand-written Verilog-2001 for a **ZedBoard**
(xc7z020clg484-1). It is controlled and observed through **VIO**, for IIIT-Delhi Cloud Labs with Vivado 2022.1.

- `burnwatch_zed_vio/`: the package (RTL, testbenches, XDC, Tcl, Python model, docs). Start with its
  [README](burnwatch_zed_vio/README.md).
- `burnwatch_zed_vio.zip`: the same package as one download.

Part A (pixels -> tile means) and Part B (tile score, gate, baselines) match golden.py bit for bit in
simulation. The frames come from an on-chip generator (simulated input), because the board has no camera input
in Cloud Labs. This is separate from the HLS/PYNQ path (P8/P9) and does not replace it.
