# Version Manager v2

Use this reference for private `MODULAR_PORTRAIT_LIBRARY_V5` component
versioning. The private library is the binary production authority. This Git
repository is the canonical public skill, tool, tests, approved CC0 export, and
release history.

## Single authority and coverage

Each gender has one selector:

```text
<gender>/component_library_v1/_metadata/current/authority_manifest.json
```

For E/M assets, choose an explicit profile from `version-management.json`:

- `female_em_v1`: E01-E06 and M01-M06, S01-S04,
  N00/G01-G04/X01-X03, `.png`; 32 files per identity, 384 total.
- `male_em_v1`: E01-E06 and M01-M06, S01-S04, N00/G01-G04;
  `.webp`, 20 files per identity, 240 total. Male has no X groups.

Never infer one gender's coverage from the other.

## Revision lifecycle and old versions

Every identity owns complete, immutable revisions:

```text
<category>/<identity>/
  current/
    approved/<revision>/          # exactly one complete selected revision
    candidates/<revision>/        # complete but not selected
  old_versions/
    superseded/<revision>/        # formerly approved
    rejected/<revision>/          # explicitly rejected candidate
```

A three-cell fix is still packaged as a complete identity revision. Promotion
moves the old approved directory to that identity's `superseded` folder and
moves the accepted candidate directory unchanged to `current/approved`.
Nothing is overwritten and no revision is selected by its name or date.

Production/recovery evidence belongs under:

```text
_work_history/current/<job-id>/
_work_history/old_versions/{superseded|rejected}/<job-id>/
```

Cross-identity assembly QC belongs under:

```text
_mixed_qc/current/<qc-id>/
_mixed_qc/old_versions/{superseded|rejected}/<qc-id>/
```

QC packages reference formal components by path and SHA-256. They do not
contain selectable component payloads and never act as an authority. Public old
versions are Git tags/releases; do not publish private `old_versions`, work
history, candidates, or QC binaries.

## Commands

Set `<tool>` to
`skill/modular-portrait-assets/scripts/portrait_version_manager.py`.

Read-only gender audit:

```text
python <tool> audit <v5-root> female female_em_v1 --output <audit.json>
python <tool> audit <v5-root> male male_em_v1 --output <audit.json>
```

Recovery lifecycle:

```text
python <tool> plan-recovery <v5-root> <lane-registry.json> <recovery-root> <revision> <plan-id> female_em_v1 E02 E03 E04 E05 E06 M02 M03 M04 M05 M06 --output <plan.json>
python <tool> apply-recovery <plan.json> --output <apply-report.json>
python <tool> resume-apply <plan.json> --output <apply-report.json>
python <tool> promote <plan.json> <acceptance-record.json> --output <promotion-report.json>
```

`plan-recovery` is no-write. `apply-recovery` creates complete candidates only.
For a legacy lane registry whose paths point to deleted staging, pass
`--frozen-inventory <inventory.json>`; every selected SHA must match both that
frozen inventory and the deterministic recovered full-canvas path. An
`APPLY_NEEDS_RECOVERY` journal may be continued only with `resume-apply`, which
revalidates every classified staging/candidate tree before moving anything.
`promote` requires a hash-bound acceptance record tied to the exact plan. Both
mutating commands write a transaction journal first; promotion also preserves
the previous authority manifest. A failed preflight moves nothing.

Cleanup safety report:

```text
python <tool> cleanup-check <cleanup-protection.json> --output <report.json>
```

After promotion, build the protection manifest from the exact work/QC evidence:

```text
python <tool> build-cleanup-manifest <plan.json> <work-evidence-manifest.json> <qc-evidence-manifest.json> --public-export-status pending --output <cleanup-protection.json>
```

The cleanup check never deletes. It blocks unless every protected full-canvas
source is registry-bound, has two distinct exact copies, has completed formal
state/evidence/acceptance/promotion, has no unclassified staging, and is either
present in a pushed public export or covered by an explicit hash-bound
private-only exemption.

## Recovery acceptance record

Promotion requires a JSON file inside the private component library:

```json
{
  "schema": "portrait-recovery-acceptance-v1",
  "record_id": "unique-record-id",
  "decision": "accepted",
  "accepted_by": "user",
  "accepted_at": "ISO-8601 timestamp",
  "plan_sha256": "hash from the exact adoption plan"
}
```

Do not edit the plan after acceptance. A plan, source, candidate, authority, or
acceptance hash mismatch is a hard stop.
