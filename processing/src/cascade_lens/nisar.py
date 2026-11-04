"""NISAR L2 HDF5 access.

Paths and conventions come from JPL D-102272 Rev E (GUNW), D-105010 Rev C (GOFF), D-102274 Rev E (GCOV) and the ATBD D-95677,
and were checked against the public NISAR sample granules (tests/integration/test_real_format.py). Nothing is trusted blindly:
`inspect` compares them against each real file and QA fails on a mismatch.
"""
from __future__ import annotations

from dataclasses import dataclass

import h5py
import numpy as np
from affine import Affine
from pyproj import Transformer

ID = "/science/LSAR/identification"
ROOT = {"GUNW": "/science/LSAR/GUNW/grids/frequencyA", "GOFF": "/science/LSAR/GOFF/grids/frequencyA",
        "GCOV": "/science/LSAR/GCOV/grids/frequencyA"}

UNITLESS = {"1", "unitless"}  # GOFF spec R3.4 writes "unitless"; real files write "1"
GCOV_MASKING_FLAG = "/science/LSAR/GCOV/metadata/processingInformation/parameters/validSamplesSubSwathMaskingApplied"

# value: dataset path under ROOT[product], {pol} and {layer} filled per granule. units None = not documented.
# colormap names are defined in export.COLORMAPS; quality = ids of the measurements that qualify this one.
MEASUREMENTS = {
    "gunw-phase": dict(product="GUNW", path="unwrappedInterferogram/{pol}/unwrappedPhase", units="radians",
                       name="Unwrapped phase", kind="continuous", colormap="diverging", quality=["gunw-coherence", "gunw-cc", "gunw-iono"], display="relative"),
    "gunw-phase-iono": dict(product="GUNW", path=None, units="radians", name="Phase with ionosphere screen removed", kind="continuous", colormap="diverging",
                            quality=["gunw-coherence", "gunw-cc"], display="relative"),
    "gunw-coherence": dict(product="GUNW", path="unwrappedInterferogram/{pol}/coherenceMagnitude", units=None,
                           name="Coherence magnitude", kind="continuous", colormap="sequential", quality=[]),
    "gunw-cc": dict(product="GUNW", path="unwrappedInterferogram/{pol}/connectedComponents", units="1",
                    name="Connected components", kind="categorical", colormap="categorical", quality=[]),
    "gunw-iono": dict(product="GUNW", path="unwrappedInterferogram/{pol}/ionospherePhaseScreen", units="radians",
                      name="Ionosphere phase screen", kind="continuous", colormap="diverging", quality=[], display="relative"),
    "goff-range": dict(product="GOFF", path="pixelOffsets/{pol}/layer{layer}/slantRangeOffset", units="meters",
                       name="Slant-range offset", kind="continuous", colormap="diverging", quality=["goff-snr", "goff-peak"]),
    "goff-azimuth": dict(product="GOFF", path="pixelOffsets/{pol}/layer{layer}/alongTrackOffset", units="meters",
                         name="Along-track offset", kind="continuous", colormap="diverging", quality=["goff-snr", "goff-peak"]),
    "goff-snr": dict(product="GOFF", path="pixelOffsets/{pol}/layer{layer}/snr", units=None,
                     name="Offset SNR", kind="continuous", colormap="sequential", quality=[]),
    "goff-peak": dict(product="GOFF", path="pixelOffsets/{pol}/layer{layer}/correlationSurfacePeak", units="1",
                      name="Correlation surface peak", kind="continuous", colormap="sequential", quality=[]),
    "gcov-backscatter": dict(product="GCOV", path="{term}", units="1", name="Gamma-0 backscatter", kind="continuous",
                             colormap="grey", quality=[], display="db"),
}
MASK_PATH = {"GUNW": "unwrappedInterferogram/mask", "GOFF": "pixelOffsets/mask", "GCOV": "mask"}


def _py(v):
    """HDF5 scalar/bytes -> plain python, so reports serialise to JSON."""
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    if isinstance(v, np.ndarray):
        return [_py(x) for x in v.tolist()] if v.size < 32 else f"<array {v.shape}>"
    if isinstance(v, np.generic):
        return _py(v.item())
    if isinstance(v, float) and v != v:
        return "nan"
    return v


def _read(h5, path):
    return _py(h5[path][()]) if path in h5 else None


def units_match(want: str, got) -> bool:
    return got == want or (want in UNITLESS and got in UNITLESS)


def flag(h5, path: str) -> bool:
    """NISAR booleans are the strings "True" and "False". Missing means not applied."""
    return str(_read(h5, path)).lower() == "true"


def identify(h5) -> dict:
    keys = ["productType", "missionId", "trackNumber", "frameNumber", "orbitPassDirection", "lookDirection",
            "compositeReleaseId", "productVersion", "productSpecificationVersion", "granuleId", "productDoi",
            "referenceZeroDopplerStartTime", "secondaryZeroDopplerStartTime", "zeroDopplerStartTime",
            "isFullFrame", "isUrgentObservation", "processingDateTime", "processingType", "boundingPolygon", "radarBand"]
    return {k: _read(h5, f"{ID}/{k}") for k in keys}


def polarizations(h5, product: str) -> list[str]:
    v = _read(h5, f"{ROOT[product]}/listOfPolarizations")
    return [v] if isinstance(v, str) else (v or [])


