// QC uses the actual browser resolver/compositor; Pillow is only an image codec.
// node tools/render_cross_skin_qc_v02.mjs <python> <new-output-directory>
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createCatalogIndex, resolveLayerBindings } from '../site/lib/catalog.mjs';
import { bindingAssetPaths, composeFrame, extractPairedEffect } from '../site/lib/compositor.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [python, outputArg, mode] = process.argv.slice(2);
assert.ok(mode === undefined || mode === '--blush-strengths', 'Unknown QC mode');
assert.ok(python && outputArg, 'Supply Python and an unused output directory');
const output = path.resolve(outputArg);
assert.equal(fs.existsSync(output), false, 'QC evidence must not be overwritten');
const relativeToAssets = path.relative(path.join(root, 'assets'), output);
const insideAssets = relativeToAssets === '' || (relativeToAssets !== '..'
  && !relativeToAssets.startsWith(`..${path.sep}`) && !path.isAbsolute(relativeToAssets));
assert.ok(!insideAssets, 'QC is never a source asset');
const sha = (data) => createHash('sha256').update(data).digest('hex');
function py(code, args = [], input = undefined) {
  const result = spawnSync(python, ['-B', '-c', code, ...args], {
    cwd: root, input, maxBuffer: 256 * 1024 * 1024, windowsHide: true,
  });
  if (result.status !== 0) throw new Error(result.stderr?.toString() || String(result.error));
  return result.stdout;
}
const catalog = JSON.parse(py(
  "import sys,json;from pathlib import Path;sys.path.insert(0,'tools');from build_pages_site import build_catalog;print(json.dumps(build_catalog(Path('.'))))",
));
const index = createCatalogIndex(catalog);
const records = new Map(catalog.assets.map((asset) => [asset.path, asset]));
const verified = new Set();
const cache = new Map();
const bytesPerImage = 1254 * 1254 * 4;
function imagesFor(bindings) {
  const paths = bindingAssetPaths(bindings);
  const missing = paths.filter((relative) => !cache.has(relative));
  for (const relative of missing) {
    assert.ok(records.has(relative), `Unregistered input: ${relative}`);
    assert.equal(sha(fs.readFileSync(path.join(root, relative))), records.get(relative).sha256);
    verified.add(relative);
  }
  if (missing.length) {
    const data = py("import sys;from PIL import Image\nfor p in sys.argv[1:]:\n im=Image.open(p).convert('RGBA');assert im.size==(1254,1254);sys.stdout.buffer.write(im.tobytes())", missing);
    assert.equal(data.length, missing.length * bytesPerImage);
    missing.forEach((relative, i) => cache.set(relative, {
      width: 1254, height: 1254,
      data: new Uint8ClampedArray(data.subarray(i * bytesPerImage, (i + 1) * bytesPerImage)),
    }));
  }
  const sources = new Map(paths.map((relative) => [relative, cache.get(relative)]));
  while (cache.size > 48) cache.delete(cache.keys().next().value);
  return sources;
}
function save(name, frame) {
  py("import sys;from PIL import Image;Image.frombytes('RGBA',(1254,1254),sys.stdin.buffer.read()).save(sys.argv[1])",
    [path.join(output, name)], Buffer.from(frame.data));
  return { path: name, sha256: sha(fs.readFileSync(path.join(output, name))) };
}

const groups = { female: ['N00', 'G01', 'G02', 'G03', 'G04', 'X01', 'X02', 'X03'],
  male: ['N00', 'G01', 'G02', 'G03', 'G04'] };
let coverage = 0;
for (const [gender, expressions] of Object.entries(groups)) {
  for (const expression of expressions) for (let f = 1; f <= 5; f += 1) {
    for (const S of ['S01', 'S02', 'S03', 'S04']) for (const ear of ['human', 'elf']) {
      const selection = { gender, expression, F: `F0${f}`, S, E: 'E01', M: 'M01',
        H: 'H01', C: 'C01', ear, hairHue: 210 };
      const layers = resolveLayerBindings(index, selection);
      const effects = layers.filter(({ role }) => ['blush', 'sweat', 'ear_blush', 'ear_sweat'].includes(role));
      assert.equal(effects.length, gender === 'male' && expression === 'N00' ? 0 : 4);
      const expressive = expression === 'G02' || expression.startsWith('X');
      assert.equal(layers.some(({ role }) => role === 'face_expression_base'), expressive);
      if (S !== 'S01' && expressive) assert.ok(layers.find(({ role }) => role === 'face_expression_base').pairedDelta);
      coverage += 1;
    }
  }
}
fs.mkdirSync(output, { recursive: true });
const report = { schema: 'cross-s-effects-qc-v1', status: 'PENDING_VISUAL_QC',
  sourceManifestSha256: catalog.source_manifest_sha256, catalogSha256: catalog.catalog_sha256,
  coverage, tools: ['tools/render_cross_skin_qc_v02.mjs', 'site/lib/catalog.mjs', 'site/lib/compositor.mjs', 'tools/render_examples.py']
    .map((relative) => ({ path: relative, sha256: sha(fs.readFileSync(path.join(root, relative))) })),
  records: [], isolated: [], inputs: [] };
