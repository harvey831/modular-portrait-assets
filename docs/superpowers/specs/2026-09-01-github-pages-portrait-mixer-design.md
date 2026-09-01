# 規格：GitHub Pages 大頭相混編器

狀態：設計已批准，繁體中文為正式規格

日期：2026-09-01

Repository：`harvey831/modular-portrait-assets`

## 1. 目標

建立一個公開、雙語的 GitHub Pages 網頁，展示並使用本 repo 的 CC0
模組化大頭相素材。訪客可以組合相容的女性或男性角色、以固定 seed
隨機混編、調整髮色、查看組合配方，並下載原生 1254×1254 PNG。

這個網頁同時是作品展示與參考實作。它必須遵守素材庫的同座標、圖層
ownership 與來源雜湊契約；組合完成的角色圖只屬衍生展示圖，不可冒充為
可拆用的來源模組。

成功狀態：任何人不需要帳號、API key、後端、模型或外部生圖服務，便能
在公開網址完成「選擇 → 預覽 → 隨機混編 → 匯出」流程。

## 2. 已批准的產品決定

- 使用零後端的純靜態網站，透過 GitHub Actions 部署。
- 內部合成與 PNG 匯出維持原生 1254×1254 RGBA；CSS 只縮放畫面預覽。
- 預設英文，右上角可切換繁體中文；只在 local storage 記住語言。
- 預設顯示 `N00`、`G01`–`G04`；`X01`–`X03` 放在預設關閉的
  `Extended expressions` 開關後。
- 提供 `Randomize`、`Reset`、`Download PNG`、`Copy recipe JSON`。
- 不提供移動、旋轉、縮放、裁切、warp 或手動調整 z-order。
- 只使用正式 release manifest 內、具正確 SHA-256 的公開素材。

## 3. 前提假設

1. 支援現代桌面與手機瀏覽器，使用 ES modules、Canvas 2D、
   `createImageBitmap` 與 Clipboard API。剪貼簿失敗時要有可見 fallback，
   但不能阻止生圖與下載。
2. 公開 repo 是唯一素材權威；網站不得讀取私人 V5 路徑、工作歷史或候選圖。
3. 現有公開素材為 974 個圖檔、約 172 MB。部署可包含全部素材，但瀏覽器
   初次只下載 catalog 與目前選中的圖層。
4. GitHub Pages publishing source 設為 GitHub Actions。
5. GitHub Pages 不能直接發布 Git LFS pointer。workflow 必須先取回 LFS
   實體內容，再建立只包含普通靜態檔案的 Pages artifact；artifact 內出現
   LFS pointer 必須令 build 失敗。

## 4. 技術棧

- HTML5 與 responsive CSS，不加入 UI framework。
- Browser-native JavaScript ES modules，沒有 runtime package dependency。
- Canvas 2D 負責 alpha 合成、ownership mask reset、髮色、預覽及 PNG 匯出。
- Python 3 建立並驗證 Pages catalog/artifact；沿用 repo 現有 Pillow 依賴。
- Node 內建 `node:test` 測試 JavaScript 純邏輯。
- Python `unittest` 測試 build/catalog，並保留現有 release tests。
- GitHub Actions 使用 GitHub 官方 Pages actions。

## 5. 指令

在 repo root 執行：

```text
# 驗證 974 個正式素材
python skill/modular-portrait-assets/scripts/validate_release.py .

# JavaScript 單元測試
node --test site/tests

# Python 測試，包括既有 release 與 renderer 測試
python -m unittest discover -s tests -v

# 建立本機 Pages artifact
python tools/build_pages_site.py . .pages-dist

# 本機預覽
python -m http.server 8000 --directory .pages-dist
```

`.pages-dist/` 是可刪除 build output，必須加入 `.gitignore`，不可 commit。

## 6. 專案結構

