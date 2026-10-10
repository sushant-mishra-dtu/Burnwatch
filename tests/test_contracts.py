import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import contracts as c  # noqa: E402


def test_udp_sizes():
    assert c.UDP_HEADER_SIZE == 31
    assert c.UDP_PACKET_SIZE == 3631


def test_udp_frame_round_trip():
    scores = np.arange(3600, dtype=np.uint32).astype(np.uint8).reshape(45, 80)
    pkt = c.pack_viewer_packet(7, 1791622800.5, "SUSPECT", True, 3.1, "pl", (480, 224, 608, 352), scores)
    assert len(pkt) == c.UDP_PACKET_SIZE and pkt[:4] == b"BW01"
    d = c.unpack_viewer_packet(pkt)
    assert (d["kind"], d["frame_no"], d["ts"], d["state"], d["gate"], d["mode"]) == \
        ("frame", 7, 1791622800.5, "SUSPECT", True, "pl")
    assert d["bbox"] == (480, 224, 608, 352)
    assert abs(d["fps"] - 3.1) < 1e-6
    assert np.array_equal(np.frombuffer(d["scores"], np.uint8).reshape(45, 80), scores)
    assert c.unpack_viewer_packet(c.pack_viewer_packet(0, 0, "CLEAR", 0, 0, "arm", None, scores))["bbox"] is None


def test_udp_verdict_round_trip():
    v = {"camera": "rwa-gate-2", "ts": 1791622800, "is_smoke": True, "confidence": 0.86,
         "likely_source": "leaf or biomass burning", "state": "CONFIRMED",
         "verifier": "nemotron", "evidence": "Grey plume."}
    d = c.unpack_viewer_packet(c.pack_verdict_packet(v))
    assert d.pop("kind") == "verdict" and c.check_fields(d, c.VERDICT_FIELDS) == v


def test_topics_keys_metadata():
    assert c.topic("rwa-gate-2", "verdict") == "burnwatch/rwa-gate-2/verdict"
    assert c.client_id("rwa-gate-2") == "burnwatch-rwa-gate-2"
    assert c.client_id("rwa-gate-2", "selftest") == "burnwatch-rwa-gate-2-selftest"
    key = c.s3_key("rwa-gate-2", 1791622800)
    assert key == "frames/rwa-gate-2/1791622800.jpg"
    assert c.parse_s3_key(key) == ("rwa-gate-2", 1791622800)
    with pytest.raises(ValueError):
        c.topic("RWA Gate", "events")
    ev = {"camera": "rwa-gate-2", "state": "SUSPECT", "score": 0.42, "tiles": 11,
          "bbox": [480, 224, 608, 352], "s3_key": key, "ts": 1791622800}
    c.check_fields(ev, c.EVENT_FIELDS)
    md = c.s3_metadata(ev)
    assert md == {"camera": "rwa-gate-2", "ts": "1791622800", "score": "0.42",
                  "tiles": "11", "bbox": "[480,224,608,352]"}
    assert json.loads(md["bbox"]) == ev["bbox"]


def test_rgb_word_packing():
    rgb = np.random.default_rng(0).integers(0, 256, (720, 1280, 3), dtype=np.uint8)
    w = c.pack_rgb_words(rgb)
    assert w.dtype == np.uint32 and w.shape == (921600,)
    assert int(w[0]) == int(rgb[0, 0, 0]) | (int(rgb[0, 0, 1]) << 8) | (int(rgb[0, 0, 2]) << 16)
    assert int(w.max()) < (1 << 24)
    assert np.array_equal(c.unpack_rgb_words(w), rgb)
