const CORE_AXES = Object.freeze(['gender', 'S', 'expression', 'F', 'E', 'M']);
const ALL_AXES = Object.freeze([...CORE_AXES, 'H', 'C', 'ear']);
// Full S01 redness overwhelms darker bases. Only shared blush is attenuated;
// native assets, expression creases, eyes, mouths and liquid highlights are not.
const SHARED_BLUSH_STRENGTH = Object.freeze({ S02: 0.65, S03: 0.45, S04: 0.25 });
const REQUIRED_STYLE_ROLES = Object.freeze({
  hair: Object.freeze(['hair_back', 'hair_front', 'hair_tint_mask']),
  clothing: Object.freeze(['clothing_back', 'clothing_main', 'clothing_front']),
});


export class CatalogError extends Error {
  constructor(message) {
    super(message);
    this.name = 'CatalogError';
  }
}


function compareValues(left, right) {
  if (left === right) return 0;
  const expressionOrder = { N: 0, G: 1, X: 2 };
  if (left?.[0] in expressionOrder || right?.[0] in expressionOrder) {
    const leftRank = expressionOrder[left?.[0]] ?? 9;
    const rightRank = expressionOrder[right?.[0]] ?? 9;
    if (leftRank !== rightRank) return leftRank - rightRank;
  }
  return String(left).localeCompare(String(right), 'en');
}


function sortedUnique(values) {
  return [...new Set(values)].sort(compareValues);
}


function logicalKey(asset) {
  return [
    asset.gender, asset.family, asset.component, asset.face, asset.skin,
    asset.expression, asset.role, asset.ear,
  ].map((value) => value ?? '').join('|');
}


function validateCatalog(catalog) {
  if (!catalog || catalog.schema !== 'modular-portrait-web-catalog-v1') {
    throw new CatalogError('Unsupported catalog schema');
  }
  if (!Array.isArray(catalog.canvas)
      || catalog.canvas[0] !== 1254
      || catalog.canvas[1] !== 1254
      || catalog.canvas[2] !== 'RGBA') {
    throw new CatalogError('Catalog canvas must be 1254×1254 RGBA');
  }
  if (!Array.isArray(catalog.assets) || catalog.asset_count !== catalog.assets.length) {
    throw new CatalogError('Catalog asset count does not match assets');
  }
  if (!/^[0-9a-f]{64}$/.test(catalog.source_manifest_sha256 ?? '')) {
    throw new CatalogError('Catalog source manifest hash is invalid');
  }
  if (!/^[0-9a-f]{64}$/.test(catalog.catalog_sha256 ?? '')) {
    throw new CatalogError('Catalog digest is invalid');
  }
}


function recordsMatching(index, criteria) {
  const familyRecords = criteria.family
    ? (index.byFamily.get(criteria.family) ?? [])
    : index.assets;
  return familyRecords.filter((asset) => Object.entries(criteria).every(
    ([field, value]) => value === undefined || asset[field] === value,
  ));
}


function oneRecord(index, criteria, { optional = false } = {}) {
  const matches = recordsMatching(index, criteria);
  if (matches.length === 0 && optional) return null;
  if (matches.length !== 1) {
    throw new CatalogError(
      `Expected one asset for ${JSON.stringify(criteria)}, found ${matches.length}`,
    );
  }
  return matches[0];
}


function neutralFacePair(index, { gender, F, S }) {
  const base = oneRecord(index, {
    gender, family: 'base', face: F, skin: S, role: 'earless_head_body',
  }, { optional: true });
  const head = oneRecord(index, {
    gender, family: 'base', face: F, skin: S, role: 'earless_head',
  }, { optional: true });
  if (Boolean(base) !== Boolean(head)) {
    throw new CatalogError(`Incomplete neutral face pair: ${gender}/${F}/${S}`);
  }
  return base ? { base, head, expressionOwned: false } : null;
}


function assetRef(asset) {
  return Object.freeze({ path: asset.path, sha256: asset.sha256 });
}


function pairedDelta(dry, donor = null) {
  if (!dry) throw new CatalogError('Missing paired dry source');
  return Object.freeze({
    algorithm: 'signed-rgb-delta-v1', dry: assetRef(dry),
    ...(donor ? { donor: assetRef(donor) } : {}),
  });
}


