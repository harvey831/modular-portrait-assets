# Cross-skin expression effects / 跨膚色共用

Use this route when approved target-S bases and E/M exist but expression faces
or effects only exist at S01. This is deterministic rendering, not generation,
extraction of new source assets, or component promotion. Preserve all source
bytes, full 1254×1254 coordinates and alpha. Native same-S assets take priority.

## Resolve owners first

- Share only across S within the same gender, F and expression. Never borrow
  another gender, F, expression, or a visually similar source.
- N00/G01/G03/G04 use the native target-S neutral paired base/head.
- Female G02/X01/X02/X03 and male G02 require expression-face detail. Male has
  no X expressions.
- Keep E and M native to the selected S and expression. Tears belong to E;
  saliva belongs to M. Do not attenuate either with blush.
- Shared human/elf ears are the intentional gender-shared family: choose the
  exact selected ear type and S. Ear effects remain gender/F/expression-bound.

## Registered operations

All RGB calculations below use decoded 8-bit sRGB channel values, not linear
light. Clamp/round the final RGB to bytes; do not change the target alpha.

| Layer | Missing same-S source |
| --- | --- |
| Expression face | Start with target-S neutral base; add matching S01 expression-base RGB minus matching S01 neutral-base RGB. Require identical source-pair and target alpha geometry. |
| Face blush | Use matching S01 expression face as dry for G02/female X; use matching neutral face for other expressions. Add `strength × sourceAlpha/255 × (blushRGB − dryRGB)` to the current face. |
| Ear blush | Same delta operation, but dry is the matching S01 shared **ear pair**, not the earless face. |
| Sweat / ear sweat | Ordinary source-over using the existing S01 extracted RGBA, retaining droplet highlights. |

Skip delta pixels where the source, dry or target alpha is zero. The face
checkpoint, with its derived expression RGB, is restored through the matching
head alpha above clothing; do not paint neutral head RGB over the expression.
Keep the normal layer order from `SKILL.md`.

The accepted v04 shared-blush calibration is S02 **0.65**, S03 **0.45**, S04
**0.25**. S01 and any native same-S effects retain their original rendering.
These are this library's visual calibration values, not a general skin model.
Apply the strength only to face/ear blush, not to face creases or liquids.
Any new S or changed policy requires a new explicit calibration and QC.

Existing blush is already paired-difference extracted. Skin-relative RGB does
not mean extraction was omitted. Do not paste the whole S01 face, re-extract
accepted assets, solve a minimum-alpha foreground (which amplifies tiny pale
skin differences), or apply the blush delta to sweat highlights.

Missing/incomplete required source pairs are errors, not permission to silently
fall back to a neutral expression or omit effects. The released male N00 has
no effect layers; intentionally transparent effect files are also valid.

## Reproduce, validate and accept

In the full repository, use `site/lib/catalog.mjs` and
`site/lib/compositor.mjs`; the equivalent offline path is
`tools/render_examples.py`. Do not build a competing resolver. If only this
skill package is installed and the renderer/tools are absent, locate the
matching repository revision before attempting assembly.

Record selection, ordered bindings, source manifest hash, each source/dry/donor
SHA-256, algorithm `signed-rgb-delta-v1`, blush strength, tool hashes and output
hashes. Web bindings use `pairedDelta`; offline bindings use `paired_delta`.
The repository's `provenance/renderer-cross-s-v04.json` is a renderer-acceptance
receipt, not a selector for component originals.

Use `tools/render_cross_skin_qc_v02.mjs <python> <unused-output-directory>`
for the actual browser-compositor QC: 520 binding checks and 52 portraits
covering four S values and both genders' expression sets. `--blush-strengths`
compares fixed-character strengths. Inspect full-size images as well as boards:
look for blood-red fields, pale patches, lost creases, dimmed sweat highlights
and mismatched ear effects. Numerical test success alone is not visual approval.

Keep prior outputs/reviews immutable. Append a separate acceptance event bound
to the demonstrated output, QC manifest and tool hashes; do not rewrite an old
pending/rejected verdict. Changes to source bytes or rendering policy invalidate
affected evidence and need new QC. Mere documentation changes do not alter
rendered pixels. Treat out-of-scope source defects separately.

Renderer acceptance does not replace assets or change private authority. New
component payloads use the separate version-manager workflow. Publish code or
skill changes only with user authorization, after tests/build/validation; then
verify live Pages and the public itch.io embed, not just a local preview.
