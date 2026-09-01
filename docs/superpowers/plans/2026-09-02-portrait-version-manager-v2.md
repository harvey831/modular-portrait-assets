# Portrait Version Manager v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single fail-closed version lifecycle interface, adopt the exact female E/M recovery into complete formal revisions, validate/export the authorities, and push a clean public release commit.

**Architecture:** The private V5 tree remains the binary production authority while this Git repository owns canonical lifecycle tooling, coverage schemas, tests, the public skill, and approved exports. The manager plans every mutation first, validates exact hashes and gender-specific coverage, writes owner-correct evidence, and separates promotion from cleanup.

**Tech Stack:** Python 3 standard library, JSON, SHA-256, `unittest`, existing release exporter/validator, Git.

**Spec:** `docs/superpowers/specs/2026-09-02-portrait-version-manager-v2-design.md`

## Global Constraints

- Female E/M coverage is S01-S04 × N00/G01-G04/X01-X03; male E/M coverage is S01-S04 × N00/G01-G04.
- Never use a QC thumbnail, timestamp, revision label, or visual similarity as source authority.
- Every formal revision is complete for one identity and immutable after creation.
- Version Manager v2 never deletes files.
- Private candidates, history, QC, and absolute paths never enter the public release.
- The later S02-S04/M01/X03 correction is outside this recovery commit.

---

### Task 1: Coverage profiles and authority audit

**Files:**
- Create: `skill/modular-portrait-assets/references/version-management.json`
- Create: `skill/modular-portrait-assets/scripts/portrait_version_manager.py`
- Create: `tests/test_portrait_version_manager.py`

**Interfaces:**
- Produces: `load_profiles(path) -> dict`, `expected_em_paths(profile, identity) -> set[str]`, and `audit_authority(v5_root, gender, profile) -> dict`.

- [ ] **Step 1: Write failing coverage tests**

Test that `female_em_v1` yields 32 paths per identity, `male_em_v1` yields 20,
female includes X03, male excludes every X group, and malformed profiles fail.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `python -m unittest tests.test_portrait_version_manager -v`

Expected: import or missing-file failure for `portrait_version_manager`.

- [ ] **Step 3: Implement profile loading and read-only authority audit**

The audit must resolve only `approved_authorities.E` and `.M`, require one
identity record each, compare exact relative paths, verify file SHA-256, and
report missing/extra/hash-mismatch without modifying the library.

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_portrait_version_manager -v`

Expected: all Task 1 tests pass.

### Task 2: Deterministic recovery plan and cleanup gate

**Files:**
- Modify: `skill/modular-portrait-assets/scripts/portrait_version_manager.py`
- Modify: `tests/test_portrait_version_manager.py`

**Interfaces:**
- Produces: `plan_female_em_recovery(...) -> dict`, `verify_adoption_plan(plan) -> dict`, `apply_recovery_plan(...) -> dict`, `promote_recovery_plan(...) -> dict`, and `cleanup_check(manifest) -> dict`.

- [ ] **Step 1: Write failing recovery-plan tests**

Build temporary E02/M02 authorities with 11 retained files and a recovery
registry with 21 exact files per identity. Require a deterministic 32-file
candidate plan and failure on one missing, duplicated, wrong-gender, wrong-group,
or hash-mismatched file.

- [ ] **Step 2: Write failing cleanup tests**

Require failure for one copy, thumbnail-only evidence, unclassified staging,
pending promotion, or missing export status; require PASS only for two exact
copies plus lifecycle/evidence/export completion.

- [ ] **Step 3: Write failing apply/promotion transaction tests**

Require a full preflight before writes, collision refusal, complete candidates,
identity-local superseded placement, exact candidate-to-approved moves, an
atomic authority-manifest replacement, and rollback or a durable recovery
journal if any mutation step fails. The manager must never overwrite or delete
a component payload.

- [ ] **Step 4: Implement the minimal planner, transactions, and cleanup checker**

The planner emits source path, source SHA-256, identity, destination relative
path, and source role for every file. It refuses overwrite and does not select
by directory label. Apply and promotion re-verify the plan and all hashes,
write a transaction journal before mutation, and fail closed. The cleanup
checker emits JSON and never deletes.

- [ ] **Step 5: Run focused tests**

Run: `python -m unittest tests.test_portrait_version_manager -v`

Expected: all recovery and cleanup tests pass.

### Task 3: Skill routing and lifecycle documentation

**Files:**
- Modify: `skill/modular-portrait-assets/SKILL.md`
- Create: `skill/modular-portrait-assets/references/version-management.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Version Manager v2 CLI and coverage profile names from Tasks 1-2.
- Produces: one discoverable route for modular V5 versioning and cleanup.

