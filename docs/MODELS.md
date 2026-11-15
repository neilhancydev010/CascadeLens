# First models (audit P2)

The audit asks for the simplest defensible model for each capability, with out-of-sample skill reported before anything is called a forecast. The model code and the yardstick were added on 13 November 2026 and tested on synthetic data. Later the same day, the rainfall-trigger threshold (L2) was **run on real data for the first time**. It did not beat chance in the held-out years, and the app says so. The other models still wait for data, and the [readiness engine](READINESS.md) records exactly which.

## What exists

| Capability | Code | Method | Tested on |
|---|---|---|---|
| L2/L3 rainfall-trigger thresholds | `cascade_lens/models/thresholds.py` | Event rainfall E against duration D, E = α·D^β, fitted in log space, then lowered so a chosen share of triggering events lies below (frequentist method, Brunetti et al. 2010). `ongoing` and `warnings` follow the event so far, day by day, reading no later day. Plus an antecedent precipitation index | Synthetic events, then real data (below) |
| L1 susceptibility | `cascade_lens/models/susceptibility.py` | Ridge logistic regression on standardised features, validated only by spatial block cross-validation | Synthetic terrain: known effects are recovered, and shuffled labels score an AUC of 0.5 |
| F3 threshold forecast (river) | `cascade_lens/models/gr4j.py` | GR4J (Perrin et al. 2003) with a one-band degree-day snow routine, calibrated by seeded differential evolution on NSE | Synthetic catchment: unit hydrographs sum to one, snow conserves water, calibration recovers the catchment (NSE > 0.98) |
| Verification for all of them | `cascade_lens/verify.py` | POD, FAR, CSI and bias; event matching; `windowed` scoring with a lead window; a month-preserving shuffle for chance level; chronological splits; the `available_at` leakage guard; spatial-block folds; AUC; NSE | Hand-worked cases |

Tests: `tests/processing/test_models.py`, `tests/processing/test_verify.py`.

## L2 on real data: the first run

### Data

