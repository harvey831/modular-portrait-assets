import { createAppState, localizeStatus, reduceAppState } from './lib/app-state.mjs';
import { createCatalogIndex } from './lib/catalog.mjs';
import { PortraitCompositor } from './lib/compositor.mjs';
import { createTranslator, MESSAGES } from './lib/i18n.mjs';
import { buildRecipe } from './lib/selection.mjs';


const LANGUAGE_KEY = 'portrait-mixer-language';
const CONTROL_BY_AXIS = Object.freeze({
  gender: 'gender',
  S: 'skin',
  expression: 'expression',
  F: 'face',
  E: 'eyes',
  M: 'mouth',
  H: 'hair',
  C: 'clothing',
  ear: 'ear',
});


function readLanguage() {
  try {
    const stored = localStorage.getItem(LANGUAGE_KEY);
    return Object.hasOwn(MESSAGES, stored) ? stored : 'en';
  } catch {
    return 'en';
  }
}


function writeLanguage(language) {
  try {
    localStorage.setItem(LANGUAGE_KEY, language);
  } catch {
    // Language persistence is optional when storage is unavailable.
  }
}


function randomSeed() {
  const buffer = new Uint32Array(1);
  crypto.getRandomValues(buffer);
  return buffer[0];
}


function optionText(axis, value, translate) {
  if (axis === 'gender') return translate(`gender.${value}`);
  if (axis === 'ear') return translate(`ear.${value}`);
  if (axis === 'expression') return translate(`expression.${value}`);
  return value;
}


function recipeJson(recipe) {
  return `${JSON.stringify(recipe, null, 2)}\n`;
}


