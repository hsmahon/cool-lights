"""Deterministic checks for music response, without Bluetooth or audio capture."""
import math
import unittest

from scripts.server import BassMeter


class BassMeterTests(unittest.TestCase):
    def test_silence_has_no_pulse(self):
        meter = BassMeter()
        for _ in range(20):
            self.assertEqual(meter.update([0.0] * 400, 3), 0)

    def test_bass_has_stronger_attack_than_treble(self):
        def attack(frequency):
            meter = BassMeter()
            return max(meter.update([
                0.1 * math.sin(2 * math.pi * frequency * (frame * 400 + i) / 8000)
                for i in range(400)], 1) for frame in range(5))
        self.assertGreater(attack(60), attack(2000) * 3)

    def test_pulse_decays_after_audio_stops(self):
        meter = BassMeter()
        pulse = [0.1 * math.sin(2 * math.pi * 90 * i / 8000) for i in range(400)]
        self.assertGreater(meter.update(pulse, 1.5), 0.5)
        for _ in range(50):
            level = meter.update([0.0] * 400, 1.5)
        self.assertLess(level, 0.001)

    def test_non_finite_samples_do_not_poison_the_meter(self):
        meter = BassMeter()
        value = meter.update([float('nan'), float('inf'), -float('inf'), 0.0], 1.5)
        self.assertTrue(math.isfinite(value))

    def test_high_sensitivity_keeps_dynamics_instead_of_clipping(self):
        meter = BassMeter()
        levels = []
        for frame in range(200):
            amplitude = 0.04 if frame % 25 < 15 else 0.1
            samples = [amplitude * math.sin(2 * math.pi * 90 * (frame * 160 + i) / 8000) for i in range(160)]
            levels.append(meter.update(samples, 2.5))
        self.assertLess(max(levels[50:]), 0.99)
        self.assertGreater(max(levels[50:]) - min(levels[50:]), 0.2)

    def test_small_audio_windows_have_fast_attack(self):
        meter = BassMeter()
        level = meter.update([0.1 * math.sin(2 * math.pi * 90 * i / 8000) for i in range(160)], 1.5)
        self.assertGreater(level, 0.65)

    def test_five_millisecond_blocks_react_and_keep_continuous_filter_state(self):
        meter = BassMeter()
        levels = []
        for frame in range(10):
            levels.append(meter.update([
                0.1 * math.sin(2 * math.pi * 90 * (frame * 40 + i) / 8000)
                for i in range(40)], 1.5))
        self.assertGreater(max(levels[:3]), 0.7)  # React within 15 ms.
        self.assertGreater(min(levels[3:]), 0.5)  # Don't reset at block boundaries.
        for _ in range(100):
            level = meter.update([0.0] * 40, 1.5)
        self.assertLess(level, 0.001)


if __name__ == '__main__':
    unittest.main()
