"""Original whole-lamp interpretations of familiar lighting effects."""
import colorsys
import math

PRESETS = {
    "aurora": {"name": "Aurora", "description": "Slow green, teal, blue, and violet transitions", "palette": ["#19E6A1", "#18AFC9", "#2848B8", "#A35CE0"], "period": 24},
    "sunset": {"name": "Sunset", "description": "Amber, coral, pink, and twilight violet", "palette": ["#FFAE45", "#FF6249", "#DF458E", "#6D42AF"], "period": 32},
    "ocean": {"name": "Ocean Drift", "description": "Blue and teal with a gentle wave of brightness", "palette": ["#133C97", "#087FB0", "#24C8BA", "#A3E1E8"], "period": 20},
    "rainbow": {"name": "Rainbow", "description": "A smooth full-hue color cycle", "palette": ["#FF4444", "#FFD740", "#43DE86", "#4E8AFF", "#CD55FF"], "period": 18},
    "breathe": {"name": "Breathe", "description": "Your selected color gently fades up and down", "palette": ["#303042", "#B7BAFF"], "period": 6},
    "candle": {"name": "Candle", "description": "Warm amber with soft, irregular flame-like variation", "palette": ["#C44A12", "#FFAE45"], "period": 12},
}


# Palette and timing choices are original whole-lamp adaptations.
PRESETS['android'] = {'name': 'Android', 'description': 'Traveling pulses with a shifting colorful tail', 'palette': ['#33FF66', '#19BDB0', '#6555FF'], 'period': 5}
PRESETS['black-hole'] = {'name': 'Black Hole', 'description': 'Deep blue and violet with soft white highlights', 'palette': ['#03051A', '#281066', '#571CA8', '#CCD8FF'], 'period': 16}
PRESETS['blends'] = {'name': 'Blends', 'description': 'Independently phased flowing color blends', 'palette': ['#FF568B', '#FFBE56', '#36D3BE', '#7165EB'], 'period': 13}
PRESETS['bpm'] = {'name': 'BPM', 'description': 'Palette pulses at your chosen tempo', 'palette': ['#EE287D', '#734CEE', '#24D9C6', '#FFD45E'], 'period': 12}
PRESETS['chunchun'] = {'name': 'Chunchun', 'description': 'Clusters of soft colorful pulses', 'palette': ['#F494BC', '#86DAD5', '#B49BF1'], 'period': 9}
PRESETS['colored-bursts'] = {'name': 'Colored Bursts', 'description': 'Rising and decaying bursts of changing hues', 'palette': ['#FF5378', '#56CFF5', '#FFCD57', '#B35EFF'], 'period': 8}
PRESETS['colorful'] = {'name': 'Colorful', 'description': 'Softened red, amber, green and blue sequence', 'palette': ['#EF394F', '#FFB83F', '#38D273', '#3989ED'], 'period': 10}
PRESETS['dna'] = {'name': 'DNA', 'description': 'Complementary colors with opposing brightness waves', 'palette': ['#19C9E8', '#EE4279'], 'period': 7}
PRESETS['dj-light'] = {'name': 'DJ Light', 'description': 'Playback bass, mids and treble mix the colors', 'palette': ['#FF4040', '#40FF60', '#4060FF'], 'period': 8}
PRESETS['dna-spiral'] = {'name': 'DNA Spiral', 'description': 'Rotating complementary hues and crossing pulses', 'palette': ['#ED49B1', '#36DDA0', '#6782FF'], 'period': 11}
PRESETS['freqwave'] = {'name': 'Freqwave', 'description': 'Playback frequency steers hue; energy drives brightness', 'palette': ['#FF5B41', '#4BDB98', '#7164EF'], 'period': 10}
PRESETS['ps-vortex'] = {'name': 'PS Vortex', 'description': 'Layered color and brightness cycles suggest a swirl', 'palette': ['#7526DA', '#18BFCF', '#F169AC'], 'period': 14}
PRESETS['candy-cane'] = {'name': 'Candy Cane', 'description': 'Red and creamy white with pink and icy blue', 'palette': ['#F02A48', '#FFF1DD', '#F49EC3', '#9DDFEF'], 'period': 12}
PRESETS['halloween'] = {'name': 'Halloween', 'description': 'Orange and violet with eerie green accents', 'palette': ['#FF6C18', '#6022AE', '#8CBF28', '#2F124F'], 'period': 15}
PRESETS['merry-christmas'] = {'name': 'Merry Christmas', 'description': 'Red and evergreen with gold and warm white', 'palette': ['#D92636', '#176B3A', '#F9BB49', '#FFF0CB'], 'period': 18}
PRESETS['fire-2012'] = {'name': 'Fire 2012', 'description': 'Red embers, orange flames and golden peaks', 'palette': ['#9F1605', '#F54D0C', '#FFB52B'], 'period': 6}
PRESETS['pacifica'] = {'name': 'Pacifica', 'description': 'Layered slow ocean waves with pale highlights', 'palette': ['#041B4B', '#075D89', '#11999A', '#8BD5CA'], 'period': 30}
PRESETS['plasma'] = {'name': 'Plasma', 'description': 'Overlapping oscillations of hue and brightness', 'palette': ['#F244B0', '#6844E8', '#23C8DD', '#F79941'], 'period': 10}


