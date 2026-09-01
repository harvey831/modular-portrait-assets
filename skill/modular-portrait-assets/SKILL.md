---
name: modular-portrait-assets
description: Generate, assemble, QC, validate, or publish same-coordinate modular portrait assets from this CC0 library. Use for F/S/E/M/H/C portrait modules and public-release provenance; do not use for unrelated Godot runtime code.
---

# Modular Portrait Assets

Work only from files listed in `provenance/asset-manifest.json`. Validate the
release before selecting modules:

```text
python skill/modular-portrait-assets/scripts/validate_release.py <repo-root>
```

Stop if validation fails. Never select a file by revision number, timestamp,
`latest`, or visual similarity.

## Private V5 versioning route

For any private V5, E/M, different-S, modular QC, recovery, candidate,
promotion, old-version, or cleanup task, first read
[`references/version-management.md`](references/version-management.md) and use
`scripts/portrait_version_manager.py`. The female and male E/M contracts are
different: female includes X01-X03; male does not.

`different_s_em_status_version_manager_v01.py` is only a timed-worker
transaction ledger. It never selects components, promotes a revision, or
updates `_metadata/current/authority_manifest.json`; do not treat it as the
component version manager.

For female cross-skin E/M generation or repair, including a mouth that looks
shifted, shortened, cut, or contaminated by face-profile alpha, also read
[`references/female-expression-repair.md`](references/female-expression-repair.md).
It defines the flat-field donor, literal-coordinate, native-mask, and visual
gates that must pass before a complete candidate revision can be shown for
acceptance.

## Assembly contract

All production layers use the original 1254×1254 canvas. Do not crop, shift,
scale, rotate, mirror, warp, or blur a module to hide a registration mismatch.
Select one compatible gender, face/body identity `F`, skin `S`, eye+brow `E`,
mouth `M`, hair `H`, clothing `C`, and ear type.

Neutral order:

```text
hair_back -> clothing_back -> earless_head_body -> clothing_main
-> earless_head -> eye_brow -> mouth -> hair_front -> ear_pair
-> hair_ear_cover (optional) -> clothing_front
```

Expression/effect order:

```text
hair_back -> clothing_back -> face_expression_base -> clothing_main
-> face_expression_head -> blush -> eye_brow -> mouth -> sweat -> hair_front
-> ear_pair -> selected ear blush/sweat -> hair_ear_cover (optional)
-> clothing_front
```

Use ordinary alpha source-over compositing. Hair back remains a complete uncut
rear-hair owner; do not subtract `hair_front` alpha from it. Ears normally sit
above `hair_front`, with the optional hairstyle-owned ear-cover layer above the
ear. Clothing crossing the chin or face belongs in `clothing_front`.

For component meaning and compatibility checks, read
[`references/component-contract.md`](references/component-contract.md).

## Generating a new module

Use only project-owned or explicitly CC0 inputs. Before a generation call,
record input paths/hashes, the generation service or exact model and license,
the prompt, expected owner layer, canvas, and prohibited changes. Commercial
permission alone is not proof that the output can be dedicated to CC0.

When using OpenAI image generation, preserve the tool call record and output
hash. Do not claim that an AI output is unique. Never import a third-party
character, franchise, logo, stock image, or personal likeness into the CC0
release without separate authority.

For foreground extraction, do not use RMBG-2.0 in this public route. A
permissively licensed remover may create a mask, but record its exact code and
weight source. Never redistribute its weights inside this repository.

Every new module requires:

- exact source/output SHA-256;
- 1254×1254 coordinate preservation;
- isolated alpha inspection on black, white, magenta, and checkerboard;
- mixed assembly QC across multiple F/S/E/M/H/C combinations;
- explicit user acceptance and rights-holder CC0 declaration;
- manifest update followed by a clean validator pass.

## Publication gate

Run the export tool only against the private V5 source authority:

```text
python skill/modular-portrait-assets/scripts/export_release.py <private-v5-root> <clean-release-root>
```

It fails closed on hash mismatches, history/candidate/QC paths, RMBG-named
sources, unsupported files, model weights, or output collisions. It exports
only hash-bound `approved_authorities` payloads and writes a sanitized public
manifest. Do not bypass a failed gate or manually copy extra assets afterward.
