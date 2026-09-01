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


test('G-series expression labels match the approved emotion meanings', () => {
  const english = createTranslator('en');
  const traditionalChinese = createTranslator('zh-Hant');

  assert.deepEqual(
    ['G01', 'G02', 'G03', 'G04'].map((id) => english(`expression.${id}`)),
    ['G01 · Smile', 'G02 · Hit / Angry', 'G03 · Terrified', 'G04 · Dazed'],
  );
  assert.deepEqual(
    ['G01', 'G02', 'G03', 'G04'].map((id) => traditionalChinese(`expression.${id}`)),
    ['G01 · 笑', 'G02 · 受擊生氣', 'G03 · 驚恐', 'G04 · 失神'],
  );
});


test('supported language metadata is stable and user-facing', () => {
  assert.deepEqual(supportedLanguages(), [
    { id: 'en', label: 'English' },
    { id: 'zh-Hant', label: '繁體中文' },
  ]);
});
