from __future__ import annotations

import json
import hashlib
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skill" / "modular-portrait-assets" / "scripts"
PROFILE_PATH = (
    REPO_ROOT
    / "skill"
    / "modular-portrait-assets"
    / "references"
    / "version-management.json"
)
sys.path.insert(0, str(SCRIPT_DIR))

import portrait_version_manager as pvm  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_sha256(files: dict[str, bytes]) -> str:
    records = "".join(
        f"{path}\0{sha256(data)}\n" for path, data in sorted(files.items())
    )
    return hashlib.sha256(records.encode("utf-8")).hexdigest()


class CoverageProfileTests(unittest.TestCase):
    def test_female_and_male_profiles_keep_distinct_group_contracts(self) -> None:
        profiles = pvm.load_profiles(PROFILE_PATH)

        female = pvm.expected_em_paths(profiles["female_em_v1"], "M03")
        male = pvm.expected_em_paths(profiles["male_em_v1"], "M03")

        self.assertEqual(len(female), 32)
        self.assertEqual(len(male), 20)
        self.assertIn("S04/X03/mouth.png", female)
        self.assertIn("S04/G04/mouth.webp", male)
        self.assertNotIn("S04/G04/mouth.png", male)
        self.assertFalse(any("/X" in path for path in male))

    def test_rejects_a_profile_whose_identity_prefix_has_no_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "bad": {
                                "gender": "female",
                                "identities": ["E01", "M01"],
                                "skins": ["S01"],
                                "groups": ["N00"],
                                "filenames": {"E": "eye_brow.png"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(pvm.VersionManagerError):
                pvm.load_profiles(path)


class AuthorityAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.v5_root = Path(self.temp_dir.name) / "V5"
        self.profile = {
            "gender": "female",
            "identities": ["E01", "M01"],
            "skins": ["S01", "S02"],
            "groups": ["N00"],
            "filenames": {"E": "eye_brow.png", "M": "mouth.png"},
        }

    def write_authority(self) -> tuple[Path, dict]:
        component_root = self.v5_root / "female" / "component_library_v1"
        approved: dict[str, dict] = {"E": {}, "M": {}}
        for identity in self.profile["identities"]:
            category = identity[0]
            files: dict[str, bytes] = {}
            for relative in sorted(pvm.expected_em_paths(self.profile, identity)):
                payload = f"{identity}:{relative}".encode()
                files[relative] = payload
                target = (
                    component_root
                    / category
                    / identity
                    / "current"
                    / "approved"
                    / "r1"
                    / Path(relative)
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            approved[category][identity] = {
                "path": f"{category}/{identity}/current/approved/r1",
                "tree_sha256": tree_sha256(files),
                "files_sha256": {
                    relative: sha256(payload) for relative, payload in files.items()
                },
            }
        manifest_path = (
            component_root / "_metadata" / "current" / "authority_manifest.json"
        )
        manifest_path.parent.mkdir(parents=True)
        document = {"approved_authorities": approved}
        manifest_path.write_text(json.dumps(document), encoding="utf-8")
        return component_root, document

    def test_passes_only_when_every_expected_file_and_hash_is_exact(self) -> None:
        self.write_authority()

        result = pvm.audit_authority(self.v5_root, "female", self.profile)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["expected_file_count"], 4)
        self.assertEqual(result["verified_file_count"], 4)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["extra"], [])
        self.assertEqual(result["hash_mismatches"], [])
        self.assertEqual(result["layout_errors"], [])
        self.assertEqual(result["duplicate_approved"], [])

    def test_blocks_hash_tampering_and_a_second_approved_revision(self) -> None:
        component_root, _ = self.write_authority()
        target = (
            component_root
            / "E"
            / "E01"
            / "current"
            / "approved"
            / "r1"
            / "S01"
            / "N00"
            / "eye_brow.png"
        )
        target.write_bytes(b"tampered")
        duplicate = target.parents[3] / "r2" / "S01" / "N00" / "eye_brow.png"
        duplicate.parent.mkdir(parents=True)
        duplicate.write_bytes(b"duplicate")

        result = pvm.audit_authority(self.v5_root, "female", self.profile)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(len(result["hash_mismatches"]), 1)
        self.assertEqual(result["duplicate_approved"], ["E/E01: r1, r2"])

    def test_blocks_manifest_or_physical_files_outside_exact_coverage(self) -> None:
        component_root, document = self.write_authority()
        record = document["approved_authorities"]["M"]["M01"]
        record["files_sha256"].pop("S02/N00/mouth.png")
        extra = (
            component_root
            / "E"
            / "E01"
            / "current"
            / "approved"
            / "r1"
            / "S03"
            / "N00"
            / "eye_brow.png"
        )
        extra.parent.mkdir(parents=True)
        extra.write_bytes(b"extra")
        manifest_path = (
            component_root / "_metadata" / "current" / "authority_manifest.json"
        )
        manifest_path.write_text(json.dumps(document), encoding="utf-8")

        result = pvm.audit_authority(self.v5_root, "female", self.profile)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("M/M01/S02/N00/mouth.png", result["missing"])
        self.assertIn("E/E01/S03/N00/eye_brow.png", result["extra"])


class RecoveryPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.v5_root = self.root / "V5"
        self.recovery_root = self.root / "recovery"
        self.recovery_root.mkdir()
        self.profile = {
            "gender": "female",
            "identities": ["E02", "M02"],
            "skins": ["S01", "S02"],
            "groups": ["N00", "G01"],
            "filenames": {"E": "eye_brow.png", "M": "mouth.png"},
        }
        self.registry_path = self.root / "registry.json"
        self.write_partial_authority_and_registry()

    def write_partial_authority_and_registry(self) -> None:
        component_root = self.v5_root / "female" / "component_library_v1"
        approved: dict[str, dict] = {"E": {}, "M": {}}
        lanes: list[dict] = []
        for identity in self.profile["identities"]:
            category = identity[0]
            filename = self.profile["filenames"][category]
            retained_relatives = [
                f"S01/N00/{filename}",
                f"S01/G01/{filename}",
                f"S02/N00/{filename}",
            ]
            retained_files: dict[str, bytes] = {}
            for relative in retained_relatives:
                payload = f"retained:{identity}:{relative}".encode()
                retained_files[relative] = payload
                target = (
                    component_root
                    / category
                    / identity
                    / "current"
                    / "approved"
                    / "old-partial"
                    / Path(relative)
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            approved[category][identity] = {
                "path": f"{category}/{identity}/current/approved/old-partial",
                "tree_sha256": tree_sha256(retained_files),
                "files_sha256": {
                    relative: sha256(payload)
                    for relative, payload in retained_files.items()
                },
            }

            recovered = (
                self.recovery_root
                / "reconstructed"
                / "removal"
                / "inspyrenet_1024_v01"
                / "S02"
                / "E02_M02"
                / "G01"
                / ("E_only" if category == "E" else "M_only")
                / "rgba_hidden_rgb_zero.png"
            )
            recovered.parent.mkdir(parents=True, exist_ok=True)
            recovered_payload = f"recovered:{identity}".encode()
            recovered.write_bytes(recovered_payload)
            lanes.append(
                {
                    "S": "S02",
                    "expression": "E02_M02",
                    "group": "G01",
                    "lane": "E_only" if category == "E" else "M_only",
                    "path": str(recovered),
                    "sha256": sha256(recovered_payload),
                    "resolution": "exact_sha_recovered_copy",
                }
            )

        manifest_path = (
            component_root / "_metadata" / "current" / "authority_manifest.json"
        )
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(
            json.dumps({"approved_authorities": approved}), encoding="utf-8"
        )
        self.registry_path.write_text(
            json.dumps({"schema": "test-recovery-v1", "lanes": lanes}),
            encoding="utf-8",
        )

    def build_plan(self) -> dict:
        return pvm.plan_female_em_recovery(
            v5_root=self.v5_root,
            profile=self.profile,
            lane_registry_path=self.registry_path,
            recovery_root=self.recovery_root,
            target_identities=["E02", "M02"],
            revision="r-complete",
            plan_id="test-recovery",
        )

    def test_legacy_lane_paths_require_frozen_inventory_hash_crosscheck(self) -> None:
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        frozen_records = []
        for lane in registry["lanes"]:
            lane.pop("resolution")
            lane["origin"] = "latest_v04_fresh_removal"
            lane["path"] = str(self.root / "deleted-staging" / Path(lane["path"]).name)
            frozen_records.append(
                {
                    "origin": "latest_v04_fresh_removal",
                    "S": lane["S"],
                    "expression": lane["expression"],
                    "group": lane["group"],
                    "lane": lane["lane"],
                    "clean_rgba_sha256": lane["sha256"],
                }
            )
        self.registry_path.write_text(json.dumps(registry), encoding="utf-8")
        frozen_path = self.root / "frozen-inventory.json"
        frozen_path.write_text(
            json.dumps({"schema": "frozen-test-v1", "records": frozen_records}),
            encoding="utf-8",
        )

        plan = pvm.plan_female_em_recovery(
            v5_root=self.v5_root,
            profile=self.profile,
            lane_registry_path=self.registry_path,
            recovery_root=self.recovery_root,
            frozen_inventory_path=frozen_path,
            target_identities=["E02", "M02"],
            revision="r-complete",
            plan_id="test-recovery",
        )

        self.assertEqual(plan["status"], "READY")
        self.assertEqual(plan["recovery_evidence_mode"], "legacy_frozen_inventory_crosscheck")
        frozen_records[0]["clean_rgba_sha256"] = "0" * 64
        frozen_path.write_text(
            json.dumps({"schema": "frozen-test-v1", "records": frozen_records}),
            encoding="utf-8",
        )
        with self.assertRaises(pvm.VersionManagerError):
            pvm.plan_female_em_recovery(
                v5_root=self.v5_root,
                profile=self.profile,
                lane_registry_path=self.registry_path,
                recovery_root=self.recovery_root,
                frozen_inventory_path=frozen_path,
                target_identities=["E02", "M02"],
                revision="r-complete",
                plan_id="test-recovery",
            )

    def test_builds_a_deterministic_complete_candidate_plan(self) -> None:
        first = self.build_plan()
        second = self.build_plan()

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "READY")
        self.assertEqual(first["summary"]["identity_count"], 2)
        self.assertEqual(first["summary"]["file_count"], 8)
        self.assertEqual(first["summary"]["retained_count"], 6)
        self.assertEqual(first["summary"]["recovered_count"], 2)
        self.assertEqual(
            {item["source_role"] for item in first["files"]},
            {"retained_approved", "recovered_exact"},
        )
        self.assertEqual(pvm.verify_adoption_plan(first)["status"], "PASS")

    def test_rejects_missing_duplicate_or_hash_mismatched_recovery_lanes(self) -> None:
        original = json.loads(self.registry_path.read_text(encoding="utf-8"))
        mutations = {
            "missing": original["lanes"][:-1],
            "duplicate": original["lanes"] + [dict(original["lanes"][0])],
            "wrong-group": [
                {**original["lanes"][0], "group": "X03"},
                original["lanes"][1],
            ],
            "wrong-lane": [
                {**original["lanes"][0], "lane": "M_only"},
                original["lanes"][1],
            ],
            "wrong-hash": [
                {**original["lanes"][0], "sha256": "0" * 64},
                original["lanes"][1],
            ],
        }
        for label, lanes in mutations.items():
            with self.subTest(label=label):
                self.registry_path.write_text(
                    json.dumps({"schema": "test-recovery-v1", "lanes": lanes}),
                    encoding="utf-8",
                )
                with self.assertRaises(pvm.VersionManagerError):
                    self.build_plan()
        self.registry_path.write_text(json.dumps(original), encoding="utf-8")

    def test_rejects_a_recovery_source_outside_the_protected_recovery_root(self) -> None:
        document = json.loads(self.registry_path.read_text(encoding="utf-8"))
        outside = self.root / "outside.png"
        outside.write_bytes(b"outside")
        document["lanes"][0]["path"] = str(outside)
        document["lanes"][0]["sha256"] = sha256(b"outside")
        self.registry_path.write_text(json.dumps(document), encoding="utf-8")

        with self.assertRaises(pvm.VersionManagerError):
            self.build_plan()

    def test_apply_creates_only_complete_hash_verified_candidates_and_a_journal(self) -> None:
        plan = self.build_plan()

        result = pvm.apply_recovery_plan(plan)

        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(len(result["candidates"]), 2)
        for identity in ("E02", "M02"):
            category = identity[0]
            candidate = (
                self.v5_root
                / "female"
                / "component_library_v1"
                / category
                / identity
                / "current"
                / "candidates"
                / "r-complete"
            )
            self.assertTrue(candidate.is_dir())
            self.assertEqual(len(list(candidate.rglob("*.png"))), 4)
            self.assertEqual(
                pvm.tree_sha256(candidate), plan["identity_tree_sha256"][identity]
            )
        journal = Path(result["journal_path"])
        self.assertEqual(
            json.loads(journal.read_text(encoding="utf-8"))["status"], "APPLIED"
        )

    def test_apply_preflights_every_source_and_destination_before_writing(self) -> None:
        plan = self.build_plan()
        Path(plan["files"][0]["source_path"]).write_bytes(b"tampered-after-plan")

        with self.assertRaises(pvm.VersionManagerError):
            pvm.apply_recovery_plan(plan)

        component_root = self.v5_root / "female" / "component_library_v1"
        self.assertFalse(
            (component_root / "E" / "E02" / "current" / "candidates" / "r-complete").exists()
        )
        self.assertFalse(
            (component_root / "M" / "M02" / "current" / "candidates" / "r-complete").exists()
        )

    def test_verify_rejects_a_rehashed_plan_whose_destination_breaks_the_contract(self) -> None:
        plan = self.build_plan()
        plan["files"][0]["destination_relative"] = (
            "female/component_library_v1/E/E02/current/candidates/"
            "r-complete/S02/G01/not_the_component.png"
        )
        plan["plan_sha256"] = pvm._canonical_sha256(plan, "plan_sha256")

        with self.assertRaises(pvm.VersionManagerError):
            pvm.verify_adoption_plan(plan)

    def test_verify_rejects_a_rehashed_recovered_source_outside_recovery_root(self) -> None:
        plan = self.build_plan()
        recovered = next(
            item for item in plan["files"] if item["source_role"] == "recovered_exact"
        )
        outside = self.root / "outside-recovery.png"
        outside.write_bytes(Path(recovered["source_path"]).read_bytes())
        recovered["source_path"] = str(outside)
        plan["plan_sha256"] = pvm._canonical_sha256(plan, "plan_sha256")

        with self.assertRaises(pvm.VersionManagerError):
            pvm.verify_adoption_plan(plan)

    def test_atomic_json_write_retries_a_transient_windows_replace_lock(self) -> None:
        target = self.root / "journal.json"
        target.write_text('{"status":"old"}', encoding="utf-8")
        real_replace = os.replace
        attempts = 0

        def transient_replace(source: Path, destination: Path) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError(5, "transient Windows file lock")
            real_replace(source, destination)

        with patch.object(pvm.os, "replace", side_effect=transient_replace):
            pvm._write_json_atomic(target, {"status": "new"})

        self.assertEqual(
            json.loads(target.read_text(encoding="utf-8")), {"status": "new"}
        )
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_resume_apply_verifies_and_finishes_only_classified_partial_candidates(self) -> None:
        plan = self.build_plan()
        applied = pvm.apply_recovery_plan(plan)
        candidate_roots = pvm._candidate_roots(plan)
        identity = "M02"
        candidate = candidate_roots[identity]
        staging = candidate.with_name(
            f".{candidate.name}.{plan['plan_id']}.staging"
        )
        candidate.rename(staging)
        journal_path = Path(applied["journal_path"])
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["status"] = "APPLY_NEEDS_RECOVERY"
        journal["moved_candidates"].remove(identity)
        journal_path.write_text(json.dumps(journal), encoding="utf-8")
        stale_atomic_temp = journal_path.with_name(
            f".{journal_path.name}.failed-attempt.tmp"
        )
        stale_atomic_temp.write_text('{"status":"interrupted"}', encoding="utf-8")

        result = pvm.resume_apply_recovery_plan(plan)

        self.assertEqual(result["status"], "APPLIED")
        self.assertTrue(candidate.is_dir())
        self.assertFalse(staging.exists())
        self.assertEqual(pvm.tree_sha256(candidate), plan["identity_tree_sha256"][identity])
        self.assertFalse(stale_atomic_temp.exists())
        self.assertTrue(
            (journal_path.parent / "failed_atomic_writes" / stale_atomic_temp.name).is_file()
        )

    def write_acceptance_record(self, plan: dict) -> Path:
        path = (
            self.v5_root
            / "female"
            / "component_library_v1"
            / "_work_history"
            / "current"
            / "test-recovery"
            / "acceptance_record.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema": "portrait-recovery-acceptance-v1",
                    "record_id": "test-recovery-user-acceptance",
                    "decision": "accepted",
                    "accepted_by": "user",
                    "accepted_at": "2026-09-02T12:00:00+08:00",
                    "plan_sha256": plan["plan_sha256"],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return path

    def test_promote_archives_old_revisions_and_atomically_selects_exact_candidates(self) -> None:
        plan = self.build_plan()
        pvm.apply_recovery_plan(plan)
        acceptance = self.write_acceptance_record(plan)

        result = pvm.promote_recovery_plan(
            plan, acceptance_record_path=acceptance
        )

        self.assertEqual(result["status"], "PROMOTED")
        component_root = self.v5_root / "female" / "component_library_v1"
        for identity in ("E02", "M02"):
            category = identity[0]
            self.assertTrue(
                (
                    component_root
                    / category
                    / identity
                    / "current"
                    / "approved"
                    / "r-complete"
                ).is_dir()
            )
            self.assertTrue(
                (
                    component_root
                    / category
                    / identity
                    / "old_versions"
                    / "superseded"
                    / "old-partial"
                ).is_dir()
            )
            self.assertFalse(
                (
                    component_root
                    / category
                    / identity
                    / "current"
                    / "candidates"
                    / "r-complete"
                ).exists()
            )
        audit = pvm.audit_authority(self.v5_root, "female", self.profile)
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["verified_file_count"], 8)
        journal = json.loads(
            Path(result["journal_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(journal["status"], "PROMOTED")
        self.assertTrue(Path(journal["authority_backup_path"]).is_file())

    def test_promote_refuses_a_tampered_candidate_without_moving_old_approved(self) -> None:
        plan = self.build_plan()
        pvm.apply_recovery_plan(plan)
        acceptance = self.write_acceptance_record(plan)
        candidate_file = (
            self.v5_root
            / Path(plan["files"][0]["destination_relative"])
        )
        candidate_file.write_bytes(b"tampered-candidate")

        with self.assertRaises(pvm.VersionManagerError):
            pvm.promote_recovery_plan(plan, acceptance_record_path=acceptance)

        component_root = self.v5_root / "female" / "component_library_v1"
        self.assertTrue(
            (
                component_root
                / "E"
                / "E02"
                / "current"
                / "approved"
                / "old-partial"
            ).is_dir()
        )
        manifest_path = (
            component_root / "_metadata" / "current" / "authority_manifest.json"
        )
        self.assertEqual(pvm.file_sha256(manifest_path), plan["authority_manifest"]["sha256"])

    def test_promote_retries_a_transient_lock_on_the_authority_swap(self) -> None:
        plan = self.build_plan()
        pvm.apply_recovery_plan(plan)
        acceptance = self.write_acceptance_record(plan)
        manifest_path = Path(plan["authority_manifest"]["path"]).resolve()
        real_replace = os.replace
        authority_lock_injected = False

        def transient_authority_replace(source: Path, destination: Path) -> None:
            nonlocal authority_lock_injected
            if Path(destination).resolve() == manifest_path and not authority_lock_injected:
                authority_lock_injected = True
                raise PermissionError(5, "transient authority lock")
            real_replace(source, destination)

        with patch.object(
            pvm.os, "replace", side_effect=transient_authority_replace
        ):
            result = pvm.promote_recovery_plan(
                plan, acceptance_record_path=acceptance
            )

        self.assertTrue(authority_lock_injected)
        self.assertEqual(result["status"], "PROMOTED")
        self.assertEqual(
            pvm.audit_authority(self.v5_root, "female", self.profile)["status"],
            "PASS",
        )

    def test_promoted_plan_builds_two_copy_cleanup_protection_and_waits_for_export(self) -> None:
        plan = self.build_plan()
        pvm.apply_recovery_plan(plan)
        acceptance = self.write_acceptance_record(plan)
        pvm.promote_recovery_plan(plan, acceptance_record_path=acceptance)
        evidence_payload = acceptance.parent / "evidence" / "proof.json"
        evidence_payload.parent.mkdir(parents=True)
        evidence_payload.write_text('{"proof":true}', encoding="utf-8")
        evidence_manifest = acceptance.parent / "EVIDENCE_MANIFEST.json"
        evidence_manifest.write_text(
            json.dumps(
                {
                    "files": [
                        {
                            "path": "evidence/proof.json",
                            "sha256": pvm.file_sha256(evidence_payload),
                            "bytes": evidence_payload.stat().st_size,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        pending = pvm.build_cleanup_protection(
            plan,
            evidence_manifest_paths=[evidence_manifest],
            public_export={"status": "pending"},
        )

        self.assertEqual(len(pending["protected_artifacts"]), 2)
        pending_report = pvm.cleanup_check(pending)
        self.assertEqual(pending_report["status"], "BLOCKED")
        self.assertEqual(
            {item["code"] for item in pending_report["blockers"]},
            {"public_export_pending"},
        )

        pending["public_export"] = {"status": "pushed", "commit": "a" * 40}
        self.assertEqual(pvm.cleanup_check(pending)["status"], "PASS")

    def test_cli_runs_plan_apply_promote_and_audit_as_one_lifecycle_interface(self) -> None:
        profiles_path = self.root / "profiles.json"
        profiles_path.write_text(
            json.dumps({"profiles": {"female_test": self.profile}}),
            encoding="utf-8",
        )
        plan_path = self.root / "plan.json"
        apply_report = self.root / "apply.json"
        promote_report = self.root / "promote.json"
        audit_report = self.root / "audit.json"

        with redirect_stdout(io.StringIO()):
            self.assertEqual(
                pvm.main(
                    [
                        "--profiles",
                        str(profiles_path),
                        "plan-recovery",
                        str(self.v5_root),
                        str(self.registry_path),
                        str(self.recovery_root),
                        "r-complete",
                        "test-recovery",
                        "female_test",
                        "E02",
                        "M02",
                        "--output",
                        str(plan_path),
                    ]
                ),
                0,
            )
            self.assertEqual(
                pvm.main(["apply-recovery", str(plan_path), "--output", str(apply_report)]),
                0,
            )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        acceptance = self.write_acceptance_record(plan)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(
                pvm.main(
                    [
                        "promote",
                        str(plan_path),
                        str(acceptance),
                        "--output",
                        str(promote_report),
                    ]
                ),
                0,
            )
            self.assertEqual(
                pvm.main(
                    [
                        "--profiles",
                        str(profiles_path),
                        "audit",
                        str(self.v5_root),
                        "female",
                        "female_test",
                        "--output",
                        str(audit_report),
                    ]
                ),
                0,
            )

        self.assertEqual(
            json.loads(audit_report.read_text(encoding="utf-8"))["status"], "PASS"
        )


class CleanupGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        payload = b"full-canvas-component"
        self.copy_a = self.root / "recovery" / "asset.png"
        self.copy_b = self.root / "approved" / "asset.png"
        self.copy_a.parent.mkdir()
        self.copy_b.parent.mkdir()
        self.copy_a.write_bytes(payload)
        self.copy_b.write_bytes(payload)
        self.digest = sha256(payload)

    def valid_manifest(self) -> dict:
        return {
            "schema": "portrait-cleanup-protection-v1",
            "protected_artifacts": [
                {
                    "id": "female/M02/S02/G01/mouth.png",
                    "kind": "full_canvas_component",
                    "sha256": self.digest,
                    "registry_bound": True,
                    "copies": [str(self.copy_a), str(self.copy_b)],
                }
            ],
            "formal_state_complete": True,
            "evidence_complete": True,
            "acceptance_complete": True,
            "promotion_complete": True,
            "public_export": {"status": "pushed", "commit": "a" * 40},
            "unclassified_staging": [],
        }

    def test_passes_only_with_two_exact_full_canvas_copies_and_completed_lifecycle(self) -> None:
        result = pvm.cleanup_check(self.valid_manifest())

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["verified_artifacts"], 1)
        self.assertEqual(result["blockers"], [])

    def test_blocks_each_unsafe_cleanup_condition_with_a_machine_code(self) -> None:
        cases: dict[str, tuple[callable, str]] = {
            "one-copy": (
                lambda manifest: manifest["protected_artifacts"][0].update(
                    {"copies": [str(self.copy_a)]}
                ),
                "insufficient_verified_copies",
            ),
            "thumbnail": (
                lambda manifest: manifest["protected_artifacts"][0].update(
                    {"kind": "qc_thumbnail"}
                ),
                "thumbnail_is_not_source",
            ),
            "unclassified": (
                lambda manifest: manifest.update(
                    {"unclassified_staging": ["staging/unknown"]}
                ),
                "unclassified_staging",
            ),
            "pending-promotion": (
                lambda manifest: manifest.update({"promotion_complete": False}),
                "promotion_pending",
            ),
            "pending-export": (
                lambda manifest: manifest.update(
                    {"public_export": {"status": "pending"}}
                ),
                "public_export_pending",
            ),
            "invalid-export-commit": (
                lambda manifest: manifest.update(
                    {"public_export": {"status": "pushed", "commit": "abc123"}}
                ),
                "public_export_pending",
            ),
        }
        for label, (mutate, expected_code) in cases.items():
            with self.subTest(label=label):
                manifest = self.valid_manifest()
                mutate(manifest)

                result = pvm.cleanup_check(manifest)

                self.assertEqual(result["status"], "BLOCKED")
                self.assertIn(expected_code, {item["code"] for item in result["blockers"]})

    def test_private_only_exemption_must_be_explicit_and_hash_bound(self) -> None:
        manifest = self.valid_manifest()
        manifest["public_export"] = {
            "status": "private_only",
            "exemption": {
                "reason": "non-public recovery evidence",
                "approved_by": "user",
                "record_sha256": "1" * 64,
            },
        }

        self.assertEqual(pvm.cleanup_check(manifest)["status"], "PASS")

        manifest["public_export"]["exemption"].pop("record_sha256")
        result = pvm.cleanup_check(manifest)
        self.assertIn(
            "private_only_exemption_invalid",
            {item["code"] for item in result["blockers"]},
        )


if __name__ == "__main__":
    unittest.main()
