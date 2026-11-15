"""Testing a "cliff ricochet": where along a flow path could a flow have hit a valley wall hard, and do the data show the marks?

HYPOTHESIS. Source: a mentor, oral communication, no location or figures given. This module finds candidate places from the
terrain and tests each for the marks a hard outer-bank impact leaves. It never confirms that an impact happened.

Everything here works in a flat metric frame (x east, y north, metres), so it can run on synthetic terrain in the tests.
The terrain is passed as two functions, height(x, y) in metres and slope(x, y) in degrees, and the mapped flow extent as a
shapely geometry in the same frame.

Steps, with the thresholds fixed before looking at the results (they are not tuned to make any site pass):
1. Densify the path to a point every 50 m. A bend is where the flow direction turns by at least 45 degrees between the
   750 m before a point and the 750 m after it (so within 1.5 km). Only the sharpest point of each bend is kept.
2. The outer bank is the side the flow would hit going straight on: opposite the way it turns. A bend is a candidate when the
   terrain slope on the outer bank reaches at least 35 degrees within 300 m of the channel.
3. Superelevation (Hungr et al. 1984): a flow round a bend stands higher on the outer bank by dh = k v^2 b / (g R_c), so
   v = sqrt(g R_c dh / (k b)), with k from 1 to 5 (debris flows often need k > 1).
4. Run-up: a flow that climbs h_up up a facing wall had at least v = sqrt(2 g h_up) when it arrived (all speed into height).
5. A control: on straight stretches (turning less than 15 degrees) the same edge heights are compared left against right.
   Any steady difference there (the mapped extent or the path sitting off-centre in the valley, or one bank simply steeper)
   would show up at every bend too, so it is taken off each bend's outer-minus-inner difference before judging.
6. Where the channel width b or the bend radius R_c is under two terrain cells, or the bend is not on a mapped river,
   or the mapped extent does not reach the bend, the answer is "cannot judge here", not a number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from shapely.geometry import LineString, Point

G = 9.81
STEP_M = 50.0
WINDOW_M = 750.0          # each side of a point: the turn is measured over 1.5 km
MIN_TURN_DEG = 45.0
WALL_SLOPE_DEG = 35.0
WALL_REACH_M = 300.0
SECTION_HALF_M = 1500.0
SECTIONS_EACH_SIDE_M = 300.0  # cross-sections from 300 m before the apex to 300 m after it, every STEP_M
K_RANGE = (1.0, 5.0)
DEM_CELL_M = 30.0
MIN_RESOLVED_M = 2 * DEM_CELL_M  # anything narrower than two terrain cells cannot be measured
DEM_NOISE_M = 5.0             # Copernicus GLO-30 height error is a few metres: a smaller difference says nothing

SUPPORTS = "supports a hard outer-bank impact"
NOT_SHOWN = "does not show it"
CANNOT = "cannot judge"


def densify(xy: np.ndarray, step: float = STEP_M) -> tuple[np.ndarray, np.ndarray]:
    """Points every `step` metres along a polyline, and the distance of each from the start."""
    seg = np.hypot(*np.diff(xy, axis=0).T)
    dist = np.concatenate([[0.0], np.cumsum(seg)])
    d = np.arange(0.0, dist[-1] + 1e-9, step)
    return np.column_stack([np.interp(d, dist, xy[:, 0]), np.interp(d, dist, xy[:, 1])]), d


def turn_angles(pts: np.ndarray, window: float = WINDOW_M, step: float = STEP_M) -> np.ndarray:
    """Signed turn in degrees at each point, from the direction over the `window` before it to the direction over the `window`
    after it. Positive is a left turn (anticlockwise). NaN where the window runs off either end."""
    w = int(round(window / step))
    out = np.full(len(pts), np.nan)
    for i in range(w, len(pts) - w):
        a = pts[i] - pts[i - w]
        b = pts[i + w] - pts[i]
        out[i] = math.degrees(math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1]))
    return out


def find_bends(turn: np.ndarray, min_turn: float = MIN_TURN_DEG, separation: int = int(2 * WINDOW_M / STEP_M)) -> list[int]:
    """Indices of the sharpest point of each bend of at least `min_turn` degrees, at least 1.5 km apart."""
    mag = np.nan_to_num(np.abs(turn), nan=0.0)
    picked: list[int] = []
    for i in np.argsort(-mag):
        if mag[i] < min_turn:
            break
        if all(abs(int(i) - j) >= separation for j in picked):
            picked.append(int(i))
    return sorted(picked)


def circumradius(a, b, c) -> float:
    """Radius of the circle through three points, in metres. Infinite for points in a line."""
    ab, bc, ca = (math.dist(a, b), math.dist(b, c), math.dist(c, a))
    cross = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    return math.inf if cross < 1e-9 else ab * bc * ca / (2 * cross)


def superelevation_speed(dh: float, rc: float, b: float, k: float) -> float:
    """Hungr et al. (1984): v = sqrt(g R_c dh / (k b)), in m/s."""
    return math.sqrt(G * rc * dh / (k * b))


def runup_speed(h_up: float) -> float:
    """Lower bound on the speed that climbs h_up metres: v = sqrt(2 g h_up), in m/s."""
    return math.sqrt(2 * G * h_up)


def _unit(v):
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n)


def _edge(extent, start, direction, reach=SECTION_HALF_M, step=10.0):
    """Walk from `start` along `direction` while inside the extent. Returns the last inside point, or None if `start` is outside."""
    if extent is None or not extent.covers(Point(start)):
        return None
    last = start
    for s in np.arange(step, reach + step, step):
        p = (start[0] + direction[0] * s, start[1] + direction[1] * s)
        if not extent.covers(Point(p)):
            return last
        last = p
    return last


@dataclass
class Site:
    km: float
    x: float
    y: float
    turn_deg: float
    outer_side: str            # "left" or "right" of the flow
    on_mapped_river: bool
    rc_m: float | None = None
    b_m: float | None = None
    wall_slope_deg: float = 0.0
    wall_height_m: float = 0.0
    inner_slope_deg: float = 0.0
    river_m: float = 0.0
    sections: int = 0
    dh_raw_m: float | None = None   # outer minus inner, before the straight-stretch control
    bias_m: float = 0.0             # the control's left-minus-right difference, signed for this bend's outer side
    dh_m: float | None = None       # after the control: what is judged
    h_up_m: float | None = None
    h_up_inner_m: float | None = None
    v_super: tuple[float, float] | None = None   # (k = 5, k = 1): slowest and fastest
    v_runup: float | None = None
    radar: dict = field(default_factory=dict)
    outcome: str = CANNOT
    reasons: list[str] = field(default_factory=list)


STRAIGHT_DEG = 15.0


def edge_heights(pts, j, height, extent, side):
    """The height of the extent's edge on one side (+1 left of the flow, -1 right) at point j, and the bed there. None if outside."""
    d = _unit(pts[min(j + 1, len(pts) - 1)] - pts[max(j - 1, 0)])
    n = (-d[1] * side, d[0] * side)
    c = tuple(pts[j])
    e = _edge(extent, c, n)
    if e is None:
        return None
    return height(*e)