```text
site/
  index.html                 公開入口
  styles.css                 responsive 暗色角色工房介面
  app.mjs                    DOM orchestration 與使用者操作
  lib/
    catalog.mjs              catalog index 與相容性查詢
    selection.mjs            預設值、固定 seed random、recipe
    compositor.mjs           Canvas 載圖、髮色及圖層合成
    i18n.mjs                 英文及繁體中文文字
  tests/
    catalog.test.mjs
    selection.test.mjs
    compositor.test.mjs
    i18n.test.mjs
tools/
  build_pages_site.py        驗證 catalog 與 Pages artifact
tests/
  test_pages_site.py         build/artifact integration tests
.github/workflows/
  pages.yml                  測試、build、upload、deploy
docs/superpowers/specs/
  2026-09-01-github-pages-portrait-mixer-design.md
```

生成的 artifact 包含網站檔案、精簡 `catalog.json`、`.nojekyll`、公開授權
說明，以及已從 LFS pointer 解出的 `assets/**` 圖檔實體內容。

## 7. 架構

### 7.1 Catalog builder

`tools/build_pages_site.py` 讀取 `provenance/asset-manifest.json`，驗證 manifest
shape 與來源檔案，再輸出瀏覽器真正需要的資料：公開相對路徑、SHA-256、
由路徑解析的 category/axis，以及 canvas contract。

以下情況必須 fail closed：

- 路徑是 absolute、含 traversal 或逃出 repo root；
- 圖檔不在正式 manifest、檔案不存在或 SHA-256 不符；
- 圖檔內容其實是 Git LFS pointer；
- 同一 logical component 出現多個相衝突檔案；
- 缺少網站必需檔或 1254×1254 canvas contract。

精簡 web catalog 不可包含 provenance 內的 `source_ref`。完整公開 provenance
仍保留在 repo，但瀏覽器不需要下載私人來源語境。

### 7.2 相容性模型

瀏覽器必須由 `catalog.json` 推導選項，不可假設所有 Cartesian combination
都存在。

- Gender 選擇 female 或 male 素材家族。
- `S` 與 expression 限制可用的 `E`、`M`。
- `F`、`S` 必須解析成同一套 face/body authority pair。
- Expression face/effect 只有成對齊全才使用；否則回到相容的 neutral F/S。
- `H`、`C` 只顯示該 gender 實際存在的家族。
- Human/elf ears 由選定膚色對應 shared ear authority。
- 上游選項改變時，若下游原選擇仍相容便保留；否則選擇穩定排序中的第一個
  相容值，並在 status region 告知使用者。

任何 control 都不得虛構缺少的 cell，亦不得以「看起來相似」的圖檔代替。

### 7.3 固定 seed 隨機混編

應用狀態包含 gender、F/S/E/M/H/C、ear、expression、hair hue、是否開啟
extended expressions，以及 numeric seed。

`Randomize` 使用已文件化且有測試的固定 PRNG 與固定抽選順序。相同 catalog
版本及 seed 必須產生相同 recipe。Random 只可從相容選項抽取，並在 recipe
記錄實際 seed。`Reset` 使用明確預設組合，不可依賴 object key 的偶然順序。

複製出的 recipe 為 UTF-8 JSON，包含 schema version、選定 module IDs、
expression、hue、seed、catalog hash、canvas、依序排列的公開 layer paths 及
hashes；不可含任何本機絕對路徑。

### 7.4 Canvas compositor

所有來源圖以 1254×1254 解碼。compositor 以 release path 快取已解碼圖像；
使用者快速改選項時，舊的 async render 必須作廢，不可在新結果後覆蓋畫面。

Neutral layer order：

```text
hair_back → clothing_back → earless_head_body → clothing_main
→ earless_head ownership reset → eye_brow → mouth → hair_front → ear_pair
→ hair_ear_cover（optional）→ clothing_front
```

Expression/effect layer order：

