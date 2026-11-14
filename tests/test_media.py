"""Media lifecycle and HTTP contract with fake lamps; no screen or audio capture."""
import asyncio
import json
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from scripts import server
from scripts.media import MediaController


class MediaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.writes, self.connected = [], set()
        writes, connected = self.writes, self.connected
        class Client:
            def __init__(self, address, **kwargs):
                self.address = address
                self.services = SimpleNamespace(get_characteristic=lambda _: SimpleNamespace(properties=['write-without-response']))
            async def __aenter__(self):
                connected.add(self.address)
                return self
            async def __aexit__(self, *args):
                connected.remove(self.address)
            async def write_gatt_char(self, char, packet, response):
                writes.append((time.monotonic(), self.address, packet))
        async def find(address, **kwargs):
            return address
        self.owner = SimpleNamespace(
            STATE={'one': {'color': '#123456', 'status': 'Ready'}, 'two': {'color': '#ABCDEF', 'status': 'Ready'}},
            LAMPS={'one': 'lamp1', 'two': 'lamp2'}, CHAR='fff3', SHUTTING_DOWN=False,
            STATE_LOCK=threading.Lock(), BUSY=threading.Lock(), BleakClient=Client,
            BleakScanner=SimpleNamespace(find_device_by_address=find),
            color_packet=server.color_packet, stop_music=AsyncMock(), stop_effect=AsyncMock())
        self.media = MediaController(self.owner)
        self.colors = {'one': '#FF0000', 'two': '#0000FF'}

    async def asyncTearDown(self):
        await self.media.stop()

    async def start(self):
        state = await self.media.start(self.colors)
        await asyncio.sleep(.025)
        return state['session']

    async def test_paired_writes_explicit_stop_restores_saved_colors(self):
        session = await self.start()
        self.assertEqual(self.media.state['status'], 'running')
        self.assertEqual({address: packet for _, address, packet in self.writes},
                         {'lamp1': server.color_packet('#FF0000'), 'lamp2': server.color_packet('#0000FF')})
        await self.media.stop(session, restore=True)
        self.assertEqual(self.writes[-2][2], server.color_packet('#123456'))
        self.assertEqual(self.writes[-1][2], server.color_packet('#ABCDEF'))
        self.assertFalse(self.connected)
        self.assertFalse(self.owner.BUSY.locked())

    async def test_tab_close_timeout_retains_last_frame(self):
        self.media.lease_seconds = .07
        await self.start()
        before = list(self.writes)
        await asyncio.sleep(.15)
        self.assertEqual(self.writes, before)
        self.assertEqual(self.media.state['status'], 'stopped')
        self.assertIn('frames stopped', self.media.state['error'])
        self.assertFalse(self.connected)
        self.assertFalse(self.owner.BUSY.locked())

    async def test_shutdown_does_not_restore_even_if_requested(self):
        await self.start()
        before = list(self.writes)
        self.owner.SHUTTING_DOWN = True
        await self.media.stop(restore=True)
        self.assertEqual(self.writes, before)
        self.assertEqual(self.owner.STATE['one']['color'], '#123456')
        self.assertFalse(self.connected)

    async def test_latest_frame_replaces_old_frames_and_rate_is_bounded(self):
        session = await self.start()
        for value in range(40):
            self.media.receive(session, {'one': f'#{value:02X}0000', 'two': '#00FF00'})
        await asyncio.sleep(.105)
        self.assertEqual(self.media.state['frames'], 2)
        self.assertEqual(self.writes[-2][2], server.color_packet('#270000'))
        self.assertEqual(self.writes[-1][2], server.color_packet('#00FF00'))
        self.assertGreaterEqual(self.writes[-1][0] - self.writes[0][0], .09)

    async def test_old_session_cannot_write_or_stop_new_session(self):
        old = await self.start()
        await self.media.stop(old)
        new = await self.start()
        self.assertNotEqual(new, old)
        with self.assertRaises(RuntimeError):
            self.media.receive(old, self.colors)
        with self.assertRaises(RuntimeError):
            await self.media.stop(old, restore=True)
        self.assertEqual(self.media.state['status'], 'running')
        with self.assertRaises(RuntimeError):
            await self.media.start(self.colors)

    async def test_missing_lamp_and_tab_loss_while_connecting_release_lock(self):
        self.owner.BleakScanner.find_device_by_address = AsyncMock(return_value=None)
        await self.start()
        self.assertEqual(self.media.state['status'], 'error')
        self.assertFalse(self.owner.BUSY.locked())
        async def slow(*args, **kwargs):
            await asyncio.sleep(100)
        self.owner.BleakScanner.find_device_by_address = slow
        self.media.lease_seconds = .04
        await self.start()
        await asyncio.sleep(.1)
        self.assertFalse(self.owner.BUSY.locked())
        self.assertFalse(self.writes)

    async def test_media_stops_other_host_engines(self):
        await self.start()
        self.owner.stop_music.assert_awaited_once()
        self.owner.stop_effect.assert_awaited_once()

    async def test_restore_failure_is_reported_and_releases_clients(self):
        await self.start()
        async def disconnected(*args, **kwargs):
            raise RuntimeError('Not connected')
        self.owner.BleakClient.write_gatt_char = disconnected
        state = await self.media.stop(restore=True)
        self.assertIn('Could not restore', state['error'])
        self.assertFalse(self.connected)
        self.assertFalse(self.owner.BUSY.locked())

    async def test_http_session_contract_and_token(self):
        http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = f'http://localhost:{http.server_port}'
        def request(path, body=None, token=server.TOKEN):
            req = urllib.request.Request(base+path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'X-Lamp-Token': token, 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                with error:
                    return error.code, json.load(error)
        try:
            with patch.object(server, 'LOOP', asyncio.get_running_loop()), patch.object(server, 'MEDIA', self.media):
                status, _ = await asyncio.to_thread(request, '/api/media/start', self.colors, 'wrong')
                self.assertEqual(status, 403)
                status, _ = await asyncio.to_thread(request, '/api/media/start', {'one': '#FF0000'})
                self.assertEqual(status, 400)
                status, data = await asyncio.to_thread(request, '/api/media/start', self.colors)
                self.assertEqual(status, 200)
                session = data['session']
                status, _ = await asyncio.to_thread(request, '/api/media/frame', {'session': 'stale', **self.colors})
                self.assertEqual(status, 409)
                status, _ = await asyncio.to_thread(request, '/api/media/frame', {'session': session, **self.colors})
                self.assertEqual(status, 200)
                status, _ = await asyncio.to_thread(request, '/api/media/stop', {'session': session, 'restore': True})
                self.assertEqual(status, 200)
                self.assertFalse(self.owner.BUSY.locked())
        finally:
            await asyncio.to_thread(http.shutdown)
            http.server_close()
