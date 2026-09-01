# GitHub Pages 大頭相混編器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 建立一個公開、雙語、零後端的 GitHub Pages 大頭相混編器，依正式 manifest 在瀏覽器原生合成並匯出 1254×1254 PNG。

**Architecture：** GitHub Actions 先解出 Git LFS 實體圖檔，再由 Python builder 產生精簡 catalog 與 Pages artifact。瀏覽器以純 ES modules 建立相容性索引、固定 seed selection、正式 layer bindings 與 Canvas compositor；HTML/CSS/app orchestration 只消費這些小型模組。

**Tech Stack：** Python 3.12、Pillow、JavaScript ES modules、Node 22 內建 `node:test`、Canvas 2D、HTML5/CSS、GitHub Actions/Pages。

**Spec：** `docs/superpowers/specs/2026-09-01-github-pages-portrait-mixer-design.md`

## Global Constraints

- 所有來源圖與輸出 canvas 必須維持 1254×1254；不得 crop、shift、scale、rotate 或 warp 模組。
- 只接受 `provenance/asset-manifest.json` 內、SHA-256 相符的 974 個公開素材。
- `X01`–`X03` 預設隱藏；只有使用者開啟 `Extended expressions` 才可選擇或 randomize。
- 英文預設、繁中可切換；兩套 i18n keys 必須完全一致。
- 前端不得加入 framework、runtime dependency、API key、analytics、外部字型或 remote generation。
- Preview 與 PNG download 都由相同的 1254×1254 render canvas 產生。
- 每個行為先完成 RED → GREEN → REFACTOR；每項 task 完成一個可獨立審查的 commit。
- Build artifact 內若存在 Git LFS pointer、hash drift、private/absolute path 或缺檔，部署必須失敗。

---

## 檔案責任地圖

- `tools/build_pages_site.py`：release path 解析、catalog 生成、hash/LFS 驗證、artifact copy。
- `tests/test_pages_site.py`：Python builder 的 synthetic fixture 與實際 974-record catalog 驗證。
- `site/lib/catalog.mjs`：catalog index、axis availability、formal layer resolution。
- `site/lib/selection.mjs`：明確 default、compatible normalization、固定 PRNG、recipe serialization。
- `site/lib/compositor.mjs`：圖像 cache、pixel tint、ownership reset、Canvas 組合與 stale-render guard。
- `site/lib/i18n.mjs`：英文／繁中 dictionary 與安全 translator。
- `site/lib/app-state.mjs`：純 UI state/reducer；不讀取 DOM，供 Node 直接測試。
- `site/app.mjs`：DOM state、controls、render lifecycle、download、clipboard、language persistence。
- `site/index.html`：semantic application shell。
- `site/styles.css`：responsive 暗色角色工房視覺、focus、reduced motion。
- `site/tests/*.test.mjs`：Node 小型測試，只測本專案純邏輯。
- `.github/workflows/pages.yml`：LFS checkout、全部 gates、artifact upload、Pages deploy。

---

### Task 1：建立 fail-closed Pages catalog builder

**Files：**
- Create: `tools/build_pages_site.py`
- Create: `tests/test_pages_site.py`
- Modify: `.gitignore`

**Interfaces：**
- Consumes: `provenance/asset-manifest.json`、`site/`（後續 task 補齊）、公開 `assets/**`。
- Produces: `parse_release_path(path: str) -> dict[str, str | None]`、`build_catalog(repo_root: Path) -> dict`、`build_site(repo_root: Path, output_dir: Path) -> dict`、CLI `python tools/build_pages_site.py <repo> <output>`。

- [ ] **Step 1：先寫 release path 及 catalog 的 failing tests**

