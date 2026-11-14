"""Local HTTP controls for the two verified MELK Bluetooth lamps."""
import argparse
import asyncio
import contextlib
import json
import math
import re
import secrets
import signal
import struct
import threading
import time
from collections import deque
from concurrent.futures import TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bleak import BleakClient, BleakScanner
try:
    from .spectrum import Spectrum
    from .effects import PRESETS, catalog, frame
except ImportError:  # Direct execution: python scripts/server.py
    from spectrum import Spectrum
    from effects import PRESETS, catalog, frame

LAMPS = {"one": "BE:28:67:00:12:6E", "two": "BE:28:67:00:12:73"}
CHAR = "0000fff3-0000-1000-8000-00805f9b34fb"
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "front-end"
COLORS_PATH = ROOT / ".lamp-colors.json"
TOKEN = secrets.token_urlsafe(32)


def load_colors():
    try:
        colors = json.loads(COLORS_PATH.read_text())
        return {key: color.upper() for key, color in colors.items()
                if key in LAMPS and isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)}
    except (OSError, ValueError, AttributeError):
        return {}


SAVED_COLORS = load_colors()
STATE = {key: {"color": SAVED_COLORS.get(key), "status": "Ready", "error": None} for key in LAMPS}
STATE_LOCK = threading.Lock()
LOOP = asyncio.new_event_loop()
BUSY = threading.Lock()
MUSIC = {"status": "stopped", "level": 0.0, "sensitivity": 1.5,
         "brightness": 0.7, "colors": {key: SAVED_COLORS.get(key, "#FF69B4") for key in LAMPS}, "error": None,
         "source": None, "frames": 0, "update_hz": 0.0,
         "write_ms": 0.0, "audio_age_ms": None, "analysis_ms": 5,
         "target_hz": 60, "analysis_hz": 0.0, "missed_deadlines": 0}
MUSIC_TASK = None
AUDIO_UPDATED = None
EFFECT = {"status": "stopped", "preset": None, "target": "both", "speed": 1.0,
          "colors": {}, "frames": 0, "error": None}
EFFECT_TASK = None
SPECTRUM = {}
SHUTTING_DOWN = False


async def effect_loop(preset, targets):
    clients = {}
    process = reader = None
    audio_effect = preset in {"dj-light", "freqwave"}
    error = None
    with STATE_LOCK:
        restore = {key: STATE[key]["color"] or "#FF69B4" for key in targets}
    try:
        async with contextlib.AsyncExitStack() as stack:
            try:
                for key in targets:
                    with STATE_LOCK:
                        STATE[key].update(status="Connecting", error=None)
                    async with asyncio.timeout(45):
                        device = await BleakScanner.find_device_by_address(LAMPS[key], timeout=15)
                        if device is None:
                            raise RuntimeError(f"Lamp {key} not found. Check power and move closer.")
                        client = await stack.enter_async_context(BleakClient(device, timeout=25))
                    char = client.services.get_characteristic(CHAR)
                    if char is None or "write-without-response" not in char.properties:
                        raise RuntimeError(f"Lamp {key} has no compatible control characteristic.")
                    clients[key] = (client, char)
                if audio_effect:
                    process, reader = await open_playback(spectral=True)
                with STATE_LOCK:
                    EFFECT["status"] = "running"
                    EFFECT["audio_ready"] = False
                    for key in targets:
                        STATE[key].update(status="Animation", effect=PRESETS[preset]["name"], error=None)
                elapsed = 0.0
                previous = deadline = time.monotonic()
                while True:
                    now = time.monotonic()
                    with STATE_LOCK:
                        speed = EFFECT["speed"]
                        bpm = EFFECT.get("bpm", 120)
                        audio = dict(SPECTRUM)
                        fresh = AUDIO_UPDATED is not None and now - AUDIO_UPDATED < .25
                        EFFECT["audio_ready"] = audio_effect and fresh
                        brightness = MUSIC["brightness"] if audio_effect else .7
                    if reader is not None and reader.done():
                        reader.result()
                    if not fresh:
                        audio = {}
                    elapsed += (now - previous) * (1 if preset == "bpm" else speed)
                    previous = now
                    colors = {key: frame(preset, elapsed, restore[key], offset=0.25 if key == "two" and len(targets) == 2 else 0, bpm=bpm, audio=audio, brightness=brightness)
                              for key in targets}
                    await asyncio.wait_for(asyncio.gather(*(
                        client.write_gatt_char(char, color_packet(colors[key]), response=False)
                        for key, (client, char) in clients.items())), 3)
                    with STATE_LOCK:
                        EFFECT["frames"] += 1
                        EFFECT["colors"] = colors
                    deadline += 0.05
                    if deadline < time.monotonic():
                        deadline = time.monotonic() + 0.05
                    await asyncio.sleep(max(0, deadline - time.monotonic()))
            finally:
                await close_playback(process, reader)
                for key, (client, char) in clients.items():
                    if SHUTTING_DOWN:
                        continue  # Keep the last RGB frame; disconnect without a color write.
                    try:
                        await asyncio.wait_for(client.write_gatt_char(char, color_packet(restore[key]), response=False), 3)
                        with STATE_LOCK:
                            STATE[key].update(status="Sent", effect=None, error=None)
                    except Exception:
                        with STATE_LOCK:
                            STATE[key].update(status="Failed", effect=None, error="Connection lost. Apply a color to reconnect.")
    except asyncio.CancelledError:
        pass
    except Exception as exception:
        error = str(exception) or type(exception).__name__
    finally:
        with STATE_LOCK:
            EFFECT.update(status="error" if error else "stopped", error=error, colors={})
            for key in targets:
                if STATE[key]["status"] in {"Connecting", "Animation"}:
                    STATE[key].update(status="Failed" if error else "Ready", effect=None, error=error)
        BUSY.release()


