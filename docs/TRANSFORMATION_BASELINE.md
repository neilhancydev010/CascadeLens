# Transformation baseline

Recorded on 14 November 2026, before any change made under the transformation brief. It describes the checkout as it really was, what ran, what could not run, and what to build first.

## 1. Checkout

| Item | Value |
|---|---|
| Repository | `Ak-Gurung09/cascade-lens` |
| Base commit | `841684ac` (Merge pull request #8), equal to `origin/main` on 14 Nov 2026 |
| Working branch | `claude/jovial-raman-291b9a`, cut from that commit, clean working tree |
| Corrective PRs #6, #7, #8, #9 | All merged into this commit (#9 is an ancestor of #8's merge) |
| PR #4 (older Track 98 branch) | Not merged, conflicts with `main`, not used |
| Frontend | `frontend/`: React 19, Vite, MapLibre, static assets in `frontend/public/data` (362 MB) |
| Processing | `processing/src/cascade_lens` (Python), scripts in `processing/scripts`, configs in `processing/configs` |
| Offline package | `product/` (launcher scripts and `serve.py`) |
| CI | `.github/workflows/ci.yml`: type check, unit tests, build, Python tests, browser tests |

**Raw data on this machine:** `data/` holds 7.2 MB of granule metadata, QA inspection JSON and references only. No raw NISAR HDF5 granule, no NASA sample file and no LANDMET file is present. Nothing was downloaded for this baseline.

## 2. Checks that ran

| Check | Command | Result |
|---|---|---|
| Python tests | `python -m pytest tests -q -rs` (Python 3.14 venv with `processing/requirements.txt`) | **173 passed, 35 skipped**, 0 failed (88 s) |
| Type check | `npm run typecheck` | Passed |
| Frontend unit tests | `npm test` | **103 passed** in 16 files |
| Production build | `npm run build` | Passed. `dist/` is 365 MB, mostly the shipped data. Largest script chunk: MapView, 1.09 MB (295 kB gzip) |
| Browser tests, synthetic fixture | `npx playwright test` (Brave via `CL_BROWSER_PATH`) | **10 passed** |
| Browser tests, real build | same, with `CL_BASE_URL` pointing at this checkout's `vite preview` | **23 passed** |

Linting: the project has no lint script, so none ran.

### Skipped tests, and why

| Tests | Count | Reason |
|---|---|---|
| `tests/integration/test_real_format.py` | 14 | NASA sample products not fetched (`processing/scripts/fetch_samples.py`) |
| `tests/integration/test_rasuwa_data.py` | 9 | Rasuwa granules not downloaded |
| `tests/processing/test_landmet.py` | 6 | LANDMET file not in `data/raw/landmet` |
| Others | 6 | Same missing-data reasons, reported by pytest `-rs` |

These are tests that **could not run because data is missing**. They are not counted as passed.

### A false failure worth knowing about

The first browser run reported 8 failures. They were not defects in this checkout. Playwright reuses any server already on port 4173, and an older copy of the app (`~/Projects/cascade-lens/frontend`) was running there. That copy still shows the withdrawn 66% headline. Run against this checkout's own build, all 23 real-build tests pass. To avoid this, test with `CL_BASE_URL` set to a fresh port, or stop the other server first.

Warnings: 65 Python warnings, almost all a rasterio deprecation (`*` vs `@` on transforms) and simulation-test warnings. None of them changes a result.

## 3. Scientific state at baseline

| Topic | State |
|---|---|
| Product mask in observability | Applied (method version 2, `observability.py`). A product without its mask is refused. The 32-bit mask is decoded from its low byte (`quality.decode_gunw_mask`) |
| Disturbance vs movement | Separate tasks with separate rules (`classify`) |
| Reason flags | Outside frame, no data, masked, layover, shadow, low coherence, no components, low baseline, geometry unknown, baseline no data, kept as separate bits |
| 66% Rasuwa figure | Withdrawn everywhere. The UI withholds any observability block older than version 2 |
| Water flag | Treated as unusable for every task. The brief asks for a rule that depends on the task (open) |
| NASA `identification` QA check | Fails on every granule, and on NASA's public samples. Cause unknown. Disclosed in `docs/SCIENTIFIC_VALIDATION.md` |
| Status vocabulary | `status.json` uses COMPLETE AND TESTED / EXPERIMENTAL / BLOCKED / PLANNED. 11 capabilities carry the top label |
| Claims register | `frontend/public/data/claims.json`, 30 claims (5 GREEN, 15 AMBER, 10 RED) |

## 4. Gaps against the brief, in build order

1. **Field verification workspace** (brief §8): missing. Road stretches already have stable IDs and a "what to verify next" list, but there are no records, statuses, queue, human notes or record exports.
2. **Evidence gap → next observation** (brief §7.3): missing. The per-spot observability reasons exist and can feed it.
3. **Evidence register** (brief §5): partial. `claims.json` needs the full record and the brief's status words.
4. **Rasuwa date-by-date view with compatibility checks** (brief §6): partial. Tsho Rolpa is in good shape.
5. **Four-stage first minute** (brief §11): partial.
6. **Documentation deliverables** (brief §18): only this baseline exists so far.
7. **Smaller science items:** task-dependent water rule, more control regions, independent lake-outline check if a reference exists.
8. **Global coverage explorer** (brief §10): last, and only as a catalogue snapshot.
