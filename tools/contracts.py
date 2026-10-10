"""Shared formats for BurnWatch. docs/contracts.md is the source of truth; this
module is its executable copy, so code imports these instead of retyping them.

Pure Python (struct, json, re). numpy is imported lazily, only by the frame
packing helpers, so this module also loads on the PYNQ and in tests.
Scripts put the repo root on sys.path and use `from tools import contracts`.
"""
import json
import re
import struct

# --- Geometry -----------------------------------------------------------------
IMG_W, IMG_H = 1280, 720
TILES_X, TILES_Y = 80, 45
N_TILES = TILES_X * TILES_Y          # 3600

# --- Cameras, MQTT, S3 --------------------------------------------------------
CAMERA_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
TOPIC_ALL = "burnwatch/#"
TOPIC_TEST = "burnwatch/test"
TOPIC_KINDS = ("events", "verdict", "heartbeat")
QOS = {"events": 1, "verdict": 1, "heartbeat": 0}
HEARTBEAT_S = 60

STATES = ("CLEAR", "SUSPECT", "CONFIRMED", "REJECTED")
MODES = ("arm", "pl", "pl-live")
LIKELY_SOURCES = (
    "open waste burning", "leaf or biomass burning", "incense or small flame",
    "cooking or tandoor", "vehicle exhaust", "steam or fog", "dust",
    "not smoke", "unclear",
)


def check_camera(camera):
    if not CAMERA_RE.match(camera):
        raise ValueError(f"bad camera id {camera!r}: use [a-z0-9-], max 32 chars")
    return camera


def client_id(camera, suffix=None):
    """burnwatch-<camera> for the device; burnwatch-<camera>-<suffix> for any
    tool that connects at the same time (IoT Core drops duplicate client ids)."""
    cid = f"burnwatch-{check_camera(camera)}"
    return f"{cid}-{suffix}" if suffix else cid


def topic(camera, kind):
    if kind not in TOPIC_KINDS:
        raise ValueError(f"unknown topic kind {kind!r}")
    return f"burnwatch/{check_camera(camera)}/{kind}"


def s3_key(camera, ts):
    """frames/<camera>/<ts>.jpg, ts = integer Unix seconds (UTC)."""
    return f"frames/{check_camera(camera)}/{int(ts)}.jpg"


def parse_s3_key(key):
    m = re.match(r"^frames/([a-z0-9][a-z0-9-]{0,31})/(\d+)\.jpg$", key)
    if not m:
        raise ValueError(f"not a BurnWatch frame key: {key!r}")
    return m.group(1), int(m.group(2))


def s3_metadata(event):
    """S3 user metadata for a frame upload (boto3 Metadata=...; S3 adds the
    x-amz-meta- prefix). All values are ASCII strings."""
    return {
        "camera": event["camera"],
        "ts": str(int(event["ts"])),
        "score": f'{event["score"]:.2f}',
        "tiles": str(int(event["tiles"])),
        "bbox": json.dumps([int(v) for v in event["bbox"]], separators=(",", ":")),
    }


def to_json(msg):
    """Compact UTF-8 JSON for MQTT payloads."""
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# Field name -> allowed Python types, for tests and for checking incoming messages.
EVENT_FIELDS = {"camera": str, "state": str, "score": float, "tiles": int,
                "bbox": list, "s3_key": str, "ts": int}
VERDICT_FIELDS = {"camera": str, "ts": int, "is_smoke": bool, "confidence": float,
                  "likely_source": str, "state": str, "verifier": str, "evidence": str}
HEARTBEAT_FIELDS = {"ts": int, "state": str, "fps": float, "mode": str, "queue_len": int}


def check_fields(msg, spec):
    """Raise ValueError unless msg has exactly the fields in spec, with the right types."""
    if set(msg) != set(spec):
        raise ValueError(f"fields {sorted(msg)} != {sorted(spec)}")
    for k, t in spec.items():
        v = msg[k]
        ok = (isinstance(v, (int, float)) and not isinstance(v, bool)) if t is float else \
             (isinstance(v, int) and not isinstance(v, bool)) if t is int else isinstance(v, t)
        if not ok:
            raise ValueError(f"{k}={v!r} is not {t.__name__}")
    return msg


