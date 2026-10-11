"""Tests for detector/regions.py: smoothing, components, tracking, candidate rules, ignore masks."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from detector.config import ArmParams  # noqa: E402
from detector.regions import RegionTracker  # noqa: E402

DT = 1 / 3   # ~3 fps, as on the ARM


def frame(*boxes, value=200):
    """uint8 [45, 80] scores with `value` inside each (ty0, ty1, tx0, tx1) box, end-exclusive."""
    s = np.zeros((45, 80), np.uint8)
    for ty0, ty1, tx0, tx1 in boxes:
        s[ty0:ty1, tx0:tx1] = value
    return s


def run(tracker, frames, t0=0.0):
    t = t0
    for f in frames:
        tracker.update(f, False, t)
        t += DT
    return t - DT


def test_single_frame_spike_is_smoothed_away():
    tr = RegionTracker(t_flag=40)
    assert tr.update(frame((10, 14, 10, 14), value=90), False, 0.0) is None   # 0.4 * 90 = 36 < 40
    assert tr.update(frame(), False, DT) is None


def test_region_bbox_tiles_and_score():
    tr = RegionTracker(t_flag=40)
    r = tr.update(frame((10, 14, 20, 23)), False, 0.0)     # 0.4 * 200 = 80 >= 40
    assert r.tiles == 12 and r.bbox_tiles == (20, 10, 23, 14)
    assert r.bbox == [320, 160, 368, 224]                   # full-res pixels, multiples of 16
    assert r.score_mean == 200


def test_small_components_are_dropped_and_largest_kept():
    tr = RegionTracker(t_flag=40)
    assert tr.update(frame((5, 6, 5, 8)), False, 0.0) is None            # 3 tiles < MIN_TILES
    r = tr.update(frame((5, 6, 5, 8), (30, 33, 40, 44)), False, DT)       # the 3-tile blob and a 12-tile one
    assert r.bbox_tiles == (40, 30, 44, 33)


def test_gated_frame_changes_nothing():
    tr = RegionTracker(t_flag=40)
    r = tr.update(frame((10, 14, 20, 24)), False, 0.0)
    s = tr.s.copy()
    assert tr.update(frame(), True, DT) is r
    assert np.array_equal(tr.s, s) and len(r.history) == 1


def test_static_region_is_not_a_candidate():
    tr = RegionTracker(t_flag=40)
    run(tr, [frame((20, 25, 30, 35))] * 40)                 # 13 s, same blob
    assert tr.region is not None and tr.candidate() is None


def test_growing_region_becomes_candidate_only_after_persist():
    tr = RegionTracker(t_flag=40)
    frames = [frame((20, 25, 30, 32 + i // 3)) for i in range(40)]      # widens by a tile a second
    t = 0.0
    for f in frames:
        tr.update(f, False, t)
        if t < ArmParams().PERSIST_S:
            assert tr.candidate() is None
        t += DT
    assert tr.candidate() is tr.region


def test_rising_top_edge_is_a_candidate():
    tr = RegionTracker(t_flag=40, cfg=ArmParams(GROW_FRAC=10, CENTROID_RISE=100))   # only the top-edge rule
    frames = [frame((30 - i // 4, 34 - i // 4, 30, 34)) for i in range(30)]        # same size, moving up
    run(tr, frames)
    assert tr.candidate() is not None


def test_moving_away_starts_a_new_region():
    tr = RegionTracker(t_flag=40)
    t = run(tr, [frame((20, 25, 30, 35))] * 25)
    first = tr.region
    tr.update(frame(), False, t + DT)                       # still smoothed above threshold for a frame or two
    for k in range(2, 6):
        tr.update(frame((5, 10, 60, 65)), False, t + k * DT)
    assert tr.region is not first and tr.region.first_t > first.first_t


def test_ignore_mask_expires():
    tr = RegionTracker(t_flag=40)
    m = np.zeros((45, 80), bool)
    m[10:20, 10:20] = True
    tr.ignore(m, until=5.0)
    assert tr.update(frame((12, 16, 12, 16)), False, 0.0) is None
    assert tr.update(frame((12, 16, 12, 16)), False, 5.0) is not None
