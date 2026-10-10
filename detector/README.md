# detector/

The smoke detector logic. It runs on both the laptop and the PYNQ's ARM.

- `golden.py`: the integer reference of the tile engine. **This file is the spec.** The HLS core in `hls/` must match it bit for bit.
- `config.py`: every threshold and weight (`Params`). In the PL these are AXI-Lite registers.
- `regions.py`: temporal smoothing, connected regions and the "rising or spreading" cue.
- `state.py`: the CLEAR / SUSPECT / CONFIRMED / REJECTED state machine. It only returns actions and never runs them.
