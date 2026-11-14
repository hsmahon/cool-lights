"""32 ms playback spectrum, updated every four 5 ms capture blocks."""
import math
from collections import deque
import numpy as np


class Spectrum:
    def __init__(self):
        self.samples = deque(maxlen=256)
        self.blocks = 0
        self.peak = .02
        self.value = {'energy': 0., 'bands': [0., 0., 0.], 'frequency': 0.}

    def update(self, samples, sensitivity=1.5):
        self.samples.extend(x if math.isfinite(x) else 0. for x in samples)
        self.blocks += 1
        if len(self.samples) < 256 or self.blocks % 4:
            return self.value
        data = np.asarray(self.samples)
        rms = float(np.sqrt(np.mean(data ** 2)))
        self.peak = max(.02, self.peak * .99, rms)
        energy = min(1., max(0., rms - .0015) / self.peak) ** (1 / sensitivity)
        power = abs(np.fft.rfft((data - data.mean()) * np.hanning(256))) ** 2
        frequencies = np.fft.rfftfreq(256, 1 / 8000)
        bands = [float(power[(frequencies >= lo) & (frequencies < hi)].sum())
                 for lo, hi in [(40, 250), (250, 2000), (2000, 4001)]]
        scale = max(max(bands), 1e-12)
        normalized = [math.sqrt(value / scale) for value in bands]
        dominant = float(frequencies[int(np.argmax(power[1:])) + 1])
        hue = max(0., min(1., math.log2(max(40, dominant) / 40) / math.log2(100)))
        alpha = .7 if energy > self.value['energy'] else .3
        self.value = {'energy': self.value['energy'] + alpha * (energy - self.value['energy']),
                      'bands': normalized, 'frequency': hue}
        return self.value
