"""Latest-frame Bluetooth media sync; frames contain colors, never images."""
import asyncio
import contextlib
import re
import secrets
import time


class MediaController:
    def __init__(self, owner):
        self.owner = owner
        self.task = None
        self.restore_on_stop = False
        self.latest = {}
        self.version = 0
        self.last_seen = 0.
        self.lease_seconds = 2.
        self.state = {'status': 'stopped', 'session': None, 'colors': {},
                      'frames': 0, 'update_hz': 0., 'error': None}

    def snapshot(self):
        return {**self.state, 'colors': dict(self.state['colors']),
                'input_age_ms': round((time.monotonic() - self.last_seen) * 1000)
                if self.state['status'] in {'starting', 'running'} else None}

    @staticmethod
    def colors(body):
        result = {}
        for key in ('one', 'two'):
            value = body.get(key)
            if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                raise ValueError('Provide two six-digit hex colors')
            result[key] = value.upper()
        return result

    async def start(self, colors):
        owner = self.owner
        # An active client may replace its own session, never another client's.
        if self.task is not None and not self.task.done():
            raise RuntimeError('Media sync is already active. Stop it before starting a new session.')
        await owner.stop_music()
        await owner.stop_effect()
        if not owner.BUSY.acquire(blocking=False):
            raise RuntimeError('A lamp command is in progress. Wait for it to finish.')
        self.latest = dict(colors)
        self.version = 1
        self.last_seen = time.monotonic()
        self.restore_on_stop = False
        self.state.update(status='starting', session=secrets.token_urlsafe(24),
                          colors={}, frames=0, update_hz=0., error=None)
        self.task = asyncio.create_task(self.run())
        await asyncio.sleep(0)
        return self.snapshot()

    def receive(self, session, colors):
        if session != self.state['session'] or self.state['status'] not in {'starting', 'running'}:
            raise RuntimeError('Media session ended. Choose your video again to restart.')
        self.latest = dict(colors)
        self.version += 1
        self.last_seen = time.monotonic()
        return {'ok': True}

    async def stop(self, session=None, restore=False):
        if session is not None and session != self.state['session']:
            raise RuntimeError('This media session is no longer active')
        if self.task is not None and not self.task.done():
            self.restore_on_stop = restore
            self.task.cancel()
            await self.task
        return self.snapshot()

    async def watch(self):
        while True:
            await asyncio.sleep(min(.25, self.lease_seconds / 2))
            if time.monotonic() - self.last_seen > self.lease_seconds:
                self.state['error'] = 'Screen sharing ended or frames stopped. Last colors retained.'
                self.task.cancel()
                return

    async def run(self):
        owner = self.owner
        clients = {}
        restore = {key: owner.STATE[key]['color'] or '#FF69B4' for key in owner.LAMPS}
        watcher = asyncio.create_task(self.watch())
        error = None
        try:
            async with contextlib.AsyncExitStack() as stack:
                try:
                    for key, address in owner.LAMPS.items():
                        with owner.STATE_LOCK:
                            owner.STATE[key].update(status='Connecting', error=None)
                        async with asyncio.timeout(45):
                            device = await owner.BleakScanner.find_device_by_address(address, timeout=15)
                            if device is None:
                                raise RuntimeError(f'Lamp {key} not found. Check power and move closer.')
                            client = await stack.enter_async_context(owner.BleakClient(device, timeout=25))
                        char = client.services.get_characteristic(owner.CHAR)
                        if char is None or 'write-without-response' not in char.properties:
                            raise RuntimeError(f'Lamp {key} has no compatible control characteristic.')
                        clients[key] = (client, char)
                    self.state['status'] = 'running'
                    with owner.STATE_LOCK:
                        for key in clients:
                            owner.STATE[key].update(status='Media sync', error=None)
                    sent_version = 0
                    deadline = time.monotonic()
                    completed = []
                    while True:
                        if self.version != sent_version:
                            version, colors = self.version, dict(self.latest)
                            await asyncio.wait_for(asyncio.gather(*(
                                client.write_gatt_char(char, owner.color_packet(colors[key]), response=False)
                                for key, (client, char) in clients.items())), 3)
                            sent_version = version
                            self.state['colors'] = colors
                            with owner.STATE_LOCK:
                                for key, color in colors.items():
                                    owner.STATE[key]['media_color'] = color
                            self.state['frames'] += 1
                            now = time.monotonic()
                            completed = [stamp for stamp in completed if stamp > now - 2] + [now]
                            if len(completed) > 1:
                                self.state['update_hz'] = round((len(completed)-1)/(completed[-1]-completed[0]), 1)
                        deadline += .1
                        if deadline < time.monotonic():
                            deadline = time.monotonic() + .1
                        await asyncio.sleep(max(0, deadline-time.monotonic()))
                finally:
                    if self.restore_on_stop and not owner.SHUTTING_DOWN:
                        for key, (client, char) in clients.items():
                            try:
                                await asyncio.wait_for(client.write_gatt_char(char, owner.color_packet(restore[key]), response=False), 3)
                            except Exception:
                                self.state['error'] = 'Could not restore a saved color. Apply a color to reconnect.'
                                with owner.STATE_LOCK:
                                    owner.STATE[key].update(status='Failed', error='Could not restore saved color. Apply a color to reconnect.')
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            error = str(exc) or type(exc).__name__
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
            self.state.update(status='error' if error else 'stopped', update_hz=0.,
                              error=error or self.state['error'])
            with owner.STATE_LOCK:
                for key in owner.LAMPS:
                    if owner.STATE[key]['status'] in {'Connecting', 'Media sync'}:
                        paused = self.state['frames'] > 0 and not (self.restore_on_stop and not owner.SHUTTING_DOWN)
                        status = 'Failed' if error else 'Media paused' if paused else 'Sent' if self.restore_on_stop else 'Ready'
                        owner.STATE[key].update(status=status, error=error)
            owner.BUSY.release()
