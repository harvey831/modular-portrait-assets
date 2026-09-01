import test from 'node:test';
import assert from 'node:assert/strict';

import { createTranslator, MESSAGES, supportedLanguages } from '../lib/i18n.mjs';


test('English and Traditional Chinese dictionaries have identical keys', () => {
  assert.deepEqual(
    Object.keys(MESSAGES.en).sort(),
    Object.keys(MESSAGES['zh-Hant']).sort(),
  );
  assert(Object.keys(MESSAGES.en).length >= 45);
});


test('translator returns both languages and rejects missing keys', () => {
  assert.equal(createTranslator('en')('action.randomize'), 'Randomize');
  assert.equal(createTranslator('zh-Hant')('action.randomize'), '隨機混編');
  assert.throws(() => createTranslator('en')('missing.key'), /Missing translation/);
  assert.throws(() => createTranslator('fr'), /Unsupported language/);
});


test('supported language metadata is stable and user-facing', () => {
  assert.deepEqual(supportedLanguages(), [
    { id: 'en', label: 'English' },
    { id: 'zh-Hant', label: '繁體中文' },
  ]);
});
