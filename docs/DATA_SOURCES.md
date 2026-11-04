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
| Status here | Pair A GUNW and GOFF, Pair B GOFF: real measurements. GCOV: catalogue records only |
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