- [ ] **Step 1: Add concise skill routing**

State that V5, E/M, S-skin, modular QC, recovery, promotion, or cleanup requests
must load the version-management reference and use Version Manager v2. Clarify
that the timed different-S status ledger is not the component authority.

- [ ] **Step 2: Document lifecycle and old-version placement**

Document identity-local approved/candidate/superseded/rejected revisions,
owner-correct work history and mixed QC, public Git-tag history, and the
cleanup gate.

- [ ] **Step 3: Ignore local itch upload state**

Add `/.itch-upload/` to `.gitignore`; do not delete or commit its contents.

- [ ] **Step 4: Validate the skill and run all repository tests**

Run: `python C:/Users/ihate/.codex/skills/.system/skill-creator/scripts/quick_validate.py skill/modular-portrait-assets`

Run: `python -m unittest discover -s tests -v`

Expected: skill validation and all tests pass.

### Task 4: Adopt the exact female recovery in private V5

**Files:**
- Create: private `_work_history/current/female_em_recovery_20260902_v01/`
- Create: private `_mixed_qc/current/female_em_recovery_assembly_qc_20260902_v01/`
- Create: E02-E06/M02-M06 `current/candidates/r20260902_complete_recovery_v01/`
- Modify: private `_metadata/current/authority_manifest.json`
- Move: prior E02-E06/M02-M06 approved revisions to identity-local `old_versions/superseded/`

**Interfaces:**
- Consumes: frozen recovery inventory, exact 210 payloads, retained 110 payloads, four old QC sheets, 192 fresh composites, and zero-difference report.
- Produces: ten complete 32-file formal revisions, immutable adoption/promotion records, and updated single authority.

- [ ] **Step 1: Run `plan-recovery` without writes**

Expected: ten identities, 320 destination files, 110 retained sources, 210
recovered sources, no collision, and every SHA-256 verified.

- [ ] **Step 2: Copy the dry-run plan and immutable evidence into owner-correct packages**

Preserve frozen inventory, recovery audit, historical runner hash, selected-lane
registry, old QC sheets, fresh rebuild report, and tool hashes. Do not copy
formal component payloads into QC evidence.

- [ ] **Step 3: Apply candidate creation and validate before promotion**

Expected: each candidate has exactly 32 files and its computed tree hash matches
the planned tree hash.

- [ ] **Step 4: Record acceptance and promote atomically**

Archive each prior partial approved revision under `old_versions/superseded`,
move the exact candidate directory to `current/approved`, update the authority
with separate payload/acceptance hashes and coverage, and write one promotion
event manifest.

- [ ] **Step 5: Run full female and male audits**

Expected: female 384/384 and male 240/240 formal E/M files exist and match
authority hashes; no missing, extra, duplicate-approved, or candidate collision.

- [ ] **Step 6: Run cleanup-check against the recovery work package**

Expected before public export: BLOCKED only by `public_export_pending`; all
other protection checks pass.

### Task 5: Export, validate, commit, and push

**Files:**
- Replace through clean export: `assets/`
- Replace through clean export: `provenance/asset-manifest.json`
- Replace through clean export: `provenance/authority-summary.json`
- Modify/Create: files from Tasks 1-3 and these spec/plan documents

**Interfaces:**
- Consumes: audited private current authorities.
- Produces: sanitized validated CC0 release and pushed Git commit.

- [ ] **Step 1: Export into a clean temporary release directory**

Run: `python skill/modular-portrait-assets/scripts/export_release.py <private-v5-root> <clean-temp-root>`

Expected: PASS with no candidate/history/QC/private-path source.

- [ ] **Step 2: Validate the clean release**

Run: `python skill/modular-portrait-assets/scripts/validate_release.py <clean-temp-root>`

Expected: `PASS`.

- [ ] **Step 3: Replace only managed public release outputs**

Copy the clean `assets/`, `provenance/asset-manifest.json`, and
`provenance/authority-summary.json`; preserve site, docs, examples, and local
itch state unless regenerated by their existing tested tools.

- [ ] **Step 4: Run the full suite and inspect the exact Git diff**

Run: `python -m unittest discover -s tests -v`

Run: `git status --short` and `git diff --check`.

Expected: tests pass; no `.itch-upload`, private history, QC, candidates, or
unrelated files are staged.

- [ ] **Step 5: Commit the scoped change**

Commit message: `Add fail-closed portrait version management`

- [ ] **Step 6: Push `main` and verify the remote commit**

Run: `git push origin main`, then verify `origin/main` resolves to local HEAD.

- [ ] **Step 7: Re-run cleanup-check with the pushed export commit**

Expected: PASS. The recovery source remains protected until this final check is
recorded; Version Manager v2 still performs no deletion.