export async function bootstrap() {
  const canvas = document.getElementById('portrait-canvas');
  const status = document.getElementById('status');
  const statusText = document.getElementById('status-text');
  const downloadButton = document.getElementById('download');
  const copyButton = document.getElementById('copy-recipe');
  const recipeFallback = document.getElementById('recipe-fallback');
  const recipeSummary = document.getElementById('recipe-summary');
  const recipeHeading = document.getElementById('recipe-heading');
  const hueControl = document.getElementById('hair-hue');
  const hueOutput = document.getElementById('hair-hue-value');
  const languageControl = document.getElementById('language');
  const extendedControl = document.getElementById('extended');
  const form = document.getElementById('controls');

  let language = readLanguage();
  let translate = createTranslator(language);
  let index;
  let state;
  let compositor;
  let currentRecipe = null;
  let renderAbort = null;
  let scheduledFrame = null;
  let statusMessage = {
    key: 'status.loadingCatalog',
    variables: {},
    tone: 'working',
  };

  function setStatus(key, variables = {}, tone = 'working') {
    statusMessage = { key, variables: { ...variables }, tone };
    statusText.dataset.i18n = key;
    statusText.textContent = localizeStatus(statusMessage, translate);
    status.dataset.tone = tone;
  }

  function applyTranslations() {
    document.documentElement.lang = language;
    document.title = translate('app.title');
    document.querySelectorAll('[data-i18n]:not(#status-text)').forEach((element) => {
      element.textContent = translate(element.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-aria-label]').forEach((element) => {
      element.setAttribute('aria-label', translate(element.dataset.i18nAriaLabel));
    });
    languageControl.value = language;
    statusText.textContent = localizeStatus(statusMessage, translate);
    status.dataset.tone = statusMessage.tone;
  }

  function renderOptions() {
    for (const [axis, controlId] of Object.entries(CONTROL_BY_AXIS)) {
      const control = document.getElementById(controlId);
      const options = state.options[axis];
      control.replaceChildren(...options.map((value) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = optionText(axis, value, translate);
        return option;
      }));
      control.value = state.selection[axis];
      control.disabled = options.length === 0;
    }
    extendedControl.checked = state.extended;
    hueControl.value = String(state.selection.hairHue);
    hueOutput.value = `${state.selection.hairHue}°`;
    hueOutput.textContent = `${state.selection.hairHue}°`;
    document.documentElement.style.setProperty('--hair-hue', String(state.selection.hairHue));
  }

  function renderRecipeSummary() {
    if (!currentRecipe) {
      recipeHeading.dataset.i18n = 'recipe.waiting';
      recipeHeading.textContent = translate('recipe.waiting');
      recipeSummary.replaceChildren();
      return;
    }
    delete recipeHeading.dataset.i18n;
    const selected = currentRecipe.selection;
    recipeHeading.textContent = [
      optionText('gender', selected.gender, translate),
      selected.F,
      selected.S,
      selected.expression,
    ].join(' · ');
    const seedTerm = document.createElement('dt');
    seedTerm.textContent = translate('recipe.seed');
    const seedValue = document.createElement('dd');
    seedValue.textContent = String(currentRecipe.seed);
    const modulesTerm = document.createElement('dt');
    modulesTerm.textContent = translate('recipe.modules');
    const modulesValue = document.createElement('dd');
    modulesValue.textContent = [selected.E, selected.M, selected.H, selected.C].join(' / ');
    recipeSummary.replaceChildren(seedTerm, seedValue, modulesTerm, modulesValue);
  }

  async function renderCurrent() {
    renderAbort?.abort();
    const controller = new AbortController();
    renderAbort = controller;
    downloadButton.disabled = true;
    copyButton.disabled = true;
    recipeFallback.hidden = true;
    setStatus('status.rendering');
    try {
      const recipe = buildRecipe(index, state.selection, state.seed);
      const result = await compositor.render(
        { ...state.selection, recipe },
        recipe.layers,
        controller.signal,
      );
      if (!result.committed) return;
      currentRecipe = recipe;
      downloadButton.disabled = false;
      copyButton.disabled = false;
      renderRecipeSummary();
      const adjustment = state.adjustments.at(-1);
      if (adjustment) {
        setStatus('status.adjusted', adjustment, 'ready');
      } else {
        setStatus('status.ready', {}, 'ready');
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      currentRecipe = null;
      renderRecipeSummary();
      setStatus('status.error', { message: error.message }, 'error');
      throw error;
    }
  }

  function scheduleRender() {
    renderAbort?.abort();
    if (scheduledFrame !== null) cancelAnimationFrame(scheduledFrame);
    scheduledFrame = requestAnimationFrame(() => {
      scheduledFrame = null;
      renderCurrent().catch((error) => console.error(error));
    });
  }

  function applyEvent(event) {
    state = reduceAppState(state, event, index);
    renderOptions();
    scheduleRender();
  }

  applyTranslations();
  setStatus('status.loadingCatalog');
  const response = await fetch('./catalog.json', { cache: 'no-cache', credentials: 'same-origin' });
  if (!response.ok) throw new Error(`${translate('error.catalog')} HTTP ${response.status}`);
  index = createCatalogIndex(await response.json());
  state = createAppState(index);
  compositor = new PortraitCompositor({ outputCanvas: canvas });
  renderOptions();

  form.addEventListener('submit', (event) => event.preventDefault());
  for (const [axis, controlId] of Object.entries(CONTROL_BY_AXIS)) {
    document.getElementById(controlId).addEventListener('change', (event) => {
      applyEvent({ type: 'set-axis', axis, value: event.currentTarget.value });
    });
  }
  extendedControl.addEventListener('change', () => {
    applyEvent({ type: 'set-extended', value: extendedControl.checked });
  });
  hueControl.addEventListener('input', () => {
    applyEvent({ type: 'set-hue', value: Number(hueControl.value) });
  });
  document.getElementById('randomize').addEventListener('click', () => {
    applyEvent({ type: 'randomize', seed: randomSeed() });
  });
  document.getElementById('reset').addEventListener('click', () => {
    applyEvent({ type: 'reset' });
  });
  languageControl.addEventListener('change', () => {
    language = Object.hasOwn(MESSAGES, languageControl.value) ? languageControl.value : 'en';
    translate = createTranslator(language);
    writeLanguage(language);
    applyTranslations();
    renderOptions();
    renderRecipeSummary();
  });
  downloadButton.addEventListener('click', async () => {
    if (!currentRecipe) return;
    downloadButton.disabled = true;
    try {
      const blob = await compositor.toPngBlob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `modular-portrait-${currentRecipe.seed}.png`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      setStatus('status.downloaded', {}, 'ready');
    } catch (error) {
      setStatus('status.error', { message: translate('error.download') }, 'error');
      console.error(error);
    } finally {
      downloadButton.disabled = currentRecipe === null;
    }
  });
  copyButton.addEventListener('click', async () => {
    if (!currentRecipe) return;
    const text = recipeJson(currentRecipe);
    try {
      await navigator.clipboard.writeText(text);
      recipeFallback.hidden = true;
      setStatus('status.copied', {}, 'ready');
    } catch {
      recipeFallback.value = text;
      recipeFallback.hidden = false;
      recipeFallback.focus();
      recipeFallback.select();
      setStatus('status.copyFallback', {}, 'error');
    }
  });

  await renderCurrent();
  return Object.freeze({ index, getState: () => state, compositor });
}


if (typeof document !== 'undefined') {
  bootstrap().catch((error) => {
    const status = document.getElementById('status');
    const statusText = document.getElementById('status-text');
    if (status && statusText) {
      status.dataset.tone = 'error';
      statusText.textContent = error.message;
    }
    console.error(error);
  });
}
