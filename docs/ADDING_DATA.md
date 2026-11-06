# Adding data to Simulate

Simulate offers only what the loaded data can support. New data needs no new simulation code.

| What the data has | What Simulate shows |
|---|---|
| Rivers and terrain for an event | Flow replay and What-if flood |
| A map layer saved at several times | Time replay |
| Radar coherence analysis | Radar explainer |

## A new event

You need terrain (a GeoTIFF elevation file), rivers (GeoJSON lines) and a start point. Buildings, roads and places are optional, and any missing one is left out of the results.

1. Put the files in `frontend/public/data`.
2. Copy `processing/configs/simulation/rasuwa-2026.json` to a new name, and change the file names. `start` can be a file or `[longitude, latitude]`. Delete any optional line you have no file for, and give `output` a new name.
3. Run:

```bash
python processing/scripts/prepare_simulation.py processing/configs/simulation/your-event.json
```

4. Add the event to `CASES` in `frontend/src/services/manifest.ts`, with `simulation` set to `data/` plus your `output`.

## Data that changes over time

Any layer with `timeSteps` in its manifest gets Time replay automatically, as LANDMET does. Nothing else is needed.

## A glacial lake

This gives a case with a before/after Compare view and a lake-size chart. You need at least two NISAR GCOV files from the same track and frame over the lake. Dual-pol (10 m) and quad-pol (20 m) files can be mixed.

1. Download the GCOV `.h5` files into one folder. They can stay outside this project, for example `E:\Claude\DATA`.
2. Copy `processing/configs/lake/tsho-rolpa.json` to a new name. Change `id`, `name`, `track`, `frame`, `direction` and the `lake` block (its position, name and basin). `epsg` is the UTM zone of the files.
3. Run:

```bash
python processing/scripts/prepare_lake.py processing/configs/lake/your-lake.json "E:/Claude/DATA"
```

4. Add the case to `CASES` in `frontend/src/services/manifest.ts`, with `file` set to `your-id.json`.

The lake is the dark area that overlaps the given position. Its area is measured on every date, and the range comes from rerunning with a threshold 1 dB brighter and darker. Compare and Time replay appear on their own.

## What it cannot do yet

Each new case still needs its own manifest for the map layers, written by a script like `prepare_landmet.py`. There is no upload button. Flow replay and What-if flood assume a flow along rivers, so they do not fit data such as wildfires or storms. The limits in [LIMITATIONS.md](LIMITATIONS.md) apply to every event.
