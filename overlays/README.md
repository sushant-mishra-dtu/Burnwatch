# overlays/

The final PYNQ overlay location. A deployable PYNQ build should provide a matching pair:

```text
overlays/<name>.bit
overlays/<name>.hwh
```

The current checkout contains no final `.bit`/`.hwh` pair. The implemented hardware evidence is under [`rtl_sim/`](rtl_sim/), which is a standalone private-port SystemVerilog simulation/synthesis/OOC flow, not a PYNQ overlay.

Do not describe the RTL simulation or OOC checkpoint as board readiness. A future overlay still needs an AXI/PS wrapper, interface constraints, timing closure and a board test.