```python
class PagesCatalogTests(unittest.TestCase):
    def test_parses_eye_mouth_hair_and_shared_ear_paths(self) -> None:
        self.assertEqual(
            build_pages_site.parse_release_path(
                "assets/female/E/E04/S02/G03/eye_brow.png"
            ),
             {
                 "gender": "female", "family": "E", "component": "E04",
                 "face": None, "skin": "S02", "expression": "G03", "role": "eye_brow",
                 "ear": None,
             },
        )
        self.assertEqual(
             build_pages_site.parse_release_path(
                "assets/shared/ears/elf/F01/S04/F01_S04_elf_ear_module.png"
             )["ear"],
            "elf",
        )

    def test_actual_catalog_contains_all_hash_bound_assets(self) -> None:
        catalog = build_pages_site.build_catalog(REPO_ROOT)
        self.assertEqual(len(catalog["assets"]), 974)
        self.assertEqual(catalog["canvas"], [1254, 1254, "RGBA"])
        self.assertNotIn("source_ref", json.dumps(catalog))
```

- [ ] **Step 2：執行測試並確認 RED**

Run:

```text
C:\ComfyUI_windows_portable\python_embeded\python.exe -m unittest tests.test_pages_site.PagesCatalogTests -v
```

Expected: FAIL，因 `tools/build_pages_site.py` 尚不存在。

- [ ] **Step 3：最小實作 path parser 與 catalog**

Parser 必須逐一 full-match 下列七種正式 path shape；任何未配對路徑直接拋出 `PagesBuildError`：

```text
assets/{female|male}/{E|M}/{E01..E06|M01..M06}/{S01..S04}/{N00|G01..G04|X01..X03}/{file}
assets/{female|male}/base/{F01..F05}/{S01..S04}/{file}
assets/{female|male}/expression/{Fxx_Sxx_expression}/{file}
assets/{female|male}/hair/{H01..H05}/{file}
assets/{female|male}/clothing/{C01..C05}/{file}
assets/{female|male}/effects/{blush|sweat}/{Fxx_Sxx_expression}/{file}
assets/shared/ears/{human|elf}/F01/{S01..S04}/{file}
```

`parse_release_path` 的回傳 schema 固定為 `gender`、`family`、`component`、`face`、`skin`、`expression`、`role`、`ear`；不適用欄位寫 `None`。`role` 必須從已知 filename stem 白名單解析，不能把任意 filename 直接接受。`build_catalog` 只把 `release_path`、`sha256`、`bytes` 與上述解析結果輸出，不得複製 `source_ref` 或 `source_authority`。

```python
LFS_HEADER = b"version https://git-lfs.github.com/spec/v1\n"
CANVAS = [1254, 1254, "RGBA"]

def build_catalog(repo_root: Path) -> dict:
    manifest_path = repo_root / "provenance" / "asset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = []
    for entry in manifest["assets"]:
        parsed = parse_release_path(entry["release_path"])
        assets.append({
            "path": entry["release_path"],
            "sha256": entry["sha256"],
            **parsed,
        })
    return {
        "schema": "modular-portrait-web-catalog-v1",
        "source_manifest_sha256": sha256(manifest_path),
        "canvas": CANVAS,
        "assets": assets,
    }
```

- [ ] **Step 4：補 artifact 安全測試並再次確認 RED**

```python
def test_build_rejects_lfs_pointer_hash_drift_and_path_traversal(self) -> None:
    for corrupt_mode in ("lfs-pointer", "hash-drift", "traversal"):
        fixture = self.make_fixture(corrupt_mode=corrupt_mode)
        with self.assertRaises(build_pages_site.PagesBuildError):
            build_pages_site.build_site(fixture.root, fixture.output)

def test_build_copies_resolved_assets_and_is_deterministic(self) -> None:
    fixture = self.make_fixture()
    first = build_pages_site.build_site(fixture.root, fixture.output_a)
    second = build_pages_site.build_site(fixture.root, fixture.output_b)
    self.assertEqual(first["catalog_sha256"], second["catalog_sha256"])
    self.assertFalse(
        (fixture.output_a / fixture.asset_path).read_bytes().startswith(LFS_HEADER)
    )
```

Run the same test command. Expected: new artifact tests FAIL because `build_site` is missing.

- [ ] **Step 5：實作 deterministic artifact build**