def covariance_terms(h5) -> list[str]:
    v = _read(h5, f"{ROOT['GCOV']}/listOfCovarianceTerms")
    return [v] if isinstance(v, str) else (v or [])


def inventory(h5) -> dict:
    out = {}

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset):
            attrs = {k: _py(obj.attrs[k]) for k in ("units", "_FillValue", "long_name", "description", "grid_mapping", "epsg_code") if k in obj.attrs}
            out["/" + name] = {"shape": list(obj.shape), "dtype": str(obj.dtype), "attrs": attrs}

    h5.visititems(visit)
    return out


@dataclass
class Grid:
    epsg: int
    x: np.ndarray  # pixel-centre coordinates
    y: np.ndarray

    @property
    def dx(self) -> float:
        return float(self.x[1] - self.x[0])

    @property
    def dy(self) -> float:
        return float(self.y[1] - self.y[0])

    def transform(self, row0=0, col0=0) -> Affine:
        return Affine(self.dx, 0, self.x[col0] - self.dx / 2, 0, self.dy, self.y[row0] - self.dy / 2)

    def same_as(self, other: "Grid") -> bool:
        return self.epsg == other.epsg and self.x.shape == other.x.shape and self.y.shape == other.y.shape \
            and np.allclose(self.x, other.x) and np.allclose(self.y, other.y)


def find_grid(h5, ds_path: str) -> Grid:
    """Walk up from a dataset to the group holding its coordinates; layouts differ between products."""
    g = h5[ds_path].parent
    while g.name != "/":
        if all(k in g for k in ("xCoordinates", "yCoordinates", "projection")):
            x, y = g["xCoordinates"][()], g["yCoordinates"][()]
            if np.ptp(np.diff(x)) > 1e-6 * abs(x[1] - x[0]) or np.ptp(np.diff(y)) > 1e-6 * abs(y[1] - y[0]):
                raise ValueError(f"non-uniform grid at {g.name}")
            return Grid(int(g["projection"][()]), x, y)
        g = g.parent
    raise KeyError(f"no coordinate group above {ds_path}")


def bbox_to_window(grid: Grid, bbox) -> tuple[slice, slice] | None:
    """Row/col slices covering a lon/lat bbox in the file's own CRS, or None if they do not overlap."""
    w, s, e, n = bbox
    t = Transformer.from_crs(4326, grid.epsg, always_xy=True)
    lons = np.r_[np.linspace(w, e, 25), np.full(25, e), np.linspace(e, w, 25), np.full(25, w)]
    lats = np.r_[np.full(25, s), np.linspace(s, n, 25), np.full(25, n), np.linspace(n, s, 25)]
    xs, ys = t.transform(lons, lats)
    cols = np.flatnonzero((grid.x >= xs.min()) & (grid.x <= xs.max()))
    rows = np.flatnonzero((grid.y >= ys.min()) & (grid.y <= ys.max()))
    if not cols.size or not rows.size:
        return None
    return slice(int(rows[0]), int(rows[-1]) + 1), slice(int(cols[0]), int(cols[-1]) + 1)


def dataset_path(measurement: str, pol: str = "", layer: int = 1, term: str = "") -> str:
    m = MEASUREMENTS[measurement]
    return f"{ROOT[m['product']]}/{m['path'].format(pol=pol, layer=layer, term=term)}"


def expected_paths(h5, product: str, layer: int) -> dict[str, str]:
    pols = polarizations(h5, product)
    terms = covariance_terms(h5) if product == "GCOV" else []
    pol = pols[0] if pols else "HH"
    term = next((t for t in terms if len(t) == 4 and t[:2] == t[2:]), "HHHH")
    return {k: dataset_path(k, pol, layer, term) for k, m in MEASUREMENTS.items() if m["product"] == product and m["path"]}


def inspect(path: str, product: str, layer: int = 3) -> dict:
    """Machine-readable report of what a granule really contains."""
    with h5py.File(path, "r") as h5:
        inv = inventory(h5)
        report = {"file": str(path).replace("\\", "/").rsplit("/", 1)[-1], "product": product, "identification": identify(h5),
                  "polarizations": polarizations(h5, product), "datasets": {}, "missing": [], "unit_mismatch": []}
        if product == "GCOV":
            report["covariance_terms"] = covariance_terms(h5)
        for mid, p in expected_paths(h5, product, layer).items():
            if p not in h5:
                report["missing"].append(p)
                continue
            info = inv[p]
            want = MEASUREMENTS[mid]["units"]
            got = info["attrs"].get("units")
            if want is not None and not units_match(want, got):
                report["unit_mismatch"].append({"path": p, "expected": want, "found": got})
            g = find_grid(h5, p)
            info = info | {"measurement": mid, "epsg": g.epsg, "posting_m": [g.dx, g.dy],
                           "bounds": [float(g.x.min()), float(g.y.min()), float(g.x.max()), float(g.y.max())]}
            report["datasets"][p] = info
        mask = f"{ROOT[product]}/{MASK_PATH[product]}"
        report["mask_present"] = mask in h5
        report["group_count"] = len({p.rsplit("/", 1)[0] for p in inv})
        report["dataset_count"] = len(inv)
        report["all_datasets"] = {p: {"shape": v["shape"], "dtype": v["dtype"], "units": v["attrs"].get("units")} for p, v in inv.items()}
    return report