async def stop_effect():
    if EFFECT_TASK is not None and not EFFECT_TASK.done():
        with STATE_LOCK:
            EFFECT["status"] = "stopping"
        EFFECT_TASK.cancel()
        await EFFECT_TASK
    with STATE_LOCK:
        EFFECT.update(status="stopped", error=None, colors={})


async def start_effect(preset, target, speed, bpm=120):
    global EFFECT_TASK
    await stop_music()
    await stop_effect()
    if not BUSY.acquire(blocking=False):
        raise RuntimeError("A lamp command is in progress. Wait for it to finish.")
    with STATE_LOCK:
        EFFECT.update(status="starting", preset=preset, target=target, speed=speed, bpm=bpm, audio_ready=False, colors={}, error=None, frames=0)
    EFFECT_TASK = asyncio.create_task(effect_loop(preset, list(LAMPS) if target == "both" else [target]))
    await asyncio.sleep(0)


def color_packet(color, intensity=1.0):
    rgb = bytes(round(channel * intensity) for channel in bytes.fromhex(color[1:]))
    return b"\x7e\x07\x05\x03" + rgb + b"\x10\xef"


def save_colors():
    with STATE_LOCK:
        colors = {key: value["color"] for key, value in STATE.items() if value["color"]}
    temporary = COLORS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(colors))
    temporary.replace(COLORS_PATH)


class BassMeter:
    """40–180 Hz envelope with a noise gate and slowly adapting peak."""
    def __init__(self, rate=8000):
        self.low = self.dc = 0.0
        self.peak = 0.02
        self.average = 0.0
        self.energy = 0.0
        self.energy_alpha = 1 - math.exp(-1 / (0.006 * rate))
        self.envelope = 0.0
        self.rate = rate
        self.dc_alpha = 1 - math.exp(-2 * math.pi * 40 / rate)
        self.low_alpha = 1 - math.exp(-2 * math.pi * 180 / rate)

    def update(self, samples, sensitivity):
        for sample in samples:
            if not math.isfinite(sample):
                sample = 0.0
            self.dc += self.dc_alpha * (sample - self.dc)
            self.low += self.low_alpha * (sample - self.dc - self.low)
            # Carry filter energy across short blocks; don't reset on bass phase.
            self.energy += self.energy_alpha * (self.low * self.low - self.energy)
        rms = math.sqrt(max(0, self.energy))
        duration = len(samples) / self.rate
        self.peak = max(0.012, self.peak * math.exp(-duration / 3), rms)
        self.average += (rms - self.average) * (1 - math.exp(-duration / 0.3))
        # Subtract sustained energy so individual bass hits remain visible.
        strength = min(1.0, max(0.0, rms - max(0.0015, self.average * 0.8)) / self.peak)
        # Sensitivity bends the response rather than multiplying it into clipping.
        strength = strength ** (1 / sensitivity)
        smoothing = 1 - math.exp(-duration / (0.003 if strength > self.envelope else 0.04))
        self.envelope += (strength - self.envelope) * smoothing
        return self.envelope


