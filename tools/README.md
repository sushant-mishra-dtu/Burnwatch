# tools/

Laptop-side tools:

- `camfeed.py`: shows the phone camera (or a clip) full screen on the HDMI output that feeds the PYNQ.
- `viewer.py`: live view drawn from the 3,600 tile scores the box sends over UDP.
- `eval_clips.py`: runs the detector offline on labelled clips and writes the test table.
- `dump_golden.py`: writes the HLS test vectors from `detector/golden.py`.
- `bench.py`: throughput measurements for `docs/results.md`.
- `gen_header.py`: writes `hls/config.h` from `detector/config.py`.
