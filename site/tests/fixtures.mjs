const HASH = 'a'.repeat(64);

function record(path, fields) {
  return Object.freeze({ path, sha256: HASH, bytes: 100, ...fields });
}

function feature(gender, family, component, skin, expression) {
  const role = family === 'E' ? 'eye_brow' : 'mouth';
  return record(
    `assets/${gender}/${family}/${component}/${skin}/${expression}/${role}.png`,
    {
      gender, family, component, face: null, skin, expression, role, ear: null,
    },
  );
}

function basePair(gender, face, skin) {
  const prefix = `assets/${gender}/base/${face}/${skin}`;
  return [
    record(`${prefix}/earless_head_body.png`, {
      gender, family: 'base', component: face, face, skin,
      expression: null, role: 'earless_head_body', ear: null,
    }),
    record(`${prefix}/earless_head.png`, {
      gender, family: 'base', component: face, face, skin,
      expression: null, role: 'earless_head', ear: null,
    }),
  ];
}

function expressionPair(gender, face, skin, expression) {
  const prefix = `assets/${gender}/expression/${face}_${skin}_${expression}`;
  return [
    record(`${prefix}/face_expression_base.png`, {
      gender, family: 'expression', component: face, face, skin,
      expression, role: 'face_expression_base', ear: null,
    }),
    record(`${prefix}/face_expression_head.png`, {
      gender, family: 'expression', component: face, face, skin,
      expression, role: 'face_expression_head', ear: null,
    }),
  ];
}

function hair(gender, component, earCover = false) {
  const prefix = `assets/${gender}/hair/${component}`;
  const roles = ['hair_back', 'hair_front', 'hair_tint_mask'];
  if (earCover) roles.push('hair_ear_cover');
  return roles.map((role) => record(`${prefix}/${role}.png`, {
    gender, family: 'hair', component, face: null, skin: null,
    expression: null, role, ear: null,
  }));
}

function clothing(gender, component) {
  const prefix = `assets/${gender}/clothing/${component}`;
  return ['clothing_back', 'clothing_main', 'clothing_front', 'clothing_tint_mask']
    .map((role) => record(`${prefix}/${role}.png`, {
      gender, family: 'clothing', component, face: null, skin: null,
      expression: null, role, ear: null,
    }));
}

function ear(kind, skin) {
  return record(`assets/shared/ears/${kind}/F01/${skin}/ear_pair.png`, {
    gender: 'shared', family: 'ears', component: 'F01', face: 'F01', skin,
    expression: null, role: 'ear_pair', ear: kind,
  });
}

function effects(gender, face, skin, expression) {
  const key = `${face}_${skin}_${expression}`;
  return [
    ['blush', 'blush'],
    ['blush', 'ear_blush_human'],
    ['blush', 'ear_blush_elf'],
    ['sweat', 'sweat'],
    ['sweat', 'ear_sweat_human'],
    ['sweat', 'ear_sweat_elf'],
  ].map(([family, role]) => record(
    `assets/${gender}/effects/${family}/${key}/${role}.png`,
    {
      gender, family, component: face, face, skin, expression, role, ear: null,
    },
  ));
}

const assets = [];
for (const [gender, skins] of [
  ['female', ['S01', 'S02', 'S04']],
  ['male', ['S01', 'S04']],
]) {
  for (const skin of skins) {
    assets.push(...basePair(gender, 'F01', skin));
    for (const expression of ['N00', 'G02', 'G03']) {
      assets.push(feature(gender, 'E', 'E01', skin, expression));
      assets.push(feature(gender, 'M', 'M01', skin, expression));
    }
  }
}

for (const skin of ['S01', 'S02', 'S04']) {
  assets.push(ear('human', skin), ear('elf', skin));
}

assets.push(
  feature('female', 'E', 'E06', 'S01', 'G02'),
  feature('female', 'M', 'M02', 'S01', 'G02'),
  feature('female', 'E', 'E01', 'S01', 'X01'),
  feature('female', 'M', 'M01', 'S01', 'X01'),
  ...expressionPair('female', 'F01', 'S01', 'G02'),
  ...expressionPair('female', 'F01', 'S01', 'X01'),
  ...effects('female', 'F01', 'S01', 'G02'),
  ...hair('female', 'H01'),
  ...hair('female', 'H02', true),
  ...hair('male', 'H01'),
  ...clothing('female', 'C01'),
  ...clothing('female', 'C02'),
  ...clothing('male', 'C01'),
);

export const FIXTURE_CATALOG = Object.freeze({
  schema: 'modular-portrait-web-catalog-v1',
  license: 'CC0-1.0',
  source_manifest_sha256: 'f'.repeat(64),
  canvas: [1254, 1254, 'RGBA'],
  asset_count: assets.length,
  total_bytes: assets.length * 100,
  assets: Object.freeze(assets),
});
