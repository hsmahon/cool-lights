const {test} = require('node:test');
const assert = require('node:assert/strict');
const {sample, smooth, encode} = require('../front-end/media-colors.js');
function frame(width, height, pixel) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) data.set([...pixel(x, y), 255], (y * width + x) * 4);
  return data;
}
test('left/right halves and swap mapping', () => {
  const data = frame(20, 10, x => x < 10 ? [255, 0, 0] : [0, 0, 255]);
  const values = sample(data, 20, 10);
  assert.deepEqual(encode(values, 1), {one: '#FF0000', two: '#0000FF'});
  assert.deepEqual(encode(values, 1, true), {one: '#0000FF', two: '#FF0000'});
});
test('letterbox and pillarbox bars do not dilute picture colors', () => {
  const data = frame(20, 10, (x, y) => y < 2 || y >= 8 || x < 2 || x >= 18 ? [0, 0, 0] : x < 10 ? [255, 0, 0] : [0, 255, 0]);
  assert.deepEqual(encode(sample(data, 20, 10), 1), {one: '#FF0000', two: '#00FF00'});
});
test('black scenes remain black; dim scenes stay dim', () => {
  assert.deepEqual(encode(sample(frame(20, 10, () => [0, 0, 0]), 20, 10)), {one: '#000000', two: '#000000'});
  assert.deepEqual(encode(sample(frame(20, 10, () => [12, 12, 12]), 20, 10)), {one: '#060606', two: '#060606'});
});
test('averages light linearly and caps encoded brightness', () => {
  const data = frame(20, 10, (x, y) => (x + y) % 2 ? [255, 255, 255] : [0, 0, 0]);
  assert.deepEqual(encode(sample(data, 20, 10), 1), {one: '#BCBCBC', two: '#BCBCBC'});
  assert.deepEqual(encode([[1, 1, 1], [1, 1, 1]], .5), {one: '#808080', two: '#808080'});
});
test('smoothing uses elapsed time and converges without overshoot', () => {
  const dark = [[0, 0, 0], [0, 0, 0]], light = [[1, 1, 1], [1, 1, 1]];
  const initial = smooth(dark, light, .1, 350);
  assert.ok(initial[0][0] > 0 && initial[0][0] < .3);
  const split = smooth(initial, light, .1, 350);
  assert.ok(Math.abs(split[0][0] - smooth(dark, light, .2, 350)[0][0]) < 1e-12);
  assert.deepEqual(smooth(null, light, 0, 350), light);
});
