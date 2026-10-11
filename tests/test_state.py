"""Tests for detector/state.py with a fake clock, fake regions and hand-made verdicts."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from detector.state import StateMachine  # noqa: E402
from tools import contracts  # noqa: E402

T0 = 1_791_622_800.0
CAM = "rwa-gate-2"


class FakeRegion:
    def __init__(self):
        self.mask = np.zeros((45, 80), bool)
        self.mask[14:22, 30:38] = True
        self.tiles = 64
        self.bbox = [480, 224, 608, 352]
        self.score_mean = 107.0


def types(actions):
    return [a["type"] for a in actions]


def verdict(ts, state):
    return {"camera": CAM, "ts": ts, "is_smoke": state == "CONFIRMED", "confidence": 0.9,
            "likely_source": "unclear", "state": state, "verifier": "claude", "evidence": "x"}


def suspect(sm, t=T0):
    out = sm.step(t, FakeRegion(), True)
    assert sm.state == "SUSPECT"
    return next(a["event"] for a in out if a["type"] == "upload")


def test_clear_to_suspect_emits_a_contract_event():
    sm = StateMachine(CAM)
    assert sm.step(T0, None, True) == [] and sm.state == "CLEAR"
    ev = suspect(sm, T0 + 0.4)
    contracts.check_fields(ev, contracts.EVENT_FIELDS)
    assert ev == {"camera": CAM, "state": "SUSPECT", "score": 0.42, "tiles": 64, "bbox": [480, 224, 608, 352],
                  "s3_key": f"frames/{CAM}/{int(T0)}.jpg", "ts": int(T0)}


def test_confirmed_only_on_matching_ts():
    sm = StateMachine(CAM)
    ev = suspect(sm)
    assert sm.on_verdict(verdict(ev["ts"] - 1, "CONFIRMED"), T0 + 5) == [] and sm.state == "SUSPECT"
    assert sm.on_verdict(verdict(ev["ts"], "CONFIRMED"), T0 + 5) == [{"type": "state", "state": "CONFIRMED"}]


def test_rejected_ignores_region_rebaselines_and_clears():
    sm = StateMachine(CAM)
    ev = suspect(sm)
    out = sm.on_verdict(verdict(ev["ts"], "REJECTED"), T0 + 10)
    assert types(out) == ["state", "ignore", "rebaseline", "state"] and sm.state == "CLEAR"
    ign = out[1]
    assert ign["until"] == T0 + 10 + 180 and ign["mask"].sum() == 64


def test_upload_cooldown():
    sm = StateMachine(CAM)
    ev = suspect(sm)
    sm.on_verdict(verdict(ev["ts"], "REJECTED"), T0 + 10)
    assert sm.step(T0 + 119, FakeRegion(), True) == [] and sm.state == "CLEAR"
    assert "upload" in types(sm.step(T0 + 120, FakeRegion(), True))


def test_verdict_timeout_once_and_stays_suspect():
    sm = StateMachine(CAM)
    ev = suspect(sm)
    assert sm.step(T0 + 89, None, False) == []
    assert sm.step(T0 + 90, None, False) == [{"type": "verdict_timeout", "ts": ev["ts"]}]
    assert sm.step(T0 + 200, None, False) == [] and sm.state == "SUSPECT"


def test_confirmed_clears_after_region_gone_60s():
    sm = StateMachine(CAM)
    ev = suspect(sm)
    sm.on_verdict(verdict(ev["ts"], "CONFIRMED"), T0 + 5)
    sm.step(T0 + 10, None, False)                       # gone from t+10
    sm.step(T0 + 50, None, True)                        # back: timer resets
    sm.step(T0 + 51, None, False)
    assert sm.step(T0 + 110, None, False) == [] and sm.state == "CONFIRMED"
    assert sm.step(T0 + 111, None, False) == [{"type": "state", "state": "CLEAR"}]


def test_verdict_outside_suspect_is_ignored():
    sm = StateMachine(CAM)
    assert sm.on_verdict(verdict(int(T0), "CONFIRMED"), T0) == [] and sm.state == "CLEAR"
