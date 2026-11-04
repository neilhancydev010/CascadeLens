# Architecture decisions

## Starting point

The working folder was empty, with no repository or existing code. Python 3.14 and Node 24 were present, with `asf_search`, `h5py`, `rasterio` and `pyproj` already installed. No Earthdata credentials were found, and that is still the case.

## Decisions

| # | Decision | Reason | Consequence |
|---|---|---|---|
| 1 | Stack as specified: React, Vite, TypeScript, MapLibre, Recharts, Python | Required by the brief | Current major versions: Vite 8, MapLibre 6, geotiff 3 |
| 2 | No backend | COG range reads give real pixel sampling from static files | Needs a host with HTTP Range support |
| 3 | Manifest built from disk state | Status cannot be hardcoded, so the UI cannot overclaim | Run `generate_manifest.py` after processing |
| 4 | Separate sources per frame | Frames are unwrapped independently | A layer can have several tile sets |
| 5 | Inspector reads COG plus validity COG | Value and quality stay separate and retrievable | Two reads per sample |
| 6 | Single processing module, not one script per product | One QA path, less duplicated logic | Differs from the suggested script names |
| 7 | OSM rivers instead of HydroRIVERS | The HOT export was smaller and event-specific | Community data |
| 8 | Place names as DOM markers | Map text needs glyph files, and these are avoided to stay offline | Fine for about two dozen labels |
| 9 | `appType: 'mpa'` in Vite | A missing tile must be 404, not `index.html` | Single entry point only |
| 10 | `setWorkerUrl` for MapLibre | Bundling moves the module that the worker path derives from | One extra asset |
| 11 | CSP on `vite preview` | Makes the offline test enforced rather than observed | Keep it for demonstrations |
| 12 | Story text built from the manifest | The script can never claim an unloaded result | Text has two variants |
| 13 | Synthetic fixture served in a separate Vite mode | Proves the NISAR browser path without touching real assets | Gitignored; a permanent banner is shown |
| 14 | One CRID per run | The catalogue has duplicates under different releases | `crid` in config |
| 15 | Validate against NASA's public sample granules | They are real-format and need no login | Separate test suite, skipped if not fetched |
| 16 | Retry sampling up to three times, reopening the raster | Range reads fail intermittently: 2 of 12 first reads from `vite preview` | Bounded, so a missing file still reports failure |
| 17 | Playwright with the system Edge | Real browser tests with no browser download | Set `channel` differently on other platforms |
| 18 | Sidecar URLs stored in the catalogue | ASF lists exact QA and browse links, so nothing is guessed | Rerun discovery to refresh |
| 19 | `renderable` for colour-only layers | The damage proxy and browse pictures hold no values | The inspector explains why it cannot sample them |
| 21 | Case studies as separate manifests, chosen by a URL parameter | The brief asks for a case selector, and a reload cannot leak state between cases | `?case=landmet-2007` |
| 22 | `serve.py` with the standard library, not `vite preview` | The finished product must run with no `npm install` | Needs Python 3 |
| 23 | Colours relative to each frame's median for phase-like layers | Real frames sit about 50 radians apart | Inspector still shows stored values |
| 24 | Keep real values and classify, even for impossible LANDMET readings | Same rule as NISAR: flag, never alter | Masked in the inspector |
| 25 | Static start-up message inside `#root` | Opening `index.html` directly gave a blank page: browsers block scripts on `file://`. Plain HTML needs no scripts, so it also covers blocked scripts. React replaces it on a normal start | Appears after 2 s, so a normal start never shows it |
| 20 | Configs stored as plain ASCII | Windows default encoding corrupted an en dash once | A test enforces it |

## Adjustments to the suggested structure

- `processing/src/cascade_lens` uses flat modules (`nisar`, `quality`, `export`, `pipeline`, `manifest`, `discovery`) instead of nested folders.
- `process_nisar.py` replaces the separate extract, mask, clip and tile scripts.
- `prepare_context.py` covers vectors, terrain and the damage proxy.
- `frontend/e2e` was added for browser tests.
- Empty `data/` subfolders were not created ahead of use.

## Environment note

On Windows, native libraries failed to load inside a virtual environment under a very long path. The session folder exceeded the 260-character limit, so the environment was created at a short path. Keep the project at a short path.
