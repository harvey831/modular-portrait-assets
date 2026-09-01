import test from 'node:test';
import assert from 'node:assert/strict';

import { createCatalogIndex } from '../lib/catalog.mjs';
import { createAppState, reduceAppState } from '../lib/app-state.mjs';
import { FIXTURE_CATALOG } from './fixtures.mjs';


const INDEX = createCatalogIndex(FIXTURE_CATALOG);


test('enabling extended expressions changes availability without selecting X automatically', () => {
  const initial = createAppState(INDEX, {
    extended: false,
    selection: { expression: 'G02' },
  });
  const next = reduceAppState(initial, { type: 'set-extended', value: true }, INDEX);
  assert.equal(next.selection.expression, 'G02');
  assert(next.options.expression.includes('X01'));
  assert.equal(next.extended, true);
});


test('upstream changes normalize incompatible downstream values and report them', () => {
  const initial = createAppState(INDEX, {
    selection: {
      gender: 'female', S: 'S01', expression: 'G02', F: 'F01',
      E: 'E06', M: 'M02', H: 'H02', C: 'C02', ear: 'elf', hairHue: 210,
    },
  });
  const next = reduceAppState(
    initial,
    { type: 'set-axis', axis: 'S', value: 'S04' },
    INDEX,
  );
  assert.equal(next.selection.S, 'S04');
  assert.equal(next.selection.E, 'E01');
  assert.equal(next.selection.M, 'M01');
  assert.deepEqual(next.adjustments.map(({ axis }) => axis), ['E', 'M']);
});


test('disabling extended expressions repairs an active X selection', () => {
  const initial = createAppState(INDEX, {
    extended: true,
    selection: { gender: 'female', S: 'S01', expression: 'X01' },
  });
  const next = reduceAppState(initial, { type: 'set-extended', value: false }, INDEX);
  assert.doesNotMatch(next.selection.expression, /^X/);
  assert.equal(next.adjustments.some(({ axis }) => axis === 'expression'), true);
});


test('randomize records the requested seed and remains deterministic', () => {
  const initial = createAppState(INDEX);
  const first = reduceAppState(initial, { type: 'randomize', seed: 3186449067 }, INDEX);
  const second = reduceAppState(initial, { type: 'randomize', seed: 3186449067 }, INDEX);
  assert.equal(first.seed, 3186449067);
  assert.deepEqual(first.selection, second.selection);
  assert.deepEqual(first.options, second.options);
});


test('reset returns to the explicit defaults and keeps language-independent state', () => {
  const randomized = reduceAppState(
    createAppState(INDEX, { extended: true }),
    { type: 'randomize', seed: 7 },
    INDEX,
  );
  const reset = reduceAppState(randomized, { type: 'reset' }, INDEX);
  assert.deepEqual(reset.selection, {
    gender: 'female', S: 'S01', expression: 'N00', F: 'F01',
    E: 'E01', M: 'M01', H: 'H01', C: 'C01', ear: 'human', hairHue: 210,
  });
  assert.equal(reset.extended, false);
  assert.equal(reset.seed, 0);
});
