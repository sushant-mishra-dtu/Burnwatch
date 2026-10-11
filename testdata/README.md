# testdata/

The repository currently relies on generated/synthetic vector data rather than checked-in camera clips.

| Path | Meaning | Current state |
|---|---|---|
| `clips/` | Recorded camera clips for future detector evaluation | Git-ignored; no tracked clip set in this checkout |
| `golden/` | Binary vectors from `tools/dump_golden.py` | Git-ignored; regenerate locally |
| `labels.csv` | Planned clip labels and smoke intervals | Not present in this checkout |
| `samples/` | Planned JPEGs for the cloud verifier | Not present in this checkout |

Generate the synthetic vector sets with:

```powershell
python tools/dump_golden.py --synthetic
python tools/dump_golden.py --synthetic --update-every 3 --reset-at 0,30 --name synthetic-u3
```

Do not claim field detection accuracy until real clips, labels and an evaluator are added.
