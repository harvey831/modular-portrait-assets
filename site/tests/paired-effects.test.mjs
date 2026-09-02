import test from 'node:test';
import assert from 'node:assert/strict';
import * as compositor from '../lib/compositor.mjs';

const rgba = (...values) => new Uint8ClampedArray(values);
const image = (data) => ({ width: data.length / 4, height: 1, data });

test('paired extraction removes unchanged skin instead of recolouring it', () => {
  assert.equal(typeof compositor.extractPairedEffect, 'function');
  const dry = rgba(200, 150, 100, 255, 200, 150, 100, 255);
  const overlay = rgba(200, 150, 100, 240, 200, 75, 50, 128);
  const original = new Uint8ClampedArray(overlay);
  const effect = compositor.extractPairedEffect(overlay, dry);
  assert.deepEqual([...effect.slice(0, 4)], [0, 0, 0, 0]);
  assert.deepEqual([...effect.slice(4)], [0, Math.fround(-75 * 128 / 255), Math.fround(-50 * 128 / 255), 128]);
  assert.deepEqual(overlay, original, 'original pixels must not be mutated');
});

test('one extracted effect reconstructs its donor and works on a different skin without a target map', () => {
  assert.equal(typeof compositor.extractPairedEffect, 'function');
  const dry = rgba(200, 150, 100, 255);
  const overlay = rgba(200, 75, 50, 128);
  const render = (base, layer, pairedDelta = null) => compositor.composeFrame({}, [
    { order: 0, role: 'earless_head_body', path: 'base' },
    { order: 1, role: 'blush', path: 'effect', pairedDelta },
  ], new Map([['base', image(base)], ['effect', image(layer)], ['dry', image(dry)]])).data;
  const pair = { algorithm: 'signed-rgb-delta-v1', dry: { path: 'dry' } };
  assert.deepEqual(render(dry, overlay, pair), render(dry, overlay));
  assert.deepEqual([...render(rgba(80, 60, 40, 255), overlay, pair)], [80, 22, 15, 255]);
});

test('face extraction preserves geometry and rejects a mismatched source pair', () => {
  assert.equal(typeof compositor.extractPairedEffect, 'function');
  const dry = rgba(200, 200, 200, 123, 200, 200, 200, 255);
  const donor = rgba(100, 100, 100, 123, 255, 255, 255, 255);
  const effect = compositor.extractPairedEffect(donor, dry, { donor: true });
  assert.deepEqual([...effect], [-100, -100, -100, 123, 55, 55, 55, 255]);
  assert.throws(() => compositor.extractPairedEffect(rgba(0, 0, 0, 0), dry), /length/i);
  assert.throws(() => compositor.extractPairedEffect(rgba(100, 100, 100, 255),
    rgba(200, 200, 200, 123), { donor: true }), /geometry/i);
});

test('browser renderer loads paired dependencies and restores the derived face above clothing', async () => {
  const sources = new Map([
    ['target', image(rgba(80, 60, 40, 123))],
    ['dry', image(rgba(200, 150, 100, 123))],
    ['donor', image(rgba(100, 75, 50, 123))],
    ['clothes', image(rgba(0, 0, 255, 255))],
    ['head', image(rgba(0, 0, 0, 123))],
  ]);
  const bindings = [
    { order: 0, role: 'face_expression_base', path: 'target', pairedDelta: {
      algorithm: 'signed-rgb-delta-v1', dry: { path: 'dry' }, donor: { path: 'donor' },
    } },
    { order: 1, role: 'clothing_main', path: 'clothes' },
    { order: 2, role: 'earless_head', operation: 'ownership-reset', path: 'head' },
  ];
  const commits = [];
  const renderer = new compositor.PortraitCompositor({
    outputCanvas: { getContext: () => ({ putImageData: (frame) => commits.push(frame) }) },
    imageLoader: { load: async (path) => sources.get(path) },
  });
  assert.equal((await renderer.render({}, bindings)).committed, true);
  assert.deepEqual([...commits[0].data], [0, 0, 0, 123]);
  sources.set('dry', { width: 1, height: 2, data: rgba(0, 0, 0, 0, 0, 0, 0, 0) });
  assert.throws(() => compositor.composeFrame({}, bindings, sources), /dimensions/i);
});

test('small differences on light source skin never amplify into white patches on dark skin', () => {
  const bindings = [{ order: 0, role: 'face_expression_base', path: 'target', pairedDelta: {
    algorithm: 'signed-rgb-delta-v1', dry: { path: 'dry' }, donor: { path: 'donor' },
  } }];
  const sources = new Map([
    ['target', image(rgba(70, 50, 30, 255))],
    ['dry', image(rgba(253, 251, 249, 255))],
    ['donor', image(rgba(254, 252, 250, 255))],
  ]);
  assert.deepEqual([...compositor.composeFrame({}, bindings, sources).data], [71, 51, 31, 255]);
});

test('blush strength reduces only the blush contribution without changing alpha or the face', () => {
  const dry = rgba(200, 150, 100, 255);
  const sources = new Map([
    ['base', image(rgba(80, 60, 40, 255))], ['dry', image(dry)],
    ['effect', image(rgba(200, 75, 50, 128))],
  ]);
  const render = (strength) => compositor.composeFrame({}, [
    { order: 0, role: 'face_expression_base', path: 'base' },
    { order: 1, role: 'blush', path: 'effect', pairedDelta: {
      algorithm: 'signed-rgb-delta-v1', dry: { path: 'dry' }, strength,
    } },
  ], sources).data;
  assert.deepEqual([...render(0.25)], [80, 51, 34, 255]);
  assert.deepEqual([...render(0)], [80, 60, 40, 255]);
  assert.deepEqual([...render(1)], [80, 22, 15, 255]);
  assert.deepEqual([...sources.get('base').data], [80, 60, 40, 255]);
  for (const invalid of [-0.1, 1.1, NaN, Infinity, '0.25']) {
    assert.throws(() => render(invalid), /strength/i);
  }
});