async def capture_bass(process, spectral=False):
    global AUDIO_UPDATED, SPECTRUM
    meter = BassMeter()
    spectrum = Spectrum() if spectral else None
    ticks = deque(maxlen=200)
    while True:
        try:
            chunk = await process.stdout.readexactly(40 * 4)
        except asyncio.IncompleteReadError:
            raise RuntimeError("Playback audio capture stopped. Check your audio output.") from None
        with STATE_LOCK:
            sensitivity = MUSIC["sensitivity"]
        samples = struct.unpack("<40f", chunk)
        level = meter.update(samples, sensitivity)
        if spectrum is not None:
            value = spectrum.update(samples, sensitivity)
            with STATE_LOCK:
                SPECTRUM = dict(value)
        now = time.monotonic()
        ticks.append(now)
        with STATE_LOCK:
            MUSIC["level"] = round(level, 3)
            AUDIO_UPDATED = now
            if len(ticks) > 1 and ticks[-1] > ticks[0]:
                MUSIC["analysis_hz"] = round((len(ticks) - 1) / (ticks[-1] - ticks[0]), 1)


async def open_playback(spectral=False):
    global AUDIO_UPDATED, SPECTRUM
    AUDIO_UPDATED = None
    SPECTRUM = {}
    lookup = await asyncio.create_subprocess_exec(
        "pactl", "get-default-sink", stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    try:
        output, _ = await asyncio.wait_for(lookup.communicate(), 5)
    finally:
        if lookup.returncode is None:
            lookup.kill()
            await lookup.wait()
    if lookup.returncode or not output.strip():
        raise RuntimeError("Cannot find the laptop's playback output.")
    source = output.decode().strip() + ".monitor"
    process = await asyncio.create_subprocess_exec(
        "parec", "--raw", "--format=float32le", "--rate=8000",
        "--channels=1", "--latency-msec=5", "--process-time-msec=5", f"--device={source}",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    MUSIC["source"] = source
    return process, asyncio.create_task(capture_bass(process, spectral))


async def close_playback(process, reader):
    if reader is not None:
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await reader
    if process is not None and process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 3)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()


async def music_loop():
    clients = {}
    process = reader = None
    error = None
    with STATE_LOCK:
        restore = {key: STATE[key]["color"] or "#FF69B4" for key in LAMPS}
        MUSIC["colors"] = dict(restore)
    try:
        async with contextlib.AsyncExitStack() as stack:
            try:
                for key, address in LAMPS.items():
                    with STATE_LOCK:
                        STATE[key].update(status="Connecting", error=None)
                    async with asyncio.timeout(45):
                        device = await BleakScanner.find_device_by_address(address, timeout=15)
                        if device is None:
                            raise RuntimeError(f"Lamp {key} not found. Check power and move closer.")
                        client = await stack.enter_async_context(BleakClient(device, timeout=25))
                    char = client.services.get_characteristic(CHAR)
                    if char is None or "write-without-response" not in char.properties:
                        raise RuntimeError(f"Lamp {key} has no compatible control characteristic.")
                    clients[key] = (client, char)
                process, reader = await open_playback()
                with STATE_LOCK:
                    MUSIC["status"] = "running"
                    for key in clients:
                        STATE[key].update(status="Music sync", error=None)
                completed = deque()
                deadline = time.monotonic()
                while True:
                    frame_started = time.monotonic()
                    if reader.done():
                        reader.result()
                    with STATE_LOCK:
                        level, brightness = MUSIC["level"], MUSIC["brightness"]
                        rate = MUSIC["target_hz"]
                        if AUDIO_UPDATED is None or frame_started - AUDIO_UPDATED > 0.25:
                            level = 0.0
                    intensity = brightness * (0.04 + 0.96 * level)
                    # Dispatch the newest level to both lamps; never queue old frames.
                    write_started = time.monotonic()
                    await asyncio.wait_for(asyncio.gather(*(
                        client.write_gatt_char(char, color_packet(restore[key], intensity), response=False)
                        for key, (client, char) in clients.items())), 3)
                    finished = time.monotonic()
                    completed.append(finished)
                    while len(completed) > 2 and completed[0] < finished - 2:
                        completed.popleft()
                    with STATE_LOCK:
                        MUSIC["frames"] += 1
                        MUSIC["write_ms"] = round((time.monotonic() - write_started) * 1000, 1)
                        if len(completed) > 1:
                            MUSIC["update_hz"] = round((len(completed) - 1) / (completed[-1] - completed[0]), 1)
                    # Absolute pacing prevents timer drift. Drop overdue slots;
                    # never build a backlog of obsolete colors.
                    period = 1 / rate
                    deadline += period
                    if deadline < finished:
                        with STATE_LOCK:
                            MUSIC["missed_deadlines"] += 1
                        deadline = finished + period
                    await asyncio.sleep(max(0, deadline - time.monotonic()))
            finally:
                await close_playback(process, reader)
                for key, (client, char) in clients.items():
                    if SHUTTING_DOWN:
                        continue  # Keep the last RGB frame; disconnect without a color write.
                    try:
                        packet = color_packet(restore[key])
                        await asyncio.wait_for(client.write_gatt_char(char, packet, response=False), 3)
                        with STATE_LOCK:
                            STATE[key].update(color=restore[key], status="Sent", error=None)
                    except Exception:
                        with STATE_LOCK:
                            STATE[key].update(status="Failed", error="Connection lost. Apply a color to reconnect.")
    except asyncio.CancelledError:
        pass
    except Exception as exception:
        error = str(exception) or type(exception).__name__
    finally:
        with STATE_LOCK:
            MUSIC.update(status="error" if error else "stopped", error=error, level=0.0, update_hz=0.0)
            for key in LAMPS:
                if STATE[key]["status"] in {"Connecting", "Music sync"}:
                    STATE[key].update(status="Failed" if error else "Ready", error=error)
        BUSY.release()


async def start_music():
    global MUSIC_TASK
    await stop_effect()
    if MUSIC_TASK is not None and not MUSIC_TASK.done():
        return
    if not BUSY.acquire(blocking=False):
        raise RuntimeError("A color change is in progress. Wait for it to finish.")
    with STATE_LOCK:
        MUSIC.update(status="starting", error=None, frames=0, level=0.0, update_hz=0.0,
                     write_ms=0.0, analysis_hz=0.0, missed_deadlines=0)
    MUSIC_TASK = asyncio.create_task(music_loop())
    # Enter the task before acknowledging Start, so immediate Stop runs cleanup.
    await asyncio.sleep(0)


async def stop_music():
    if MUSIC_TASK is not None and not MUSIC_TASK.done():
        with STATE_LOCK:
            MUSIC["status"] = "stopping"
        MUSIC_TASK.cancel()
        await MUSIC_TASK


async def shutdown():
    """Release resources without replacing the lamps' last rendered colors."""
    global SHUTTING_DOWN
    SHUTTING_DOWN = True
    await stop_effect()
    await stop_music()


def request_shutdown(signum, frame):
    raise KeyboardInterrupt


NATIVE_PRESETS = [{"id": "rainbow-flow", "name": "Rainbow Flow",
                   "description": "Built-in gradual color cycle; continues after app shutdown",
                   "mode": 199}]


def native_packet(preset):
    definition = next((item for item in NATIVE_PRESETS if item["id"] == preset), None)
    if definition is None:
        raise ValueError("Choose a listed on-lamp animation")
    return bytes([0x7e, 0x07, 0x03, definition["mode"], 0xff, 0xff, 0xff, 0x00, 0xef])


async def start_native(preset, target):
    packet = native_packet(preset)
    await stop_music()
    await stop_effect()
    if not BUSY.acquire(blocking=False):
        raise RuntimeError("A lamp command is in progress. Wait for it to finish.")
    results = {}
    try:
        for key in (list(LAMPS) if target == "both" else [target]):
            with STATE_LOCK:
                STATE[key].update(status="Connecting", error=None)
            try:
                async with asyncio.timeout(45):
                    device = await BleakScanner.find_device_by_address(LAMPS[key], timeout=15)
                    if device is None:
                        raise RuntimeError(f"Lamp {key} not found. Check power and move closer.")
                    async with BleakClient(device, timeout=25) as client:
                        char = client.services.get_characteristic(CHAR)
                        if char is None or "write-without-response" not in char.properties:
                            raise RuntimeError("Control characteristic unavailable")
                        await client.write_gatt_char(char, packet, response=False)
                        await asyncio.sleep(.5)
                with STATE_LOCK:
                    STATE[key].update(status="On-lamp animation", effect="Rainbow Flow", native_preset=preset, error=None)
                results[key] = {"ok": True}
            except asyncio.CancelledError:
                with STATE_LOCK:
                    STATE[key].update(status="Ready", error=None)
                raise
            except Exception as error:
                message = str(error) or type(error).__name__
                with STATE_LOCK:
                    STATE[key].update(status="Failed", error=message)
                results[key] = {"ok": False, "error": message}
    finally:
        BUSY.release()
    return results


async def set_colors(targets, color):
    results = {}
    for key in targets:
        with STATE_LOCK:
            STATE[key].update(status="Connecting", error=None)
        try:
            async with asyncio.timeout(55):
                device = await BleakScanner.find_device_by_address(LAMPS[key], timeout=15)
                if device is None:
                    raise RuntimeError("Lamp not found. Check power and move the laptop closer.")
                async with BleakClient(device, timeout=25) as client:
                    characteristic = client.services.get_characteristic(CHAR)
                    if characteristic is None or "write-without-response" not in characteristic.properties:
                        raise RuntimeError("Expected Bluetooth control characteristic is unavailable.")
                    await client.write_gatt_char(characteristic, color_packet(color), response=False)
                    await asyncio.sleep(0.5)
            with STATE_LOCK:
                STATE[key].update(color=color, status="Sent", error=None)
            save_colors()
            results[key] = {"ok": True}
        except Exception as error:
            message = str(error) or type(error).__name__
            with STATE_LOCK:
                STATE[key].update(status="Failed", error=message)
            results[key] = {"ok": False, "error": message}
    return results


class Handler(BaseHTTPRequestHandler):
    def respond(self, code, body, content_type="application/json"):
        data = json.dumps(body).encode() if content_type == "application/json" else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def valid_host(self):
        return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def do_GET(self):
        if not self.valid_host():
            return self.respond(403, {"error": "Local access only"})
        if self.path == "/api/state":
            with STATE_LOCK:
                return self.respond(200, STATE)
        if self.path == "/api/music":
            with STATE_LOCK:
                MUSIC["audio_age_ms"] = round((time.monotonic() - AUDIO_UPDATED) * 1000) if AUDIO_UPDATED is not None and MUSIC["status"] == "running" else None
                return self.respond(200, MUSIC)
        if self.path == "/api/native":
            return self.respond(200, {"presets": NATIVE_PRESETS})
        if self.path == "/api/effects":
            with STATE_LOCK:
                return self.respond(200, {**EFFECT, "presets": catalog()})
        files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
        if self.path not in files:
            return self.respond(404, {"error": "Not found"})
        name, mime = files[self.path]
        data = (STATIC / name).read_bytes().replace(b"__TOKEN__", TOKEN.encode())
        self.respond(200, data, mime)

    def do_POST(self):
        if not self.valid_host() or self.headers.get("X-Lamp-Token") != TOKEN:
            return self.respond(403, {"error": "Reload this local page and try again."})
        if self.path in {"/api/music/start", "/api/music/stop", "/api/music/settings"}:
            return self.music_request()
        if self.path == "/api/native/start":
            return self.native_request()
        if self.path in {"/api/effects/start", "/api/effects/stop", "/api/effects/settings"}:
            return self.effect_request()
        if self.path != "/api/color":
            return self.respond(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length))
            target, color = body.get("target"), body.get("color")
            if target not in {"one", "two", "both"} or not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("Choose a lamp and a six-digit hex color.")
        except (ValueError, AttributeError, UnicodeError) as error:
            return self.respond(400, {"error": str(error)})
        if not BUSY.acquire(blocking=False):
            return self.respond(409, {"error": "A color change is already in progress. Please wait."})
        try:
            targets = list(LAMPS) if target == "both" else [target]
            future = asyncio.run_coroutine_threadsafe(set_colors(targets, color.upper()), LOOP)
            try:
                results = future.result(timeout=120)
            except FutureTimeout:
                future.cancel()
                return self.respond(504, {"error": "Bluetooth operation timed out. Try again."})
            self.respond(200, {"results": results})
        finally:
            BUSY.release()

    def music_request(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Expected settings object")
            if self.path == "/api/music/settings":
                sensitivity, brightness = body.get("sensitivity"), body.get("brightness")
                with STATE_LOCK:
                    rate = body.get("target_hz", MUSIC["target_hz"])
                if (type(sensitivity) not in {int, float} or not 0.5 <= sensitivity <= 3
                        or type(brightness) not in {int, float} or not 0.1 <= brightness <= 1
                        or type(rate) not in {int, float} or not 10 <= rate <= 60):
                    raise ValueError("Invalid sensitivity, brightness, or update rate")
                with STATE_LOCK:
                    MUSIC.update(sensitivity=sensitivity, brightness=brightness, target_hz=rate)
            else:
                coroutine = start_music() if self.path.endswith("/start") else stop_music()
                future = asyncio.run_coroutine_threadsafe(coroutine, LOOP)
                future.result(timeout=30)
            with STATE_LOCK:
                self.respond(200, MUSIC)
        except (ValueError, UnicodeError) as error:
            self.respond(400, {"error": str(error)})
        except RuntimeError as error:
            self.respond(409, {"error": str(error)})
        except FutureTimeout:
            self.respond(504, {"error": "Music operation is taking longer than expected. Check status."})

    def native_request(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Expected settings object")
            preset, target = body.get("preset"), body.get("target", "both")
            if not isinstance(target, str) or target not in {"one", "two", "both"}:
                raise ValueError("Choose a lamp target")
            native_packet(preset)
            future = asyncio.run_coroutine_threadsafe(start_native(preset, target), LOOP)
            results = future.result(timeout=100)
            self.respond(200, {"results": results})
        except (ValueError, UnicodeError) as error:
            self.respond(400, {"error": str(error)})
        except RuntimeError as error:
            self.respond(409, {"error": str(error)})
        except FutureTimeout:
            self.respond(504, {"error": "On-lamp command is taking longer than expected. Check status."})

    def effect_request(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Expected settings object")
            if self.path.endswith("/stop"):
                coroutine = stop_effect()
            else:
                speed = body.get("speed", EFFECT.get("speed", 1.0))
                bpm = body.get("bpm", EFFECT.get("bpm", 120))
                if type(bpm) not in {int, float} or not 40 <= bpm <= 200:
                    raise ValueError("Tempo must be between 40 and 200 BPM")
                if type(speed) not in {int, float} or not 0.25 <= speed <= 3:
                    raise ValueError("Speed must be between 0.25 and 3")
                if self.path.endswith("/settings"):
                    with STATE_LOCK:
                        EFFECT.update(speed=speed, bpm=bpm)
                    with STATE_LOCK:
                        return self.respond(200, EFFECT)
                preset, target = body.get("preset"), body.get("target", "both")
                if not isinstance(preset, str) or preset not in PRESETS or not isinstance(target, str) or target not in {"one", "two", "both"}:
                    raise ValueError("Choose a listed animation and lamp target")
                coroutine = start_effect(preset, target, speed, bpm)
            asyncio.run_coroutine_threadsafe(coroutine, LOOP).result(timeout=30)
            with STATE_LOCK:
                self.respond(200, EFFECT)
        except (ValueError, UnicodeError) as error:
            self.respond(400, {"error": str(error)})
        except RuntimeError as error:
            self.respond(409, {"error": str(error)})
        except FutureTimeout:
            self.respond(504, {"error": "Animation transition is taking longer than expected. Check status."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    threading.Thread(target=LOOP.run_forever, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    signal.signal(signal.SIGTERM, request_shutdown)
    print(f"Lamp control: http://localhost:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        asyncio.run_coroutine_threadsafe(shutdown(), LOOP).result(timeout=30)
        server.server_close()
        LOOP.call_soon_threadsafe(LOOP.stop)
