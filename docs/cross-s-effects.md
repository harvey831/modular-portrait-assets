# 跨膚色表情效果與 QC

本次修改只改組裝方式，不重畫、不更換 `assets/`，不變更 private authority。
使用者於 2026-09-02 回覆「OK」，接受上一則展示的 v04 淡化結果。
本次是組裝器／QC 視覺接受，不是來源素材升版，也不擴大為其他原檔問題的批准。
使用者另行明確授權 commit、push、更新 GitHub Pages／itch.io，並同步 skill。
實際部署結果以對應提交的 GitHub Actions 及公開頁面驗證為準。

## 原因與組裝規則

原本 resolver 只尋找同一個 S 的表情底臉、面紅和汗。當 S02–S04 沒有
獨立效果 PNG 時，會退回中性底臉並略過效果。E/M 齊全不代表效果也有載入。

現有 S01 面紅是已提取的配對差分透明圖，不是未提取的整張底臉。
它的 RGB 仍與 S01 底色相關，不能直接把淡膚色的 RGB 原樣蓋到深膚色。

| 部分 | 缺少同 S 原生版本時 |
| --- | --- |
| 女性 G02、X01–X03；男性 G02 底臉 | 目標 S 中性底臉 + 同 F 的 S01「表情底臉 − 中性底臉」RGB 差分 |
| 面紅 | 以對應的 S01 表情／中性底臉為 dry，取 `alpha × (效果 RGB − dry RGB)`，按目標 S 減弱後加到目標臉 |
| 耳朵面紅 | 同上，但 dry 必須是 S01 對應耳型的共用耳朵，不能拿無耳底臉當 dry |
| 汗及耳汗 | 沿用已提取的原 RGBA，以一般透明合成保留液滴高光 |
| E/M | 使用目標 S 原有模組，不換來源、不減弱 |

原生同 S 素材優先；S01 保持原有組裝結果。男性 N00 沒有效果層是合法空集合。
其他缺少必要來源或效果組不再靜默略過，而是明確報錯。
所有處理保持 1254×1254、原座標與底臉透明度，不縮放、不位移、不改幾何。

## 面紅強度

原本完整 S01 差分在深膚色上造成血紅色塊。使用者明確拒絕此效果，
因此只減弱面紅，不把整張圖、表情底臉、汗或眼淚一起減淡。

| 目標膚色 | 共用面紅差分強度 |
| --- | --- |
| S01 | 原生 RGBA 不改 |
| S02 | 65% |
| S03 | 45% |
| S04 | 25% |

這是本素材庫的視覺校準值，不是一般人類膚色的物理模型。
Web recipe 的 `pairedDelta` 與離線 renderer 的 `paired_delta` 記錄 dry、
donor（如適用）、來源 SHA-256、演算法及強度。後續新增膚色需明確校準，
不能默認套入完整強度。

## 驗證與證據

```powershell
node --test site/tests/*.test.mjs
python -B -m unittest discover -s tests -v
python -B skill/modular-portrait-assets/scripts/validate_release.py .
node tools/render_cross_skin_qc_v02.mjs python <全新的QC輸出資料夾>
node tools/render_cross_skin_qc_v02.mjs python <另一個全新的輸出資料夾> --blush-strengths
```

QC 使用實際 Web resolver/compositor，不以另一套模擬 renderer 代替。
完整模式檢查 520 組 layer bindings，產生男女 52 張原尺寸 PNG 和四膚色總覽。
強度模式用同一個角色比較 100%、50%、25%、0%，其他模組固定不變。
manifest 保存來源雜湊、selection、bindings、工具雜湊與輸出雜湊；
工具拒絕覆寫既有 QC 資料夾，也拒絕輸出到 `assets/` 內（含 Windows 大小寫別名）。
總覽縮圖只供檢視，不是來源素材。

QC 工具 v02 修正輸出路徑保護並沿用現有跨平台字型回退；不修改 v04 的
resolver/compositor。原工具 v01 的精確快照與接受證據保留，不回寫舊 manifest。
工具版本和 renderer 視覺版本是兩個不同維度。

v02 重跑確認 52 張角色 PNG、29 張獨立效果圖及 260 個來源與已接受的 v04
雜湊一致（包括 13 張 S01）。接受／重跑的工具及 manifest 雜湊分開記錄於
[`renderer-cross-s-v04.json`](../provenance/renderer-cross-s-v04.json)。

開發過程各輪輸出與獨立 review 記錄保留在 repo 外的版本化 QC 資料夾：

- v01：拒絕；minimum-alpha 逆解放大淡膚色微小差異，造成白斑。
- v02：需修正；汗也套差分，令高光變暗。
- v03：拒絕；完整強度面紅在深膚色上像血。
- v04：降低跨 S 面紅強度，汗保持原 RGBA；2026-09-02 使用者接受。

接受事件另存為 `acceptance-20260902-v01.json`，不改寫原本待確認的
`review.json`，也不改寫 v01–v03 的失敗紀錄。接受時重新核對 52 張輸出、
260 個來源及 3 個工具雜湊。綁定的 v04 manifest SHA-256：
`94d8c1e0fde2efde3c3a9f7b70da85a9d7f2aa9916a1ba9f8d68ac3566905b99`。

舊 `examples/` 是先前版本的展示證據，不由修 renderer 的步驟自動覆寫。
新的 QC 確認後，才另外更新公開展示或部署；不得把未通過的候選當成正式成果。
