# Flood and landslide readiness

Added 13 November 2026 (audit item P1). CascadeLens does not forecast floods or landslides. The readiness engine records, from the files actually on disk, how far each forecasting capability could honestly go, what blocks it, and the next thing it needs. The app shows the result under **What is real? → Flood and landslide outlooks**.

## States

A capability earns the first state on this ladder that it does not get past:

| State | Meaning |
|---|---|
| Not available | An essential dataset is missing |
| Data available, processing required | Every essential dataset is present, but one fails a condition |
| Model required | The data is fit for use, but no model output is recorded |
| Calibration required | A model output exists, with no calibration record |
| Validation required | No independent validation record, the validation data is missing, or the validation ran and missed the criterion it stated beforehand (`"criterionMet": false`) |
| Experimental | Validated out of sample, with its metrics recorded |
| Operationally evaluated | A full season evaluated with partners |
| Context only | For context capabilities (F0, L0): the data is fit, and nothing is predicted |

Some capabilities have a ceiling they can never pass, whatever is on disk. Inundation (F4) stops at *Validation required*, because the corridor has no surveyed cross-sections. InSAR movement (L4) stops at the same state, because the phase sign convention is unanswered.

## Conditions checked for each dataset

For each dataset it needs, a capability checks:

* that the dataset is present;
* its variables and units;
* spatial overlap with the needed area;
* coverage of the needed time window;
* resolution;
* CRS;
* the missing-value fraction;
* quality flags;
* freshness, from `available_at`;
* product maturity;
* licence.

Every check is recorded with its reason. A copy of a dataset that fails a check is not used if another copy passes.

## Today

| Capability | State | Next requirement |
|---|---|---|
| F0 Geographic context | Context only | B5: DEM for the whole Trishuli catchment |
| F1 Flood susceptibility | Not available | B5 |
| F2 Rainfall monitoring | Not available | B2: DHM discharge (IMERG rainfall, B1, is now on disk) |
| F3 24-hour threshold forecast | Not available | B2: DHM discharge; B1 covers 2016 to 2026 but its window starts in 2014 |
| F4 Inundation forecast | Not available (ceiling: validation required) | B7: cross-sections |
| F5 Infrastructure impact | Not available | B2: DHM discharge |
| L0 Terrain and geology | Context only | C2: geological map |
| L1 Susceptibility | Not available | C2: geological map (the NASA catalogue is present as C1 but ends in 2016) |
| L2 Rainfall-trigger monitoring | Data available, processing required | C1: the BIPAD inventory has no stated licence. A threshold was fitted, calibrated and validated on real data, and missed its criterion (see [MODELS.md](MODELS.md)) |
| L3 24-hour threshold forecast | Not available | B3: archived rainfall forecasts |
| L4 InSAR movement | Data available, processing required (ceiling: validation required) | C7: the NISAR GUNW series is registered (five Track 48 pairs over frames 74 and 75, 23 Jul to 3 Oct 2026, and five Track 98 pairs, 26 Jul to 6 Oct) but ends before window W1 closes on 10 Oct. Phase is not converted to displacement |
| L5 Infrastructure impact | Not available | E1: field reports for named places |

`frontend/public/data/readiness.json` holds every check behind these.

## Adding a dataset

1. Put the files under `data/raw/<domain>/<provider>/<product>/` with their original names. For example, `data/raw/met/nasa-gesdisc/imerg-v07-late/`.
2. Register them, giving the catalogue ID from `processing/configs/readiness.json`:

   ```bash
   python processing/scripts/register_source.py data/raw/met/nasa-gesdisc/imerg-v07-late --dataset B1 --provider "NASA GES DISC" --product "IMERG V07 Late" --licence "NASA open data" --available-at 2026-11-12T04:00:00Z --variables precipitation --units precipitation=mm/h --quality-flags
   ```

   It writes `SOURCE.json`, and reads the extent, CRS, resolution and table dates from the files where it can.
3. Run the engine:

   ```bash
   python processing/scripts/prepare_readiness.py
   ```

`available_at` is when the provider published the data. A backtest for issue time *t* may read only records with `available_at` no later than *t*, which keeps hindcasts free of leakage.

The datasets the repository already ships (group A: NISAR, the DEM clip, UNOSAT, OpenStreetMap and HOT) are registered by `prepare_readiness.py` itself, in `data/metadata/sources`. Reference data kept in the repository, such as the Nepal subset of NASA's Global Landslide Catalog, sits under `data/reference` with its own `SOURCE.json`. The model code that would use these is described in [MODELS.md](MODELS.md).

## Model evidence

A model, calibration, validation or operational record is a JSON file in `data/metadata/evidence`, written by the model code that produced it:

```json
{"key": "flood.F3.validation", "summary": "Chronological test 2025-2026: POD 0.71, FAR 0.32, CSI 0.53 at the danger level", "needsDatasets": ["B2"], "report": "data/qa/f3-validation.json"}
```

A record counts only while the datasets it names are on disk. A validation record states its pass criterion before it is scored, and carries `"criterionMet"`. When it is false, the record is kept and shown, but the capability stays at *Validation required*: a model that ran and missed its own bar has not been validated. A unit test (`frontend/src/services/readiness.test.ts`) fails if a capability sits above a rung whose record is missing or failed, or above *Data available, processing required* while any data check fails.

The app lists recorded model work under each capability ("Model work recorded"), passed or not, next to whatever still blocks it.
