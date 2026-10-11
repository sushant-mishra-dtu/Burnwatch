# zedboard/

The BurnWatch tile engine as hand-written Verilog-2001 for a **ZedBoard** (`xc7z020clg484-1`). It is controlled and observed through **VIO** for IIIT-Delhi Cloud Labs with Vivado 2022.1.

- `burnwatch_zed_vio/`: the package (RTL, testbenches, XDC, Tcl, Python model, docs). Start with its
  [README](burnwatch_zed_vio/README.md).
- `burnwatch_zed_vio.zip`: the same package as one download.

Part A (pixels → tile means) and Part B (tile score, gate, baselines) are checked against `detector/golden.py` in simulation. The frames come from an on-chip generator because the Cloud Labs board has no camera input. This is separate from the HLS/PYNQ path and does not replace it.

The package is therefore useful as a **PL-only validation/demo target**, not as evidence that the final PYNQ camera/cloud product is complete.
