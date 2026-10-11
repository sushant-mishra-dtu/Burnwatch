# tools/

Implemented utilities:

| File | What it does |
|---|---|
| `camfeed.py` | Opens a webcam or clip, letterboxes to 1280×720 and displays it full-screen on a selected monitor |
| `contracts.py` | Shared MQTT/S3/UDP/RGB-packing constants and helpers |
| `dump_golden.py` | Generates deterministic synthetic, clip or PNG golden vectors and state dumps |
| `gen_header.py` | Generates/checks `hls/config.h` from `detector/config.py` |

Documented but absent from this checkout:

```text
viewer.py
eval_clips.py
bench.py
replay_viewer.py
cloud_selftest.py
```

Therefore the repository currently has no checked-in live score viewer, field-clip evaluator or performance benchmark. Do not link those commands as runnable until their files are added.
