# testdata/

Videos and generated vectors are git-ignored; the labels and the review of each alarm are tracked.

| Path | Meaning | Current state |
|---|---|---|
| `clips/20261011_*.mp4` | Our own phone clips of incense smoke (audio removed; originals in `clips/originals/`) | Git-ignored; 6 clips, smoke from the first frame |
| `clips/firesense/` | FIRESENSE smoke set: 13 smoke (`pos/`) and 9 non-smoke (`neg/`) videos | Git-ignored; download below |
| `golden/` | Binary vectors from `tools/dump_golden.py` | Git-ignored; regenerate locally |
| `labels.csv` | Label and smoke window for every clip (`docs/contracts.md` section 8) | Tracked, 28 rows |
| `suspect_review.csv` | By-eye check of every SUSPECT snapshot: is the region on the smoke? | Tracked |
| `samples/` | Planned JPEGs for the cloud verifier | Not present in this checkout |

## FIRESENSE download

FIRESENSE database of videos for flame and smoke detection (FP7-ENV-244088), Dimitropoulos, Barmpoutis and
Grammalidis, [doi:10.5281/zenodo.836749](https://doi.org/10.5281/zenodo.836749), licence CC-BY-4.0. Only the
smoke archive is used (197.6 MB, md5 `5ee6bc867c4a9332b4e75f308c26fc23`):

```bash
mkdir -p testdata/clips/firesense && cd testdata/clips/firesense
curl -L -o smoke_videos.1407.zip "https://zenodo.org/api/records/836749/files/smoke_videos.1407.zip/content"
md5sum smoke_videos.1407.zip
python -c "import zipfile; zipfile.ZipFile('smoke_videos.1407.zip').extractall('.')"
```

`neg/testneg03.809.avi` declares 25 s but only about 7 s decode.

## Evaluate

```bash
python tools/eval_clips.py                    # writes docs/test_table.md
python tools/eval_clips.py --snapshots out/   # also saves the frame at every SUSPECT, for the review file
```

Generate the synthetic vector sets with:

```powershell
python tools/dump_golden.py --synthetic
python tools/dump_golden.py --synthetic --update-every 3 --reset-at 0,30 --name synthetic-u3
```
