# Agent guide

## Find the relevant code

- `front-end/index.html`: compact card layout, per-lamp selection, presets, music controls, and responsive tabs.
- `front-end/app.js`: UI state, authenticated API calls, music polling, and per-lamp preview colors.
- `front-end/style.css`: card sizing and viewport-responsive layouts. Preserve the user's compact menu and equal desktop card sizes; avoid promotional copy.
- `scripts/server.py`: stdlib HTTP server, Bleak control, playback capture, bass analysis, scheduling, and saved colors.
- `scripts/effects.py`: 24 original whole-lamp animation definitions and deterministic RGB frame generation; sources are recorded in `docs/preset-research.md`.
- `scripts/spectrum.py`: rolling 256-sample NumPy FFT, updated every four 5 ms blocks for playback-reactive presets.
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
- `GET /api/effects`: animation status, current preview colors, and the preset catalog.
- `POST /api/effects/start`: `{ "preset": <catalog id>, "target": "one" | "two" | "both", "speed": 0.25–3, "bpm": 40–200 }`.
- `POST /api/effects/stop`: `{}`; stops and restores selected lamps' static colors.
- `POST /api/effects/settings`: `{ "speed": 0.25–3, "bpm": 40–200 }`; changes running speed without resetting phase.

All POST requests require `X-Lamp-Token`, read from the page's `lamp-token` meta element. Reload after server restart. Preserve Host validation and token checks. The server binds only to 127.0.0.1.

The browser stops music sync before a manual color command; the server rejects competing color operations while its Bluetooth lock is held. Keep controls available during active music, locking them only for in-progress transitions. Retain error feedback and recovery after failed requests.

Animation start stops the previous effect and music sync before taking the same Bluetooth lock. Music start stops animations. The browser stops animation before a static color command. Preserve cancellation cleanup and recovery after missing devices, and never save generated effect frames into `.lamp-colors.json`. Effects restore static colors on in-app Stop or error. Server shutdown sets SHUTTING_DOWN before cancellation and releases audio/connections without replacement RGB writes, leaving the last frame on the lamps. Do not persist animation frames into saved static colors. Laptop effects use verified RGB writes at 20 Hz. The separate allowlisted Rainbow Flow command uses the tested on-lamp mode; segment writes remain unverified. Don't describe the UI's gradient swatches as verified per-segment gradients.

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

The animation gallery renders catalog order in exactly four columns and six rows; retain all 24 buttons without pagination. Custom color entry is hidden in animation mode. BPM uses manual tempo (120 default). DJ Light and Freqwave use shared playback capture/cleanup and the Music settings sensitivity/brightness. They are mutually exclusive with bass sync; no second capture process. Audio readiness means fresh samples, not detected music. Spectrum analysis is 32 ms refreshed every 20 ms; do not label it 5 ms frequency analysis. Test spectrum tones and capture failure/cancellation without real audio playback.

## On-lamp animations

Rainbow Flow (`rainbow-flow`) is a separate firmware animation, not one of the 24 laptop-generated effects. On 2026-11-14, mode 199 (`7e 07 03 c7 ff ff ff 00 ef`) was sent once to Lamp 01, then the sender disconnected and exited. The user visually confirmed it kept animating. Do not claim Lamp 02 visual confirmation or support for other firmware IDs without testing.

`GET /api/native` lists the allowlisted presets; `POST /api/native/start` accepts `preset` and `target` with the same token and Host protections as other commands. It stops laptop audio/effects, acquires BUSY, connects/writes/disconnects once per target, and releases BUSY. It must not retain a client, generate RGB frames, restore colors at disconnect, or overwrite saved static colors. It creates no ongoing animation task. Shutdown must leave native animations untouched. Solid RGB commands override native animations. Native state is last-command status held in memory, not readback or persisted firmware detection after restart.

The default UI category is On-lamp animations; Laptop animations retains the 24-item 4-by-6 grid. Do not misleadingly map the custom presets to firmware modes with unrelated effects.

## Shutdown contract and regression checks

