"""Road access screen (audit P0.4): which places still have a road path to a hub, and how much longer it is, when given
roads are closed.

The graph is built from OpenStreetMap ways. Two ways connect only where they share a vertex, which is how OSM joins roads at
junctions; a crossing without a shared vertex (a bridge over a road, or two layers) is not a junction. Edge lengths are
metres in the projected CRS. Shortest paths are plain Dijkstra, so results are deterministic and can be checked by hand.

Every way carries one of four states. Unknown is the default, and nothing is ever assumed open or closed without a source:
  open       reported intact by a named source
  closed     mapped as destroyed, or reported washed out
  uncertain  reported damaged, passability not known
  unknown    no report

Results say "no road path in this network", never "isolated": footpaths, unmapped tracks, river crossings and helicopters
are outside this network, and OSM is incomplete. A screen to direct checks, not a statement about who can be reached.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

STATES = ("open", "closed", "uncertain", "unknown")
DRIVABLE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "track", "service",
            "trunk_link", "primary_link", "secondary_link", "tertiary_link", "living_street", "road"}


@dataclass
class Graph:
    """Vertices keyed by exact coordinates; adjacency lists of (neighbour, length_m, way_id)."""
    nodes: dict[tuple[float, float], int] = field(default_factory=dict)
    xy: list[tuple[float, float]] = field(default_factory=list)
    adj: list[list[tuple[int, float, str]]] = field(default_factory=list)
    ways: dict[str, dict] = field(default_factory=dict)

    def node(self, p: tuple[float, float]) -> int:
        k = (round(p[0], 3), round(p[1], 3))  # millimetre key in metres: shared OSM nodes project to the same point
        if k not in self.nodes:
            self.nodes[k] = len(self.xy)
            self.xy.append(k)
            self.adj.append([])
        return self.nodes[k]

    def add_way(self, way_id: str, coords: list[tuple[float, float]], **props) -> None:
        """coords in projected metres. One edge per consecutive vertex pair, all labelled with the way's ID."""
        self.ways[way_id] = {"state": "unknown", "lengthM": 0.0, **props}
        ids = [self.node(c) for c in coords]
        for a, b in zip(ids, ids[1:]):
            if a == b:
                continue
            d = math.dist(self.xy[a], self.xy[b])
            self.adj[a].append((b, d, way_id))
            self.adj[b].append((a, d, way_id))
            self.ways[way_id]["lengthM"] += d

    def set_state(self, way_id: str, state: str, source: str) -> None:
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}")
        w = self.ways[way_id]
        # A stronger report wins: closed over uncertain over open over unknown; ties keep every source
        rank = {"unknown": 0, "open": 1, "uncertain": 2, "closed": 3}
        if rank[state] > rank[w["state"]]:
            w["state"], w["sources"] = state, [source]
        elif rank[state] == rank[w["state"]] and state != "unknown":
            w.setdefault("sources", []).append(source)

    def nearest(self, p: tuple[float, float], max_m: float) -> int | None:
        best, bi = max_m, None
        for i, q in enumerate(self.xy):
            d = math.dist(p, q)
            if d <= best:
                best, bi = d, i
        return bi


def shortest(g: Graph, source: int, closed: set[str] = frozenset()) -> tuple[list[float], list[tuple[int, str] | None]]:
    """Dijkstra from one vertex, skipping closed ways. Returns distances (inf where unreachable) and back-pointers."""
    dist = [math.inf] * len(g.xy)
    prev: list[tuple[int, str] | None] = [None] * len(g.xy)
    dist[source] = 0.0
    heap = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for v, w, way in g.adj[u]:
            if way in closed:
                continue
            nd = d + w
            if nd < dist[v] - 1e-9 or (abs(nd - dist[v]) <= 1e-9 and prev[v] is not None and (u, way) < prev[v]):
                dist[v], prev[v] = nd, (u, way)
                heapq.heappush(heap, (nd, v))
    return dist, prev