# --- UDP viewer packets (device -> laptop :9999) --------------------------------
VIEWER_PORT = 9999

# Frame packet: header + 3600 uint8 scores, row-major 45x80. Little-endian, no padding.
UDP_MAGIC = b"BW01"
UDP_HEADER_FMT = "<4sIdBBfB4H"     # magic, frame_no, ts, state, gate, fps, mode, x1 y1 x2 y2
UDP_HEADER_SIZE = struct.calcsize(UDP_HEADER_FMT)   # 31
UDP_PACKET_SIZE = UDP_HEADER_SIZE + N_TILES         # 3631

# Verdict packet: magic + UTF-8 verdict JSON, sent when a verdict reaches the device.
UDP_VERDICT_MAGIC = b"BWV1"


def pack_viewer_packet(frame_no, ts, state, gate, fps, mode, bbox, scores):
    """state in STATES, mode in MODES, bbox (x1, y1, x2, y2) or None,
    scores: 3600 uint8 values (numpy array or bytes)."""
    data = scores.tobytes() if hasattr(scores, "tobytes") else bytes(scores)
    if len(data) != N_TILES:
        raise ValueError(f"scores must be {N_TILES} bytes, got {len(data)}")
    x1, y1, x2, y2 = bbox if bbox is not None else (0, 0, 0, 0)
    head = struct.pack(UDP_HEADER_FMT, UDP_MAGIC, frame_no & 0xFFFFFFFF, float(ts),
                       STATES.index(state), int(bool(gate)), float(fps),
                       MODES.index(mode), x1, y1, x2, y2)
    return head + data


def unpack_viewer_packet(packet):
    """Return a dict for a BW01 frame packet (scores as 3600 bytes; the viewer
    does np.frombuffer(..., np.uint8).reshape(45, 80)), or the verdict dict for
    a BWV1 packet with "kind" set to "verdict". Raises ValueError otherwise."""
    if packet[:4] == UDP_VERDICT_MAGIC:
        return {"kind": "verdict", **json.loads(packet[4:].decode("utf-8"))}
    if len(packet) != UDP_PACKET_SIZE or packet[:4] != UDP_MAGIC:
        raise ValueError(f"not a BW01 packet ({len(packet)} bytes)")
    magic, frame_no, ts, state, gate, fps, mode, x1, y1, x2, y2 = \
        struct.unpack_from(UDP_HEADER_FMT, packet)
    return {"kind": "frame", "frame_no": frame_no, "ts": ts, "state": STATES[state],
            "gate": bool(gate), "fps": fps, "mode": MODES[mode],
            "bbox": None if (x2, y2) == (0, 0) else (x1, y1, x2, y2),
            "scores": packet[UDP_HEADER_SIZE:]}


def pack_verdict_packet(verdict):
    return UDP_VERDICT_MAGIC + to_json(verdict)


# --- Frame words (HLS m_axi input and test vectors) ------------------------------
def pack_rgb_words(rgb):
    """uint8 [H, W, 3] RGB -> uint32 [H*W], each word R | G<<8 | B<<16 (bits 31:24 = 0)."""
    import numpy as np
    rgb = np.asarray(rgb, dtype=np.uint8)
    w = rgb[..., 0].astype(np.uint32)
    w |= rgb[..., 1].astype(np.uint32) << 8
    w |= rgb[..., 2].astype(np.uint32) << 16
    return w.reshape(-1)


def unpack_rgb_words(words, h=IMG_H, w=IMG_W):
    import numpy as np
    words = np.asarray(words, dtype=np.uint32).reshape(h, w)
    out = np.empty((h, w, 3), np.uint8)
    for i in range(3):
        out[..., i] = (words >> (8 * i)) & 0xFF
    return out


# --- Logs and labels ---------------------------------------------------------------
EVAL_LOG_COLUMNS = ("ts", "frame_no", "state", "gate", "region_tiles")
LABEL_COLUMNS = ("clip", "label", "smoke_start_s", "smoke_end_s", "notes")
LABELS = ("smoke", "person", "cloth", "lights", "bump", "exposure", "steam", "empty")