```python
def build_site(repo_root: Path, output_dir: Path) -> dict:
    catalog = build_catalog(repo_root)
    safe_output = prepare_output(repo_root, output_dir)
    copy_site_source(repo_root / "site", safe_output)
    for record in catalog["assets"]:
        source = checked_asset(repo_root, record)
        destination = safe_join(safe_output, record["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    write_canonical_json(safe_output / "catalog.json", catalog)
    (safe_output / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copyfile(repo_root / "LICENSE", safe_output / "LICENSE")
    return build_summary(safe_output, catalog)
```

`checked_asset` 必須先檢查 LFS header，再比對 SHA-256；`prepare_output` 只允許刪除明確傳入且不等於 repo root 的 output directory。

- [ ] **Step 6：驗證 GREEN、compile 與 diff**

```text
C:\ComfyUI_windows_portable\python_embeded\python.exe -m unittest tests.test_pages_site -v
C:\ComfyUI_windows_portable\python_embeded\python.exe -m compileall -q tools tests
git diff --check
```

Expected: PASS，暫時的完整 `build_site` 測試可用 minimal `site/index.html` fixture，而不是依賴尚未建立的真實 UI。

- [ ] **Step 7：Commit**

```text
git add .gitignore tools/build_pages_site.py tests/test_pages_site.py
git commit -m "Add the validated Pages catalog builder"
```

---

### Task 2：建立 catalog index、相容選擇與固定 seed recipe

**Files：**
- Create: `site/lib/catalog.mjs`
- Create: `site/lib/selection.mjs`
- Create: `site/tests/catalog.test.mjs`
- Create: `site/tests/selection.test.mjs`
- Create: `site/tests/fixtures.mjs`

**Interfaces：**
- Consumes: `catalog.json` records from Task 1。
- Produces: `createCatalogIndex(catalog)`、`availableValues(index, selection, axis)`、`resolveLayerBindings(index, selection)`、`defaultSelection(index)`、`normalizeSelection(index, selection, options)`、`randomSelection(index, seed, options)`、`buildRecipe(index, selection, seed)`。

- [ ] **Step 1：寫 catalog/selection failing tests**

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { FIXTURE_CATALOG } from './fixtures.mjs';
import {
  createCatalogIndex, availableValues, resolveLayerBindings,
} from '../lib/catalog.mjs';
import {
  defaultSelection, normalizeSelection, randomSelection, buildRecipe,
} from '../lib/selection.mjs';

test('compatibility exposes only cells present in the catalog', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  assert.deepEqual(
    availableValues(index, { gender: 'female', skin: 'S02', expression: 'G03' }, 'E'),
    ['E01'],
  );
});

test('same seed and catalog produce the same non-extended recipe', () => {
  const index = createCatalogIndex(FIXTURE_CATALOG);
  const first = randomSelection(index, 3186449067, { extended: false });
  const second = randomSelection(index, 3186449067, { extended: false });
  assert.deepEqual(first, second);
  assert.doesNotMatch(first.expression, /^X/);
  assert.deepEqual(buildRecipe(index, first, 3186449067), buildRecipe(index, second, 3186449067));
});
```

`site/tests/fixtures.mjs` 要以一個 `asset(fields)` helper 產生完整 catalog record，固定 `canvas: [1254, 1254, 'RGBA']` 與 catalog hash。Fixture 至少涵蓋：female `S01/S02`、male `S01/S04`、`N00/G02/G03/X01`、一個只有 female `S01` 支援的 `E06`、human/elf ears、帶／不帶 `hair_ear_cover` 的 hairstyle，以及完整 neutral/expression/effect layer pair。測試不得引用未宣告的常數。

- [ ] **Step 2：執行並確認 RED**

Run: `node --test site/tests/catalog.test.mjs site/tests/selection.test.mjs`

Expected: FAIL with module-not-found。

- [ ] **Step 3：實作 catalog index 及正式 layer resolver**

```js
export function createCatalogIndex(catalog) {
  validateCatalog(catalog);
  const byLogicalKey = new Map();
  for (const asset of catalog.assets) {
    const key = logicalKey(asset);
    if (byLogicalKey.has(key)) throw new CatalogError(`Ambiguous asset: ${key}`);
    byLogicalKey.set(key, Object.freeze({ ...asset }));
  }
  return Object.freeze({ catalog, byLogicalKey });
}

