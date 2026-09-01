import test from 'node:test';
import assert from 'node:assert/strict';

import {
  BrowserImageLoader,
  PortraitCompositor,
  buildLuminanceLut,
  composeFrame,
  deriveHairPalette,
  tintRgba,
} from '../lib/compositor.mjs';


function image(width, height, pixels) {
  return { width, height, data: new Uint8ClampedArray(pixels) };
}


function identityLut() {
  return Uint8ClampedArray.from(
    { length: 256 * 3 },
    (_, offset) => Math.floor(offset / 3),
  );
}


function identityToneMap() {
  return Uint8ClampedArray.from({ length: 256 }, (_, value) => value);
}


test('hue 210 derives the documented dark OKLCH hair palette', () => {
  const palette = deriveHairPalette(210);
  assert.equal(palette.algorithmRevision, 'oklch-five-anchor-browser-v06');
  assert.equal(palette.hueDegrees, 210);
  assert.deepEqual(
    Object.values(palette.stops).map(({ srgb8 }) => srgb8),
    [[0, 35, 47], [0, 94, 119], [0, 148, 167], [74, 167, 183]],
  );
  const lut = buildLuminanceLut(palette);
  assert.deepEqual([...lut.slice(0, 3)], [0, 0, 0]);
  assert.deepEqual([...lut.slice(32 * 3, 32 * 3 + 3)], [0, 35, 47]);
  assert.deepEqual([...lut.slice(255 * 3)], [74, 167, 183]);
});


test('hair tint changes only mask-owned RGB and preserves every alpha byte', () => {
  const source = new Uint8ClampedArray([
    40, 50, 60, 0,
    80, 90, 100, 128,
    120, 130, 140, 255,
  ]);
  const mask = new Uint8ClampedArray([255, 0, 255]);
  const output = tintRgba(source, mask, identityLut(), identityToneMap());
  assert.deepEqual([output[3], output[7], output[11]], [0, 128, 255]);
  assert.deepEqual([...output.slice(4, 7)], [...source.slice(4, 7)]);
  assert.notDeepEqual([...output.slice(8, 11)], [...source.slice(8, 11)]);
});


test('ownership-reset restores checkpoint pixels instead of drawing the head mask', () => {
  const bindings = [
    { order: 0, role: 'face_expression_base', operation: 'alpha-composite', path: 'base' },
    { order: 1, role: 'clothing_main', operation: 'alpha-composite', path: 'clothes' },
    { order: 2, role: 'face_expression_head', operation: 'ownership-reset', path: 'head-mask' },
  ];
  const sources = new Map([
    ['base', image(1, 1, [210, 30, 20, 255])],
    ['clothes', image(1, 1, [10, 20, 230, 255])],
    ['head-mask', image(1, 1, [0, 255, 0, 255])],
  ]);
  const frame = composeFrame({ hairHue: 210 }, bindings, sources);
  assert.deepEqual([...frame.data], [210, 30, 20, 255]);
});


function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}


test('stale async render never replaces the latest committed frame', async () => {
  const pending = new Map([
    ['old', deferred()],
    ['new', deferred()],
  ]);
  const commits = [];
  const canvas = {
    width: 1,
    height: 1,
    getContext: () => ({ putImageData: (frame) => commits.push(frame.data[0]) }),
  };
  const compositor = new PortraitCompositor({
    outputCanvas: canvas,
    imageLoader: { load: (path) => pending.get(path).promise },
    frameComposer: (_selection, bindings, sources) => sources.get(bindings[0].path),
  });
  const oldRender = compositor.render(
    { recipe: { recordId: 'old' } },
    [{ order: 0, role: 'plain', operation: 'alpha-composite', path: 'old' }],
  );
  const newRender = compositor.render(
    { recipe: { recordId: 'new' } },
    [{ order: 0, role: 'plain', operation: 'alpha-composite', path: 'new' }],
  );

  pending.get('new').resolve(image(1, 1, [22, 0, 0, 255]));
  assert.deepEqual(await newRender, {
    committed: true,
    recipe: { recordId: 'new' },
  });
  pending.get('old').resolve(image(1, 1, [11, 0, 0, 255]));
  assert.deepEqual(await oldRender, { committed: false });
  assert.deepEqual(commits, [22]);
  assert.equal(compositor.committedRecipe.recordId, 'new');
});


test('browser image cache is bounded and evicts the least-recently-used asset', async () => {
  const fetched = [];
  const loader = new BrowserImageLoader({
    maxEntries: 2,
    fetchImpl: async (path) => {
      fetched.push(path);
      return { ok: true, status: 200, blob: async () => ({ path }) };
    },
    bitmapFactory: async () => ({ width: 1254, height: 1254, close() {} }),
    canvasFactory: () => ({
      getContext: () => ({
        drawImage() {},
        getImageData: () => ({ data: new Uint8ClampedArray(4) }),
      }),
    }),
  });

  await loader.load('assets/a.png');
  await loader.load('assets/b.png');
  await loader.load('assets/a.png');
  await loader.load('assets/c.png');
  await loader.load('assets/b.png');

  assert.deepEqual(fetched, [
    './assets/a.png',
    './assets/b.png',
    './assets/c.png',
    './assets/b.png',
  ]);
});
