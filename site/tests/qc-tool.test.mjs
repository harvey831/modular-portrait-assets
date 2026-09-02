import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const tool = path.join(root, 'tools/render_cross_skin_qc_v02.mjs');

function probeOutput(relative) {
  const output = path.join(root, relative, `__qc_guard_${process.pid}`);
  assert.equal(fs.existsSync(output), false);
  // Node is deliberately not Python: an allowed path fails before rendering or mkdir.
  const result = spawnSync(process.execPath, [tool, process.execPath, output], {
    cwd: root, encoding: 'utf8', windowsHide: true,
  });
  assert.ifError(result.error);
  assert.notEqual(result.status, 0);
  assert.equal(fs.existsSync(output), false, 'The safety probe must not write output');
  return result.stderr;
}

test('QC rejects an output inside source assets before invoking Python', () => {
  assert.match(probeOutput('assets'), /QC is never a source asset/);
});

test('QC rejects case aliases of source assets on Windows', {
  skip: process.platform !== 'win32',
}, () => {
  assert.match(probeOutput('ASSETS'), /QC is never a source asset/);
});

test('QC does not confuse an assets-prefixed sibling with source assets', () => {
  const stderr = probeOutput('assets2');
  assert.doesNotMatch(stderr, /QC is never a source asset/);
  assert.match(stderr, /bad option: -B/);
});
