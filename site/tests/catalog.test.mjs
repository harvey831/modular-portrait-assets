import test from 'node:test';
import assert from 'node:assert/strict';

import {
  CatalogError,
  availableValues,
  createCatalogIndex,
  resolveLayerBindings,
} from '../lib/catalog.mjs';
import { composeFrame } from '../lib/compositor.mjs';
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
    'clothing_front', 'hair_front', 'ear_pair', 'ear_blush', 'ear_sweat', 'hair_ear_cover',
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

const crossSkin = {
  gender: 'female', F: 'F01', S: 'S04', expression: 'G02',
  E: 'E01', M: 'M01', H: 'H01', C: 'C01', ear: 'elf', hairHue: 210,
};

test('cross-S uses target face plus paired expression detail and all four shared effects', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  for (const gender of ['female', 'male']) {
    const layers = resolveLayerBindings(index, { ...crossSkin, gender });
    const face = layers.find(({ role }) => role === 'face_expression_base');
    assert.ok(face, `${gender} G02 cannot become a neutral face`);
    assert.match(face.path, /base\/F01\/S04\//);
    assert.match(face.pairedDelta.dry.path, /base\/F01\/S01\//);
    assert.match(face.pairedDelta.donor.path, /F01_S01_G02/);
    for (const ref of [face.pairedDelta.dry, face.pairedDelta.donor]) {
      assert.match(ref.sha256, /^[a-f0-9]{64}$/);
    }
    for (const role of ['blush', 'sweat', 'ear_blush', 'ear_sweat']) {
      const effect = layers.find((layer) => layer.role === role);
      assert.ok(effect, `${gender}/${role} must not disappear`);
      assert.match(effect.path, /F01_S01_G02/);
      if (role.includes('blush')) {
        if (role === 'ear_blush') {
          assert.match(effect.pairedDelta.dry.path, /shared\/ears\/elf\/F01\/S01/);
        } else {
          assert.match(effect.pairedDelta.dry.path, /F01_S01_G02\/face_expression_base/);
        }
        assert.equal(effect.pairedDelta.donor, undefined, 'an effect is already an overlay');
        assert.equal(effect.pairedDelta.strength, 0.25, 'deep skin must not receive full pale-skin redness');
      } else {
        assert.equal(effect.pairedDelta, undefined, 'liquid highlights keep their own RGBA');
      }
    }
    const head = layers.find(({ operation }) => operation === 'ownership-reset');
    assert.match(head.path, /base\/F01\/S04\/earless_head/);
    assert.match(layers.find(({ role }) => role === 'eye_brow').path, /\/S04\/G02\//);
    assert.match(layers.find(({ role }) => role === 'mouth').path, /\/S04\/G02\//);
  }
});

test('native S01 is unchanged and neutral-owned G03 only shares effects', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  const native = resolveLayerBindings(index, { ...crossSkin, S: 'S01' });
  assert.equal(native.some(({ pairedDelta }) => pairedDelta), false);
  const layers = resolveLayerBindings(index, { ...crossSkin, expression: 'G03' });
  assert.match(layers.find(({ role }) => role === 'earless_head_body').path, /\/S04\//);
  assert.ok(layers.find(({ role }) => role === 'blush')?.pairedDelta);
  const neutral = resolveLayerBindings(index, { ...crossSkin, gender: 'male', expression: 'N00' });
  assert.equal(neutral.some(({ role }) => role === 'blush'), false);
});

test('missing expression source or required effect pairs fail instead of silently disappearing', () => {
  for (const roles of [
    ['face_expression_base', 'face_expression_head'], ['blush'], ['blush', 'sweat'], ['ear_sweat_elf'],
  ]) {
    const assets = FIXTURE_CATALOG.assets.filter((asset) => !(
      asset.gender === 'female' && asset.expression === 'G02' && roles.includes(asset.role)
    ));
    assert.throws(() => {
      const index = createCatalogIndex({ ...FIXTURE_CATALOG, assets, asset_count: assets.length });
      resolveLayerBindings(index, crossSkin);
    }, CatalogError);
  }
});


// Four spatially independent pixels: opaque braid, soft braid, bare high
// collar, and ear root. The garment spans the entire fixture, including the
// lower braid; using only a cropped collar would miss the original defect.
function foregroundImage(role) {
  const clear = [0, 0, 0, 0];
  let pixels = [clear, clear, clear, clear];
  if (role === 'hair_front') pixels = [
    [100, 100, 100, 255], [200, 200, 200, 128], clear, [150, 150, 150, 255],
  ];
  if (role === 'hair_tint_mask') pixels = Array(4).fill([255, 255, 255, 255]);
  if (role === 'clothing_front') pixels = Array(4).fill([20, 80, 180, 255]);
  if (['earless_head_body', 'face_expression_base'].includes(role)) {
    pixels = [clear, clear, [220, 150, 110, 255], clear];
  }
  if (['earless_head', 'face_expression_head', 'clothing_main', 'eye_brow', 'mouth'].includes(role)) {
    pixels = [clear, clear, [240, 20, 30, 255], clear];
  }
  if (role === 'ear_pair') pixels = [clear, clear, clear, [230, 150, 90, 255]];
  if (role.startsWith('ear_sweat_')) pixels = [clear, clear, clear, [30, 210, 80, 255]];
  if (role === 'hair_ear_cover') pixels = [clear, clear, clear, [230, 230, 230, 255]];
  return { width: 4, height: 1, data: new Uint8ClampedArray(pixels.flat()) };
}

for (const gender of ['female', 'male']) {
  for (const expression of ['N00', 'G02']) {
    test(`resolved ${gender}/${expression} preserves foreground hair over full garment`, () => {
      const selection = {
        gender, F: 'F01', S: 'S01', expression, E: 'E01', M: 'M01',
        H: gender === 'female' ? 'H02' : 'H01', C: 'C01', ear: 'human', hairHue: 210,
      };
      const index = createCatalogIndex(FIXTURE_CATALOG);
      const bindings = resolveLayerBindings(index, selection);
      const sources = new Map(FIXTURE_CATALOG.assets.map((asset) => [
        asset.path, foregroundImage(asset.role),
      ]));
      // This baseline runs the real tint/composition consumer on the same
      // resolved hair owners, without face or clothing layers.
      const hair = composeFrame(selection, bindings.filter(({ tintMask }) => tintMask), sources);
      const frame = composeFrame(selection, bindings, sources);
      const pixel = (image, x) => [...image.data.slice(x * 4, x * 4 + 4)];
      const cloth = [20, 80, 180, 255];
      const soft = pixel(hair, 1);
      const softOverCloth = [
        ...soft.slice(0, 3).map((channel, index) => Math.round(
          (channel * soft[3] + cloth[index] * (255 - soft[3])) / 255,
        )), 255,
      ];
      const hasEarEffects = gender === 'female' || expression === 'G02';
      assert.deepEqual({
        opaqueBraid: pixel(frame, 0), softBraid: pixel(frame, 1),
        bareHighCollar: pixel(frame, 2), earRoot: pixel(frame, 3),
      }, {
        opaqueBraid: pixel(hair, 0), softBraid: softOverCloth,
        bareHighCollar: cloth,
        earRoot: gender === 'female' ? pixel(hair, 3)
          : hasEarEffects ? [30, 210, 80, 255] : [230, 150, 90, 255],
      });
      assert.deepEqual([pixel(hair, 0)[3], soft[3]], [255, 128]);
      assert.equal(bindings.some(({ role }) => role === 'hair_ear_cover'), gender === 'female');
      const order = (role) => bindings.find((binding) => binding.role === role).order;
      assert.ok(order('mouth') < order('clothing_front'));
      assert.ok(order('clothing_front') < order('hair_front'));
      assert.ok(order('hair_front') < order('ear_pair'));
      if (hasEarEffects) assert.ok(order('ear_pair') < order('ear_sweat'));
      if (gender === 'female') assert.ok(order('ear_sweat') < order('hair_ear_cover'));
    });
  }
}