function resolveFacePair(index, { gender, F, S, expression }) {
  const neutral = neutralFacePair(index, { gender, F, S });
  if (!neutral) return null;
  const ownsExpression = expression === 'G02'
    || (gender === 'female' && ['X01', 'X02', 'X03'].includes(expression));
  if (!ownsExpression) return neutral;
  const expressionBase = oneRecord(index, {
    gender, family: 'expression', face: F, skin: S, expression,
    role: 'face_expression_base',
  }, { optional: true });
  const expressionHead = oneRecord(index, {
    gender, family: 'expression', face: F, skin: S, expression,
    role: 'face_expression_head',
  }, { optional: true });
  if (Boolean(expressionBase) !== Boolean(expressionHead)) {
    throw new CatalogError(`Incomplete expression face pair: ${gender}/${F}/${S}/${expression}`);
  }
  if (expressionBase) {
    return { base: expressionBase, head: expressionHead, expressionOwned: true };
  }

  if (S === 'S01') {
    throw new CatalogError(`Missing required expression face: ${gender}/${F}/${S}/${expression}`);
  }
  const source = resolveFacePair(index, { gender, F, S: 'S01', expression });
  const sourceNeutral = neutralFacePair(index, { gender, F, S: 'S01' });
  if (!source || !sourceNeutral) throw new CatalogError('Missing shared expression source pair');
  return {
    ...neutral, expressionOwned: true,
    pairedDelta: pairedDelta(sourceNeutral.base, source.base),
  };
}


function completeComponents(index, gender, family) {
  const required = REQUIRED_STYLE_ROLES[family];
  const components = sortedUnique(
    recordsMatching(index, { gender, family }).map(({ component }) => component),
  );
  return components.filter((component) => required.every(
    (role) => recordsMatching(index, { gender, family, component, role }).length === 1,
  ));
}


function buildCores(index) {
  const genders = sortedUnique(index.assets
    .filter(({ gender }) => gender === 'female' || gender === 'male')
    .map(({ gender }) => gender));
  const cores = [];
  for (const gender of genders) {
    const skins = sortedUnique(recordsMatching(index, { gender, family: 'E' })
      .map(({ skin }) => skin));
    for (const S of skins) {
      const expressions = sortedUnique(recordsMatching(index, { gender, family: 'E', skin: S })
        .map(({ expression }) => expression));
      for (const expression of expressions) {
        const eyes = sortedUnique(recordsMatching(index, {
          gender, family: 'E', skin: S, expression,
        }).map(({ component }) => component));
        const mouths = sortedUnique(recordsMatching(index, {
          gender, family: 'M', skin: S, expression,
        }).map(({ component }) => component));
        const faces = sortedUnique(index.assets
          .filter((asset) => asset.gender === gender && asset.face)
          .map(({ face }) => face));
        for (const F of faces) {
          if (!resolveFacePair(index, { gender, F, S, expression })) continue;
          for (const E of eyes) {
            for (const M of mouths) cores.push(Object.freeze({ gender, S, expression, F, E, M }));
          }
        }
      }
    }
  }
  return Object.freeze(cores);
}


export function createCatalogIndex(catalog) {
  validateCatalog(catalog);
  const assets = catalog.assets.map((asset) => Object.freeze({ ...asset }));
  const byLogicalKey = new Map();
  const byFamily = new Map();
  for (const asset of assets) {
    if (typeof asset.path !== 'string' || !asset.path.startsWith('assets/')) {
      throw new CatalogError(`Unsafe public asset path: ${asset.path}`);
    }
    const key = logicalKey(asset);
    if (byLogicalKey.has(key)) throw new CatalogError(`Ambiguous asset: ${key}`);
    byLogicalKey.set(key, asset);
    const familyRecords = byFamily.get(asset.family) ?? [];
    familyRecords.push(asset);
    byFamily.set(asset.family, familyRecords);
  }
  const index = {
    catalog: Object.freeze({ ...catalog, assets }),
    assets: Object.freeze(assets),
    byLogicalKey,
    byFamily,
    cores: null,
  };
  index.cores = buildCores(index);
  return Object.freeze(index);
}


export function availableValues(index, selection, axis, { extended = false } = {}) {
  if (!ALL_AXES.includes(axis)) throw new CatalogError(`Unknown selection axis: ${axis}`);
  if (CORE_AXES.includes(axis)) {
    const axisIndex = CORE_AXES.indexOf(axis);
    const upstream = CORE_AXES.slice(0, axisIndex);
    const matches = index.cores.filter((core) => upstream.every(
      (field) => selection[field] === undefined || core[field] === selection[field],
    ));
    let values = sortedUnique(matches.map((core) => core[axis]));
    if (axis === 'expression' && !extended) {
      values = values.filter((value) => !value.startsWith('X'));
    }
    return values;
  }
  if (axis === 'H') return completeComponents(index, selection.gender, 'hair');
  if (axis === 'C') return completeComponents(index, selection.gender, 'clothing');
  return sortedUnique(recordsMatching(index, {
    gender: 'shared', family: 'ears', skin: selection.S, role: 'ear_pair',
  }).map(({ ear }) => ear));
}


