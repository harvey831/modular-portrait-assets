# Reproducible Examples

These images are deterministic derivatives assembled from the hash-pinned
modules in `assets/`. They are included for visual QC and capability
demonstration only. Do not treat either board as a reusable module or as an
asset-source authority.

## Included images

- `mixed-character-qc-48.webp` — a 6×8 board of 48 distinct combinations:
  24 female and 24 male portraits. It deliberately varies face, skin, eyes,
  mouth, hair, clothing, ear type, hair colour, and expression.
- `expression-showcase.png` — one fixed female identity across N00, G01–G04,
  and X01–X03; one fixed male identity across N00 and G01–G04. Only the
  expression lane changes within each gender.

The male release currently exposes H01, H02, and H04. Male H03 and H05 are
therefore intentionally excluded rather than fabricated. The female board
uses H01–H05.

## Reproduce

From the repository root:

```powershell
python -m pip install -r requirements.txt
python tools/render_examples.py . examples
```

Rendering uses deterministic alpha composition only; no generative model,
ComfyUI, WebUI, sampler, or remote service is invoked. The fixed master seed is
`3186449067`.

[`manifest.json`](manifest.json) records the source-manifest hash, renderer
hash, output hashes, coverage, every cell's module recipe, resolved source
paths and hashes, and generated hair-colour palette. This is the reproduction
and audit evidence for the two boards.
