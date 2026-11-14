/* Pure color analysis shared by the capture worker and synthetic-frame tests. */
(function (scope) {
  const linear = Array.from({length: 256}, (_, value) => {
    const c = value / 255;
    return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
  });
  function sample(data, width, height) {
    const black = (x, y) => {
      const index = (y * width + x) * 4;
      return Math.max(data[index], data[index + 1], data[index + 2]) <= 8;
    };
    const rowBlack = y => {
      let count = 0;
      for (let x = 0; x < width; x++) if (black(x, y)) count++;
      return count >= width * .98;
    };
    let top = 0, bottom = height, left = 0, right = width;
    while (top < Math.floor(height * .2) && rowBlack(top)) top++;
    while (bottom > height - Math.floor(height * .2) && rowBlack(bottom - 1)) bottom--;
    const columnBlack = x => {
      let count = 0;
      for (let y = top; y < bottom; y++) if (black(x, y)) count++;
      return count >= (bottom - top) * .98;
    };
    while (left < Math.floor(width * .2) && columnBlack(left)) left++;
    while (right > width - Math.floor(width * .2) && columnBlack(right - 1)) right--;
    const middle = Math.floor((left + right) / 2);
    const average = (start, end) => {
      const channels = [0, 0, 0];
      let count = 0;
      for (let y = top; y < bottom; y++) for (let x = start; x < end; x++) {
        const index = (y * width + x) * 4;
        for (let c = 0; c < 3; c++) channels[c] += linear[data[index + c]];
        count++;
      }
      return channels.map(value => count ? value / count : 0);
    };
    return [average(left, middle), average(middle, right)];
  }
  function smooth(previous, next, seconds, smoothingMs) {
    if (!previous) return next.map(color => [...color]);
    const alpha = 1 - Math.exp(-Math.max(0, seconds) / (smoothingMs / 1000));
    return next.map((color, side) => color.map((value, c) => previous[side][c] + alpha * (value - previous[side][c])));
  }
  function encode(colors, brightness = .5, swap = false) {
    const hex = color => '#' + color.map(value => {
      const c = value <= .0031308 ? value * 12.92 : 1.055 * value ** (1 / 2.4) - .055;
      return Math.round(Math.max(0, Math.min(1, c)) * brightness * 255 + 1e-9).toString(16).padStart(2, '0');
    }).join('').toUpperCase();
    return {one: hex(colors[swap ? 1 : 0]), two: hex(colors[swap ? 0 : 1])};
  }
  const api = {sample, smooth, encode};
  if (typeof module !== 'undefined') module.exports = api;
  else scope.MediaColors = api;
})(globalThis);