function binding(role, asset, {
  operation = 'alpha-composite', tintMask = null, pairedDelta: delta = null,
} = {}) {
  const result = {
    role,
    operation,
    path: asset.path,
    sha256: asset.sha256,
  };
  if (tintMask) {
    result.tintMask = { path: tintMask.path, sha256: tintMask.sha256 };
  }
  if (delta) result.pairedDelta = delta;
  return result;
}


function resolveEffects(index, { gender, F, S, expression, ear }) {
  const query = (skin) => [
    ['blush', 'blush'], ['sweat', 'sweat'],
    ['blush', `ear_blush_${ear}`], ['sweat', `ear_sweat_${ear}`],
  ].map(([family, role]) => oneRecord(index, {
    gender, family, face: F, skin, expression, role,
  }, { optional: true }));
  let skin = S;
  let records = query(skin);
  if (records.every((record) => !record) && S !== 'S01') {
    skin = 'S01';
    records = query(skin);
  }
  if (records.every((record) => !record) && gender === 'male' && expression === 'N00') {
    return null;
  }
  if (records.some((record) => !record)) {
    throw new CatalogError(`Incomplete expression effects: ${gender}/${F}/${skin}/${expression}/${ear}`);
  }
  const [blush, sweat, earBlush, earSweat] = records;
  if (skin === S) return { blush, sweat, earBlush, earSweat };
  const strength = SHARED_BLUSH_STRENGTH[S];
  if (strength === undefined) throw new CatalogError(`Unreviewed shared blush skin: ${S}`);
  const sourceFace = resolveFacePair(index, { gender, F, S: skin, expression });
  const sourceEar = oneRecord(index, {
    gender: 'shared', family: 'ears', skin, role: 'ear_pair', ear,
  });
  return {
    blush, sweat, earBlush, earSweat,
    pairedDelta: Object.freeze({ ...pairedDelta(sourceFace?.base), strength }),
    earPairedDelta: Object.freeze({ ...pairedDelta(sourceEar), strength }),
  };
}


export function resolveLayerBindings(index, selection) {
  const { gender, F, S, expression, E, M, H, C, ear } = selection;
  const coreMatch = index.cores.some((core) => CORE_AXES.every(
    (axis) => core[axis] === selection[axis],
  ));
  if (!coreMatch) throw new CatalogError('Selection is not compatible with the catalog');
  if (!completeComponents(index, gender, 'hair').includes(H)
      || !completeComponents(index, gender, 'clothing').includes(C)) {
    throw new CatalogError('Selection has an incomplete style module');
  }

  const hairMask = oneRecord(index, {
    gender, family: 'hair', component: H, role: 'hair_tint_mask',
  });
  const hair = (role) => oneRecord(index, { gender, family: 'hair', component: H, role });
  const clothes = (role) => oneRecord(index, {
    gender, family: 'clothing', component: C, role,
  });
  const facePair = resolveFacePair(index, { gender, F, S, expression });
  const eye = oneRecord(index, {
    gender, family: 'E', component: E, skin: S, expression, role: 'eye_brow',
  });
  const mouth = oneRecord(index, {
    gender, family: 'M', component: M, skin: S, expression, role: 'mouth',
  });
  const earPair = oneRecord(index, {
    gender: 'shared', family: 'ears', skin: S, role: 'ear_pair', ear,
  });

  const layers = [
    binding('hair_back', hair('hair_back'), { tintMask: hairMask }),
    binding('clothing_back', clothes('clothing_back')),
    binding(facePair.expressionOwned ? 'face_expression_base' : facePair.base.role,
      facePair.base, { pairedDelta: facePair.pairedDelta }),
    binding('clothing_main', clothes('clothing_main')),
    binding(facePair.head.role, facePair.head, { operation: 'ownership-reset' }),
  ];

  const effects = resolveEffects(index, { gender, F, S, expression, ear });
  const effectBinding = (role, asset) => binding(role, asset, {
    pairedDelta: role === 'blush' ? effects.pairedDelta
      : role === 'ear_blush' ? effects.earPairedDelta : null,
  });
  if (effects) layers.push(effectBinding('blush', effects.blush));
  layers.push(binding('eye_brow', eye), binding('mouth', mouth));
  if (effects) layers.push(effectBinding('sweat', effects.sweat));
  layers.push(
    binding('hair_front', hair('hair_front'), { tintMask: hairMask }),
    binding('ear_pair', earPair),
  );

  if (effects) {
    layers.push(
      effectBinding('ear_blush', effects.earBlush),
      effectBinding('ear_sweat', effects.earSweat),
    );
  }

  const earCover = oneRecord(index, {
    gender, family: 'hair', component: H, role: 'hair_ear_cover',
  }, { optional: true });
  if (earCover) layers.push(binding('hair_ear_cover', earCover, { tintMask: hairMask }));
  layers.push(binding('clothing_front', clothes('clothing_front')));
  return layers.map((layer, order) => Object.freeze({ order, ...layer }));
}
