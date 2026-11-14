const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness() {
  const requests = [], messages = [], closed = [];
  let feed, now = 100, current;
  const readable = new ReadableStream({start(controller) { feed = controller; }});
  class Canvas {
    getContext() { return {
      drawImage(frame) { current = frame; },
      getImageData() { return {data: current.data}; }
    }; }
  }
  const context = vm.createContext({OffscreenCanvas: Canvas, performance: {now: () => now},
    fetch: async (url, options) => { requests.push({url, body: JSON.parse(options.body), headers: options.headers}); return {ok: true, json: async () => ({ok: true})}; },
    self: {postMessage: data => messages.push(data)},
  });
  context.importScripts = () => vm.runInContext(fs.readFileSync(path.join(__dirname, '../front-end/media-colors.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../front-end/media-worker.js'), 'utf8'), context);
  return {requests, messages, closed, readable,
    send: data => context.self.onmessage({data}),
    frame(time) {
      now = time;
      const data = new Uint8ClampedArray(160 * 90 * 4);
      for (let p = 0; p < data.length; p += 4) { data[p] = 255; data[p + 3] = 255; }
      feed.enqueue({data, close() { closed.push(time); }});
    },
  };
}
test('worker samples locally, sends colors only, caps cadence and closes video frames', async () => {
  const h = harness();
  const reading = h.send({type: 'capture', stream: h.readable, token: 'test-token'});
  h.frame(100); await tick();
  assert.equal(h.requests.length, 0); // Selecting video alone does not control lamps.
  await h.send({type: 'session', session: 'session-1'});
  h.frame(150); await tick(); // Drop frames sooner than 100 ms.
  h.frame(200); await tick();
  assert.equal(h.requests.length, 1);
  assert.deepEqual(h.requests[0].body, {session: 'session-1', one: '#800000', two: '#800000'});
  assert.equal(h.requests[0].headers['X-Lamp-Token'], 'test-token');
  assert.equal(h.closed.length, 3);
  await h.send({type: 'stop', restore: false, notify: false});
  await reading;
  assert.equal(h.requests.length, 1); // Main thread owns explicit Stop restoration.
});
test('worker stream end stops session without restoring colors', async () => {
  const h = harness();
  const reading = h.send({type: 'capture', stream: h.readable, token: 'test-token'});
  await h.send({type: 'session', session: 'session-2'});
  await h.send({type: 'stop', restore: false});
  await reading;
  assert.deepEqual(h.requests.map(request => request.body), [{session: 'session-2', restore: false}]);
});
