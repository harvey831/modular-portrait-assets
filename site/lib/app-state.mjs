import { availableValues } from './catalog.mjs';
import {
  defaultSelection,
  normalizeSelection,
  randomSelection,
  SelectionError,
} from './selection.mjs';


const OPTION_AXES = Object.freeze(['gender', 'S', 'expression', 'F', 'E', 'M', 'H', 'C', 'ear']);


function deriveOptions(index, selection, extended) {
  const options = {};
  for (const axis of OPTION_AXES) {
    options[axis] = Object.freeze(
      availableValues(index, selection, axis, { extended }),
    );
  }
  return Object.freeze(options);
}


function stateFrom(index, selection, { extended, seed, adjustments = [] }) {
  return Object.freeze({
    selection: Object.freeze({ ...selection }),
    extended: Boolean(extended),
    seed: seed >>> 0,
    options: deriveOptions(index, selection, Boolean(extended)),
    adjustments: Object.freeze([...adjustments]),
  });
}


export function createAppState(index, {
  selection = {},
  extended = false,
  seed = 0,
} = {}) {
  const normalized = normalizeSelection(index, selection, { extended });
  return stateFrom(index, normalized.selection, {
    extended,
    seed,
    adjustments: normalized.adjustments,
  });
}


export function reduceAppState(state, event, index) {
  if (!event || typeof event.type !== 'string') {
    throw new SelectionError('State event must have a type');
  }
  if (event.type === 'set-axis') {
    if (!OPTION_AXES.includes(event.axis)) {
      throw new SelectionError(`Unknown state axis: ${event.axis}`);
    }
    const requested = { ...state.selection, [event.axis]: event.value };
    const normalized = normalizeSelection(index, requested, { extended: state.extended });
    return stateFrom(index, normalized.selection, {
      extended: state.extended,
      seed: state.seed,
      adjustments: normalized.adjustments,
    });
  }
  if (event.type === 'set-hue') {
    const normalized = normalizeSelection(
      index,
      { ...state.selection, hairHue: event.value },
      { extended: state.extended },
    );
    return stateFrom(index, normalized.selection, {
      extended: state.extended,
      seed: state.seed,
      adjustments: normalized.adjustments,
    });
  }
  if (event.type === 'set-extended') {
    const extended = Boolean(event.value);
    const normalized = normalizeSelection(index, state.selection, { extended });
    return stateFrom(index, normalized.selection, {
      extended,
      seed: state.seed,
      adjustments: normalized.adjustments,
    });
  }
  if (event.type === 'randomize') {
    const seed = event.seed >>> 0;
    return stateFrom(
      index,
      randomSelection(index, seed, { extended: state.extended }),
      { extended: state.extended, seed },
    );
  }
  if (event.type === 'reset') {
    return stateFrom(index, defaultSelection(index), {
      extended: false,
      seed: 0,
    });
  }
  throw new SelectionError(`Unknown state event: ${event.type}`);
}
