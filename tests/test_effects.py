"""Pure animation checks and controller lifecycle tests without real devices."""
import asyncio
import re
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import server
from scripts.effects import PRESETS, catalog, frame


class FrameTests(unittest.TestCase):
    def test_catalog_and_frames(self):
        self.assertEqual(len(catalog()), 24)
        for preset in PRESETS:
            colors = [frame(preset, t / 20, '#59CFE8', speed=3, audio={'energy': .7, 'bands': [.1 + t / 400, .4, .2], 'frequency': t / 300}) for t in range(300)]
            self.assertGreater(len(set(colors)), 10, preset)
            self.assertTrue(all(re.fullmatch(r'#[0-9A-F]{6}', color) for color in colors))
            self.assertEqual(frame(preset, 1, '#FF483D', brightness=0), '#000000')

    def test_breathe_keeps_selected_color(self):
        red = bytes.fromhex(frame('breathe', 2, '#FF0000')[1:])
        blue = bytes.fromhex(frame('breathe', 2, '#0000FF')[1:])
        self.assertGreater(red[0], 0)
        self.assertEqual(red[1:], b'\x00\x00')
        self.assertGreater(blue[2], 0)
        self.assertEqual(blue[:2], b'\x00\x00')

    def test_lamps_can_have_different_phases(self):
        self.assertNotEqual(frame('aurora', 2, '#FFFFFF'), frame('aurora', 2, '#FFFFFF', offset=.25))

    def test_tempo_changes_pulse_not_palette(self):
        self.assertNotEqual(frame('bpm', .25, '#FFFFFF', bpm=60), frame('bpm', .25, '#FFFFFF', bpm=120))
        self.assertEqual(frame('bpm', .25, '#FFFFFF', bpm=120), frame('bpm', .25, '#FFFFFF', bpm=120))

    def test_audio_presets_react_to_input(self):
        for preset in ['dj-light', 'freqwave']:
            quiet = frame(preset, 1, '#FFFFFF')
            bass = frame(preset, 1, '#FFFFFF', audio={'energy': 1, 'bands': [1, .1, .1], 'frequency': .1})
            treble = frame(preset, 1, '#FFFFFF', audio={'energy': 1, 'bands': [.1, .1, 1], 'frequency': .9})
            self.assertNotEqual(quiet, bass)
            self.assertNotEqual(bass, treble)

    def test_holiday_palettes_and_phase(self):
        for preset in ['candy-cane', 'halloween', 'merry-christmas']:
            self.assertEqual(len(PRESETS[preset]['palette']), 4)
            self.assertNotEqual(frame(preset, 1, '#FFFFFF'), frame(preset, 1, '#FFFFFF', offset=.25))


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.writes = []
        self.connected = set()
        self.saved = {'one': {'color': '#59CFE8', 'status': 'Ready', 'error': None},
                      'two': {'color': '#FF483D', 'status': 'Ready', 'error': None}}
        self.stack = []
        writes, connected = self.writes, self.connected

        class Client:
            def __init__(self, address, **kwargs):
                self.address = address
                self.services = SimpleNamespace(get_characteristic=lambda uuid: SimpleNamespace(properties=['write-without-response']))
            async def __aenter__(self):
                connected.add(self.address)
                return self
            async def __aexit__(self, *args):
                connected.remove(self.address)
            async def write_gatt_char(self, char, packet, response):
                writes.append((self.address, packet))

        async def find(address, **kwargs):
            return address

        replacements = {
            'BleakClient': Client, 'BleakScanner': SimpleNamespace(find_device_by_address=find),
            'BUSY': threading.Lock(), 'STATE': self.saved, 'MUSIC_TASK': None,
            'EFFECT_TASK': None,
            'EFFECT': {'status': 'stopped', 'preset': None, 'target': 'both', 'speed': 1, 'colors': {}, 'frames': 0, 'error': None},
        }
        for key, value in replacements.items():
            item = patch.object(server, key, value)
            item.start()
            self.stack.append(item)

    async def asyncTearDown(self):
        await server.stop_effect()
        for item in reversed(self.stack):
            item.stop()

    async def test_single_lamp_restores_color_and_releases_connection(self):
        await server.start_effect('aurora', 'one', 1)
        await asyncio.sleep(.12)
        self.assertGreater(server.EFFECT['frames'], 0)
        await server.stop_effect()
        self.assertTrue(all(address == server.LAMPS['one'] for address, _ in self.writes))
        self.assertEqual(self.writes[-1][1], server.color_packet('#59CFE8'))
        self.assertEqual(self.saved['one']['color'], '#59CFE8')
        self.assertEqual(self.saved['two']['status'], 'Ready')
        self.assertFalse(self.connected)
        self.assertFalse(server.BUSY.locked())

    async def test_switch_effects_and_restore_independent_colors(self):
        await server.start_effect('sunset', 'both', 1)
        await asyncio.sleep(.07)
        await server.start_effect('breathe', 'both', .5)
        await asyncio.sleep(.07)
        self.assertEqual(server.EFFECT['preset'], 'breathe')
        await server.stop_effect()
        for key in ['one', 'two']:
            packets = [packet for address, packet in self.writes if address == server.LAMPS[key]]
            self.assertEqual(packets[-1], server.color_packet(self.saved[key]['color']))
        self.assertFalse(server.BUSY.locked())

    async def test_missing_lamp_does_not_hold_lock(self):
        async def missing(*args, **kwargs):
            return None
        with patch.object(server.BleakScanner, 'find_device_by_address', missing):
            await server.start_effect('rainbow', 'one', 1)
            await asyncio.sleep(.02)
        self.assertEqual(server.EFFECT['status'], 'error')
        self.assertFalse(self.writes)
        self.assertFalse(server.BUSY.locked())

    async def test_stop_while_connecting_releases_lock(self):
        async def slow(*args, **kwargs):
            await asyncio.sleep(100)
        with patch.object(server.BleakScanner, 'find_device_by_address', slow):
            await server.start_effect('ocean', 'one', 1)
            await server.stop_effect()
        self.assertFalse(server.BUSY.locked())
        self.assertEqual(server.EFFECT['status'], 'stopped')

    async def test_effect_start_stops_music_before_connecting(self):
        server.BUSY.acquire()
        async def music():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                pass
            finally:
                server.BUSY.release()
        server.MUSIC_TASK = asyncio.create_task(music())
        await asyncio.sleep(0)
        await server.start_effect('candle', 'one', 1)
        await asyncio.sleep(.07)
        self.assertTrue(server.MUSIC_TASK.done())
        self.assertEqual(server.EFFECT['status'], 'running')

    async def test_audio_capture_failure_restores_and_unlocks(self):
        async def broken(**kwargs):
            raise RuntimeError('Playback capture unavailable')
        with patch.object(server, 'open_playback', broken):
            await server.start_effect('dj-light', 'one', 1)
            await asyncio.sleep(.03)
        self.assertEqual(server.EFFECT['status'], 'error')
        self.assertIn('Playback', server.EFFECT['error'])
        self.assertEqual(self.writes[-1][1], server.color_packet('#59CFE8'))
        self.assertFalse(self.connected)
        self.assertFalse(server.BUSY.locked())

    async def test_audio_stop_closes_capture(self):
        closed = []
        async def opened(**kwargs):
            return object(), asyncio.create_task(asyncio.sleep(100))
        async def close(process, reader):
            if reader:
                reader.cancel()
                try:
                    await reader
                except asyncio.CancelledError:
                    pass
                closed.append(True)
        with patch.object(server, 'open_playback', opened), patch.object(server, 'close_playback', close):
            await server.start_effect('freqwave', 'both', 1)
            await asyncio.sleep(.06)
            await server.stop_effect()
        self.assertEqual(closed, [True])
        self.assertFalse(server.BUSY.locked())
