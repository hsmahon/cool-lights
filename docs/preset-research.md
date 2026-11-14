# Preset inspirations and verification limits

Research date: 2026-11-14. These notes guide a small collection of original effects for the two MELK-OA10WCT lamps used by Cool Lights.

## Original six

The selection uses established lighting-effect ideas rather than claiming a ranked list of the world's most popular presets. WLED documents Aurora, Breathe, Candle, and Colorloop effects; Philips Hue explicitly highlights Arctic aurora and Savanna sunset as fan-favorite scenes. Those first-party references make aurora, sunset, rainbow cycles, breathing, and candlelight recognizable starting points. [WLED effects](https://kno.wled.ge/features/effects/), [Philips Hue scene gallery](https://www.philips-hue.com/en-gb/explore-hue/apps/bridge)

| Cool Lights preset | First-party inspiration | Intended interpretation on these lamps |
| --- | --- | --- |
| **Aurora** | WLED's Aurora effect and Aurora palettes; Hue's Arctic aurora scene | Slow changes through green, teal, blue, and violet. |
| **Sunset** | WLED's Sunset palette and Hue's Savanna sunset scene | A warm-to-cool sequence through amber, coral, pink, and purple. |
| **Ocean Drift** | WLED's Ocean palette | Gentle movement among deep blue, teal, and pale aqua. |
| **Rainbow** | WLED's Rainbow palette and Colorloop effect | A continuous color cycle through the spectrum. |
| **Breathe** | WLED's Breathe effect | A smooth, repeating brightness rise and fall using the selected lamp color. |
| **Candle** | WLED's Candle effect | Warm amber with restrained, irregular brightness variation. |

These are original interpretations, not ports of WLED algorithms or reproductions of proprietary Hue scenes. The exact colors, timing, interpolation, and brightness behavior should be chosen for this application and tested on these lamps. No source code or proprietary scene data was copied for this research note.

## Source details

- **WLED effects:** Aurora is described as an aurora-borealis simulation; Breathe fades between colors; Candle resembles candle flicker; Colorloop cycles all LEDs through rainbow colors. These establish the effect concepts, not support for WLED commands on MELK hardware. [Official effect catalog](https://kno.wled.ge/features/effects/)
- **WLED palettes:** Aurora uses greens and dark blue, with a second variant adding pink and blue. Ocean combines blue, teal, and white; Rainbow spans the hues; Sunset combines dark blue with purple, red, and yellow. This research uses those broad color families, not copied palette tables. [Official palette catalog](https://kno.wled.ge/features/palettes/)
- **Philips Hue:** its app page presents Arctic aurora and Savanna sunset as fan favorites. It does not publish the precise RGB stops or animation timing needed to reproduce those scenes, so Cool Lights should not describe its versions as exact Hue presets. [Official Hue app page](https://www.philips-hue.com/en-gb/explore-hue/apps/bridge)

## What is verified on the local hardware

The existing `scripts/server.py` generates one RGB value per lamp with `color_packet`: `7e 07 05 03 RR GG BB 10 ef`, written to characteristic `0000fff3-0000-1000-8000-00805f9b34fb` without response. The project's README records visible color confirmation and operation on both tested lamps. This provides a known path for creating whole-lamp transitions and brightness animations. [Local server](../scripts/server.py), [project hardware notes](../README.md#configure-your-lamps)

The related MELK-OA10 protocol documentation describes native animation modes, but warns that mode mappings vary by hardware. A mode name from that research is not a verified behavior of MELK-OA10WCT. The current work should use the known RGB write path unless a separate, visibly confirmed native-mode test establishes compatibility. [Related controller protocol](https://github.com/wporter82/lotus-lamp-python/blob/main/docs/PROTOCOL.md)

## Product wording and limits

- Call the new collection **animated presets** or **whole-lamp color transitions**.
- A gradient swatch can preview the palette, but it must not imply that several colors will appear simultaneously along one lamp.
- Segment addressing, custom pixel gradients, and a spatial chase within a lamp remain unverified. Sending successive full-lamp RGB values does not establish those capabilities.
- Distinguish a successful Bluetooth write from a visibly confirmed effect. Do not claim a measured optical refresh rate or exact fidelity to another lighting system.
- Keep the user's saved static colors separate from transient animation frames, so stopping an effect can restore them.

No hardware commands were sent as part of this research.

## Expanded gallery

The 24-preset catalog adds Android, Black Hole, Blends, BPM, Chunchun, Colored Bursts, Colorful, DNA, DJ Light, DNA Spiral, Freqwave, PS Vortex, Candy Cane, Halloween, Merry Christmas, Fire 2012, Pacifica, and Plasma. Names and broad concepts come from the [official WLED effect catalog](https://kno.wled.ge/features/effects/). Fire 2012 suggests red/yellow flame flicker; Pacifica suggests gentle ocean waves; Plasma suggests overlapping plasma-like color motion. Cool Lights implements original deterministic whole-lamp versions, not WLED algorithm ports.

PS Vortex is a spatial particle effect in WLED; this app approximates swirling motion with layered hue/brightness cycles and two-lamp phase offsets. It cannot reproduce a 2D vortex on a single uniformly controlled lamp. DNA, Android, Black Hole, and other spatial names likewise describe interpretations over time, not verified segment addressing.

The [retired effects section](https://kno.wled.ge/features/effects/#retired-effects) lists Candy Cane, Halloween, and Merry Christmas as superseded by Chase 2 variants. Our seasonal versions enrich those classic families: red/creamy white with pink/icy blue; orange/violet with green; red/evergreen with gold/warm white. They soften transitions rather than copying pixel chases.

BPM uses a manual tempo. DJ Light and Freqwave use playback-band energy and dominant frequency respectively. A 32 ms NumPy FFT window is refreshed every 20 ms alongside the existing 5 ms bass analyzer. There is no claim of WLED audio fidelity, automatic beat tracking, or optical timing verification.
