importScripts('/media-colors.js');
let reader, track, session = null, token, last = 0, smoothed = null;
let settings = {brightness: .5, smoothing: 350, swap: false};
let ended = false;
const post = async (path, body, keepalive = false) => {
  const response = await fetch('/api/media/' + path, {method: 'POST', keepalive,
    headers: {'Content-Type': 'application/json', 'X-Lamp-Token': token}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Media sync unavailable');
  return data;
};
async function close(restore = false, notify = true) {
  ended = true;
  const active = session;
  session = null;
  if (reader) await reader.cancel().catch(() => {});
  if (track) track.stop();
  if (active && notify) await post('stop', {session: active, restore}, true).catch(() => {});
}
async function consume(stream) {
  reader = stream.getReader();
  const canvas = new OffscreenCanvas(160, 90);
  const context = canvas.getContext('2d', {willReadFrequently: true});
  try {
    while (!ended) {
      const {value: frame, done} = await reader.read();
      if (done) break;
      let colors;
      try {
        const now = performance.now();
        if (now - last < 100) continue;
        context.drawImage(frame, 0, 0, 160, 90);
        const values = MediaColors.sample(context.getImageData(0, 0, 160, 90).data, 160, 90);
        smoothed = MediaColors.smooth(smoothed, values, (now - last) / 1000, settings.smoothing);
        colors = MediaColors.encode(smoothed, settings.brightness, settings.swap);
        last = now;
      } finally { frame.close(); }
      if (!colors) continue;
      self.postMessage({type: 'colors', colors});
      // Await one request; track processor buffers only the newest video frame.
      if (session) await post('frame', {session, ...colors});
    }
    if (!ended) self.postMessage({type: 'ended'});
  } catch (error) {
    if (!ended) self.postMessage({type: 'error', message: error.message});
  } finally { await close(false); }
}
self.onmessage = async ({data}) => {
  if (data.type === 'probe') {
    self.postMessage({type: 'capabilities', processor: typeof MediaStreamTrackProcessor !== 'undefined', canvas: typeof OffscreenCanvas !== 'undefined'});
  } else if (data.type === 'capture') {
    token = data.token;
    try {
      track = data.track;
      const stream = data.stream || new MediaStreamTrackProcessor({track, maxBufferSize: 1}).readable;
      await consume(stream);
    } catch (error) { self.postMessage({type: 'error', message: error.message}); await close(false); }
  } else if (data.type === 'session') session = data.session;
  else if (data.type === 'settings') settings = {...settings, ...data.settings};
  else if (data.type === 'stop') { await close(data.restore, data.notify !== false); self.postMessage({type: 'closed'}); }
};
