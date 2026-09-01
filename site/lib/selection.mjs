import { availableValues, CatalogError, resolveLayerBindings } from './catalog.mjs';


const AXES = Object.freeze(['gender', 'S', 'expression', 'F', 'E', 'M', 'H', 'C', 'ear']);
const EXPLICIT_DEFAULT = Object.freeze({
  gender: 'female',
  S: 'S01',
  expression: 'N00',
  F: 'F01',
  E: 'E01',
  M: 'M01',
  H: 'H01',
  C: 'C01',
  ear: 'human',
  hairHue: 210,
});


export class SelectionError extends Error {
  constructor(message) {
    super(message);
    this.name = 'SelectionError';
  }
}


function chooseDefault(axis, values) {
  const preferred = EXPLICIT_DEFAULT[axis];
  return values.includes(preferred) ? preferred : values[0];
}


function normalizedHue(value) {
  if (!Number.isFinite(value)) return EXPLICIT_DEFAULT.hairHue;
  return Math.max(0, Math.min(359, Math.round(value)));
}


export function normalizeSelection(index, selection = {}, { extended = false } = {}) {
  const normalized = {};
  const adjustments = [];
  for (const axis of AXES) {
    const values = availableValues(index, normalized, axis, { extended });
    if (values.length === 0) throw new SelectionError(`No compatible values for ${axis}`);
    const requested = selection[axis];
    const value = values.includes(requested) ? requested : chooseDefault(axis, values);
    normalized[axis] = value;
    if (requested !== undefined && requested !== value) {
      adjustments.push(Object.freeze({ axis, from: requested, to: value }));
    }
  }
  const hairHue = normalizedHue(selection.hairHue);
  normalized.hairHue = hairHue;
  if (selection.hairHue !== undefined && selection.hairHue !== hairHue) {
    adjustments.push(Object.freeze({ axis: 'hairHue', from: selection.hairHue, to: hairHue }));
  }
  return Object.freeze({
    selection: Object.freeze(normalized),
    adjustments: Object.freeze(adjustments),
  });
}


export function defaultSelection(index) {
  return normalizeSelection(index, EXPLICIT_DEFAULT, { extended: false }).selection;
}


export function mulberry32(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6D2B79F5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}


function pick(values, random) {
  if (values.length === 0) throw new SelectionError('Cannot choose from an empty option list');
  return values[Math.floor(random() * values.length)];
}


export function randomSelection(index, seed, { extended = false } = {}) {
  const random = mulberry32(seed);
  const selection = {};
  for (const axis of AXES) {
    selection[axis] = pick(availableValues(index, selection, axis, { extended }), random);
  }
  selection.hairHue = Math.floor(random() * 360);
  return Object.freeze(selection);
}


export function buildRecipe(index, selection, seed) {
  const extended = String(selection.expression ?? '').startsWith('X');
  const normalized = normalizeSelection(index, selection, { extended });
  if (normalized.adjustments.length > 0) {
    throw new CatalogError('Cannot build a recipe from an incompatible selection');
  }
  const layers = resolveLayerBindings(index, normalized.selection).map((layer) => ({ ...layer }));
  return Object.freeze({
    schema: 'modular-portrait-recipe-v1',
    catalogSha256: index.catalog.catalog_sha256,
    canvas: [...index.catalog.canvas],
    seed: seed >>> 0,
    selection: { ...normalized.selection },
    layers,
  });
}
