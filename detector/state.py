"""Alert state machine: CLEAR, SUSPECT, CONFIRMED, REJECTED (ARM side, P3).

Pure logic. Every method takes the time (seconds) and returns a list of actions for the caller to execute;
nothing here touches the network, LEDs or a clock.

  CLEAR     -> SUSPECT    candidate region and >= UPLOAD_COOLDOWN_S since the last upload: emits "upload"
  SUSPECT   -> CONFIRMED  verdict for the open event with state "CONFIRMED" (the cloud applies CONF_THRESHOLD, F3)
  SUSPECT   -> REJECTED   verdict with state "REJECTED": emits "ignore" (region tiles, IGNORE_S) and
                          "rebaseline" (the caller calls engine.reset(), F7), then -> CLEAR
  SUSPECT                 no verdict for VERDICT_TIMEOUT_S: stays SUSPECT, emits "verdict_timeout" once
  CONFIRMED -> CLEAR      the region has been gone for CLEAR_AFTER_S

Actions are dicts with a "type":
  {"type": "upload", "event": <event dict, docs/contracts.md section 2>}
  {"type": "ignore", "mask": bool [45, 80], "until": t}
  {"type": "rebaseline"}
  {"type": "verdict_timeout", "ts": <event ts>}
  {"type": "state", "state": <new state>}          on every transition, for LEDs, logs and the viewer
"""
from detector.config import ArmParams
from tools import contracts


class StateMachine:
    def __init__(self, camera, cfg=None):
        self.camera = contracts.check_camera(camera)
        self.cfg = cfg if cfg is not None else ArmParams()
        self.state = "CLEAR"
        self.last_upload_t = None
        self.event = None          # the open SUSPECT event
        self.event_t = None
        self.event_mask = None
        self.timeout_sent = False
        self.gone_since = None     # CONFIRMED: when the region disappeared

    def _go(self, state):
        self.state = state
        return {"type": "state", "state": state}

    def step(self, t, candidate, region_present):
        """Advance on one processed frame. candidate: a Region from RegionTracker.candidate(), or None."""
        c, out = self.cfg, []
        if self.state == "CLEAR":
            if candidate is not None and (self.last_upload_t is None or t - self.last_upload_t >= c.UPLOAD_COOLDOWN_S):
                ts = int(t)
                self.event = contracts.check_fields({
                    "camera": self.camera, "state": "SUSPECT",
                    "score": round(candidate.score_mean / 255, 2), "tiles": candidate.tiles,
                    "bbox": candidate.bbox, "s3_key": contracts.s3_key(self.camera, ts), "ts": ts,
                }, contracts.EVENT_FIELDS)
                self.event_t, self.event_mask = t, candidate.mask.copy()
                self.last_upload_t, self.timeout_sent = t, False
                out += [self._go("SUSPECT"), {"type": "upload", "event": self.event}]
        elif self.state == "SUSPECT":
            if not self.timeout_sent and t - self.event_t >= c.VERDICT_TIMEOUT_S:
                self.timeout_sent = True
                out.append({"type": "verdict_timeout", "ts": self.event["ts"]})
        elif self.state == "CONFIRMED":
            if region_present:
                self.gone_since = None
            elif self.gone_since is None:
                self.gone_since = t
            elif t - self.gone_since >= c.CLEAR_AFTER_S:
                self.event = None
                out.append(self._go("CLEAR"))
        return out

    def on_verdict(self, verdict, t):
        """Apply a verdict (docs/contracts.md section 2). Ignored unless it answers the open SUSPECT event."""
        if self.state != "SUSPECT" or verdict.get("ts") != self.event["ts"]:
            return []
        if verdict.get("state") == "CONFIRMED":
            self.gone_since = None
            return [self._go("CONFIRMED")]
        if verdict.get("state") == "REJECTED":
            out = [self._go("REJECTED"),
                   {"type": "ignore", "mask": self.event_mask, "until": t + self.cfg.IGNORE_S},
                   {"type": "rebaseline"}]
            self.event = None
            out.append(self._go("CLEAR"))
            return out
        return []