def side_bias(pts, turn, height, extent, on_river=None) -> tuple[float, int]:
    """Median left-minus-right height of the extent's edge on straight stretches: the control for any steady one-sided offset."""
    diffs = []
    for j in range(len(pts)):
        if not np.isfinite(turn[j]) or abs(turn[j]) >= STRAIGHT_DEG or j % 4:
            continue
        if on_river is not None and not on_river(*pts[j]):
            continue
        hl, hr = edge_heights(pts, j, height, extent, 1), edge_heights(pts, j, height, extent, -1)
        if hl is not None and hr is not None:
            diffs.append(hl - hr)
    side_bias.spread = (float(np.percentile(diffs, 25)), float(np.percentile(diffs, 75))) if diffs else (0.0, 0.0)
    return (float(np.median(diffs)), len(diffs)) if diffs else (0.0, 0)


def assess(xy: np.ndarray, height: Callable[[float, float], float], slope: Callable[[float, float], float], extent=None,
           on_river: Callable[[float, float], bool] | None = None, km_of: Callable[[float], float] | None = None) -> list[Site]:
    """Find candidate bends along a path (metres) and test each. `km_of` turns metres along the densified path into the
    path's own km; `on_river` says whether a point is on a mapped river rather than a straight join."""
    pts, dist = densify(np.asarray(xy, float))
    turn = turn_angles(pts)
    w = int(round(WINDOW_M / STEP_M))
    bias_lr, n_control = side_bias(pts, turn, height, extent, on_river) if extent is not None else (0.0, 0)
    lo, hi = getattr(side_bias, "spread", (0.0, 0.0))
    assess.control = {"leftMinusRightM": round(bias_lr, 1), "sections": n_control, "p25M": round(lo, 1), "p75M": round(hi, 1)}
    sites = []
    for i in find_bends(turn):
        p = tuple(pts[i])
        fwd = _unit(pts[i] - pts[i - w])                  # the way the flow arrives
        left = (-fwd[1], fwd[0])
        outer = (-left[0], -left[1]) if turn[i] > 0 else left  # a left turn throws the flow to the right, and the reverse
        inner = (-outer[0], -outer[1])

        def bank(side, fan):
            # A fan of directions, out to WALL_REACH_M. The outer bank: from straight on to square to that side, the ground a flow
            # going straight on would meet. The inner bank: from square to the other side round to back up the incoming channel.
            best_s, top = 0.0, -math.inf
            for ang in np.radians(fan):
                d = (fwd[0] * math.cos(ang) + side[0] * math.sin(ang), fwd[1] * math.cos(ang) + side[1] * math.sin(ang))
                for s in np.arange(DEM_CELL_M, WALL_REACH_M + 1, DEM_CELL_M):
                    q = (p[0] + d[0] * s, p[1] + d[1] * s)
                    best_s = max(best_s, slope(*q))
                    top = max(top, height(*q))
            return best_s, top

        river = min(height(p[0] + a, p[1] + b) for a in (-60, -30, 0, 30, 60) for b in (-60, -30, 0, 30, 60))
        s_out, top_out = bank(outer, np.arange(0, 91, 15))
        s_in, _ = bank(inner, np.arange(90, 181, 15))
        if s_out < WALL_SLOPE_DEG:
            continue
        site = Site(km=round(km_of(dist[i]) if km_of else dist[i] / 1000, 2), x=p[0], y=p[1], turn_deg=round(float(turn[i]), 1),
                    outer_side="right" if turn[i] > 0 else "left", on_mapped_river=bool(on_river(*p)) if on_river else True,
                    wall_slope_deg=round(s_out, 1), wall_height_m=round(top_out - river, 1), inner_slope_deg=round(s_in, 1), river_m=round(river, 1))
        rc = circumradius(pts[i - w], pts[i], pts[i + w])
        site.rc_m = None if not math.isfinite(rc) else round(rc, 1)
        # Channel width where the mapped extent crosses the bend, square to the flow
        normal = _unit((fwd[0] + _unit(pts[i + w] - pts[i])[0], fwd[1] + _unit(pts[i + w] - pts[i])[1]))
        normal = (-normal[1], normal[0])
        if extent is not None and extent.covers(Point(p)):
            line = LineString([(p[0] - normal[0] * SECTION_HALF_M, p[1] - normal[1] * SECTION_HALF_M), (p[0] + normal[0] * SECTION_HALF_M, p[1] + normal[1] * SECTION_HALF_M)])
            cut = line.intersection(extent)
            parts = [g for g in getattr(cut, "geoms", [cut]) if g.length > 0]
            here = [g for g in parts if g.distance(Point(p)) < 1.0]
            site.b_m = round(here[0].length, 1) if here else None
        # Cross-sections through the bend: the height of the extent's edge on each bank
        dh, up, up_in = [], [], []
        j0, j1 = max(w, i - int(SECTIONS_EACH_SIDE_M / STEP_M)), min(len(pts) - w - 1, i + int(SECTIONS_EACH_SIDE_M / STEP_M))
        for j in range(j0, j1 + 1):
            d = _unit(pts[min(j + 1, len(pts) - 1)] - pts[max(j - 1, 0)])
            n_left = (-d[1], d[0])
            o = n_left if site.outer_side == "left" else (-n_left[0], -n_left[1])
            c = tuple(pts[j])
            e_out, e_in = _edge(extent, c, o), _edge(extent, c, (-o[0], -o[1]))
            if e_out is None or e_in is None:
                continue
            bed = min(height(c[0] + o[0] * s, c[1] + o[1] * s) for s in np.arange(-90, 91, 30))
            h_o, h_i = height(*e_out), height(*e_in)
            dh.append(h_o - h_i)
            up.append(h_o - bed)
            up_in.append(h_i - bed)
        site.sections = len(dh)
        if dh:
            site.dh_raw_m = round(float(np.median(dh)), 1)
            site.bias_m = round(bias_lr if site.outer_side == "left" else -bias_lr, 1)
            site.dh_m = round(site.dh_raw_m - site.bias_m, 1)
            site.h_up_m = round(float(np.median(up)), 1)
            site.h_up_inner_m = round(float(np.median(up_in)), 1)
        decide(site)
        sites.append(site)
    return sites