if (mode === '--blush-strengths') {
  for (const row of [7, 2]) {
    const selection = { gender: 'female', expression: groups.female[row], F: 'F03', S: 'S04',
      E: `E0${row % 6 + 1}`, M: `M0${(row + 2) % 6 + 1}`, H: 'H01', C: 'C01',
      ear: row % 2 ? 'elf' : 'human', hairHue: (row * 53 + 25) % 360 };
    const baseBindings = resolveLayerBindings(index, selection);
    const sources = imagesFor(baseBindings);
    for (const strength of [1, 0.5, 0.25, 0]) {
      const bindings = baseBindings.map((binding) => binding.role.includes('blush')
        ? { ...binding, pairedDelta: { ...binding.pairedDelta, strength } } : binding);
      const frame = composeFrame(selection, bindings, sources);
      const name = `female-${selection.expression}-S04-blush-${String(strength * 100).padStart(3, '0')}.png`;
      report.records.push({ selection, strength, bindings, output: save(name, frame) });
    }
  }
  report.inputs = [...verified].sort().map((relative) => ({ path: relative, sha256: records.get(relative).sha256 }));
  fs.writeFileSync(path.join(output, 'manifest.json'), JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
  py("import json,sys;from pathlib import Path;from PIL import Image,ImageDraw;sys.path.insert(0,'tools');from render_examples import _font\np=Path(sys.argv[1]);r=json.loads((p/'manifest.json').read_text());font=_font(24);board=Image.new('RGB',(1800,980),(30,32,39));d=ImageDraw.Draw(board)\nfor i,c in enumerate(r['records']):\n im=Image.open(p/c['output']['path']);bg=Image.new('RGBA',im.size,(226,226,229,255));bg.alpha_composite(im);tile=bg.convert('RGB').crop((180,170,1080,1070)).resize((450,450),Image.Resampling.LANCZOS);x=(i%4)*450;y=(i//4)*490;board.paste(tile,(x,y));d.text((x+8,y+455),f\"{c['selection']['expression']} blush {c['strength']:.0%}\",font=font,fill='white')\nboard.save(p/'blush-strength-comparison.jpg',quality=95)", [output]);
  console.log(JSON.stringify({ output, portraits: report.records.length }));
  process.exit(0);
}
for (const [gender, expressions] of Object.entries(groups)) {
  for (const [row, expression] of expressions.entries()) {
    for (const S of ['S01', 'S02', 'S03', 'S04']) {
      const selection = { gender, expression, F: `F0${row % 5 + 1}`, S,
        E: `E0${row % 6 + 1}`, M: `M0${(row + 2) % 6 + 1}`,
        H: 'H01', C: 'C01', ear: row % 2 ? 'elf' : 'human', hairHue: (row * 53 + 25) % 360 };
      const bindings = resolveLayerBindings(index, selection);
      const sources = imagesFor(bindings);
      const frame = composeFrame(selection, bindings, sources);
      const name = `${gender}-${expression}-${S}.png`;
      report.records.push({ selection, bindings, output: save(name, frame) });
      // The isolated shared layers are independent of S: save just one set.
      if (S === 'S04') for (const binding of bindings.filter(({ pairedDelta }) => pairedDelta)) {
        const pair = binding.pairedDelta;
        const donor = pair.donor ? sources.get(pair.donor.path) : sources.get(binding.path);
        const dry = sources.get(pair.dry.path);
        const delta = extractPairedEffect(donor.data, dry.data, { donor: Boolean(pair.donor) });
        const data = new Uint8ClampedArray(delta.length);
        for (let offset = 0; offset < delta.length; offset += 4) {
          if (delta[offset + 3] === 0) continue;
          for (let channel = 0; channel < 3; channel += 1) data[offset + channel] = 128 + delta[offset + channel];
          data[offset + 3] = 255;
        }
        report.isolated.push({ selection, role: binding.role,
          representation: 'diagnostic signed delta centered at RGB 128; not a source module',
          output: save(`${gender}-${expression}-${binding.role}-isolated.png`, { data }) });
      }
      console.log(`${gender}/${expression}/${S}: rendered`);
    }
  }
}
report.inputs = [...verified].sort().map((relative) => ({ path: relative, sha256: records.get(relative).sha256 }));
fs.writeFileSync(path.join(output, 'manifest.json'), JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
py("import json,sys;from pathlib import Path;from PIL import Image,ImageDraw;sys.path.insert(0,'tools');from render_examples import _font\np=Path(sys.argv[1]);r=json.loads((p/'manifest.json').read_text());font=_font(20)\nfor gender,rows in [('female',8),('male',5)]:\n board=Image.new('RGB',(1440,rows*390),(30,32,39));d=ImageDraw.Draw(board)\n cells=[x for x in r['records'] if x['selection']['gender']==gender]\n for i,c in enumerate(cells):\n  im=Image.open(p/c['output']['path']);bg=Image.new('RGBA',im.size,(226,226,229,255));bg.alpha_composite(im);tile=bg.convert('RGB').crop((180,170,1080,1070)).resize((360,360),Image.Resampling.LANCZOS);x=(i%4)*360;y=(i//4)*390;board.paste(tile,(x,y));s=c['selection'];d.text((x+8,y+363),f\"{s['F']} {s['S']} {s['expression']} {s['E']} {s['M']}\",font=font,fill='white')\n board.save(p/f'{gender}-cross-s-qc.jpg',quality=95)", [output]);
console.log(JSON.stringify({ output, coverage, portraits: report.records.length, inputs: verified.size }));