* **Rainfall:** GPM IMERG Late V07, daily, 0.1° (about 11 km), 84.0–86.5° E, 27.5–29.5° N, every UTC day from 1 June 2016 to 31 October 2026 (3,805 days, none missing). Late is used rather than Final because it is what a warning could have used on the day. `fetch_imerg.py`, then `prepare_rainfall.py`.
* **Landslides:** BIPAD incident records (NDRRMA), hazard "Landslide". There are 1,826 reports in the same box, placed on the rainfall grid, with several reports in one cell on one day counting once. `fetch_bipad.py`, then `prepare_bipad_inventory.py`. See [DATA_SOURCES.md](DATA_SOURCES.md#bipad-landslide-incidents) for what these records are: reports at ward reference points, with reporting that grew strongly over the years and no stated licence.

### Method, fixed before the test years were scored

The full method is the docstring of `processing/scripts/run_rain_thresholds.py`:

1. A report's triggering rainfall is the event running that day, or one that stopped the day before. Two dry days end an event, and a wet day has at least 1 mm.
2. The threshold is fitted to these events on 2016–2022.
3. Calibration on 2023–2024 picks two things together: the share of triggering events left below the line (5, 10, 20, 30 or 50%), and the share of the corridor's 72 cells that must be over the line before the corridor (area R1) is warned (any, 10%, 25% or 50%).
4. The chosen level is refitted on 2016–2024.
5. **Validation** uses 1 January 2025 to 31 October 2026, which was never scored before. A corridor-day with at least one report is an event day.
6. **As published:** IMERG Late appears about 14 hours after the UTC day ends, at 19:45 the next day in Nepal. So a warning counts only for reports 2 or 3 days after its rainfall day.
7. **Criterion, stated in advance:** the corridor's CSI as published must exceed the 95th percentile of 1,000 shuffles. Each shuffle keeps the number of warning days in every calendar month, so the bar is "better than knowing which months are wet".

Scoring cell by cell (each 11 km cell on each day) was tried first, on the training years only, and dropped. Reports are too sparse per cell for it to mean anything.

### Result

| | Value |
|---|---|
| Threshold | E = 6.7 · D^1.17 mm, fitted to 820 triggering events, 20% of them below the line. 25 reports had no rainfall event and were left out |
| Corridor warning | When at least 50% of the corridor's cells are over the line (chosen on 2023–2024, CSI 0.285 there) |
| Held out, corridor, as published | 170 warning days and 136 event days in 669 days. 47 hits, 89 misses, 95 false alarms. **POD 0.35, FAR 0.67, CSI 0.20**, bias 1.04 |
| Chance, same months | CSI median 0.19, 95th percentile 0.21. **p = 0.12** |
| Criterion | **Not met** |
| Without the publication delay (diagnostic only) | CSI 0.23, POD 0.38, FAR 0.63 |

**What this means:** daily IMERG Late rainfall, used this way, adds little to knowing that the monsoon is the landslide season. The threshold is not a usable warning for the corridor. The validation record says so (`"criterionMet": false`), the app lists it under "Model work recorded", and L2 cannot rise above *Validation required* on this evidence.

### Why it may have failed

These are hypotheses, not findings:

* BIPAD records reports, not landslides. Many landslides are never reported, and reports cluster where people and roads are.
* A report's point is a ward reference point, so a landslide can sit in the next 11 km cell.
* A daily total at 11 km smooths out the short, local downpours that trigger many slides.
* Reporting grew strongly in 2024–2026, so the test years have far more reports per wet day than the years the threshold learned from.
* The 14-hour delay of the Late run removes the same-day warning. Even without it, the CSI is 0.23.

### What it would take to do better

* Sub-daily IMERG (half-hourly) for intensity-duration thresholds.
* An antecedent-wetness term: the `api` function exists, and SMAP soil moisture (C6) is not on disk.
* A mapped, dated inventory instead of reports.
* Gauge rainfall from DHM. This needs an API key.

### Why the readiness state is lower still

BIPAD states no licence or terms of reuse. The readiness engine therefore fails C1's licence check and holds L2 at *Data available, processing required*, whatever the scores. The records stay under `data/raw`, which git ignores, and are not redistributed. Once NDRRMA confirms terms, record them in `data/raw/hazard/bipad/SOURCE.json` and run `prepare_readiness.py`. L2 would then show *Validation required*, because the validation missed its criterion.

To reproduce:

```bash
python processing/scripts/fetch_imerg.py
python processing/scripts/prepare_rainfall.py
python processing/scripts/fetch_bipad.py
python processing/scripts/prepare_bipad_inventory.py
python processing/scripts/run_rain_thresholds.py
python processing/scripts/prepare_readiness.py
```

The rainfall stacks are committed under `data/reference/rainfall/GPM_3IMERGDL.07`, so the first two steps are only needed to refresh them. `fetch_imerg.py` needs an Earthdata Login token. The evidence records are in `data/metadata/evidence`, and the full output is in `data/qa/rain_thresholds.json`.

## What still blocks the other models

| Model | Needs | Status, 13 November 2026 |
|---|---|---|
| L3 24-hour forecast | L2's thresholds, plus archived rainfall forecasts as issued (B3) | Not attempted: no archived forecasts, and L2 did not beat chance |
| L1 susceptibility | A multi-event inventory with accurate locations, and a geological map (C2) | No geological map. The only open one (USGS OFR 97-470C) is meant for scales of 1:5,000,000 and coarser. The Durham 3 km landslide grid (CC BY 4.0) is a candidate inventory, but ends in 2021 |
| F3 GR4J | DHM discharge with danger levels (B2), IMERG rainfall, temperature, and archived forecasts | DHM's observation API refuses requests without an API key. Four corridor stations were destroyed in August 2026 |

## The NASA Global Landslide Catalog

`processing/scripts/prepare_inventory.py` takes the Nepal records from NASA's Global Landslide Catalog. That's 481 events, 21 March 2007 to 13 October 2016, and the output is `data/reference/hazard/nasa-glc/glc_nepal.csv` with its `SOURCE.json`. The readiness engine records it as a copy of C1, present but not fit:

* It ends in October 2016, so it does not cover the 2016–2024 training window or the 2025–2026 test years.
* It is compiled from media and reports, so places with no record are not confirmed negatives.
* Only 29 of the 481 locations are exact or within 1 km. Most are within 5 to 50 km, which is far too coarse for a 30 m susceptibility model.
* Its licence is not stated on data.nasa.gov, so the engine marks the licence as not established.

No model was fitted to it.

## To run a model once data exists

1. Put the data under `data/raw/...` and register it with `register_source.py` (see [READINESS.md](READINESS.md)).
2. Fit on the training period only, calibrate on the validation period, and score the test period with `cascade_lens.verify`. Inputs must pass the `available_at` guard at each issue time.
3. State the pass criterion before scoring the test period.
4. Write the evidence records (`data/metadata/evidence/<capability>.<rung>.json`) with the scores, `criterionMet` and the datasets relied on, then run `prepare_readiness.py`. The app then shows the state that has been earned, and no more.
