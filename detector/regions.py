"""Turn per-frame tile scores into one tracked smoke region (ARM side, P3).

Floats are fine here: this never goes to HW. Time is always passed in (seconds); nothing here reads a clock.

Per processed frame (gated frames are skipped and change nothing):
  1. s = (1 - SMOOTH)*s + SMOOTH*scores                    temporal smoothing (default 0.6 / 0.4)
  2. mask = s >= T_FLAG, minus any ignore masks still active  (REJECTED cooldown)
  3. 8-connected components; keep the largest with >= MIN_TILES tiles
  4. Track it: the same region while its bbox overlaps the previous one, else a new region starts
  5. candidate() when it has lasted >= PERSIST_S and, over the last PERSIST_S seconds, it grew by GROW_FRAC
     of its area, or its top edge rose >= RISE_TILES, or its centroid rose. Rising or spreading is the cue.
"""
import cv2
import numpy as np

from detector.config import TILE_FULL, TILES_X, TILES_Y, ArmParams


class Region:
    """One tracked component. bbox_tiles = (x1, y1, x2, y2) in tiles, x2/y2 exclusive."""

    def __init__(self, t):
        self.first_t = t
        self.history = []          # (t, area, top_row, centroid_row)
        self.mask = None           # bool [45, 80]
        self.bbox_tiles = None
        self.score_mean = 0.0      # mean raw score (0..255) over the region's tiles, this frame

    @property
    def tiles(self):
        return int(self.mask.sum())

    @property
    def bbox(self):
        """[x1, y1, x2, y2] in full-res pixels (tiles * 16), x2/y2 exclusive."""
        return [int(v) * TILE_FULL for v in self.bbox_tiles]


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class RegionTracker:
    def __init__(self, t_flag=40, cfg=None):
        self.t_flag = t_flag
        self.cfg = cfg if cfg is not None else ArmParams()
        self.s = np.zeros((TILES_Y, TILES_X), np.float32)
        self.ignores = []          # (bool mask [45, 80], until_t)
        self.region = None         # the tracked Region, or None when nothing qualifies this frame

    def ignore(self, mask, until):
        """Ignore these tiles until time `until` (REJECTED cooldown)."""
        self.ignores.append((np.asarray(mask, bool).copy(), until))

    def update(self, scores, gate, t):
        """Feed one processed frame. Returns the tracked Region or None."""
        if gate:
            return self.region
        a = self.cfg.SMOOTH
        self.s = (1 - a) * self.s + a * scores.astype(np.float32)
        mask = self.s >= self.t_flag
        self.ignores = [(m, u) for m, u in self.ignores if t < u]
        for m, _ in self.ignores:
            mask &= ~m

        n, labels, stats, cents = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
        if n <= 1:
            self.region = None
            return None
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < self.cfg.MIN_TILES:
            self.region = None
            return None
        x, y, w, h = (int(stats[i, k]) for k in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP,
                                                 cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
        bbox = (x, y, x + w, y + h)
        if self.region is None or not _overlap(self.region.bbox_tiles, bbox):
            self.region = Region(t)
        r = self.region
        r.mask = labels == i
        r.bbox_tiles = bbox
        r.score_mean = float(scores[r.mask].mean())
        r.history.append((t, area, y, float(cents[i][1])))
        return r

    def candidate(self):
        """The tracked region if it has persisted and is rising or spreading, else None."""
        r, c = self.region, self.cfg
        if r is None:
            return None
        t_now = r.history[-1][0]
        if t_now - r.first_t < c.PERSIST_S:
            return None
        start = next(h for h in r.history if h[0] >= t_now - c.PERSIST_S)
        _, area, top, cy = r.history[-1]
        _, area0, top0, cy0 = start
        grew = area >= area0 * (1 + c.GROW_FRAC)
        rose = top0 - top >= c.RISE_TILES or cy0 - cy > c.CENTROID_RISE
        return r if (grew or rose) else None
