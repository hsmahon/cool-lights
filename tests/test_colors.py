"""Color preservation for independent music pulses and server restarts."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import server


class ColorTests(unittest.TestCase):
    def test_independent_pulse_packets_preserve_rgb(self):
        self.assertEqual(server.color_packet('#59CFE8'), bytes.fromhex('7e 07 05 03 59 cf e8 10 ef'))
        self.assertEqual(server.color_packet('#FF483D'), bytes.fromhex('7e 07 05 03 ff 48 3d 10 ef'))
        self.assertEqual(server.color_packet('#59CFE8', 0.5), bytes.fromhex('7e 07 05 03 2c 68 74 10 ef'))
        self.assertEqual(server.color_packet('#FF483D', 0), bytes.fromhex('7e 07 05 03 00 00 00 10 ef'))

    def test_saved_colors_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(server, 'COLORS_PATH', Path(directory) / 'colors.json'):
                with patch.object(server, 'STATE', {'one': {'color': '#59CFE8'}, 'two': {'color': '#FF483D'}}):
                    server.save_colors()
                self.assertEqual(server.load_colors(), {'one': '#59CFE8', 'two': '#FF483D'})


if __name__ == '__main__':
    unittest.main()
