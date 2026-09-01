import test from 'node:test';
import assert from 'node:assert/strict';

import { createCatalogIndex } from '../lib/catalog.mjs';
import {
  buildRecipe,
  defaultSelection,
  normalizeSelection,
  randomSelection,
} from '../lib/selection.mjs';
import { FIXTURE_CATALOG } from './fixtures.mjs';


test('default selection is explicit and compatible', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  assert.deepEqual(defaultSelection(index), {
    gender: 'female', S: 'S01', expression: 'N00', F: 'F01',
    E: 'E01', M: 'M01', H: 'H01', C: 'C01', ear: 'human',
    hairHue: 210,
  });
});

test('normalization repairs incompatible downstream values and reports the adjustment', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  const result = normalizeSelection(index, {
    gender: 'female', S: 'S04', expression: 'G02', F: 'F01',
    E: 'E06', M: 'M02', H: 'H02', C: 'C02', ear: 'elf', hairHue: 999,
  });
  assert.equal(result.selection.E, 'E01');
  assert.equal(result.selection.M, 'M01');
  assert.equal(result.selection.hairHue, 359);
  assert.deepEqual(result.adjustments.map(({ axis }) => axis), ['E', 'M', 'hairHue']);
});

test('same seed and catalog produce the same non-extended recipe', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  const first = randomSelection(index, 3186449067, { extended: false });
  const second = randomSelection(index, 3186449067, { extended: false });
  assert.deepEqual(first, second);
  assert.doesNotMatch(first.expression, /^X/);
  assert.deepEqual(
    buildRecipe(index, first, 3186449067),
    buildRecipe(index, second, 3186449067),
  );
});

test('extended randomization can select X-series with a hand-checked seed', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  const selected = randomSelection(index, 7, { extended: true });
  assert.equal(selected.expression, 'X01');
});

test('recipe contains only public ordered paths and reproducibility metadata', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  const selection = defaultSelection(index);
  const recipe = buildRecipe(index, selection, 7);
  assert.equal(recipe.schema, 'modular-portrait-recipe-v1');
  assert.equal(recipe.catalogSha256, 'f'.repeat(64));
  assert.deepEqual(recipe.canvas, [1254, 1254, 'RGBA']);
  assert.equal(recipe.seed, 7);
  assert.equal(recipe.layers[0].order, 0);
  assert.equal(recipe.layers.every(({ path }) => path.startsWith('assets/')), true);
  assert.doesNotMatch(JSON.stringify(recipe), /source_ref|[A-Z]:\\|\/home\//);
});
