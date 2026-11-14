"""Synthetic playback tones verify band and frequency separation."""
import math
import unittest
from scripts.spectrum import Spectrum


class SpectrumTests(unittest.TestCase):
    def tone(self, frequency, amplitude=.4):
        spectrum = Spectrum()
        for block in range(40):
            result = spectrum.update([amplitude * math.sin(math.tau * frequency * (block * 40 + i) / 8000) for i in range(40)])
        return result

    def test_frequency_bands(self):
        for index, frequency in enumerate([125, 1000, 3000]):
            result = self.tone(frequency)
            self.assertEqual(result['bands'].index(max(result['bands'])), index)
            self.assertGreater(result['energy'], .1)
        self.assertLess(self.tone(125)['frequency'], self.tone(3000)['frequency'])

    def test_silence_and_nonfinite_are_bounded(self):
        spectrum = Spectrum()
        for _ in range(20):
            result = spectrum.update([float('nan'), float('inf')] + [0.] * 38)
        self.assertEqual(result['energy'], 0)
        self.assertTrue(all(math.isfinite(x) and 0 <= x <= 1 for x in result['bands']))

    def test_frequency_window_and_update_stride(self):
        spectrum = Spectrum()
        initial = spectrum.value
        for _ in range(7):
            spectrum.update([.1] * 40)
        self.assertIs(spectrum.value, initial)
        spectrum.update([.1] * 40)
        self.assertIsNot(spectrum.value, initial)

    def test_silence_decays(self):
        spectrum = Spectrum()
        for block in range(20):
            spectrum.update([.4 * math.sin(math.tau * 125 * (block * 40 + i) / 8000) for i in range(40)])
        for _ in range(80):
            result = spectrum.update([0.] * 40)
        self.assertLess(result['energy'], .002)
