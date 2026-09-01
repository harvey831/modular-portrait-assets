import test from 'node:test';
import assert from 'node:assert/strict';

import {
  CatalogError,
  availableValues,
  createCatalogIndex,
  resolveLayerBindings,
} from '../lib/catalog.mjs';
import { FIXTURE_CATALOG } from './fixtures.mjs';


test('compatibility exposes only feature cells present in the catalog', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  assert.deepEqual(
    availableValues(index, {
      gender: 'female', S: 'S01', expression: 'G02', F: 'F01',
    }, 'E'),
    ['E01', 'E06'],
  );
  assert.deepEqual(
    availableValues(index, {
      gender: 'female', S: 'S04', expression: 'G02', F: 'F01',
    }, 'E'),
    ['E01'],
  );
});

test('extended expressions stay hidden until explicitly enabled', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  const selection = { gender: 'female', S: 'S01' };
  assert.deepEqual(
    availableValues(index, selection, 'expression', { extended: false }),
    ['N00', 'G02', 'G03'],
  );
  assert.deepEqual(
    availableValues(index, selection, 'expression', { extended: true }),
    ['N00', 'G02', 'G03', 'X01'],
  );
});

test('resolver emits the formal expression ownership order and optional layers', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  const bindings = resolveLayerBindings(index, {
    gender: 'female', F: 'F01', S: 'S01', expression: 'G02',
    E: 'E06', M: 'M02', H: 'H02', C: 'C02', ear: 'elf', hairHue: 215,
  });
  assert.deepEqual(bindings.map(({ role }) => role), [
    'hair_back', 'clothing_back', 'face_expression_base', 'clothing_main',
    'face_expression_head', 'blush', 'eye_brow', 'mouth', 'sweat',
    'hair_front', 'ear_pair', 'ear_blush', 'ear_sweat', 'hair_ear_cover',
    'clothing_front',
  ]);
  assert.equal(bindings[0].tintMask.path.endsWith('/hair_tint_mask.png'), true);
  assert.equal(bindings[4].operation, 'ownership-reset');
  assert.deepEqual(bindings.map(({ order }) => order), [...bindings.keys()]);
});

test('catalog rejects an ambiguous duplicate asset path', () => {
  const duplicate = {
    ...FIXTURE_CATALOG,
    asset_count: FIXTURE_CATALOG.asset_count + 1,
    total_bytes: FIXTURE_CATALOG.total_bytes + 100,
    assets: [...FIXTURE_CATALOG.assets, FIXTURE_CATALOG.assets[0]],
  };
  assert.throws(() => createCatalogIndex(duplicate), CatalogError);
});
