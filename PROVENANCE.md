# Provenance and release boundary

This public package is a clean export from the private
`MODULAR_PORTRAIT_LIBRARY_V5` production library. Export selection is governed
by the female and male `approved_authorities` records and exact SHA-256 values,
not by folder timestamps or filenames.

The public manifest records each released file, its SHA-256, byte length,
sanitized source reference, and the hashes of the two authority manifests. Raw
prompts, generated-image service paths, rejected candidates, private QC, and
work history remain outside this repository.

## Creation route

The private evidence chain records user-directed OpenAI built-in image
generation/editing for regenerated donors, followed by deterministic
project-authored compositing, coordinate-preserving extraction, tint-mask
construction, and QC. Earlier accepted project-owned generations were also
used as locked identity/style inputs. No third-party stock artwork is
intentionally included in this release.

Thirty active modules previously affected by the old RMBG route were rebuilt
and promoted from fresh InSPyReNet masks in the accepted v03 revision. The old
RMBG outputs, masks, and history are not exported.

The project owner, as the party directing the generations and holding the
applicable rights in the inputs and outputs, applies CC0 only to the clean files
listed in `provenance/asset-manifest.json`. This statement does not claim that
AI output is unique and does not grant rights in third-party names, likenesses,
trademarks, or material accidentally resembling protected work.

## Reproducibility

The public package deliberately does not redistribute model weights. The
release validator is deterministic and can prove that the published bytes
match the manifest; full donor-generation records remain in the private source
library for audit when required.
