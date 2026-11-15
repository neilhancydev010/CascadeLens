"""Validity classes and QA gates. Masks never change a measurement: they classify it, the raw value stays in the COG."""
from __future__ import annotations

import csv

import numpy as np

NODATA, VALID, MASKED = 0, 1, 2  # validity raster classes, shared with the frontend inspector
GUNW_CC_FILL_SPEC = 65535  # connectedComponents fill in GUNW Rev E; used only when a file lacks the _FillValue attribute


def zero_filled_phase(phase: np.ndarray) -> np.ndarray:
    """Unwrapped phase stored as exactly 0.0. The product writes 0 where unwrapping failed, so an exact zero is treated as
    "no measurement" (masked, value kept). A component's own reference pixel can legitimately be 0, so this may also
    mask at most one real pixel per component; that loss is accepted to stop zero-fill being read as a measurement."""
    phase = np.asarray(phase)
    return np.isfinite(phase) & (phase == 0)


def unreliable_component(cc: np.ndarray, fill=GUNW_CC_FILL_SPEC) -> np.ndarray:
    """ATBD 5.9.1.7: label 0 was not reliably unwrapped. The fill value holds no component. Non-finite holds no label."""
    cc = np.asarray(cc)
    return ~np.isfinite(cc) | (cc == 0) | (cc == fill)


def clean(a: np.ndarray, fill=None) -> np.ndarray:
    """Float32 copy with fill, NaN and +-inf all represented as NaN."""
    out = np.array(a, dtype=np.float32)
    if fill is not None and not (isinstance(fill, float) and np.isnan(fill)) and fill != "nan":
        out[np.asarray(a) == fill] = np.nan
    out[~np.isfinite(out)] = np.nan
    return out


