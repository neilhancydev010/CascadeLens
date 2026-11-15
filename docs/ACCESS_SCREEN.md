# Road access screen

Added 13 November 2026 (audit item P0.4). **Experimental.** It shows which named places in the Rasuwa corridor keep a road path to a health facility once reported damage is closed, and which closures cause each change. It is a screen that tells you what to check. It does not say who can be reached.

## Question

For each named place: is there a road path to the nearest health facility, how long is it, and what changes when damaged roads and bridges are closed? And which places still share a connected piece of the road network?

## Data

| Input | Source | Use |
|---|---|---|
| Roads | HOT OpenStreetMap export for the 2026 flood (HDX `hot_flood_npl`), roads GeoPackage | Graph. Way IDs, `highway`, `bridge`, `layer`, unsimplified geometry, and `status` (`Destroyed` on 332 roads) |
| Destroyed features | Same export, destroyed features | Destroyed bridges that the roads file lacks (32 ways) |
| Bridge damage assessment | HOT volunteer field reports, 58 bridges in the study area | 39 washed out, 4 damaged, 15 intact |
| Places | Same export, populated places | 26 named places (unnamed points are left out) |
| Health facilities | Same export | 3 places of care (hospital, clinic). Pharmacies are left out |
| Helipads | Same export | 14, for the helipad results in the data file |

`python processing/scripts/fetch_context.py` downloads them, and `python processing/scripts/prepare_access.py processing/configs/access/rasuwa-2026.json data/raw/context frontend/public/data <out dir>` runs the screen. Then `merge_observability.py` folds its fragment into the manifest.

## Method

`processing/src/cascade_lens/access.py`, tested on synthetic networks with hand-computed answers in `tests/processing/test_access.py`.

- **Graph.** One edge per pair of consecutive vertices, in UTM 45N metres. Two ways connect only where they share an OSM vertex, which is how OSM joins roads at junctions. A crossing without a shared vertex, such as a bridge over a road, is not a junction.
- **Road classes.** Trunk to tertiary, unclassified, residential, track and service roads, with their links. Footpaths are left out.
- **Four states per way.** *Closed*: OSM maps the road as destroyed, or a bridge on it is reported washed out. *Uncertain*: reported damaged. *Open*: reported intact. *Unknown*: no report, which is the default. When reports disagree, the stronger one wins: closed over uncertain over open.
- **Bridge reports** are points. Each is matched to the nearest OSM bridge within 60 m. Of 58 reports, 30 matched (16 washed out, 4 damaged, 10 intact). The other 28 are listed in the data file and not used: a report is never attached to a road it may not belong to.
- **Places** join the network at the nearest vertex within 500 m.
- **Shortest paths** use Dijkstra with deterministic tie-breaking. The nearest facility uses a multi-source search.

## Three networks

| Network | Closed | Named places with a road path to a health facility | Connected pieces holding a place or facility |
|---|---|---|---|
| Every mapped road open | Nothing. Includes roads OSM now maps as destroyed, the closest thing to the network before the event | 20 of 26 | 5 |
| Reported damage closed | 260 ways, 65.7 km: roads mapped as destroyed and bridges reported washed out | 10 of 26 | 18 |
| Hypothetical | As above, plus every stretch the exposure screen found on ground UNOSAT mapped as hit in 2026 | 5 of 26 | 34 |

For every place whose path is lost or longer, the data file and the panel name the closures on its old route, with their sources. With reported damage closed, 10 places lose their road path. All 10 old routes cross two bridges the volunteer assessment reports washed out: the Furke Khola bridge and the Trisuli River Bridge at Ghatbesi. Four also cross Trishuli river bridges that OSM maps as destroyed. Check those bridges first.

Six places have no road path to a health facility even with every road open: Silintar, Shyaphru, Shyaphru Bensi, Rasuwa Gadhi, Simle and Mailung. That is a gap in the mapped network, or in the destinations, not a closure, and the app says so.

## Limits

- It is a screen. Footpaths, river crossings, unmapped tracks and helicopters are outside the network, so "no road path in this network" never means a place is isolated.
- **The network stops at the study area.** A detour that leaves it, for example from Trishuli through Kathmandu, is not found. "No road path" can therefore be a boundary effect.
- Only three health facilities are mapped in OSM inside the study area. The real nearest facility may be missing, or just outside the area.
- OSM was edited after the event and is incomplete. A road with no report is Unknown, and the reported network leaves it open, which may be wrong either way.
- No traffic, surface, vehicle, season or road capacity is modelled. Distances run along the mapped centre line.
- The hypothetical network closes whole OSM ways that carry a stretch on ground mapped as hit, which is cautious: the real damage may cover only part of the way.

## In the app

Hazard screens → *Road access to health care*: the scenario, the places that lose their road path, and the closures on those routes, each listed once with its source and how many routes it sits on. A checkbox shows road and bridge states, plus health facilities and helipads, on the map. The detail file `frontend/public/data/access/rasuwa-2026.json` (about 110 KB) loads only when the panel is opened.
