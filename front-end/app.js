(() => {
  const $ = id => document.getElementById(id);
  const root = document.documentElement;
  const token = document.querySelector('meta[name="lamp-token"]').content;
  let busy = false;
  let musicActive = false;
  let musicPending = false;
  let musicSettingsLoaded = false;
  let effectActive = false;
  let catalogLoaded = false;
  let currentPreset = null;
  const target = () => document.querySelector('input[name="target"]:checked').value;
  function setPanel(panel) {
    $('workspace').dataset.panel = panel;
    $('color-tab').setAttribute('aria-selected', String(panel === 'color'));
    $('music-tab').setAttribute('aria-selected', String(panel === 'music'));
  }
  $('color-tab').addEventListener('click', () => setPanel('color'));
  $('music-tab').addEventListener('click', () => setPanel('music'));
  function preview(color) {
    root.style.setProperty('--accent', color);
    const selected = target();
    if (selected !== 'two') root.style.setProperty('--one', color);
    if (selected !== 'one') root.style.setProperty('--two', color);
  }
  function selectColor(color) {
    $('color').value = color;
    $('hex').value = color.toUpperCase();
    $('hex').removeAttribute('aria-invalid');
    $('hex-error').textContent = '';
    preview(color);
  }
  function feedback(message, error = false) {
    $('feedback').textContent = message;
    $('feedback').classList.toggle('error', error);
  }
  async function refresh() {
    try {
      const response = await fetch('/api/state');
      if (!response.ok) throw new Error('Status unavailable');
      const state = await response.json();
      for (const [key, value] of Object.entries(state)) {
        $('state-' + key).textContent = value.status === 'Animation' ? value.effect + ' · animation' : value.status === 'Music sync' ? 'Music sync · bass pulse' : value.status === 'Connecting' ? 'Connecting…' : value.error ? 'Could not send · try again' : value.color ? value.color + ' · last sent' : 'No color sent this session';
        $('dot-' + key).style.background = value.color || '#625a55';
        $('state-' + key).title = value.error || 'Last command sent, not a live reading from the lamp';
      }
      return state;
    } catch (error) {
      if (!busy) feedback('Local server unavailable. Restart it and reload this page.', true);
    }
  }
  async function apply(color) {
    if (busy || musicPending) return;
    if (!/^#[0-9a-f]{6}$/i.test(color)) {
      $('hex').setAttribute('aria-invalid', 'true');
      $('hex-error').textContent = 'Use #RRGGBB';
      $('hex').focus();
      return;
    }
    const selected = target();
    selectColor(color);
    busy = true;
    updateControls();
    $('apply').textContent = 'Sending over Bluetooth…';
    feedback(selected === 'both' ? 'Connecting to each lamp in turn. This can take up to a minute per lamp.' : 'Connecting to your lamp…');
    try {
      await effectsPost('stop');
      effectActive = false;
      if (musicActive) {
        feedback('Stopping music sync, then applying your color…');
        renderMusic(await musicPost('stop'));
      }
      const response = await fetch('/api/color', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Lamp-Token': token}, body: JSON.stringify({target: selected, color})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Unable to send color');
      const failed = Object.entries(data.results).filter(([,result]) => !result.ok);
      if (failed.length) feedback(failed.map(([key, result]) => `Lamp ${key === 'one' ? '01' : '02'}: ${result.error}`).join(' '), true);
      else feedback(`Sent ${color.toUpperCase()} to ${selected === 'both' ? 'both lamps' : selected === 'one' ? 'lamp 01' : 'lamp 02'}.`);
    } catch (error) {
      feedback(error.message, true);
    } finally {
      busy = false;
      updateControls();
      $('apply').innerHTML = 'Apply color <span>↗</span>';
      restorePreview(await refresh());
    }
  }
  $('color').addEventListener('input', event => selectColor(event.target.value));
  $('hex').addEventListener('input', event => { if (/^#[0-9a-f]{6}$/i.test(event.target.value)) selectColor(event.target.value); });
  $('hex').addEventListener('keydown', event => { if (event.key === 'Enter') apply($('hex').value); });
  document.querySelectorAll('input[name="target"]').forEach(el => el.addEventListener('change', () => preview($('color').value)));
  $('apply').addEventListener('click', () => apply($('hex').value));
  $('presets').addEventListener('click', event => { const button = event.target.closest('button[data-color]'); if (button) apply(button.dataset.color); });
  $('off').addEventListener('click', () => apply('#000000'));
  function updateControls() {
    const locked = busy || musicPending;
    document.querySelectorAll('.targets input, .picker input, #hex, #apply, #presets button, #effect-presets button, #effect-speed, #effect-bpm, #preset-kind, #off').forEach(el => el.disabled = locked);
    $('music-toggle').disabled = busy || musicPending;
    $('effect-stop').disabled = locked || !effectActive;
  }
  function restorePreview(state) {
    if (!state) return;
    for (const key of ['one', 'two']) {
      if (state[key].color) root.style.setProperty('--' + key, state[key].color);
    }
  }
  async function musicPost(path, body = {}) {
    const response = await fetch('/api/music/' + path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Lamp-Token': token}, body: JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Music sync request failed');
    return data;
  }
  function renderMusic(state) {
    if (!musicSettingsLoaded) {
      $('sensitivity').value = state.sensitivity;
      $('brightness').value = Math.round(state.brightness * 100);
      $('sensitivity-value').textContent = state.sensitivity + '×';
      $('brightness-value').textContent = Math.round(state.brightness * 100) + '%';
      $('rate').value = state.target_hz;
      $('rate-value').textContent = state.target_hz + ' Hz';
      musicSettingsLoaded = true;
    }
    musicActive = ['starting', 'running', 'stopping'].includes(state.status);
    $('music-toggle').textContent = musicActive ? 'Stop music sync ■' : 'Start music sync ♫';
    $('music-toggle').disabled = busy || musicPending || state.status === 'stopping';
    $('music-meter').value = state.level;
    $('music-status').textContent = state.error ? state.error : state.status === 'starting' ? 'Connecting both lamps…' : state.status === 'running' ? (state.audio_age_ms > 1000 ? 'Waiting for playback audio…' : 'Laptop playback · ' + (state.level > 0.03 ? 'bass detected' : 'waiting for music')) + ` · ${state.analysis_ms} ms analysis · ${state.update_hz || 0} updates/s · ${state.write_ms || 0} ms write` : state.status === 'stopping' ? 'Restoring previous colors…' : 'Stopped · returns to your previous colors when stopped.';
    $('music-status').classList.toggle('error', Boolean(state.error));
    updateControls();
    if (state.status === 'stopping') $('music-toggle').disabled = true;
    if (state.status === 'running') {
      const intensity = state.brightness * (0.04 + 0.96 * state.level);
      for (const key of ['one', 'two']) {
        const color = state.colors[key];
        const rgb = color.slice(1).match(/../g).map(v => Math.round(parseInt(v, 16) * intensity).toString(16).padStart(2, '0')).join('');
        root.style.setProperty('--' + key, '#' + rgb);
      }
    }
  }
  async function pollMusic() {
    try {
      const response = await fetch('/api/music');
      if (!response.ok) throw new Error('Music status unavailable');
      const state = await response.json();
      renderMusic(state);
    } catch (error) {
      $('music-status').textContent = 'Music status unavailable. Reload after restarting the server.';
    }
  }
  $('music-toggle').addEventListener('click', async () => {
    const stopping = musicActive;
    musicPending = true;
    updateControls();
    $('music-status').textContent = stopping ? 'Stopping…' : 'Starting…';
    try {
      if (!stopping && effectActive) {
        await effectsPost('stop');
        effectActive = false;
      }
      if (!stopping) await musicPost('settings', musicSettings());
      const state = await musicPost(stopping ? 'stop' : 'start');
      renderMusic(state);
      if (stopping) restorePreview(await refresh());
    } catch (error) {
      $('music-status').textContent = error.message;
    } finally {
      musicPending = false;
      updateControls();
    }
  });
  function musicSettings() {
    return {sensitivity: Number($('sensitivity').value), brightness: Number($('brightness').value) / 100, target_hz: Number($('rate').value)};
  }
  for (const id of ['sensitivity', 'brightness', 'rate']) {
    $(id).addEventListener('input', () => {
      $(id + '-value').textContent = $(id).value + (id === 'sensitivity' ? '×' : id === 'rate' ? ' Hz' : '%');
    });
    $(id).addEventListener('change', async () => {
      try {
        await musicPost('settings', musicSettings());
      } catch (error) { $('music-status').textContent = error.message; }
    });
  }
  async function effectsPost(path, body = {}) {
    const response = await fetch('/api/effects/' + path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Lamp-Token': token}, body: JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Animation request failed');
    return data;
  }
  async function pollEffects() {
    try {
      const response = await fetch('/api/effects');
      if (!response.ok) throw new Error('Animation status unavailable');
      const state = await response.json();
      if (!catalogLoaded) {
        for (const preset of state.presets) {
          const button = document.createElement('button');
          button.dataset.effect = preset.id;
          button.title = preset.description + (preset.audio ? ' · laptop playback audio' : '');
          button.setAttribute('aria-pressed', 'false');
          const swatch = document.createElement('i');
          swatch.style.background = `linear-gradient(135deg, ${preset.palette.join(',')})`;
          button.append(swatch, document.createTextNode(preset.name));
          $('effect-presets').append(button);
        }
        catalogLoaded = true;
      }
      currentPreset = state.preset;
      $('tempo-control').hidden = state.preset !== 'bpm';
      $('effect-speed').hidden = state.preset === 'bpm';
      if (document.activeElement !== $('effect-bpm')) $('effect-bpm').value = state.bpm || 120;
      effectActive = ['starting', 'running', 'stopping'].includes(state.status);
      updateControls();
      document.querySelectorAll('#effect-presets button').forEach(button => button.setAttribute('aria-pressed', String(effectActive && button.dataset.effect === state.preset)));
      if (state.status === 'running' && !busy && !musicPending) {
        for (const [key, color] of Object.entries(state.colors)) root.style.setProperty('--' + key, color);
      }
      if (state.error) feedback(state.error, true);
      else if (effectActive && ['dj-light', 'freqwave'].includes(state.preset)) feedback((state.preset === 'dj-light' ? 'DJ Light' : 'Freqwave') + (state.audio_ready ? ' · playback capture active' : ' · waiting for playback audio…'));
    } catch (error) {
      if (!busy) feedback(error.message, true);
    }
  }
  $('preset-kind').addEventListener('change', () => {
    const effects = $('preset-kind').value === 'effects';
    $('color-panel').dataset.mode = effects ? 'effects' : 'solid';
    document.querySelector('.color-entry').hidden = effects;
    $('apply').hidden = effects;
    $('presets').hidden = effects;
    $('effect-presets').hidden = !effects;
    $('effect-actions').hidden = !effects;
  });
  $('effect-presets').addEventListener('click', async event => {
    const button = event.target.closest('button[data-effect]');
    if (!button || busy || musicPending) return;
    busy = true;
    updateControls();
    feedback('Starting ' + button.textContent.trim() + '…');
    try {
      const state = await effectsPost('start', {preset: button.dataset.effect, target: target(), speed: button.dataset.effect === 'bpm' ? 1 : Number($('effect-speed').value), bpm: Number($('effect-bpm').value)});
      effectActive = ['starting', 'running'].includes(state.status);
      musicActive = false;
      feedback(button.textContent.trim() + ' · whole-lamp animation');
    } catch (error) { feedback(error.message, true); }
    finally { busy = false; updateControls(); await pollEffects(); await refresh(); }
  });
  $('effect-stop').addEventListener('click', async () => {
    if (busy || musicPending) return;
    busy = true;
    updateControls();
    try {
      await effectsPost('stop');
      effectActive = false;
      feedback('Animation stopped. Saved colors restored.');
      restorePreview(await refresh());
    } catch (error) { feedback(error.message, true); }
    finally { busy = false; updateControls(); }
  });
  $('effect-speed').addEventListener('change', async () => {
    if (!effectActive) return;
    try { await effectsPost('settings', {speed: Number($('effect-speed').value)}); }
    catch (error) { feedback(error.message, true); }
  });
  $('effect-bpm').addEventListener('change', async () => {
    const bpm = Number($('effect-bpm').value);
    if (bpm < 40 || bpm > 200) { feedback('Choose 40–200 BPM.', true); return; }
    if (!effectActive || currentPreset !== 'bpm') return;
    try { await effectsPost('settings', {bpm, speed: 1}); }
    catch (error) { feedback(error.message, true); }
  });
  pollEffects();
  setInterval(pollEffects, 500);
  pollMusic();
  setInterval(pollMusic, 500);
  refresh();
  setInterval(refresh, 2000);
})();