```text
hair_back → clothing_back → face_expression_base → clothing_main
→ face_expression_head ownership reset → blush → eye_brow → mouth → sweat
→ hair_front → ear_pair → ear blush/sweat → hair_ear_cover（optional）
→ clothing_front
```

`face_expression_head`／`earless_head` 是 ownership mask：其 alpha 擁有的像素
需要回復到 `clothing_main` 之前保存的 face checkpoint，不是普通 source-over
圖層。這必須與現有 public offline renderer 一致，防止服裝 main layer 遮住臉。

髮色使用所有選定 hairstyle owner layers 的共用 luminance tone map，以及由
所選 hue 生成的 OKLCH 四段 palette。只可在 `hair_tint_mask` 擁有且 source
可見的像素改 RGB；原始 alpha 與 geometry 必須完全不變。

完整 render 成功後才可換掉可見 canvas。若失敗，保留上一張成功圖、停用該次
pending export，並顯示失敗的公開 release path。

### 7.5 使用者介面

桌面版左側是大型預覽、右側是控制面板；手機版預覽在上、控制項在下。

- Identity：gender、face `F`、skin `S`、ear type。
- Expression：expression、eye+brow `E`、mouth `M`、extended toggle。
- Style：hair `H`、hair hue preset/slider、clothing `C`。

Header 說明它是 deterministic CC0 modular portrait mixer。Footer 連到 repo、
LICENSE、provenance 及 offline validator。匯出按鈕附近顯示簡短 recipe 摘要。

視覺風格是克制的暗色角色工房：深藍／炭黑底、暖金及青綠 accent、大圖優先，
不採用浮誇 AI neon。不得使用外部字型或 tracking resource。

必須支援 keyboard、清楚 focus、semantic labels、足夠對比、screen-reader status
announcement 及 `prefers-reduced-motion`。

### 7.6 雙語

預設英文，可在 header 切換繁體中文。所有使用者可見文字集中在 `i18n.mjs`，
兩套 dictionary 的 key 必須完全相同。Module IDs 與 recipe schema 不翻譯。
local storage 只保存 language code。

## 8. 程式風格

Catalog、selection 與 compositor 使用小型純函式及明確 data shape；DOM 操作
只放在 `app.mjs`。遇到 invariant violation 要明確報錯，不可 silent fallback。

```js
export function compatibleValues(index, selection, axis) {
  const values = index.query({
    gender: selection.gender,
    skin: selection.skin,
    expression: selection.expression,
    axis,
  });
  if (values.length === 0) {
    throw new CatalogError(`No compatible ${axis} values`);
  }
  return values;
}
```

錯誤訊息必須指出失敗的 axis 或公開 release path。

## 9. 測試策略

### 9.1 JavaScript 小型測試

- Catalog path 正確解析 axes，malformed/ambiguous records 會被拒絕。
- Compatibility query 絕不回傳不存在的 cell。
- 固定 seed 產生固定 recipe；extended toggle 關閉時不會抽到 X-series。
- 英文與繁中 dictionary keys 完全一致。
- Layer resolver 回傳正式 neutral/expression order 與正確 optional layers。
- Hair tint 只改 mask-owned RGB 並保持 alpha；使用微型 synthetic pixel buffer，
  不 mock Canvas framework 行為。

### 9.2 Python integration tests

- Build output 包含 `index.html`、`.nojekyll`、catalog、LICENSE 及實體圖檔。
- Catalog record count 與來源 manifest hash 相符。
- Traversal、hash drift、LFS pointer、duplicate logical asset 都令 build 失敗。
- 相同輸入產生 deterministic build catalog。

### 9.3 瀏覽器驗收

1. 初始 portrait 完整顯示，console 零 error，所選 JSON/image request 成功。
2. 所有 selector、Randomize、Reset、extended toggle、language toggle 在桌面及
   手機寬度正常。
3. 下載 PNG 精確為 1254×1254，並與可見 recipe 相符。
4. 複製 recipe 不含私人或本機絕對路徑。
5. 快速連續切換選項不會顯示過期 render。