The original shutdown called `stop_effect()` and `stop_music()` directly, so task cleanup sent saved RGB colors and replaced the visible animation frame. `shutdown()` now sets `SHUTTING_DOWN = True` before cancelling either task. Both `effect_loop()` and `music_loop()` still close playback capture and release Bluetooth clients/locks, but their restoration loops skip all RGB writes during process shutdown. Ctrl+C reaches the main `finally` block; SIGTERM is translated to `KeyboardInterrupt` by `request_shutdown()` and reaches the same path. Do not set this flag during ordinary UI Stop or effect transitions: those operations should still restore saved static colors.

Keeping a last RGB frame is different from keeping an animation alive. Host-generated effects freeze when their task exits. Native Rainbow Flow continues because `start_native()` sends mode 199 once and releases the connection; no server task generates its frames. Starting/stopping the server must not reconnect to a native lamp to restore a static color. A later explicit solid-color command can replace the native mode.

Keep these invariants covered in `tests/test_effects.py`:

- Shutdown adds no RGB writes after the last completed laptop-effect or music frame, while capture, clients, and BUSY are released.
- Ordinary in-app Stop restores each lamp’s own saved color.
- Starting Rainbow Flow writes exactly the native mode packet to the requested target, disconnects, and holds no background animation task or BUSY lock.
- Shutdown after a native start sends no additional packet; saved static colors are not overwritten by native status or transient RGB frames.
- Native connection failure releases the lock, and unsupported preset IDs are rejected before device writes.

Verification evidence: the owner confirmed static color retention after updated server shutdown, then separately confirmed native mode 199 continued animating on Lamp 01 after a standalone process disconnected and exited. Do not generalize that optical confirmation to Lamp 02 or power-cycle retention. Automated tests prove command/lifecycle behavior, not optical output. Routine release checks must not interrupt or change the user’s current lamps.

## Browser media sync

`front-end/media.js` owns the screen picker, capture session, controls, and lifecycle. `media-worker.js` analyzes video using `media-colors.js`; feature-detect the video processor in a dedicated worker, then fall back to a main-thread processor with a transferable readable stream. Neither path uses animation callbacks or main-thread timers for frame sampling, because the user watches video in another tab. If both processor routes or OffscreenCanvas are unavailable, show an explicit unsupported-browser error. Never capture without the user selecting a source, request audio, record frames, or transmit image data.

`GET /api/media` exposes controller status, session, last sent colors, frame count/rate, input age, and errors. Token-protected POST endpoints are `/api/media/start` (`one`, `two` hex colors), `/api/media/frame` (`session`, `one`, `two`), and `/api/media/stop` (`session`, `restore` boolean). Start returns a fresh session ID; frame and stop reject stale IDs. Only the current tab owns its session; a second active start returns 409. All bodies retain the 1024-byte limit and existing Host/token checks.

`scripts/media.py` owns persistent paired Bluetooth clients, BUSY, a newest-frame buffer, a fixed 10 Hz send ceiling, and a two-second frame lease. Keep frame acceptance on the asyncio loop. Connect/write errors, stale frames, permission/capture loss, tab closure, and shutdown must release resources. The lease also cancels connection attempts when the tab disappears. The browser worker sends at most one frame request at a time. Explicit Stop restores static colors; capture loss, tab closure, mode handoffs, and shutdown stop without restoration. The worker must not race an explicit restore request with its own no-restore stop: the main thread owns explicit Stop and tells the worker not to notify the server.

Media start stops music and laptop effects. Other lighting modes stop media before acquiring BUSY. Never overwrite STATE's saved `color` or `.lamp-colors.json` with media frames. `media_color` and Media paused describe last-command preview only. Default left/right mapping is Lamp 01/Lamp 02, brightness .5, smoothing 350 ms; swap is applied in the browser. Linear-light sampling trims uniform black borders up to 20% per edge, keeps dark scenes dim, and closes every VideoFrame, including dropped frames.

The Sync card's visible Music/Media tab buttons initialize before other controls and polling, support click and arrow-key selection, and preserve equal desktop cards and responsive no-scroll controls; it does not change the 24-preset gallery. `npm test` includes synthetic color and worker tests plus Python controller/HTTP tests. They do not prove browser compatibility or optical performance. Do not recreate test_ui.cjs. Manual acceptance remains: picker permission/cancel, alternate video tab, fullscreen, connected display, visible lamp mapping/smoothing, tab closure, and server shutdown. Never claim capture-protected content is supported or attempt to bypass it. The browser host was unavailable during this implementation, so these manual checks must be stated as outstanding until observed.
