# Demonstration

> Real NISAR measurements are loaded. Nothing below claims displacement, or a cause.

## Launch

Unzip `CascadeLens.zip` to a short path, then double-click **Start CascadeLens.bat**. Do not open `index.html` directly: it cannot start that way. It needs no internet connection, and on Windows nothing installed: without Python 3, the launcher uses Windows' own PowerShell. The browser refuses all external requests, so the demo cannot depend on the network.

## Script (about 2 minutes 45 seconds)

**0:00 The problem.** After a mountain disaster, evidence is scattered and radar data is hard to read. CascadeLens puts NISAR measurements in one place, with their quality and limits visible.

**0:25 The source.** Start the guided story. Show the UNOSAT detachment zone. Point out the honest finding: Pair A holds no usable measurement here. The radar product's own quality mask marks the whole zone as having no valid subswath in the 28 August acquisition, a gap in that acquisition's coverage. Then switch the pair to 19–31 August (Track 98, the opposite side): coherence there is very low, 0.09 against 0.46 nearby. Say that low coherence is what a heavily changed surface can look like, but steep slopes and snow lower it too. The story then shows that Pair B, viewing from the other side, does reach it, and that image matching largely fails there.

**0:55 Interferometric evidence.** Choose *Bhote Koshi corridor* and Coherence. Show the dark ribbon along the river under the UNOSAT extent. Median coherence is 0.19 inside against 0.46 nearby, and frame 75 agrees. Say clearly that this agrees with independent mapping, but it is not proof.

**1:20 The ionosphere.** Show raw phase, then Phase with ionosphere screen removed. The broad stripes vanish: they were atmosphere, not ground. That is why phase is not displacement.

**1:40 Pixel offsets.** Open the Pixel offsets tab at the same place. Offsets are a different measurement, and they show no large coherent shift. Reporting that is part of being honest.

**1:55 Independent evidence.** Turn on the Sentinel-1 damage proxy. Explain that it is a different mission, and only a picture, so it cannot be sampled.

**2:15 Inspect.** Open the Inspector and read a stored value, with its pixel, quality and source granule.

**2:30 Close.** CascadeLens makes advanced NISAR evidence understandable and inspectable. It does not predict disasters or replace field investigation.

**If there is time.** Switch the Case study menu to the Tsho Rolpa glacial lake. NISAR GCOV on four dates, through the monsoon, shows that the lake did not change size. Do not say the dam or the glacier moved or stayed still: the app shows where the surface stayed the same (coherence), not how far anything moved.

## Known demonstration limitations

- The observability figures were rebuilt on 13 November 2026 with the product's quality mask, over frames 74 and 75. Do not quote figures from before that date: the first method ignored the mask and was withdrawn.
- Present the before/after comparison as consistent with surface change, not as proof of cause. The two pairs differ in length and radar mode.
- 14% of the mapped mudflow and 18% of the Trishuli corridor lie outside both frames, so the radar says nothing there.
- Rasuwa GCOV snapshots are not downloaded, so that tab shows *Download required*.
- Keep the Illustrations group (What if, Simulate) out of the main script. They rest on assumed inputs: breach depths, an invented flow speed, a height-above-river rule. If a judge asks, open them as labelled illustrations, not results.
- All NISAR products are Provisional.
- Terrain stops at the search envelope.
- Keep the browser window in front: browsers pause map drawing in hidden windows.

## Evaluation questions

### Why NISAR instead of simply using Sentinel-1?

CascadeLens is built for NISAR's repeat-pass L-band observations and higher-level products. GUNW and GOFF offer two different kinds of radar measurement of the same event. Sentinel-1 analyses are included as independent context, and they are identified separately.

### How can you prove that the movement you display is real?

We don't display movement. We display phase, coherence and pixel offsets, each with quality information. We mask what the product marks as unreliable, and we show what cannot be measured, such as the masked ground at the source. Low coherence along the channel agrees with independent UNOSAT mapping, but it is evidence, not proof. Against a pair from before the event, coherence fell inside the mapped area (median 0.38 to 0.19) while the ground around it rose (0.40 to 0.50), which is consistent with surface change there. That comparison is indicative, because the pair before is longer and was acquired in a different radar mode. A like-for-like pre-event pair is the proper next test.

### Can CascadeLens predict another landslide or flood in Nepal?

No. It is an observation and investigation tool, not a validated early-warning system. Forecasting would need rainfall, terrain, geological, hydrological and ground data, with calibrated and independently validated methods.
