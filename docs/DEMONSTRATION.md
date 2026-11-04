# Demonstration

> Real NISAR measurements are loaded. Nothing below claims displacement, or a cause.

## Launch

Unzip `CascadeLens.zip` to a short path, then double-click **Start CascadeLens.bat**. Do not open `index.html` directly: it cannot start that way. It needs Python 3 and no internet connection. The browser refuses all external requests, so the demo cannot depend on the network.

## Script (about 2 minutes 45 seconds)

**0:00 The problem.** After a mountain disaster, evidence is scattered and radar data is hard to read. CascadeLens puts NISAR measurements in one place, with their quality and limits visible.

**0:25 The source.** Start the guided story. Show the UNOSAT detachment zone. Point out the honest finding: Pair A has no measurement here, because it falls in a swath gap. The story then shows that Pair B, viewing from the other side, does reach it, and that image matching largely fails there.

**0:55 Interferometric evidence.** Choose *Bhote Koshi corridor* and Coherence. Show the dark ribbon along the river under the UNOSAT extent. Median coherence is 0.19 inside against 0.46 nearby, and frame 75 agrees. Say clearly that this agrees with independent mapping, but it is not proof.

**1:20 The ionosphere.** Show raw phase, then Phase with ionosphere screen removed. The broad stripes vanish: they were atmosphere, not ground. That is why phase is not displacement.

**1:40 Pixel offsets.** Open the Pixel offsets tab at the same place. Offsets are a different measurement, and they show no large coherent shift. Reporting that is part of being honest.

**1:55 Independent evidence.** Turn on the Sentinel-1 damage proxy. Explain that it is a different mission, and only a picture, so it cannot be sampled.

**2:15 Inspect.** Open the Inspector and read a stored value, with its pixel, quality and source granule.

**2:30 Close.** CascadeLens makes advanced NISAR evidence understandable and inspectable. It does not predict disasters or replace field investigation.

**If there is time.** Switch the Case study menu to the LANDMET test. It is a completely different global weather dataset, which shows the product is not tied to one file. Say clearly that it is not NISAR and not Rasuwa.

## Known demonstration limitations

- GCOV snapshots are not downloaded, so that tab shows *Download required*.
- All NISAR products are Provisional.
- Terrain stops at the search envelope.
- Keep the browser window in front: browsers pause map drawing in hidden windows.

## Evaluation questions

### Why NISAR instead of simply using Sentinel-1?

CascadeLens is built for NISAR's repeat-pass L-band observations and higher-level products. GUNW and GOFF offer two different kinds of radar measurement of the same event. Sentinel-1 analyses are included as independent context, and they are identified separately.

### How can you prove that the movement you display is real?

We don't display movement. We display phase, coherence and pixel offsets, each with quality information. We mask what the product marks as unreliable, and we show what cannot be measured, such as the swath gap at the source. Low coherence along the channel agrees with independent UNOSAT mapping, but it is evidence, not proof. We have not yet compared a pre-event pair, and that is the proper next test.

### Can CascadeLens predict another landslide or flood in Nepal?

No. It is an observation and investigation tool, not a validated early-warning system. Forecasting would need rainfall, terrain, geological, hydrological and ground data, with calibrated and independently validated methods.