def nearest_source(g: Graph, sources: dict[str, int], closed: set[str] = frozenset()):
    """Multi-source Dijkstra: for every vertex, the distance to the nearest of several destinations (such as health
    facilities), which one it is, and back-pointers for the route. Ties go to the source listed first in sorted order."""
    dist = [math.inf] * len(g.xy)
    prev: list[tuple[int, str] | None] = [None] * len(g.xy)
    origin: list[str | None] = [None] * len(g.xy)
    heap = []
    for name in sorted(sources):
        s = sources[name]
        if s is not None and dist[s] > 0:
            dist[s], origin[s] = 0.0, name
            heap.append((0.0, name, s))
    heapq.heapify(heap)
    while heap:
        d, name, u = heapq.heappop(heap)
        if d > dist[u] or origin[u] != name:
            continue
        for v, w, way in g.adj[u]:
            if way in closed:
                continue
            nd = d + w
            if nd < dist[v] - 1e-9:
                dist[v], prev[v], origin[v] = nd, (u, way), name
                heapq.heappush(heap, (nd, name, v))
    return dist, prev, origin


def pieces(g: Graph, closed: set[str] = frozenset()) -> list[int]:
    """Connected piece of the network for every vertex, with the given ways closed. Labels are the smallest vertex index in
    each piece, so they are stable from run to run."""
    label = [-1] * len(g.xy)
    for start in range(len(g.xy)):
        if label[start] >= 0:
            continue
        label[start], stack = start, [start]
        while stack:
            u = stack.pop()
            for v, _, way in g.adj[u]:
                if way not in closed and label[v] < 0:
                    label[v] = start
                    stack.append(v)
    return label


def path_ways(prev, target: int) -> list[str]:
    out, v = [], target
    while prev[v] is not None:
        u, way = prev[v]
        if not out or out[-1] != way:
            out.append(way)
        v = u
    return out[::-1]


def reach(g: Graph, hub: int, anchors: dict[str, int | None], closed: set[str]) -> dict[str, dict]:
    """From the hub to every anchor, with the given ways closed. Distances in km, the ways used, and how many of them have no
    report (unknown) or a damage report (uncertain), so a path through unverified road is never shown as a clean result."""
    dist, prev = shortest(g, hub, closed)
    out = {}
    for name, n in anchors.items():
        if n is None:
            out[name] = {"path": False, "reason": "No mapped road within reach of this place"}
            continue
        if math.isinf(dist[n]):
            out[name] = {"path": False, "reason": "No road path in this network"}
            continue
        ways = path_ways(prev, n)
        states = [g.ways[w]["state"] for w in ways]
        out[name] = {"path": True, "km": round(dist[n] / 1000, 2), "ways": len(ways),
                     "uncertainWays": states.count("uncertain"), "unknownWays": states.count("unknown")}
    return out


def blocking(g: Graph, hub: int, target: int | None, closed: set[str]) -> list[str]:
    """The closed ways on the route the base network would use: what to check first when a place loses its path."""
    if target is None:
        return []
    _, prev = shortest(g, hub, set())
    return [w for w in path_ways(prev, target) if w in closed]


def compare(base: dict[str, dict], scen: dict[str, dict]) -> dict[str, dict]:
    """Per anchor: lost (path in the base network, none here), longer (detour in km), or unchanged."""
    out = {}
    for name, b in base.items():
        s = scen[name]
        if b["path"] and not s["path"]:
            out[name] = {"change": "no path", "baseKm": b["km"]}
        elif b["path"] and s["path"] and s["km"] > b["km"] + 0.05:
            out[name] = {"change": "longer", "baseKm": b["km"], "km": s["km"], "detourKm": round(s["km"] - b["km"], 2)}
        elif b["path"]:
            out[name] = {"change": "unchanged", "km": s["km"]}
        else:
            out[name] = {"change": "no path in either", "reason": b["reason"]}
    return out
