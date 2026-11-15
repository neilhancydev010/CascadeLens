# Data sources

Every source keeps its own identity in the app. Only NISAR layers are NISAR results.

## NISAR GUNW, GOFF, GCOV, GSLC

| | |
|---|---|
| Provider | NASA/JPL and ISRO; distributed by ASF DAAC |
| Product types | L2 geocoded unwrapped interferogram, pixel offsets, covariance, SLC |
| Source | [ASF](https://search.asf.alaska.edu), collections `NISAR_L2_*_PROVISIONAL_V1` |
| Dates | See [DATA_ACQUISITION.md](DATA_ACQUISITION.md) |
| Maturity | PROVISIONAL (CRID P05023), calibrated and partly validated, per ASF |
| Limitations | NASA's general maturity definition says Provisional products are not intended for scientific research. [ASF known issues](https://nisar-docs.asf.alaska.edu/provisional-known-issues/) |
| Status here | Pair A GUNW and GOFF, Pair B GUNW and GOFF, and five-pair GUNW series on Track 48 and Track 98: real measurements. GCOV: Tsho Rolpa only; Rasuwa catalogue records only |
| Attribution | NASA/JPL-Caltech/ISRO, NISAR; distributed by ASF DAAC |

## UNOSAT event layers

| | |
|---|---|
| Provider | UNOSAT / UNITAR |
| Dataset | [Mudflow/Rockflow Impact Assessment in Rasuwa & Nuwakot](https://data.humdata.org/dataset/mudflow-rockflow-impact-assessment-in-rasuwa-nuwakot-districts-bagmati-province-nepal-as-o), event FL20260826NPL |
| Layers used | Mudflow extent, analysis extent, barrier lakes, detachment zone, affected roads, affected structures |
| Sensors | Multi-sensor; Cartosat-3 for lakes; Landsat-9 for detachment zone |
| Dates | 26–28 August 2026 |
| Type | Derived reference map, EPSG:4326 |
| Licence | CC BY-SA |
| Limitations | `FieldValidation = 0`, "Not yet field validated", in the source's own coded domain |
| Attributes kept | `SiteID`, `SensorDate`, `SensorID`, `ConfidenceID`, `FieldValidation`, `Settlement_Name`, `Notes`, `Main_Damage_Site_Class`, `Grouped_Damage_Classes`, `EventCode`, `ImageID_Num`; for roads `SourceID`, `RoadID`, `ONme`, `RteNme`, `FClass`, `OpStatus`. `StaffID` is left out |

Source issues found and how they are handled:

| Issue | Handling |
|---|---|
| Detachment layer name says 26 August; its `SensorDate` says 26 September | Shown as unresolved in the app |
| Flood `Area_ha` duplicates `Area_m2` | Ignored. 64.91 km² computed in UTM 45N |
| Affected road geometry has stray vertices near 29°E, 9°N | Clipped to the UNOSAT analysis extent |
| Press figure of about 30 km² versus 64.91 km² here | Not reconciled; the published scopes may differ |
| HDX lists both products at the same geodatabase | Verified identical by SHA-256; used once |

## Copernicus DEM GLO-30

| | |
|---|---|
| Provider | ESA / Copernicus |
| Source | [AWS Open Data](https://registry.opendata.aws/copernicus-dem/), four 1° tiles |
| Type | Digital surface model, 1 arcsecond, EPSG:4326, about 30 m |
| Dates | Source campaign 2011–2015 |
| Attribution | © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA |
| Limitations | Pre-event. Clipped to the search envelope, so terrain stops at its edge |
| Usage | Elevation layer, inspector and hillshade background |

## OpenStreetMap

| | |
|---|---|
| Provider | OpenStreetMap contributors, via [HOT export on HDX](https://data.humdata.org/dataset/hot_flood_npl) |
| Layers used | Rivers and streams, roads, populated places |
| Type | Contextual, EPSG:4326 |
| Licence | ODbL, © OpenStreetMap contributors |
| Limitations | Community data; features may predate or postdate the event. HydroRIVERS was not needed |
| Attributes kept | OSM `id` (for example `way/345313941`) on every feature; roads also keep `highway`, `name`, `name_en`, `bridge`, `layer` and `surface`. The export has no `tunnel` tag |

## HOT post-event mapping and bridge reports

| | |
|---|---|
| Provider | Humanitarian OpenStreetMap Team, [HOT export on HDX](https://data.humdata.org/dataset/hot_flood_npl) |
| Layers used | Health facilities, education facilities, helipads, destroyed and damaged features (OSM), and the volunteer bridge damage assessment |
| Type | Contextual and reported, EPSG:4326 |
| Licence | ODbL, © OpenStreetMap contributors |
| Limitations | Volunteer reports and mapping, not field verified here. The bridge assessment gives points with a status (washed out, damaged, intact) and no link to OSM, so CascadeLens matches each to the nearest OSM bridge within 60 m and leaves the rest unused |

## NASA Global Landslide Catalog, Nepal subset

| | |
|---|---|
| Provider | NASA Goddard Space Flight Center, [Global Landslide Catalog Export](https://data.nasa.gov/dataset/global-landslide-catalog-export) |
| Used as | Readiness dataset C1 (dated landslide inventory); no model is fitted to it |
| Content | 481 Nepal events, 2007-03-21 to 2016-10-13, in `data/reference/hazard/nasa-glc/glc_nepal.csv` |
| Licence | Not stated on data.nasa.gov; NASA-produced. The readiness engine marks the licence as not established |
| Limitations | Compiled from media and reports, so unrecorded places are not confirmed negatives. Only 29 locations are exact or within 1 km; most are within 5 to 50 km |

## Sentinel-1 damage proxy map

| | |
|---|---|
| Provider | Earth Observatory of Singapore, Remote Sensing Lab (EOS-RS) |
| Dataset | [Nepal Flood Glacial: Damage Proxy Map, Aug 2026](https://data.humdata.org/dataset/nepal-damage-proxy-map-glacial-flood-aug-2026), v0.9 |
| Mission | Copernicus Sentinel-1, not NISAR |
| Dates | Before: 5 May to 16 August 2026. During: 28 August 2026 |
| Type | Derived product, RGBA GeoTIFF, about 30 m, EPSG:4326 |
| Licence | CC BY |
| Attribution | EOS-RS. Contains modified Copernicus Sentinel data (2026), processed by ESA |
| Limitations | Preliminary guidance. Less reliable over vegetated or mountainous areas; scattered pixels may be false positives; no colour does not mean no damage |
| Usage | Map layer only. The file holds colours, not values, so the inspector does not sample it |

## Sentinel-1 change screening

| | |
|---|---|
| Provider | IMPACT Initiatives / REACH |
| Dataset | [Nepal Flash Flood: Damage Assessment using Sentinel-1 Radar](https://data.humdata.org/dataset/nepal-flash-flood-damage-assessment-using-sentinel-1-radar-data), v3 |
| Dates | Baseline August 2025 to August 2026; post-event 28 August 2026 |
| Type | Derived polygons, 753 high-confidence features |
| Licence | CC BY |
| Limitations | Measures backscatter change, not structural damage. Only assessed around pre-event built areas |

## District boundaries

| | |
|---|---|
| Provider | Survey Department of Nepal and UN RCO, via [OCHA COD-AB](https://data.humdata.org/dataset/cod-ab-npl) |
| Type | Contextual. District (admin 2) outlines clipped to the search envelope |
| Licence | CC BY-IGO |

## GPM IMERG Late daily rainfall

| | |
|---|---|
| Provider | NASA GES DISC |
| Dataset | GPM IMERG Late Precipitation L3 1 day 0.1° V07 (`GPM_3IMERGDL.07`), DOI [10.5067/GPM/IMERGDL/DAY/07](https://doi.org/10.5067/GPM/IMERGDL/DAY/07) |
| Retrieved | 13 November 2026, by OPeNDAP subset of 84.0–86.5° E, 27.5–29.5° N (`fetch_imerg.py`), with an Earthdata Login token |
| Coverage | 1 June 2016 to 31 October 2026, every UTC day, 20 × 25 cells of 0.1° |
| Stored | `data/reference/rainfall/GPM_3IMERGDL.07`: one GeoTIFF per year, mean rate in mm/h (× 24 for the day's total), the valid half-hour count per day, and `days.csv` with each day's file version and publication time (`prepare_rainfall.py`) |
| Why Late, not Final | Late is what a warning could have used on the day: it appears about 14 h after the UTC day ends. Final is gauge-adjusted but appears about 3.5 months later, and in November 2026 it stops at September 2025 |
| Licence | NASA open data, no restrictions on reuse; cite the DOI |
| Limitations | Satellite estimate at about 11 km, with no gauge adjustment in the Late run. History is the V07 reprocessing, not what was issued at the time. Days are UTC; Nepal is UTC+5:45 |
| Used for | Datasets B1 and C5 of the readiness engine, and the rainfall-trigger threshold run ([MODELS.md](MODELS.md)) |

## BIPAD landslide incidents

| | |
|---|---|
| Provider | National Disaster Risk Reduction and Management Authority (NDRRMA), Government of Nepal, through the [BIPAD portal](https://bipadportal.gov.np) |
| Dataset | Incident records, hazard "Landslide", from the public API (`fetch_bipad.py`): 6,672 incidents, 14 May 2011 to 11 November 2026, retrieved 13 November 2026 |
| Location | Each record's point is BIPAD's reference point for a ward or municipality, not the landslide. In the Trishuli area, 1,826 reports share 431 points |
| Licence | **Not stated.** No licence or terms of reuse were found on the portal or its API (13 November 2026). The records are kept under `data/raw` (not committed), and the readiness engine marks the licence as not established until NDRRMA confirms terms |
| Limitations | Reports, not a mapped inventory: a day without a report is not a day without a landslide. Reporting grew strongly (57 reports in the Trishuli area in 2016, 293 in 2024, 531 in 2026), so years are not comparable. Records before 2020 were backfilled |
| Used for | Dataset C1 and the rainfall-trigger threshold run |

## Checked and not used

| Source | What it is | Why not used |
|---|---|---|
| Durham University 3 × 3 km landslide grid ([Zenodo 22709999](https://doi.org/10.5281/zenodo.22709999), CC BY 4.0) | Active landslide cells per 3 km cell each year, 2000 to 2021, all Nepal | No dates within a year, so it cannot pair landslides with rainfall. Ends in 2021, before the readiness window closes. A candidate for a coarse susceptibility model once a geological map exists |
| USGS geologic map of South Asia ([OFR 97-470C](https://doi.org/10.3133/ofr97470C), public domain) | Generalised geology from UNESCO 1:5 M and 1:10 M maps | Its own use constraint: "not intended to be used at a scale of larger than 1:5,000,000". Far too coarse for a 100 km corridor, so L1 still waits for the DMG Nepal map |
| DHM river and rainfall observations ([hydrology.gov.np](https://hydrology.gov.np)) | Station list is public; Trishuli River at Betrawati is station 4783 | The observation API answers "Permission denied or Api Keys required". Needs a key from DHM |
| NASA Global Landslide Catalog, COOLR | Point inventory | The catalogue ends in October 2016 (already registered as C1, not fit). The COOLR map server did not answer from this environment |

## LANDMET, test case only

| | |
|---|---|
| Provider | W. B. Rossow, City College of New York NOAA/CREST |
| Dataset | Land Surface Atmospheric Boundary Interaction Product L3 v1, DOI [10.5067/MEASURES/LANDMET/DATA001](https://doi.org/10.5067/MEASURES/LANDMET/DATA001) |
| File | `landmet_L3_20071231_v1.nc`, supplied by the project owner |
| Coverage | Global land, 31 December 2007, 8 three-hourly steps, equal-area cells of about 110 km |
| Sources within it | ISCCP FD, ISCCP NNHIRS, Integrated Surface Database stations, TMPA and GPCP |
| Usage | A test of the product. Not NISAR data, and unrelated to the 2026 event |
| Licence | Not stated in the file. Check before publishing this case |
| Quality notes | 7 listed variables are entirely fill. Some valid ranges are swapped. Some variables use `scale` instead of `scale_factor`. Values include 118.6 m/s wind and 150 percent humidity |

## NISAR sample products, software testing only

| | |
|---|---|
| Provider | NASA/JPL, [sample data page](https://science.nasa.gov/mission/nisar/sample-data/) |
| Scene | 2008 ALOS-derived pair over California, CRID D00404 |
| Usage | Reader and pipeline validation. Never part of the shipped app, and shown only under a banner saying they are not Rasuwa data |

## Event narrative

The story uses reported facts only and marks them as reported: [ADRC report](https://www.adrc.asia/publications/disaster_report/pdf/2026/ADRC_FL_NPL_Rasuwa_20260826_EN.pdf), [SPF analysis](https://www.spf.org/opri/en/global-data/The_Langtang_Collapse.pdf). These sources differ on the origin of the event, so the story does not name one precise source.

## Specifications

- [GUNW JPL D-102272 Rev E](https://nisar.asf.earthdatacloud.nasa.gov/NISAR-SAMPLE-DATA/DOCS/NISAR_D-102272_RevE_NASA_SDS_Product_Specification_L2_GUNW_Nov8_2024_w-sigs.pdf)
- [GOFF JPL D-105010 Rev C](https://nisar.asf.earthdatacloud.nasa.gov/NISAR-SAMPLE-DATA/DOCS/NISAR_D-105010_RevC_NASA_SDS_Product_Specification_L2_GOFF_Nov8_2024_w-sigs.pdf)
- [GCOV JPL D-102274 Rev E](https://nisar.asf.earthdatacloud.nasa.gov/NISAR-SAMPLE-DATA/DOCS/NISAR_D-102274_RevE_NASA_SDS_Product_Specification_L2_GCOV_Nov8_2024_w-sigs.pdf)
- [L1 and L2 ATBD JPL D-95677](https://nisar.asf.earthdatacloud.nasa.gov/NISAR-SAMPLE-DATA/DOCS/NISAR_D-95677_NASA_L1_L2_ATBD_20231112_R3.4_w-sigs.pdf)