### 9.4 Regression gates

- 現有 Python suite 全綠。
- Release validator 繼續驗證 974 個素材。
- 現有 reproducible example hashes 不變。

## 10. GitHub Pages 部署

`.github/workflows/pages.yml` 在相關檔案推上 `main` 時運行，也支援手動觸發。

Workflow：

1. Checkout repo 並取回 Git LFS 實體內容。
2. 執行 release validator、JavaScript tests、Python suite。
3. Build `.pages-dist`，確認沒有 LFS pointer。
4. 使用 `actions/configure-pages`、`actions/upload-pages-artifact` 及
   `actions/deploy-pages`；permissions 只給 `contents: read`、`pages: write`、
   `id-token: write`。

Artifact 必須低於 GitHub Pages 10 GB 限制。任何 LFS download、test、validator
或 build 失敗都要阻止部署，不發布部分完成網站。

預期網址：

```text
https://harvey831.github.io/modular-portrait-assets/
```

## 11. 安全與私隱

- 不使用 API key、登入、analytics、廣告、外部字型或 remote generation。
- 不從 catalog string 建立任意 HTML；ID 只放進 text node/option，並先驗證。
- Asset/catalog path 是 build tool 生成的 same-origin relative URL，不接受任意
  使用者 URL。
- Recipe copy/download 只輸出 data-only JSON。
- 只保存 language code；portrait selection 與圖片只留在記憶體，永不上傳。

## 12. 工作邊界

### 必須做

- Build/deploy 前驗證公開 release。
- 保持來源 hash-bound 與 1254×1254 contract。
- 新行為先寫 failing test；完成前執行 browser runtime verification。
- Composite/example 清楚標示為衍生展示，不是 source module。

### 必須先問

- 加入 frontend framework 或第三方 runtime dependency。
- 加入 analytics、remote storage、authentication 或其他 hosting provider。
- Release 後改 public recipe schema。
- 預設開啟 extended expressions。
- Downscale、crop 或建立另一套 lossy source asset authority。

### 絕不做

- 把 Git LFS pointer 當圖片發布。
- 讀取或洩漏私人 source path、credential、model weight 或 rejected candidate。
- 虛構缺少的 module combination 或暗中更改 ownership/layer order。
- 上傳訪客生成的 portrait 或 recipe。

## 13. 風險與對策

- **Pages/LFS 不相容：** Actions 先解出實體內容再上傳普通 artifact；pointer
  signature 直接令 build 失敗。
- **部署體積：** 約 172 MB，只在相關變更時部署；瀏覽器按選擇 lazy-load。
- **Canvas CPU：** cache decoded image/tone map、取消 stale render，顯示只用 CSS
  縮放，不維護第二張 render canvas。
- **Sparse compatibility：** 選單由實際 catalog 推導，並測試已知 female/male
  sparse lanes。
- **公開內容解讀：** X-series 預設隱藏，雙語清楚標示 opt-in control。

## 14. 完成標準

- 公開 Pages URL 不需登入，能顯示完整預設角色。
- 所有 axes 只能選擇實際相容值。
- 相同 seed 與 catalog 產生相同 recipe。
- Extended expressions 預設不可見，明確開啟後才出現。
- 英文及繁中介面完整且 keys 一致。
- Preview 與下載 PNG 都使用原生 1254×1254 composition。
- Hair tint 保持 alpha，只影響 mask-owned RGB。
- Recipe 包含依序排列的公開 paths/hashes，沒有私人路徑。
- 桌面及手機 browser check 沒有 console error。
- JavaScript tests、Python tests、974-asset validator、Pages build 與 Pages deploy
  全部通過。

## 15. 未決問題

沒有。產品範圍、部署方式、解析度、語言、表情政策、控制項及驗收標準都已在
寫入本文件前逐段以繁體中文確認並獲批准。