def decide(site: Site) -> None:
    """The outcome, from fixed rules. Speeds are only given where the inputs can be resolved."""
    r = site.reasons
    if not site.on_mapped_river:
        r.append("the path here is a straight line joining mapped features, not a mapped channel")
    if site.b_m is None:
        r.append("the mapped extent does not cross the channel at the bend")
    elif site.b_m < MIN_RESOLVED_M:
        r.append(f"channel width {site.b_m:.0f} m is under two terrain cells")
    if site.rc_m is None or site.rc_m < MIN_RESOLVED_M:
        r.append("bend radius is not resolved by the terrain")
    if site.sections < 3:
        r.append(f"only {site.sections} cross-sections reach both edges of the extent")
    if r:
        site.outcome = CANNOT
        return
    if site.h_up_m is not None and site.h_up_m > 0:
        site.v_runup = round(runup_speed(site.h_up_m), 1)
    if site.dh_m is not None and site.dh_m > 0:
        site.v_super = (round(superelevation_speed(site.dh_m, site.rc_m, site.b_m, K_RANGE[1]), 1),
                        round(superelevation_speed(site.dh_m, site.rc_m, site.b_m, K_RANGE[0]), 1))
    if site.dh_m is not None and site.dh_m >= DEM_NOISE_M:
        site.outcome = SUPPORTS
        r.append(f"after the straight-stretch control, the extent reaches {site.dh_m:.0f} m higher on the outer bank than the inner, more than the terrain's error")
    else:
        site.outcome = NOT_SHOWN
        r.append(f"after the straight-stretch control, the extent's edge is not higher on the outer bank by more than the terrain's error ({DEM_NOISE_M:.0f} m): {site.dh_m:+.0f} m")
