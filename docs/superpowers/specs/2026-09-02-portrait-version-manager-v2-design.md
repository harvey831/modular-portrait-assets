# Portrait Version Manager v2 Design

## Purpose

Prevent another loss of modular portrait source assets by replacing the current
multi-entry version workflow with one explicit lifecycle interface. The private
V5 library remains the full production authority; this Git repository remains
the canonical public skill, tooling, schemas, approved CC0 export, and release
history.

## Failure being corrected

The deleted female different-S E/M staging set exposed four independent gaps:

1. `different_s_em_status_version_manager_v01.py` manages timed job
   transactions, but its name made it look like the component version manager.
2. The real selector is each gender's
   `_metadata/current/authority_manifest.json`, which was not updated for
   E02-E06 and M02-M06.
3. QC evidence survived, but the 210 formal full-canvas payloads were left in
   staging instead of identity-owned revisions.
4. No cleanup gate required formal registration, two verified copies, and a
   published Git export before staging could be treated as disposable.

The recovery proves that the 210 payloads are byte-identical to the frozen
pre-deletion inventory, but recovery evidence is not itself a formal component
revision.

## Two-tier authority

### Private V5 production library

`MODULAR_PORTRAIT_LIBRARY_V5` owns:

- formal component revisions;
- the single female and male authority manifests;
- production inputs and extraction provenance under `_work_history`;
- mixed assembly QC under `_mixed_qc`;
- rejected and superseded private revisions.

The V5 folder is not a Git repository. Immutability therefore comes from exact
SHA-256 manifests, lifecycle directories, two verified copies before cleanup,
and fail-closed tooling.

### Public Git repository

This repository owns:

- the canonical public `modular-portrait-assets` skill;
- Version Manager v2 code, schemas, and tests;
- only assets exported from hash-bound `current/approved` authorities;
- sanitized provenance;
- Git commits, tags, and GitHub releases as public old-version history.

Private work history, candidates, rejected files, QC sheets, and absolute local
paths never enter the public release.

## One lifecycle interface

The canonical CLI is
`skill/modular-portrait-assets/scripts/portrait_version_manager.py`. It has
these responsibilities:

- `audit`: validate authority layout, lifecycle placement, coverage profile,
  file existence, SHA-256, and the exactly-one-approved-revision invariant;
- `plan-recovery`: validate a frozen recovery registry and produce a
  deterministic no-write adoption plan;
- `apply-recovery`: create complete identity-owned candidate revisions and a
  durable transaction journal from a verified plan;
- `promote`: archive the former approved revision, promote the exact accepted
  candidate, and atomically rewrite the single authority manifest;
- `build-cleanup-manifest`: bind separately classified immutable work/QC
  evidence to the promoted recovery and its two full-canvas copies;
- `cleanup-check`: refuse cleanup unless all protected artifacts have two
  verified copies, formal lifecycle state, immutable evidence, and either a
  validated Git export or an explicit private-only exemption.

The existing timed-job ledger keeps its narrow name and role in documentation:
it is a worker transaction ledger, not a component selector and not an
authority writer.

## Coverage profiles

Coverage is explicit data, never inferred from the other gender:

- `female_em_v1`: E01-E06 and M01-M06; S01-S04; N00, G01-G04, X01-X03;
  32 files per identity and 384 files total.
- `male_em_v1`: E01-E06 and M01-M06; S01-S04; N00, G01-G04; 20 files per
  identity and 240 files total. Male has no X01-X03.

The profiles live in
`skill/modular-portrait-assets/references/version-management.json` and are
validated by tests.

## Formal component layout

Every identity owns complete revisions:

```text
<category>/<identity>/
  current/
    approved/<revision>/
    candidates/<revision>/
  old_versions/
    superseded/<revision>/
    rejected/<revision>/
```

`current/approved` contains exactly one complete revision. A candidate that
changes only three cells still contains the full identity coverage. Promotion
moves the former approved revision to `old_versions/superseded`, promotes the
accepted candidate directory unchanged, and records a hash-bound event.

Rejected candidates move to `old_versions/rejected`. Nothing is overwritten,
renamed into an existing revision, or selected by timestamp/version label.

## Evidence layout

Production and recovery evidence:

```text
_work_history/
  current/<job-id>/
  old_versions/superseded/<job-id>/
  old_versions/rejected/<job-id>/
```

Cross-identity assembly evidence:

```text
_mixed_qc/
  current/<qc-id>/
  old_versions/superseded/<qc-id>/
  old_versions/rejected/<qc-id>/
```

Evidence packages reference formal components by path and SHA-256. They never
contain selectable component payloads and never act as `current` aliases.
Evidence remains under `current` while any active authority/candidate depends
on it; otherwise it moves to the matching old-version lifecycle.

## Female E/M recovery adoption

The recovery adoption is limited to E02-E06 and M02-M06. Each new complete
revision combines:

- the existing approved S01 N00/G01-G04/X01-X03 and S02-S04 N00 files; and
- the 210 recovered S02-S04 G01-G04/X01-X03 files whose SHA-256 matches the
  frozen pre-deletion registry.

The resulting revision has 32 files per identity. The 192-cell old QC, fresh
module rebuild, zero-difference report, frozen inventory, runner hash, and
recovery audit become immutable evidence. E01/M01 are not changed in this
adoption.

The later S02-S04/M01/X03 tongue correction is a separate candidate revision
and separate acceptance event.

## Cleanup gate

`cleanup-check` fails if any protected artifact is:

- absent from a hash-bound registry;
- represented only by a QC thumbnail/contact sheet;
- present in fewer than two verified locations;
- still the only source for a candidate or authority revision;
- missing its source/tool/remover/QC provenance;
- awaiting acceptance, promotion, or public export;
- inside an unclassified staging directory.

The gate emits a machine-readable report and never deletes anything. Cleanup
is a separate explicit action outside Version Manager v2.

## Git and release policy

- Export only from current approved authorities into a clean destination.
- Validate the clean export before replacing managed public assets/provenance.
- Do not commit `.itch-upload`, build output, private absolute paths, candidates,
  old private binaries, or QC evidence.
- Commit the Version Manager/tooling change separately from later M01/X03 work.
- Push only after the working tree contains no unrelated staged files and the
  complete test/validation suite passes.
- Preserve old public releases through Git tags/GitHub releases, not an
  `assets/old_versions` tree.

## Success criteria

1. Coverage profiles reject female/male contract confusion.
2. The recovered female E02-E06/M02-M06 identities each resolve to one complete
   32-file revision with exact hashes.
3. The old partial revisions remain in `old_versions/superseded`.
4. Work history and mixed QC are owner-correct and immutable.
5. Both gender authorities pass a full physical hash audit.
6. Cleanup-check refuses the original unsafe staging condition.
7. The public release validates, tests pass, and the scoped commit is pushed.