export function resolveLayerBindings(index, selection) {
  const facePair = resolveExpressionFacePair(index, selection)
    ?? resolveNeutralFacePair(index, selection);
  const bindings = expressionOrder(facePair, selection, index);
  return bindings.map((binding, order) => ({ order, ...binding }));
}
```

Resolver 的 exact order、optional layer、shared ears 及 face ownership reset 必須由 tests 斷言；不存在或不完整 pair 直接 throw。

- [ ] **Step 4：實作 fixed PRNG、normalization 與 recipe**

```js
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

export function randomSelection(index, seed, { extended = false } = {}) {
  const random = mulberry32(seed);
  const selection = defaultSelection(index);
  // Draw in the fixed order gender, skin, expression, F, E, M, H, C, ear, hue;
  // normalize after each constrained axis and never draw X-series when extended=false.
  return drawCompatibleSelection(index, selection, random, extended);
}
```

`buildRecipe` 必須附 source catalog hash 與 ordered bindings；任何 `C:\\`、`/home/` 或 `source_ref` 出現即測試失敗。

- [ ] **Step 5：執行 GREEN 與 full JS tests**

```text
node --test site/tests/*.test.mjs
git diff --check
```

Expected: all Task 2 tests PASS。

- [ ] **Step 6：Commit**

```text
git add site/lib/catalog.mjs site/lib/selection.mjs site/tests/catalog.test.mjs site/tests/selection.test.mjs site/tests/fixtures.mjs
git commit -m "Add deterministic compatible portrait selection"
```

---

### Task 3：建立原生 Canvas compositor 與髮色演算法

**Files：**
- Create: `site/lib/compositor.mjs`
- Create: `site/tests/compositor.test.mjs`
- Modify: `site/lib/catalog.mjs`
- Modify: `site/tests/catalog.test.mjs`

**Interfaces：**
- Consumes: ordered bindings from `resolveLayerBindings`。
- Produces: `deriveHairPalette(hue)`、`buildLuminanceLut(palette)`、`tintRgba(source, mask, lut, toneMap)`、`PortraitCompositor.render(selection, bindings, signal)`、`PortraitCompositor.toPngBlob()`。

- [ ] **Step 1：寫 pure pixel 與 render-version failing tests**

```js
function identityLut() {
  return Uint8ClampedArray.from(
    { length: 256 * 3 },
    (_, offset) => Math.floor(offset / 3),
  );
}

function identityToneMap() {
  return Uint8ClampedArray.from({ length: 256 }, (_, value) => value);
}

test('hair tint changes only mask-owned RGB and preserves every alpha byte', () => {
  const source = new Uint8ClampedArray([
    40, 50, 60, 0,
    80, 90, 100, 128,
    120, 130, 140, 255,
  ]);
  const mask = new Uint8ClampedArray([255, 0, 255]);
  const output = tintRgba(source, mask, identityLut(), identityToneMap());
  assert.deepEqual([output[3], output[7], output[11]], [0, 128, 255]);
  assert.deepEqual([...output.slice(4, 7)], [...source.slice(4, 7)]);
  assert.notDeepEqual([...output.slice(8, 11)], [...source.slice(8, 11)]);
});
```

Stale-render test 使用測試內宣告的 deferred image loader：先呼叫 `render({ recipe: { recordId: 'old' } }, oldBindings)`，再呼叫 `render({ recipe: { recordId: 'new' } }, newBindings)`；先 resolve new promise、再 resolve old promise，最後斷言 `committedRecipe.recordId === 'new'`，且舊 render 回傳 `{ committed: false }`。測試 helper、selection、bindings 都要在該 test file 明確建立，不得依賴 browser global。

- [ ] **Step 2：執行並確認 RED**

Run: `node --test site/tests/compositor.test.mjs`

Expected: FAIL，`compositor.mjs` 尚不存在。

- [ ] **Step 3：實作 OKLCH palette、tone map 與 RGB-only tint**

```js
export function tintRgba(source, maskAlpha, lut, toneMap) {
  const output = new Uint8ClampedArray(source);
  for (let pixel = 0; pixel < source.length / 4; pixel += 1) {
    const offset = pixel * 4;
    if (maskAlpha[pixel] === 0 || source[offset + 3] === 0) continue;
    const luminance = srgbLuminanceIndex(source[offset], source[offset + 1], source[offset + 2]);
    const target = toneMap[luminance] * 3;
    output[offset] = lut[target];
    output[offset + 1] = lut[target + 1];
    output[offset + 2] = lut[target + 2];
  }
  return output;
}
```

Palette anchors、tone-map rank normalization 與 hue range 必須跟 public offline renderer 的 v06 contract 對齊；不要以 CSS filter 代替。

- [ ] **Step 4：實作 Canvas render lifecycle**

```js
export class PortraitCompositor {
  #version = 0;
  #committedRecipe = null;

  async render(selection, bindings, signal) {
    const version = ++this.#version;
    const sources = await this.loader.loadAll(bindings, signal);
    const frame = await composeFrame(this.canvasFactory, selection, bindings, sources);
    if (version !== this.#version || signal?.aborted) return { committed: false };
    this.outputContext.putImageData(frame, 0, 0);
    this.#committedRecipe = selection.recipe;
    return { committed: true, recipe: this.#committedRecipe };
  }

  toPngBlob() {
    return canvasToBlob(this.outputCanvas, 'image/png');
  }
}
```

`composeFrame` 必須保存 face checkpoint；遇到 `face_expression_head`／`earless_head` role 時依 alpha ownership 從 checkpoint 回復 pixels，而不是普通 drawImage。

- [ ] **Step 5：執行 GREEN 與回歸**

```text
node --test site/tests/*.test.mjs
C:\ComfyUI_windows_portable\python_embeded\python.exe -m unittest discover -s tests -v
```

Expected: JS tests PASS；既有 Python 13 tests 仍 PASS。

- [ ] **Step 6：Commit**

```text
git add site/lib/compositor.mjs site/tests/compositor.test.mjs site/lib/catalog.mjs site/tests/catalog.test.mjs
git commit -m "Add the browser portrait compositor"
```

---

### Task 4：建立雙語、accessible、responsive UI shell

**Files：**
- Create: `site/lib/i18n.mjs`
- Create: `site/tests/i18n.test.mjs`
- Create: `site/index.html`
- Create: `site/styles.css`
- Modify: `tests/test_pages_site.py`

**Interfaces：**
- Consumes: Task 2/3 modules later由 `app.mjs` 接線。
- Produces: `MESSAGES`、`createTranslator(language)`、所有固定 DOM IDs/data-axis hooks、CSS desktop/mobile layout。

- [ ] **Step 1：寫 i18n 與 static shell failing tests**

```js
test('English and Traditional Chinese dictionaries have identical keys', () => {
  assert.deepEqual(
    Object.keys(MESSAGES.en).sort(),
    Object.keys(MESSAGES['zh-Hant']).sort(),
  );
});

test('translator rejects missing keys instead of showing undefined', () => {
  const t = createTranslator('en');
  assert.throws(() => t('missing.key'), /Missing translation/);
});
```

```python
from html.parser import HTMLParser

class HtmlProbe(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.feed(html)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.elements.append((tag, dict(attrs)))

    def by_id(self, element_id: str) -> tuple[str, dict[str, str | None]]:
        return next(item for item in self.elements if item[1].get("id") == element_id)

    def canvas_size(self, element_id: str) -> tuple[int, int]:
        tag, attrs = self.by_id(element_id)
        if tag != "canvas":
            raise AssertionError(f"{element_id} is not a canvas")
        return int(attrs["width"]), int(attrs["height"])

    def has_live_region(self, element_id: str) -> bool:
        return self.by_id(element_id)[1].get("aria-live") in {"polite", "assertive"}

    def interactive_ids(self) -> set[str]:
        interactive = {"button", "input", "select", "textarea"}
        return {
            attrs["id"]
            for tag, attrs in self.elements
            if tag in interactive and attrs.get("id")
        }

def test_site_shell_has_required_accessible_controls(self) -> None:
    document = HtmlProbe((REPO_ROOT / "site" / "index.html").read_text("utf-8"))
    self.assertEqual(document.canvas_size("portrait-canvas"), (1254, 1254))
    self.assertTrue(document.has_live_region("status"))
    required = {
        "language", "gender", "face", "skin", "ear", "expression",
        "eyes", "mouth", "extended", "hair", "hair-hue", "clothing",
        "randomize", "reset", "download", "copy-recipe",
    }
    self.assertTrue(
        required.issubset(document.interactive_ids()),
        required - document.interactive_ids(),
    )
```

- [ ] **Step 2：執行並確認 RED**

```text
node --test site/tests/i18n.test.mjs
C:\ComfyUI_windows_portable\python_embeded\python.exe -m unittest tests.test_pages_site -v
```

Expected: FAIL，i18n、HTML、CSS 尚不存在。

- [ ] **Step 3：實作完整雙語 dictionary 及 translator**

```js
export const MESSAGES = Object.freeze({
  en: Object.freeze({
    'app.title': 'Modular Portrait Mixer',
    'action.randomize': 'Randomize',
    'action.download': 'Download PNG',
    'expression.extended': 'Extended expressions',
    'status.ready': 'Portrait ready',
  }),
  'zh-Hant': Object.freeze({
    'app.title': '模組化大頭相混編器',
    'action.randomize': '隨機混編',
    'action.download': '下載 PNG',
    'expression.extended': '進階表情',
    'status.ready': '角色圖已完成',
  }),
});
```

實際 dictionary 必須涵蓋每個 label、button、status/error、license/footer 文案；tests 比較 exact keys。

- [ ] **Step 4：實作 semantic HTML 與 responsive CSS**

HTML 必須使用真實 `label for`、`fieldset/legend`、`button`、`aria-live`，canvas 寫死 `width="1254" height="1254"`。CSS desktop 使用雙欄，`@media (max-width: 860px)` 改為 preview-first 單欄；加入 `:focus-visible` 與 `@media (prefers-reduced-motion: reduce)`。

- [ ] **Step 5：執行 GREEN、HTML/static validation**

```text
node --test site/tests/*.test.mjs
C:\ComfyUI_windows_portable\python_embeded\python.exe -m unittest tests.test_pages_site -v
git diff --check
```

- [ ] **Step 6：Commit**

```text
git add site/lib/i18n.mjs site/tests/i18n.test.mjs site/index.html site/styles.css tests/test_pages_site.py
git commit -m "Add the bilingual portrait mixer interface"
```

---

### Task 5：接通 UI state、render、下載與 recipe

**Files：**
- Create: `site/app.mjs`
- Create: `site/lib/app-state.mjs`
- Create: `site/tests/app-state.test.mjs`
- Modify: `site/index.html`
- Modify: `site/styles.css`
- Modify: `site/lib/selection.mjs`

**Interfaces：**
- Consumes: `createCatalogIndex`、selection APIs、`PortraitCompositor`、`createTranslator`。
- Produces: `app-state.mjs` 的 `createAppState(index, initial)`、`reduceAppState(state, event, index)`，以及 `app.mjs` 的 browser bootstrap、download/copy actions。

- [ ] **Step 1：寫 app state reducer failing tests**

```js
import { FIXTURE_CATALOG } from './fixtures.mjs';
import { createCatalogIndex } from '../lib/catalog.mjs';
import { createAppState, reduceAppState } from '../lib/app-state.mjs';

const INDEX = createCatalogIndex(FIXTURE_CATALOG);

test('enabling extended expressions changes availability without selecting X automatically', () => {
  const initial = createAppState(INDEX, { extended: false, expression: 'G02' });
  const next = reduceAppState(initial, { type: 'set-extended', value: true }, INDEX);
  assert.equal(next.selection.expression, 'G02');
  assert(next.options.expression.includes('X01'));
});

test('upstream changes normalize incompatible downstream values', () => {
  const stateWithFemaleOnlyE06 = createAppState(INDEX, {
    gender: 'female', skin: 'S01', expression: 'G02', E: 'E06',
  });
  const next = reduceAppState(
    stateWithFemaleOnlyE06,
    { type: 'set-axis', axis: 'skin', value: 'S04' },
    INDEX,
  );
  assert(next.options.E.includes(next.selection.E));
  assert.notEqual(next.selection.E, 'E06');
  assert.match(next.notice, /E06/);
});
```

- [ ] **Step 2：執行並確認 RED**

Run: `node --test site/tests/app-state.test.mjs`

Expected: FAIL，`site/lib/app-state.mjs` 尚不存在。

- [ ] **Step 3：實作 pure state reducer**

```js
export function reduceAppState(state, event, index) {
  if (event.type === 'set-axis') {
    const requested = { ...state.selection, [event.axis]: event.value };
    const normalized = normalizeSelection(index, requested, { extended: state.extended });
    return deriveUiState(state, normalized.selection, normalized.adjustments, index);
  }
  if (event.type === 'randomize') {
    const seed = event.seed >>> 0;
    return deriveUiState(state, randomSelection(index, seed, state), [], index);
  }
  return reduceNonSelectionState(state, event, index);
}
```

- [ ] **Step 4：實作 browser bootstrap 與 side effects**

`bootstrap()` fetch `./catalog.json`、建立 index/compositor、填入 controls、排程 render。每次 render 使用新的 `AbortController`；完成前 disable download。`Download PNG` 以 object URL 下載 `modular-portrait-<seed>.png` 並 revoke URL。`Copy recipe JSON` 先用 Clipboard API，失敗則顯示可選取 `<textarea>` fallback。local storage 只可讀寫 `portrait-mixer-language`。

`site/app.mjs` 只在 `document` 存在時呼叫 `bootstrap()`；純 reducer 永遠留在 `site/lib/app-state.mjs`，避免 Node test import 時意外存取 DOM。

- [ ] **Step 5：執行 GREEN 與 full local tests**

```text
node --test site/tests/*.test.mjs
C:\ComfyUI_windows_portable\python_embeded\python.exe -m unittest discover -s tests -v
git diff --check
```

- [ ] **Step 6：Commit**

```text
git add site/app.mjs site/lib/app-state.mjs site/tests/app-state.test.mjs site/index.html site/styles.css site/lib/selection.mjs
git commit -m "Connect portrait controls and export actions"
```

---

### Task 6：建立 Pages workflow、文件及上線驗收

**Files：**
- Create: `.github/workflows/pages.yml`
- Modify: `tests/test_pages_site.py`
- Modify: `README.md`
- Modify: `site/index.html`
- Modify: `tools/build_pages_site.py`

**Interfaces：**
- Consumes: Task 1–5 tests/build/UI。
- Produces: deployable `.pages-dist`、GitHub Pages deployment、README live-demo link。

- [ ] **Step 1：先寫 workflow/build contract failing tests**

```python
def test_pages_workflow_resolves_lfs_and_runs_every_gate(self) -> None:
    workflow = (REPO_ROOT / ".github/workflows/pages.yml").read_text("utf-8")
    for required in (
        "lfs: true",
        "validate_release.py .",
        "node --test site/tests/*.test.mjs",
        "python -m unittest discover -s tests -v",
        "build_pages_site.py . .pages-dist",
        "actions/upload-pages-artifact@v4",
        "actions/deploy-pages@v4",
    ):
        self.assertIn(required, workflow)

def test_readme_links_to_the_public_pages_site(self) -> None:
    readme = (REPO_ROOT / "README.md").read_text("utf-8")
    self.assertIn(
        "https://harvey831.github.io/modular-portrait-assets/",
        readme,
    )
```

- [ ] **Step 2：執行並確認 RED**

Run: `C:\ComfyUI_windows_portable\python_embeded\python.exe -m unittest tests.test_pages_site -v`

Expected: FAIL，workflow 尚不存在，README 尚未有 live demo。

- [ ] **Step 3：實作 least-privilege Pages workflow**

```yaml
name: Deploy portrait mixer to Pages

on:
  workflow_dispatch:
  push:
    branches: [main]

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          lfs: true
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install -r requirements.txt
      - run: python skill/modular-portrait-assets/scripts/validate_release.py .
      - run: node --test site/tests/*.test.mjs
      - run: python -m unittest discover -s tests -v
      - run: python tools/build_pages_site.py . .pages-dist
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v4
        with:
          path: .pages-dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/deploy-pages@v4
        id: deployment
```

若 YAML parser 對 `${{ ... }}` 需要 escape，只在實際檔案使用原生 GitHub syntax；不可用 secret 或 broad write permissions。

- [ ] **Step 4：更新 README 與 public shell links**

README 開頭加入 `Live Portrait Mixer` 連結、功能清單、1254×1254 與瀏覽器本機合成說明。Site footer 連向 repo、LICENSE、provenance、validator；不得引用私人路徑。

- [ ] **Step 5：執行全部新鮮驗證**

```text
node --test site/tests/*.test.mjs
C:\ComfyUI_windows_portable\python_embeded\python.exe -m unittest discover -s tests -v
C:\ComfyUI_windows_portable\python_embeded\python.exe skill\modular-portrait-assets\scripts\validate_release.py .
C:\ComfyUI_windows_portable\python_embeded\python.exe tools\build_pages_site.py . .pages-dist
C:\ComfyUI_windows_portable\python_embeded\python.exe -c "import json,pathlib; s=json.loads(pathlib.Path('.pages-dist/build-summary.json').read_text()); assert s['asset_count']==974 and s['lfs_pointer_count']==0 and s['canvas']==[1254,1254,'RGBA']; print(s)"
git diff --check
```

Expected:

- Node tests 全綠；
- Python tests 全綠；
- validator 回報 974 assets、172106675 bytes、PASS；
- build summary 回報 974 assets、0 LFS pointers、1254×1254；
- `.pages-dist/index.html` 及 `.pages-dist/catalog.json` 存在。

- [ ] **Step 6：本機瀏覽器 runtime verification**

啟動：

```text
C:\ComfyUI_windows_portable\python_embeded\python.exe -m http.server 8000 --directory .pages-dist
```

以 browser DevTools 驗證 1440×1000 及 390×844：初始 portrait、每個 selector、Randomize、Reset、extended toggle、雙語、recipe、PNG download、快速連續切換。Console 必須零 error；network request 不可出現 404；下載 PNG 必須是 1254×1254。

- [ ] **Step 7：Commit implementation/docs**

```text
git add .github/workflows/pages.yml tests/test_pages_site.py README.md site/index.html tools/build_pages_site.py
git commit -m "Deploy the portrait mixer with GitHub Pages"
```

- [ ] **Step 8：Code review、push 及遠端驗證**

1. 依 `code-review-and-quality` 做 correctness/readability/architecture/security/performance review。
2. 依 `verification-before-completion` 重跑 Step 5 所有命令。
3. Push `main`，確認兩個 LFS 圖例及所有既有 LFS object 不需重傳或成功存在。
4. 設定 Pages source 為 GitHub Actions；等待 workflow 完成。
5. 讀取 workflow logs，確認 build/deploy 都成功。
6. 開啟 `https://harvey831.github.io/modular-portrait-assets/` 重做關鍵 browser smoke test。
7. 確認遠端 `main` SHA、Pages URL、local working tree clean。

---

## 實作時的 review checkpoints

- Task 1 後：builder 只處理公開 manifest，synthetic corruption 全部 fail closed。
- Task 2 後：稀疏 lane 與 fixed seed recipe 已由純邏輯測試鎖定。
- Task 3 後：alpha ownership、head reset、hair tint、stale render 均有測試。
- Task 4 後：不依賴 JavaScript 也能由 HTML 看懂結構；雙語 keys 完整。
- Task 5 後：本機完整控制流程可運作，未觸碰部署設定。
- Task 6 後：全部 gates、視覺 QC、遠端 workflow 與公開 URL 都有新鮮證據。
