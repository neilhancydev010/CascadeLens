"""Cliff-impact site finder (impact.py) on synthetic terrain. Invented values. HYPOTHESIS testing only: no site is confirmed."""
import math

import numpy as np
from shapely.geometry import LineString

from cascade_lens import impact

WALL = 60.0  # degrees


def straight_valley():
    xy = np.array([[0.0, y] for y in np.arange(0, 6001, 100)])  # flowing north along x = 0
    height = lambda x, y: 1000.0 + 0.2 * abs(x) - 0.01 * y  # noqa: E731  gentle V-shaped valley
    slope = lambda x, y: math.degrees(math.atan(0.2))  # noqa: E731  about 11 degrees everywhere
    return xy, height, slope


def test_a_straight_valley_gives_no_candidate():
    xy, height, slope = straight_valley()
    assert impact.assess(xy, height, slope) == []


def bend_against_a_wall():
    """North for 3 km, then a 90 degree turn to the west (left). Going straight on, the flow meets a steep wall to the north-east."""
    north = [[0.0, y] for y in np.arange(0, 3001, 100)]
    west = [[-x, 3000.0] for x in np.arange(100, 3001, 100)]
    xy = np.array(north + west)

    def wall(x, y):
        return y > 3060 or x > 60  # beyond the channel on the outer side of the bend

    height = lambda x, y: 1000.0 + (200.0 if wall(x, y) else 0.0)  # noqa: E731
    slope = lambda x, y: WALL if wall(x, y) else 2.0  # noqa: E731
    return xy, height, slope


def test_a_right_angle_bend_against_a_steep_wall_gives_one_candidate_on_the_correct_bank():
    xy, height, slope = bend_against_a_wall()
    sites = impact.assess(xy, height, slope)
    assert len(sites) == 1
    s = sites[0]
    assert s.turn_deg > 45  # a left turn
    assert s.outer_side == "right"  # so the flow is thrown to the right, against the wall
    assert s.wall_slope_deg >= impact.WALL_SLOPE_DEG and s.inner_slope_deg < impact.WALL_SLOPE_DEG
    assert abs(s.x) < 200 and abs(s.y - 3000) < 200
    # No mapped extent: the data cannot judge, and no speed is given
    assert s.outcome == impact.CANNOT and s.v_super is None


def test_the_same_bend_turning_right_puts_the_outer_bank_on_the_left():
    xy, _, _ = bend_against_a_wall()
    mirror = xy * np.array([-1.0, 1.0])
    height = lambda x, y: 1000.0 + (200.0 if (y > 3060 or x < -60) else 0.0)  # noqa: E731
    slope = lambda x, y: WALL if (y > 3060 or x < -60) else 2.0  # noqa: E731
    sites = impact.assess(mirror, height, slope)
    assert len(sites) == 1 and sites[0].turn_deg < -45 and sites[0].outer_side == "left"


def test_superelevation_and_runup_formulas_match_hand_values():
    # v = sqrt(g Rc dh / (k b)): g 9.81, Rc 500 m, dh 10 m, b 100 m, k 1 -> sqrt(490.5) = 22.15 m/s
    assert math.isclose(impact.superelevation_speed(10, 500, 100, 1), math.sqrt(490.5))
    assert math.isclose(impact.superelevation_speed(10, 500, 100, 1), 22.147, rel_tol=1e-4)
    # k = 5 divides the square by five
    assert math.isclose(impact.superelevation_speed(10, 500, 100, 5), math.sqrt(98.1))
    # v >= sqrt(2 g h_up): h_up 5 m -> sqrt(98.1) = 9.90 m/s
    assert math.isclose(impact.runup_speed(5), 9.9045, rel_tol=1e-4)


def test_circumradius_of_a_quarter_circle():
    r = 700.0
    pts = [(r * math.cos(a), r * math.sin(a)) for a in (0, math.pi / 4, math.pi / 2)]
    assert math.isclose(impact.circumradius(*pts), r, rel_tol=1e-9)
    assert impact.circumradius((0, 0), (1, 1), (2, 2)) == math.inf


def test_superelevation_on_a_banked_bend_is_measured_and_judged():
    """The flow's mapped extent rises higher on the outer bank: dh is measured and the site supports an impact."""
    xy, height0, slope = bend_against_a_wall()
    # Ground rises 0.5 m per metre away from the channel corner on both sides, so an extent wider on the outer side reaches higher there
    height = lambda x, y: 1000.0 + 0.5 * min(abs(x), abs(y - 3000)) + (200.0 if (y > 3200 or x > 200) else 0.0)  # noqa: E731
    channel = LineString(xy.tolist())
    # 40 m each side everywhere, and 120 m on the outer (right) side only within 700 m of the bend, so the straight-stretch control sees no offset
    near = LineString([p for p in xy.tolist() if math.dist(p, (0, 3000)) <= 700])
    extent = channel.buffer(40).union(near.buffer(-120, single_sided=True))
    s = impact.assess(xy, height, slope, extent)[0]
    assert s.sections >= 3 and s.b_m is not None and s.b_m > impact.MIN_RESOLVED_M
    assert s.dh_raw_m > impact.DEM_NOISE_M
    assert s.outcome == impact.SUPPORTS
    lo, hi = s.v_super
    assert lo < hi and math.isclose(hi, impact.superelevation_speed(s.dh_m, s.rc_m, s.b_m, 1), rel_tol=0.02)
