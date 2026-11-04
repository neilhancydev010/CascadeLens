"""Synthetic NISAR-shaped HDF5 files. SOFTWARE TEST FIXTURES ONLY: the values are invented and must never reach the app as data."""
import pathlib
import sys

import h5py
import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "processing/src"))

EPSG = 32645
X0, Y0, N, POST = 340000.0, 3130000.0, 60, 80.0  # Inside UTM 45N, overlaps the Rasuwa envelope
AOI = [84.3976, 27.7320, 85.5508, 28.3500]


def _ident(f, product, track=48, frame=74, direction="Descending"):
    i = f.create_group("/science/LSAR/identification")
    i["productType"], i["trackNumber"], i["frameNumber"], i["orbitPassDirection"] = product, track, frame, direction
    i["compositeReleaseId"], i["missionId"] = "P05023", "SYNTHETIC-TEST"
    if product == "GCOV":
        i["zeroDopplerStartTime"] = "2026-08-28T12:58:46.000"
    else:
        i["referenceZeroDopplerStartTime"] = "2026-08-16T12:58:46.000"
        i["secondaryZeroDopplerStartTime"] = "2026-08-28T12:58:46.000"


def _grid(g):
    g["xCoordinates"] = X0 + np.arange(N) * POST
    g["yCoordinates"] = Y0 - np.arange(N) * POST
    p = g.create_dataset("projection", data=EPSG, dtype="u4")
    p.attrs["epsg_code"] = EPSG


def _ds(g, name, data, units=None, fill=np.nan):
    d = g.create_dataset(name, data=data)
    if units:
        d.attrs["units"] = units
    d.attrs["_FillValue"] = fill
    return d


def make_gunw(path, frame=74):
    with h5py.File(path, "w") as f:
        _ident(f, "GUNW", frame=frame)
        root = f.create_group("/science/LSAR/GUNW/grids/frequencyA")
        root["listOfPolarizations"] = np.array([b"HH"])
        u = root.create_group("unwrappedInterferogram")
        _grid(u)
        hh = u.create_group("HH")
        phase = np.linspace(-6, 6, N * N, dtype=np.float32).reshape(N, N)
        phase[0, 0] = np.nan
        phase[1, 1] = np.inf
        _ds(hh, "unwrappedPhase", phase, "radians")
        _ds(hh, "coherenceMagnitude", np.full((N, N), 0.7, np.float32), "1")
        _ds(hh, "ionospherePhaseScreen", np.full((N, N), 0.5, np.float32), "radians")
        cc = np.ones((N, N), np.uint16)
        cc[2, 2] = 65535
        cc[3, 3] = 0
        _ds(hh, "connectedComponents", cc, "1", 65535)
        m = np.full((N, N), 11, np.uint8)
        m[4, 4] = 111  # water
        m[5, 5] = 10  # invalid secondary subswath
        m[6, 6] = 255  # fill
        _ds(u, "mask", m, "1", 255)


def make_goff(path, frame=74):
    with h5py.File(path, "w") as f:
        _ident(f, "GOFF", frame=frame)
        root = f.create_group("/science/LSAR/GOFF/grids/frequencyA")
        root["listOfPolarizations"] = np.array([b"HH"])
        po = root.create_group("pixelOffsets")
        _grid(po)
        l3 = po.create_group("HH/layer3")
        rng = np.random.default_rng(1).normal(0, 0.1, (N, N)).astype(np.float32)
        rng[10, 10] = 500  # gross outlier
        m = np.full((N, N), 11, np.uint8)
        m[4, 4] = 111  # water
        m[6, 6] = 255  # fill
        _ds(po, "mask", m, "1", 255)
        _ds(l3, "slantRangeOffset", rng, "meters")
        _ds(l3, "alongTrackOffset", rng * 0.5, "meters")
        _ds(l3, "snr", np.full((N, N), 8.0, np.float32), "1")
        _ds(l3, "correlationSurfacePeak", np.full((N, N), 0.4, np.float32), "1")


def make_gcov(path, masking_applied=True, frame=74):
    with h5py.File(path, "w") as f:
        _ident(f, "GCOV", frame=frame)
        root = f.create_group("/science/LSAR/GCOV/grids/frequencyA")
        root["listOfPolarizations"] = np.array([b"HH"])
        root["listOfCovarianceTerms"] = np.array([b"HHHH"])
        _grid(root)
        power = np.full((N, N), 0.01, np.float32)
        power[0, 0] = np.nan
        _ds(root, "HHHH", power, "1")
        m = np.full((N, N), 1, np.uint8)
        m[5, 5] = 0  # partially focused
        m[6, 6] = 255  # outside the acquisition
        _ds(root, "mask", m, "1", 255)
        p = f.create_group("/science/LSAR/GCOV/metadata/processingInformation/parameters")
        p["validSamplesSubSwathMaskingApplied"] = str(masking_applied)


def granule(product="GUNW", frame=74, group="pair-a", file_id=None):
    gcov = product == "GCOV"
    return {"product": product, "track": 48, "frame": frame, "direction": "DESCENDING", "ref_date": "2026-08-28" if gcov else "2026-08-16", "sec_date": None if gcov else "2026-08-28",
            "file_id": file_id or f"NISAR_L2_PR_{product}_TEST_F{frame}", "group": group, "size_mb": 1.0, "url": None}


@pytest.fixture
def cfg():
    return {"aoi_bbox": AOI, "crid": "P05023", "goff_layer": 3, "gross_outlier_mad_k": 10, "snr_min": None, "coherence_threshold": None,
            "min_valid_fraction": 0.01, "tile_zoom": [9, 11],
            "pairs": [{"id": "pair-a", "label": "L", "role": "R", "direction": "DESCENDING", "track": 48, "frames": [74, 75], "ref_date": "2026-08-16", "sec_date": "2026-08-28", "products": ["GUNW", "GOFF"]}],
            "snapshots": []}


@pytest.fixture
def gunw_file(tmp_path):
    p = tmp_path / "gunw.h5"
    make_gunw(p)
    return p


@pytest.fixture
def goff_file(tmp_path):
    p = tmp_path / "goff.h5"
    make_goff(p)
    return p
