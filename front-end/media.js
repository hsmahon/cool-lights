(() => {
  const $ = id => document.getElementById(id);
  const token = document.querySelector('meta[name="lamp-token"]').content;
  let worker = null, stream = null, session = null, colors = null, transitioning = false, localActive = false;
  let generation = 0, chosen = false;
  const message = (text, error = false) => { $('media-status').textContent = text; $('media-status').classList.toggle('error', error); };
  function controls() {
    $('media-choose').disabled = transitioning;
    $('media-toggle').disabled = transitioning || (!chosen && !session);
    $('media-toggle').textContent = session ? 'Stop media sync ■' : 'Start media sync';
  }
  function settings() { return {brightness: Number($('media-brightness').value) / 100, smoothing: Number($('media-smoothing').value), swap: $('media-swap').checked}; }
  async function post(path, body, keepalive = false) {
    const response = await fetch('/api/media/' + path, {method: 'POST', keepalive,
      headers: {'Content-Type': 'application/json', 'X-Lamp-Token': token}, body: JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Media sync request failed');
    return data;
  }
  async function release(restore = false, notify = true) {
    generation++;
    const oldSession = session, oldWorker = worker;
    session = null; worker = null; colors = null; chosen = false; localActive = false;
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    if (oldWorker) {
      oldWorker.postMessage({type: 'stop', restore: false, notify: false});
      setTimeout(() => oldWorker.terminate(), 1000);
    }
    controls();
    if (notify && oldSession) {
      try {
        const state = await post('stop', {session: oldSession, restore}, true);
        if (restore && state.error) throw new Error(state.error);
      } catch (error) { if (restore) throw error; }
    }
  }
  $('media-choose').addEventListener('click', async () => {
    if (transitioning) return;
    // Selection happens directly in the click handler to retain user activation.
    if (!navigator.mediaDevices?.getDisplayMedia || !window.Worker) {
      message('Screen sharing is unavailable. Open this local app in a supported desktop browser.', true); return;
    }
    transitioning = true; controls();
    let selected;
    try {
      selected = await navigator.mediaDevices.getDisplayMedia({video: {frameRate: {ideal: 10, max: 15}}, audio: false});
      await release(false);
      stream = selected;
      const id = generation;
      worker = new Worker('/media-worker.js');
      const current = worker;
      const capabilities = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Capture worker did not start.')), 3000);
        current.onmessage = event => { if (event.data.type === 'capabilities') { clearTimeout(timeout); resolve(event.data); } };
        current.onerror = () => { clearTimeout(timeout); reject(new Error('Capture worker could not load.')); };
        current.postMessage({type: 'probe'});
      });
      if (id !== generation) { selected.getTracks().forEach(track => track.stop()); return; }
      if (!capabilities.canvas) throw new Error('This browser does not support background video analysis. Try a current desktop Chromium browser.');
      current.onmessage = async ({data}) => {
        if (id !== generation) return;
        if (data.type === 'colors') {
          colors = data.colors;
          if (!chosen) { chosen = true; message('Video selected. Ready to start.'); controls(); }
          if (session) for (const [key, color] of Object.entries(colors)) document.documentElement.style.setProperty('--' + key, color);
        } else if (data.type === 'error' || data.type === 'ended') {
          await release(false);
          message(data.message || 'Screen sharing ended. Last colors retained.', data.type === 'error');
        }
      };
      current.onerror = async () => { await release(false); message('Video analysis stopped. Choose your video again.', true); };
      current.postMessage({type: 'settings', settings: settings()});
      const track = selected.getVideoTracks()[0];
      track.addEventListener('ended', async () => {
        if (id !== generation) return;
        await release(false); message('Screen sharing ended. Last colors retained.');
      });
      if (capabilities.processor) current.postMessage({type: 'capture', token, track}, [track]);
      else if (typeof window.MediaStreamTrackProcessor !== 'undefined') {
        const readable = new window.MediaStreamTrackProcessor({track, maxBufferSize: 1}).readable;
        current.postMessage({type: 'capture', token, stream: readable}, [readable]);
      } else throw new Error('This browser lacks background video-frame processing. Try a current desktop Chromium browser.');
      message('Reading selected video…');
      setTimeout(async () => {
        if (id === generation && !chosen) { await release(false); message('No video frames arrived. Try another source or browser; protected video may be unavailable.', true); }
      }, 7000);
    } catch (error) {
      if (selected) { selected.getTracks().forEach(track => track.stop()); await release(false); }
      if (error.name === 'NotAllowedError') message('Selection cancelled or permission denied. Lighting unchanged.');
      else message(error.message, true);
    } finally { transitioning = false; controls(); }
  });
  $('media-toggle').addEventListener('click', async () => {
    if (transitioning) return;
    transitioning = true; controls();
    try {
      if (session) { await release(true); message('Stopped. Saved colors restored.'); }
      else {
        if (!colors || !worker) throw new Error('Choose a screen or window first.');
        const id = generation, current = worker;
        const state = await post('start', colors);
        if (id !== generation) { await post('stop', {session: state.session, restore: false}); return; }
        session = state.session; localActive = true;
        current.postMessage({type: 'session', session});
        message('Connecting lamps…');
      }
    } catch (error) { message(error.message, true); }
    finally { transitioning = false; controls(); }
  });
  for (const id of ['media-brightness', 'media-smoothing', 'media-swap']) $(id).addEventListener('input', () => {
    $('media-brightness-value').textContent = $('media-brightness').value + '%';
    $('media-smoothing-value').textContent = $('media-smoothing').value + ' ms';
    worker?.postMessage({type: 'settings', settings: settings()});
  });
  // Mode buttons release capture immediately; the server also enforces exclusivity.
  window.addEventListener('lighting-mode-change', async () => { if (worker) { await release(false); message('Media sync ended. Lighting mode changed.'); } });
  window.addEventListener('pagehide', () => { release(false); });
  async function poll() {
    try {
      const response = await fetch('/api/media');
      if (!response.ok) throw new Error('Media status unavailable');
      const state = await response.json();
      if (localActive && state.session === session) {
        if (!['starting', 'running'].includes(state.status)) {
          await release(false, false); message(state.error || 'Media sync stopped. Last colors retained.', Boolean(state.error));
        } else message(state.status === 'starting' ? 'Connecting both lamps…' : `Matching video · ${state.update_hz} updates/s · keep this tab open`);
      }
    } catch (error) {
      if (localActive) { await release(false, false); message('Server unavailable. Media sync ended.', true); }
    }
    setTimeout(poll, 750);
  }
  controls(); poll();
})();
