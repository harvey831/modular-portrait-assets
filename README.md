# Modular Portrait Assets

A same-coordinate 1254×1254 modular portrait library with female, male, and
shared components. The release contains hash-pinned current assets only; it
does not contain private work history, rejected candidates, QC scratch files,
model weights, or generation-service credentials.

Available component axes include face/body bases (`F`), skin tones (`S`),
eye+brow modules (`E`), mouth modules (`M`), hair (`H`), clothing (`C`),
human/elf ears, blush, and sweat layers. Exact available cells are listed in
[`provenance/asset-manifest.json`](provenance/asset-manifest.json).

## Examples

The repository includes two reproducible previews assembled from the released
modules. They are derivative QC/showcase images, not source modules or an
alternative asset authority.

### 48-character mixed QC

Every cell is a different deterministic combination. The board contains 24
female and 24 male portraits and mixes face, skin, eyes, mouth, hair, clothing,
ear type, hair colour, and expression.

![48-character mixed QC](examples/mixed-character-qc-48.webp)

### Expression showcase

Identity stays fixed within each gender while the expression lane changes.

![Expression showcase](examples/expression-showcase.png)

See [`examples/README.md`](examples/README.md) for exact coverage, reproduction
instructions, and the evidence manifest.

## License

Unless a file is specifically identified in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md), the assets, original
documentation, manifests, and original scripts in this repository are
dedicated to the public domain under **CC0 1.0 Universal**. Attribution is
appreciated but not required.

CC0 cannot waive trademark, patent, privacy, publicity, or non-waivable moral
rights. Do not imply that the project owner, OpenAI, Creative Commons, or any
tool author endorses a derivative work.

## Validate the release

```powershell
python -m pip install -r requirements.txt
python skill/modular-portrait-assets/scripts/validate_release.py .
python tools/render_examples.py . examples
```

The validator checks every asset hash, rejects unexpected files, and prevents
private-history paths or model weights from entering the package.

## Use the Codex skill

Copy `skill/modular-portrait-assets` into the Codex skills directory, or point
Codex at that folder. The skill describes safe assembly order, generation
provenance, QC, and the CC0 publication gate.

## Contributing assets

New art must be original or supplied by a rights holder who can dedicate it to
CC0. A contribution must include generation/source evidence, exact hashes,
coordinate and layer ownership, and an explicit rights declaration. Visual
similarity, a filename, or a model being "commercially usable" is not enough.
