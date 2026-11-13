# Agent guide

## Find the relevant code

- `front-end/index.html`: compact card layout, per-lamp selection, presets, music controls, and responsive tabs.
- `front-end/app.js`: UI state, authenticated API calls, music polling, and per-lamp preview colors.
- `front-end/style.css`: card sizing and viewport-responsive layouts. Preserve the user's compact menu and equal desktop card sizes; avoid promotional copy.
- `scripts/server.py`: stdlib HTTP server, Bleak control, playback capture, bass analysis, scheduling, and saved colors.
- `scripts/start.sh`: creates the root `.venv`, installs Python dependencies if absent, registers Portless when installed, then starts the server.
- `scripts/name.sh`: registers the local Portless alias, targeting backend port 8765.
- `tests/`: Python audio-response and color-persistence checks.

All project paths in Python should derive from the project root, not the caller's working directory. Shell entrypoints change to that root before resolving dependencies.

## Start and check

Run from the project root:

```bash
npm ci
npm start
```

This starts http://localhost:8765 and registers http://cool-lights.localhost:1355. The first start creates `.venv` and installs `requirements.txt`. Python 3.11+, Node 24+, a working BlueZ service, and `pactl`/`parec` are needed for the full application.

For automated checks without starting the server:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm test
bash -n scripts/start.sh scripts/name.sh
```

Python tests import `scripts.server` without launching its HTTP server or touching Bluetooth. They verify audio response and independent color packets/persistence. `npm test` also checks frontend JavaScript syntax. There is no bundled browser automation suite; do not describe syntax or mocked checks as browser layout verification.

## HTTP and frontend flow

- `GET /`: renders the page with the current process's request token.
- `GET /app.js`, `/style.css`: frontend assets from `front-end/`.
- `GET /api/state`: last sent colors and per-lamp command status; not live lamp state.
- `POST /api/color`: `{ "target": "one" | "two" | "both", "color": "#RRGGBB" }`.
- `GET /api/music`: music state, per-lamp colors, level, settings, and timing diagnostics.
- `POST /api/music/start`, `/stop`: JSON object bodies, normally `{}`.
- `POST /api/music/settings`: `sensitivity` (0.5–3), `brightness` (0.1–1), and optional `target_hz` (10–60).

All POST requests require `X-Lamp-Token`, read from the page's `lamp-token` meta element. Reload after server restart. Preserve Host validation and token checks. The server binds only to 127.0.0.1.

The browser stops music sync before a manual color command; the server rejects competing color operations while its Bluetooth lock is held. Keep controls available during active music, locking them only for in-progress transitions. Retain error feedback and recovery after failed requests.

## Bluetooth and audio behavior

The `LAMPS` mapping in `scripts/server.py` contains the two local lamp addresses. Devices advertise as `MELK-OA10WCT`; identify ownership through controlled unplug/replug comparisons rather than names alone. A scan may include neighbors' devices. Bluetooth discovery is separate from the router's Wi-Fi device inventory.

The tested characteristic is `0000fff3-0000-1000-8000-00805f9b34fb`, written without response. `color_packet` creates `7e 07 05 03 RR GG BB 10 ef`. Keep protocol changes bounded to verified commands; do not change pairing, factory-reset devices, or experiment with unrelated advertised devices as part of routine checks.

Manual control connects to selected lamps sequentially and disconnects afterward. Music mode holds both connections open, captures only the default output's `.monitor`, and dispatches separate RGB packets for the two saved colors. Never collapse those colors into a shared music color. Stop restores the colors and releases the audio process and connections.

Audio is processed in memory, without microphone capture, disk recording, or uploads. The loop analyzes 5 ms blocks, carries filter state across blocks, and skips overdue send slots. Keep the bounded 10–60 Hz setting unless a task explicitly changes it.

## State, Portless, and hardware checks

`.lamp-colors.json` at the project root holds local last-sent colors; `.lamp-colors.tmp` is used for atomic replacement. Both are ignored. Preserve local state during changes. Music settings are in memory and reset on restart. Do not copy virtual environments between directories: their entrypoints can retain absolute paths.

Portless is pinned in `package-lock.json`. It routes `cool-lights.localhost:1355` to loopback port 8765, overriding upstream Host to `localhost:8765`. Preserve this override so Host validation works. Startup disables hosts-file synchronization; no certificate or administrator setup is required. Do not stop the shared proxy without checking whether other projects need it. With a custom backend port, update the alias explicitly as documented in the README.

Before hardware tests or a server restart:

1. Inspect the running server and `/api/music`; avoid launching a second controller against the same lamps.
2. Capture current settings, colors, and running status when a restart is necessary.
3. Stop sync and the old server, then start the replacement and restore the captured session settings when appropriate.
4. Verify both local URLs, token-authenticated requests, lamp connections, and per-lamp colors.

Distinguish host-side write completion, Bluetooth connection status, and visibly confirmed lamp behavior. API timing does not measure optical refresh or end-to-end latency. Report browser or hardware verification limits plainly. Routine tests should not change lighting or play sound.

The README is public-facing: retain its experiment story and supplied Wayfair link, and avoid unsupported performance or compatibility claims. Publishing source or deploying is separate from local development; do it only when requested.