def decode_gunw_mask(m: np.ndarray) -> dict:
    """GUNW and GOFF mask, a 32-bit field (the product's own mask description, P05023 files):
      bits 0-7    three decimal digits: water flag / reference subswath / secondary subswath; a 0 subswath is invalid; 255 is fill
      bits 8-15   anomaly flags for the secondary RSLC     bits 16-23  anomaly flags for the reference RSLC
      bit 24      the ionosphere screen was interpolated here (not an estimate at this pixel)
    Older 8-bit masks (Rev E samples) are the same digits with no higher bits. The digits must be read from the low byte only:
    read from the whole number, a set bit 24 turns valid subswaths into invalid ones and hides water."""
    m = np.asarray(m)
    if not np.issubdtype(m.dtype, np.integer):
        m = np.where(np.isfinite(m), m, 255)
    m = m.astype(np.int64)
    low = m & 0xFF
    fill = low == 255
    ref, sec = (low // 10) % 10, low % 10
    water = ((low // 100) == 1) & ~fill
    invalid = ((ref == 0) | (sec == 0)) & ~fill
    anomaly = (((m >> 8) & 0xFFFF) != 0) & ~fill
    return {"fill": fill, "water": water, "invalid_subswath": invalid, "anomaly": anomaly,
            "iono_interpolated": (((m >> 24) & 1) == 1) & ~fill, "unusable": water | invalid | anomaly}


def _mask_classes(shape, mask: np.ndarray | None) -> np.ndarray:
    v = np.full(shape, VALID, np.uint8)
    if mask is not None:
        d = decode_gunw_mask(mask)
        v[d["unusable"]] = MASKED
        v[d["fill"]] = NODATA
    return v


def gunw_validity(values: np.ndarray, mask: np.ndarray | None, cc: np.ndarray | None = None, cc_fill=GUNW_CC_FILL_SPEC,
                  zero_is_fill: bool = False, undefined: np.ndarray | None = None) -> np.ndarray:
    """Validity of one GUNW layer.

    cc:           pass the component labels for phase only. ATBD 5.9.1.7: label 0 could not be reliably unwrapped (masked);
                  the fill value holds no component (no data).
    zero_is_fill: for unwrapped phase, an exact 0.0 is the product's fill in unwrapping gaps (masked, value kept).
    undefined:    pixels where this layer has no meaning, e.g. the component map where the product holds no phase (no data).
    """
    v = _mask_classes(values.shape, mask)
    nodata = v == NODATA  # mask fill: kept as no data whatever the other rules say
    if zero_is_fill:
        v[zero_filled_phase(values)] = MASKED
    if cc is not None:
        cc = np.asarray(cc)
        v[cc == 0] = MASKED
        nodata |= cc == cc_fill
    if undefined is not None:
        nodata |= np.asarray(undefined, bool)
    nodata |= ~np.isfinite(values)
    v[nodata] = NODATA  # no data always wins over masked
    return v


def gross_outliers(a: np.ndarray, k: float) -> np.ndarray:
    """|x - median| > k * 1.4826 * MAD. Global, so a real large signal survives unless k is set too low."""
    valid = a[np.isfinite(a)]
    if not valid.size:
        return np.zeros(a.shape, bool)
    med = np.median(valid)
    mad = 1.4826 * np.median(np.abs(valid - med))
    if mad == 0:
        return np.zeros(a.shape, bool)
    with np.errstate(invalid="ignore"):
        return np.abs(a - med) > k * mad


def offset_validity(values: np.ndarray, k: float | None, snr: np.ndarray | None = None, snr_min: float | None = None, mask: np.ndarray | None = None) -> np.ndarray:
    v = _mask_classes(values.shape, mask)
    if k is not None:
        v[gross_outliers(values, k)] = MASKED
    if snr is not None and snr_min is not None:
        with np.errstate(invalid="ignore"):
            v[~(snr >= snr_min)] = MASKED  # NaN SNR means quality is unknown, so it is not called valid
    v[~np.isfinite(values)] = NODATA
    return v


def gcov_validity(values: np.ndarray, mask: np.ndarray | None = None, masking_applied: bool = False) -> np.ndarray:
    """Rev E: 255 is outside the acquisition, 0 is partially focused. 0 only carries that meaning if the product says
    subswath masking was applied: the public samples report False and hold 0 on every pixel."""
    v = np.full(values.shape, VALID, np.uint8)
    if mask is not None:
        if masking_applied:
            v[np.asarray(mask) == 0] = MASKED
        v[np.asarray(mask) == 255] = NODATA
    v[~np.isfinite(values)] = NODATA
    return v


def to_db(power: np.ndarray) -> np.ndarray:
    """10*log10 of a linear power term; nonpositive input has no dB value."""
    out = np.full(power.shape, np.nan, np.float32)
    ok = np.isfinite(power) & (power > 0)
    out[ok] = 10 * np.log10(power[ok])
    return out


def _date(ts) -> str | None:
    return ts[:10] if isinstance(ts, str) else None


def check_granule(report: dict, granule: dict) -> list[dict]:
    """Compare a file's own metadata to the catalogue record it was downloaded for."""
    i = report["identification"]
    expect = [("productType", report["product"], i.get("productType")),
              ("track", granule["track"], i.get("trackNumber")),
              ("frame", granule["frame"], i.get("frameNumber")),
              ("direction", granule["direction"].lower(), str(i.get("orbitPassDirection")).lower()),
              ("reference date", granule["ref_date"], _date(i.get("referenceZeroDopplerStartTime") or i.get("zeroDopplerStartTime")))]
    if granule.get("sec_date"):
        expect.append(("secondary date", granule["sec_date"], _date(i.get("secondaryZeroDopplerStartTime"))))
    out = [{"check": n, "ok": a == b, "expected": a, "found": b} for n, a, b in expect]
    out.append({"check": "required datasets present", "ok": not report["missing"], "expected": "none missing", "found": report["missing"]})
    out.append({"check": "documented units match", "ok": not report["unit_mismatch"], "expected": "no mismatch", "found": report["unit_mismatch"]})
    return out


def passed(checks: list[dict]) -> bool:
    return all(c["ok"] for c in checks)


def read_qa_summary(path) -> dict:
    """NISAR's own QA CSV. Failed rows are reported for a person to judge: the public samples FAIL the identification
    check and still read correctly, so a FAIL is not treated here as proof of a bad product."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    nan = {r["Notes"]: float(r["Actual"]) for r in rows if r["Check"].startswith("% NaN") and r["Actual"]}
    return {"checks": len(rows), "failed": [r["Check"] for r in rows if r["Result"] == "FAIL"], "percent_nan": nan}
