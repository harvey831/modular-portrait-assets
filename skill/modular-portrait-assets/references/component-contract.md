# Component contract

## Axes

- `F`: complete face/head/body geometry identity.
- `S`: skin-tone variant using the same geometry and alpha for its F identity.
- `E`: eyes and brows only.
- `M`: mouth and oral feature only.
- `H`: rear hair, front hair, optional ear cover, and tint mask.
- `C`: clothing back, main, front, and tint mask.
- ears: shared human or elf family matched to the selected skin.
- effects: blush and sweat, including selected ear variants when supplied.

Matching numeric suffixes describe identity families; they do not require
`E03` to be paired with `M03`. Cross-mixing is a core library feature.

## Required invariants

- Use exactly one F/S face-body authority per assembly.
- Keep the matching `earless_head_body` and `earless_head` pair together.
- A module owns only its declared visual region; transparent RGB must not hide
  pixels belonging to another category.
- Tint changes modify intended RGB only and must not change alpha or geometry.
- Empty transparent layers are valid when a design genuinely has no content in
  that owner layer.
- A composite is QC evidence, not a reusable source module.

For missing same-S expression faces/effects, follow
[`cross-s-effects.md`](cross-s-effects.md). Reuse is restricted to matching
gender/F/expression sources; E/M remain target-S-native. Renderer-only reuse
does not select a new component revision.

## Rejection conditions

Reject a new module when any of these is observed:

- canvas, scale, landmark, or silhouette drift;
- source or output hash cannot be reproduced;
- feature pixels leak into the wrong owner layer;
- alpha halos, solid background residue, or clipped strands/garment edges;
- generation input rights or model/output terms are unknown;
- the only evidence is a filename, thumbnail, or visually similar image.