def catalog():
    return [{"id": key, "name": value["name"], "description": value["description"],
             "palette": value["palette"], "audio": key in {"dj-light", "freqwave"}, "tempo": key == "bpm"} for key, value in PRESETS.items()]


def frame(preset, elapsed, base_color, offset=0.0, speed=1.0, brightness=0.7, bpm=120, audio=None):
    """Return one RGB hex color; never claim this is an addressable-LED frame."""
    definition = PRESETS[preset]
    phase = elapsed * speed / definition["period"] + offset
    intensity = brightness
    t = elapsed * speed
    wave = lambda x: .5 + .5 * math.sin(x)
    if preset in {"dj-light", "freqwave"}:
        audio = audio or {}
        energy = audio.get("energy", 0)
        if preset == "dj-light":
            rgb = [255 * value for value in audio.get("bands", [0, 0, 0])]
            intensity *= .12 + .88 * energy
        else:
            hue = min(1, max(0, audio.get("frequency", 0)))
            rgb = [255 * c for c in colorsys.hsv_to_rgb(hue + offset, .85, 1)]
            intensity *= .025 + .975 * energy
    elif preset in {"dna", "dna-spiral", "plasma", "ps-vortex"}:
        hue = phase + (.5 if offset else 0)
        if preset in {"plasma", "ps-vortex"}:
            hue += .2 * math.sin(t * .71 + offset * math.tau) + .12 * math.sin(t * 1.13)
        rgb = [255 * c for c in colorsys.hsv_to_rgb(hue % 1, .8, 1)]
        intensity *= .18 + .82 * wave(phase * math.tau * 2 + offset * math.tau)
    elif preset == "rainbow":
        rgb = [channel * 255 for channel in colorsys.hsv_to_rgb(phase % 1, 0.88, 1)]
    elif preset == "breathe":
        rgb = list(bytes.fromhex(base_color[1:]))
        intensity *= 0.12 + 0.88 * (0.5 - 0.5 * math.cos(phase * math.tau))
    elif preset == "candle":
        # Continuous bounded waves, without harsh flashes or random frame jumps.
        t = elapsed * speed + offset * 5
        variation = (math.sin(t * 2.1) + 0.5 * math.sin(t * 5.7 + 1.2)
                     + 0.25 * math.sin(t * 11.3)) / 1.75
        rgb = [255, 115 + 28 * variation, 24 + 12 * variation]
        intensity *= 0.72 + 0.18 * variation
    else:
        palette = definition["palette"]
        position = (phase % 1) * len(palette)
        index = int(position)
        mix = position - index
        mix = mix * mix * (3 - 2 * mix)
        a = bytes.fromhex(palette[index][1:])
        b = bytes.fromhex(palette[(index + 1) % len(palette)][1:])
        rgb = [left + (right - left) * mix for left, right in zip(a, b)]
        if preset == "android":
            intensity *= .12 + .88 * wave(phase * math.tau * 3) ** 4
        elif preset == "bpm":
            intensity *= .15 + .85 * (.5 - .5 * math.cos((t * bpm / 60 + offset) * math.tau)) ** 2
        elif preset == "chunchun":
            intensity *= .1 + .9 * wave(t * 2.6 + offset * math.tau) ** 3 * (.4 + .6 * wave(t * .7))
        elif preset == "colored-bursts":
            intensity *= .08 + .92 * wave(t * 1.7 + offset * math.tau) ** 5
        elif preset == "black-hole":
            intensity *= .18 + .65 * wave(phase * math.tau) ** 3
        elif preset == "halloween":
            intensity *= .55 + .25 * wave(t * 1.3) + .2 * wave(t * 2.7 + offset * math.tau)
        elif preset == "fire-2012":
            heat = .5 + .3 * math.sin(t * 3.1 + offset * 7) + .2 * math.sin(t * 7.7)
            rgb = [255, 30 + 170 * heat, 3 + 25 * heat ** 3]
            intensity *= .35 + .65 * heat
        elif preset == "pacifica":
            intensity *= .35 + .35 * wave(t * .61 + offset * 7) + .3 * wave(t * .37)
        elif preset == "ocean":
            intensity *= 0.7 + 0.3 * (0.5 + 0.5 * math.sin(phase * math.tau * 2))
    return "#" + "".join(f"{min(255, max(0, round(channel * intensity))):02X}" for channel in rgb)
