# RTL-SIM validation

Verified 10 Oct 2026 23:49 IST with Vivado/XSim 2022.1.

```text
BURNWATCH RTL PASS frames=80 tile_scores=288000 mismatches=0 max_cycles=928802
Clock period: 10 ns. Simulated core cycles, not measured board throughput.
```

All 80 full-resolution 1280x720 synthetic frames passed. Each frame checked 3,600 scores, output completeness/order, gate, changed, frame_count, all three persisted Q8 baselines, and prev_gate. Both vector sets contain the frame-20 brightness change; synthetic-u3 also disables baseline updates on two out of three frames and resets on frame 30.

Golden-vector digests printed by the unchanged dump_golden.py:

- synthetic: sha256 prefix df5d3395673a5e38
- synthetic-u3: sha256 prefix 5b2e921b497e9705

Reference/contract regression: 24 tests passed (`tests/test_golden.py`, `tests/test_contracts.py`). The report comes from the final single-pass RTL sources in this folder. The top-level algorithm and binary formats were not changed. No FPGA synthesis/resource-fit result, timing closure, AXI overlay integration, HDMI capture, physical board FPS or power measurement is claimed.

Reproduce using README.md and the installed run_local_sim.ps1.
