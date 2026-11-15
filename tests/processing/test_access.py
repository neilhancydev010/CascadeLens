"""Road access screen (access.py) on synthetic networks whose answers are worked out by hand. Invented roads, not OSM data.

    A --1000-- B --1000-- C --1000-- F       hub = A
    |                     |                 ways: "ab" A-B, "bc" B-C, "cf" C-F, "ad" A-D, "dc" D-E-C
  3000                  3000
    |                     |                 closing "bc" sends A->C the long way:
    D -------2000-------- E                 A-D 3000 + D-E 2000 + E-C 3000 = 8000 m, a 6000 m detour
"""
import math

import pytest

from cascade_lens import access

A, B, C, D, E, F = (0, 0), (1000, 0), (2000, 0), (0, -3000), (2000, -3000), (3000, 0)


def net():
    g = access.Graph()
    g.add_way("ab", [A, B])
    g.add_way("bc", [B, C])
    g.add_way("ad", [A, D])
    g.add_way("dc", [D, E, C])
    g.add_way("cf", [C, F])
    return g


def anchors(g):
    return {"B": g.node(B), "C": g.node(C), "F": g.node(F)}


def test_way_lengths_are_summed_from_vertices():
    g = net()
    assert g.ways["dc"]["lengthM"] == pytest.approx(5000)
    assert len(g.xy) == 6


def test_shortest_paths_match_hand_calculation():
    g = net()
    r = access.reach(g, g.node(A), anchors(g), set())
    assert r["B"]["km"] == 1.0 and r["C"]["km"] == 2.0 and r["F"]["km"] == 3.0
    assert r["C"]["ways"] == 2 and r["C"]["unknownWays"] == 2


def test_a_closure_gives_the_detour_and_its_length():
    g = net()
    base = access.reach(g, g.node(A), anchors(g), set())
    closed = access.reach(g, g.node(A), anchors(g), {"bc"})
    assert closed["C"]["km"] == 8.0
    cmp = access.compare(base, closed)
    assert cmp["C"] == {"change": "longer", "baseKm": 2.0, "km": 8.0, "detourKm": 6.0}
    assert cmp["B"] == {"change": "unchanged", "km": 1.0}


def test_cutting_every_route_reports_no_path_never_isolation():
    g = net()
    base = access.reach(g, g.node(A), anchors(g), set())
    cut = access.reach(g, g.node(A), anchors(g), {"bc", "dc"})
    assert cut["C"] == {"path": False, "reason": "No road path in this network"}
    assert access.compare(base, cut)["F"] == {"change": "no path", "baseKm": 3.0}
    text = repr(cut).lower()
    assert "isolat" not in text and "cut off" not in text


def test_crossing_without_a_shared_vertex_is_not_a_junction():
    """A bridge over a road: the lines cross, but OSM joins roads only at shared nodes, so there is no turn here."""
    g = access.Graph()
    g.add_way("ew", [(-1000, 0), (1000, 0)], bridge="yes", layer="1")
    g.add_way("ns", [(0, -1000), (0, 1000)])
    r = access.reach(g, g.node((-1000, 0)), {"north": g.node((0, 1000))}, set())
    assert r["north"]["path"] is False


def test_states_default_to_unknown_and_the_strongest_report_wins():
    g = net()
    assert {w["state"] for w in g.ways.values()} == {"unknown"}
    g.set_state("bc", "open", "volunteer survey")
    g.set_state("bc", "uncertain", "damage report")
    assert g.ways["bc"]["state"] == "uncertain" and g.ways["bc"]["sources"] == ["damage report"]
    g.set_state("bc", "open", "another survey")
    assert g.ways["bc"]["state"] == "uncertain"
    g.set_state("bc", "closed", "OSM destroyed")
    assert g.ways["bc"]["state"] == "closed"
    with pytest.raises(ValueError):
        g.set_state("bc", "fine", "x")


def test_paths_through_unverified_road_are_counted():
    g = net()
    g.set_state("ab", "open", "survey")
    g.set_state("bc", "uncertain", "damage report")
    r = access.reach(g, g.node(A), anchors(g), set())
    assert r["C"]["uncertainWays"] == 1 and r["C"]["unknownWays"] == 0


def test_a_place_with_no_road_nearby_is_said_so():
    g = net()
    far = g.nearest((50000, 50000), max_m=500)
    assert far is None
    r = access.reach(g, g.node(A), {"far": far}, set())
    assert r["far"] == {"path": False, "reason": "No mapped road within reach of this place"}


def test_equal_length_routes_are_chosen_the_same_way_every_time():
    g = access.Graph()
    g.add_way("n", [(0, 0), (0, 1000), (1000, 1000)])
    g.add_way("s", [(0, 0), (1000, 0), (1000, 1000)])
    runs = {tuple(access.path_ways(access.shortest(g, g.node((0, 0)))[1], g.node((1000, 1000)))) for _ in range(5)}
    assert len(runs) == 1
    assert math.isclose(access.shortest(g, g.node((0, 0)))[0][g.node((1000, 1000))], 2000)


def test_blocking_names_the_closed_ways_on_the_original_route():
    g = net()
    assert access.blocking(g, g.node(A), g.node(C), {"bc", "zz"}) == ["bc"]
    assert access.blocking(g, g.node(A), g.node(B), {"bc"}) == []
    assert access.blocking(g, g.node(A), None, {"bc"}) == []



def test_nearest_destination_and_its_route_follow_the_closures():
    """From B: clinic F is B-C-F = 2000 m, post D is B-A-D = 4000 m. With "bc" closed, F is 10 000 m away, so D wins."""
    g = net()
    facilities = {"clinic-F": g.node(F), "post-D": g.node(D)}
    dist, prev, origin = access.nearest_source(g, facilities)
    assert origin[g.node(B)] == "clinic-F" and math.isclose(dist[g.node(B)], 2000)
    assert access.path_ways(prev, g.node(B)) == ["cf", "bc"]  # from the facility to the place
    dist, prev, origin = access.nearest_source(g, facilities, {"bc"})
    assert origin[g.node(B)] == "post-D" and math.isclose(dist[g.node(B)], 4000)


def test_pieces_split_where_closures_cut_the_network():
    g = net()
    assert len(set(access.pieces(g))) == 1
    lab = access.pieces(g, {"bc", "dc"})
    west = {lab[g.node(p)] for p in (A, B, D)}
    east = {lab[g.node(p)] for p in (C, F)}
    assert len(west) == 1 and len(east) == 1 and west != east
    assert lab[g.node(E)] not in west | east  # E lies only on the closed way "dc", so it is a piece of its own
    assert access.pieces(g, {"bc", "dc"}) == lab  # stable labels
