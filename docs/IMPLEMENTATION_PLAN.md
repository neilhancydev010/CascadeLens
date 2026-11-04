# Implementation plan

Progress is reported in [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md).

## Done

1. Verified candidate products in the ASF catalogue.
2. Built the processing pipeline, and validated it on real-format samples.
3. Prepared terrain, UNOSAT, Sentinel-1, OSM and boundary layers.
4. Built the application, with a manifest generated from files on disk.
5. Downloaded and processed Pair A GUNW and GOFF, and Pair B GOFF.
6. Analysed them against independent UNOSAT polygons.
7. Added LANDMET as a second case study.
8. Built and acceptance-tested a one-click package.

## Next, in priority order

| Step | Action | Why | Suggested owner |
|---|---|---|---|
| 1 | Add a pre-event control pair, such as 23 Jul→16 Aug, Track 48 | Tests whether the channel is normally low in coherence. About 5 GB | Neilhancy Dev, Abhiyan Bajracharya |
| 2 | Add the Track 98 GUNW, 19→31 Aug | Coherence at the source, which Pair A cannot see | Neilhancy Dev |
| 3 | Send ASF the sign question | Needed before any displacement layer | Abhiyan Bajracharya |
| 4 | Download GCOV | Needs 31 GB; 24 GB is free now | Neilhancy Dev |
| 5 | Rehearse the demonstration | The script is in DEMONSTRATION.md | Sugam Ghimire, Samyak Timalsena |
| 6 | Test on another computer and a physical phone | Only tested here so far | Akash Gurung |

## Team decisions

| Decision | Status |
|---|---|
| Licence | MIT added as a default for code. Change it freely before publishing |
| LANDMET data licence | Not stated in the file. Check before publishing that case |
| Public repository | Not created. A `.git` folder with staged files exists, with no commits or remote |
| Hosting | Not chosen. Needs HTTP Range support |
| Sign question to ASF | Drafted in [SCIENTIFIC_VALIDATION.md](SCIENTIFIC_VALIDATION.md#open-questions), not sent |

Owners follow the suggested responsibilities in the brief. Adjust as needed.

## Fallbacks

- **A product fails QA:** show only what remains usable and explain the rest.
- **Full files cannot be downloaded:** run `--qa-only`, then `prepare_previews.py`, for clearly labelled browse pictures.
