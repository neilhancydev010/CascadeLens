# Data acquisition

## Earthdata registration

1. Create a free account at https://urs.earthdata.nasa.gov.
2. Sign in to [ASF Vertex](https://search.asf.alaska.edu) once and accept the ASF EULA when asked.
3. Choose one credential method below. Keep credentials out of the repository.

**Token.** Generate one in your Earthdata profile, then set it in your shell:

```bash
export EARTHDATA_TOKEN=your-token-here
```

On Windows PowerShell, use `$env:EARTHDATA_TOKEN = "your-token-here"`.

**netrc.** Create `~/.netrc` (`C:\Users\<you>\_netrc` on Windows) containing:

```text
machine urs.earthdata.nasa.gov login YOUR_USERNAME password YOUR_PASSWORD
```

## Product discovery

Catalogue search is public and needs no login:

```bash
python processing/scripts/discover_products.py
```

It searches 1 August to 1 October 2026 over `[84.3976, 27.7320, 85.5508, 28.3500]` and writes `data/metadata/catalogue.json`, including each frame's footprint.

## Candidate observations: verified against the catalogue

All of these exist as PROVISIONAL records. A catalogue record does not prove the science content is usable.

| Group | Product | Dates | Orbit | Track | Frames | Size |
|---|---|---|---|---|---|---|
| Pair A | GUNW, GOFF | 2026-08-16 → 08-28 | Descending | 48 | 74, 75 | 7.0 GB |
| Pair B | GOFF | 2026-08-19 → 08-31 | Ascending | 98 | 15, 16 | 2.2 GB |
| Snapshot | GCOV | 2026-08-28 | Descending | 48 | 74, 75 | 16.9 GB |
| Snapshot | GCOV | 2026-08-31 | Ascending | 98 | 15, 16 | 14.2 GB |

Footprint coverage of each bookmark, from catalogue polygons. This describes frame extent, not valid pixels.

| Group | Source | Bhote Koshi | Trishuli | Search envelope |
|---|---|---|---|---|
| Pair A | 100% | 100% | 80% | 81% |
| Pair B | 100% | 100% | 100% | 100% |
| GCOV 28 Aug | 100% | 100% | 76% | 78% |
| GCOV 31 Aug | 100% | 100% | 100% | 100% |

Other findings:

- GUNW also exists for the Track 98 pair, though the brief only lists GOFF there.
- Tracks 26 and 149 have further pairs around the event, as a fallback if a primary pair fails QA.
- Track 98 frame 16 has two releases, `P05023` and `X05026`. The pipeline uses `P05023` only, so releases are never mixed.

## What has been downloaded

Pair A GUNW and GOFF, and Pair B GOFF, all at their catalogue sizes. GCOV is not downloaded: it needs 31 GB.

## Download procedure

Check the selection first:

```bash
python processing/scripts/download_products.py --dry-run
```

Then fetch only each granule's QA summary, QA report and browse picture, a few MB in total:

```bash
python processing/scripts/download_products.py --qa-only
```

This proves the login works, and writes NISAR's own QA results to `data/qa/precheck.md`. A failed check needs reading, not automatic rejection: the public samples fail the `identification` check and still read correctly.

Then download. The default is GUNW and GOFF, 9.2 GB:

```bash
python processing/scripts/download_products.py
```

Add GCOV separately, at 31 GB:

```bash
python processing/scripts/download_products.py --products GCOV
```

Files go to `data/raw/nisar`, which is gitignored. Then:

```bash
python processing/scripts/process_nisar.py
```

```bash
python processing/scripts/generate_manifest.py
```

## If full files cannot be downloaded

After `--qa-only`, this turns the browse pictures into clearly labelled map previews. They cannot be sampled.

```bash
python processing/scripts/prepare_previews.py
```

```bash
python processing/scripts/generate_manifest.py
```

## Public sample files

These need no login and are not Rasuwa data. They test the code against the real format.

```bash
python processing/scripts/fetch_samples.py
```

## Data directories

| Path | Contents | In git |
|---|---|---|
| `data/raw/nisar` | Original HDF5 granules, QA sidecars in `qa/` | No |
| `data/raw/samples` | NASA public sample granules | No |
| `data/raw/context` | Original reference downloads | No |
| `data/processed` | Clipped native-grid rasters | No |
| `data/qa` | Inspection reports | Yes |
| `data/metadata` | Catalogue, granule state, layer fragments | Yes |
| `frontend/public/data` | Prepared browser assets | Yes |

## Common access errors

| Symptom | Cause | Fix |
|---|---|---|
| HTTP 401 from `urs.earthdata.nasa.gov` | No or wrong credentials | Check the token or netrc entry |
| Login succeeds but download is refused | EULA not accepted | Sign in to Vertex and accept it |
| `No Earthdata credentials found` | Neither method is set | Follow the steps above |
| `Could not load DLL` or `filename too long` on Windows | Project path too long | Move the project to a short path |
