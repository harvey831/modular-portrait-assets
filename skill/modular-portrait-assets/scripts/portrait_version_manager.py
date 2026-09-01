#!/usr/bin/env python3
"""Fail-closed lifecycle manager for private modular portrait revisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class VersionManagerError(RuntimeError):
    """Raised when a lifecycle input cannot be proven safe."""


def load_profiles(path: Path | str) -> dict[str, dict[str, Any]]:
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VersionManagerError(f"cannot load coverage profiles: {path}") from exc

    profiles = document.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise VersionManagerError("coverage document has no profiles")

    normalized: dict[str, dict[str, Any]] = {}
    for name, profile in profiles.items():
        if not isinstance(name, str) or not isinstance(profile, dict):
            raise VersionManagerError("coverage profile entries must be objects")
        gender = profile.get("gender")
        identities = profile.get("identities")
        skins = profile.get("skins")
        groups = profile.get("groups")
        filenames = profile.get("filenames")
        if gender not in {"female", "male"}:
            raise VersionManagerError(f"invalid gender in coverage profile {name}")
        if not all(
            isinstance(values, list)
            and values
            and all(isinstance(item, str) and item for item in values)
            for values in (identities, skins, groups)
        ):
            raise VersionManagerError(f"invalid lists in coverage profile {name}")
        if len(set(identities)) != len(identities) or len(set(skins)) != len(skins) or len(set(groups)) != len(groups):
            raise VersionManagerError(f"duplicate coverage values in profile {name}")
        if not isinstance(filenames, dict):
            raise VersionManagerError(f"missing filenames in coverage profile {name}")
        prefixes = {identity[0] for identity in identities if identity}
        if any(not isinstance(filenames.get(prefix), str) or not filenames[prefix] for prefix in prefixes):
            raise VersionManagerError(f"missing identity filename in coverage profile {name}")
        normalized[name] = profile
    return normalized


def expected_em_paths(profile: dict[str, Any], identity: str) -> set[str]:
    identities = profile.get("identities", [])
    if identity not in identities:
        raise VersionManagerError(f"identity is outside coverage profile: {identity}")
    prefix = identity[0]
    try:
        filename = profile["filenames"][prefix]
        skins = profile["skins"]
        groups = profile["groups"]
    except (KeyError, TypeError) as exc:
        raise VersionManagerError("malformed coverage profile") from exc
    return {f"{skin}/{group}/{filename}" for skin in skins for group in groups}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(directory: Path) -> str:
    records: list[str] = []
    for file_path in sorted(path for path in directory.rglob("*") if path.is_file()):
        relative = file_path.relative_to(directory).as_posix()
        records.append(f"{relative}\0{file_sha256(file_path)}\n")
    return hashlib.sha256("".join(records).encode("utf-8")).hexdigest()


def _tree_hash_from_records(files: dict[str, str]) -> str:
    records = "".join(
        f"{relative}\0{digest.casefold()}\n"
        for relative, digest in sorted(files.items())
    )
    return hashlib.sha256(records.encode("utf-8")).hexdigest()


def _canonical_sha256(document: dict[str, Any], excluded: str) -> str:
    payload = {key: value for key, value in document.items() if key != excluded}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise VersionManagerError(f"path escapes component root: {path}") from exc
    return resolved


def audit_authority(
    v5_root: Path | str, gender: str, profile: dict[str, Any]
) -> dict[str, Any]:
    if gender not in {"female", "male"} or profile.get("gender") != gender:
        raise VersionManagerError("gender does not match the coverage profile")
    v5_root = Path(v5_root).resolve()
    component_root = v5_root / gender / "component_library_v1"
    manifest_path = component_root / "_metadata" / "current" / "authority_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VersionManagerError(f"cannot load authority manifest: {manifest_path}") from exc
    approved = manifest.get("approved_authorities")
    if not isinstance(approved, dict):
        raise VersionManagerError("authority manifest has no approved_authorities")

    result: dict[str, Any] = {
        "status": "PASS",
        "gender": gender,
        "manifest_path": str(manifest_path),
        "expected_file_count": 0,
        "verified_file_count": 0,
        "missing": [],
        "extra": [],
        "hash_mismatches": [],
        "tree_hash_mismatches": [],
        "layout_errors": [],
        "duplicate_approved": [],
    }

    expected_identities = set(profile["identities"])
    manifest_identities: set[str] = set()
    for category in ("E", "M"):
        records = approved.get(category)
        if not isinstance(records, dict):
            result["layout_errors"].append(f"approved_authorities.{category} is missing")
            records = {}
        manifest_identities.update(
            identity for identity in records if isinstance(identity, str)
        )

    for identity in sorted(expected_identities):
        category = identity[0]
        expected_files = expected_em_paths(profile, identity)
        result["expected_file_count"] += len(expected_files)
        records = approved.get(category, {})
        record = records.get(identity) if isinstance(records, dict) else None
        if not isinstance(record, dict):
            result["layout_errors"].append(f"missing authority record: {category}/{identity}")
            result["missing"].extend(
                f"{category}/{identity}/{relative}" for relative in sorted(expected_files)
            )
            continue

        raw_path = record.get("path")
        expected_prefix = f"{category}/{identity}/current/approved/"
        if (
            not isinstance(raw_path, str)
            or Path(raw_path).is_absolute()
            or not raw_path.replace("\\", "/").startswith(expected_prefix)
            or len(Path(raw_path.replace("\\", "/")).parts) != 5
        ):
            result["layout_errors"].append(f"invalid approved path: {category}/{identity}")
            continue

        revision_root = _inside(component_root / Path(raw_path), component_root)
        approved_root = component_root / category / identity / "current" / "approved"
        revisions = sorted(path.name for path in approved_root.iterdir() if path.is_dir()) if approved_root.is_dir() else []
        if len(revisions) != 1:
            result["duplicate_approved"].append(
                f"{category}/{identity}: {', '.join(revisions) if revisions else '(none)'}"
            )

        hashes = record.get("files_sha256")
        if not isinstance(hashes, dict):
            result["layout_errors"].append(f"missing files_sha256: {category}/{identity}")
            hashes = {}
        manifest_files = {key for key in hashes if isinstance(key, str)}
        for relative in sorted(expected_files - manifest_files):
            result["missing"].append(f"{category}/{identity}/{relative}")
        for relative in sorted(manifest_files - expected_files):
            result["extra"].append(f"{category}/{identity}/{relative}")

        physical_files: set[str] = set()
        if revision_root.is_dir():
            physical_files = {
                path.relative_to(revision_root).as_posix()
                for path in revision_root.rglob("*")
                if path.is_file()
            }
        else:
            result["layout_errors"].append(f"approved revision is missing: {category}/{identity}")
        for relative in sorted(expected_files - physical_files):
            key = f"{category}/{identity}/{relative}"
            if key not in result["missing"]:
                result["missing"].append(key)
        for relative in sorted(physical_files - expected_files):
            key = f"{category}/{identity}/{relative}"
            if key not in result["extra"]:
                result["extra"].append(key)

        for relative in sorted(expected_files & manifest_files & physical_files):
            expected_hash = hashes[relative]
            if not isinstance(expected_hash, str):
                result["layout_errors"].append(
                    f"invalid file hash: {category}/{identity}/{relative}"
                )
                continue
            actual_hash = file_sha256(revision_root / Path(relative))
            if actual_hash != expected_hash.casefold():
                result["hash_mismatches"].append(
                    {
                        "path": f"{category}/{identity}/{relative}",
                        "expected": expected_hash.casefold(),
                        "actual": actual_hash,
                    }
                )
            else:
                result["verified_file_count"] += 1

        expected_tree = record.get("tree_sha256")
        if not isinstance(expected_tree, str):
            result["layout_errors"].append(f"missing tree_sha256: {category}/{identity}")
        elif revision_root.is_dir():
            actual_tree = tree_sha256(revision_root)
            if actual_tree != expected_tree.casefold():
                result["tree_hash_mismatches"].append(
                    {
                        "identity": identity,
                        "expected": expected_tree.casefold(),
                        "actual": actual_tree,
                    }
                )

    for identity in sorted(manifest_identities - expected_identities):
        result["layout_errors"].append(f"unexpected E/M authority identity: {identity}")

    issue_keys = (
        "missing",
        "extra",
        "hash_mismatches",
        "tree_hash_mismatches",
        "layout_errors",
        "duplicate_approved",
    )
    if any(result[key] for key in issue_keys):
        result["status"] = "BLOCKED"
    return result


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VersionManagerError(f"cannot load {label}: {path}") from exc
    if not isinstance(document, dict):
        raise VersionManagerError(f"{label} must be a JSON object")
    return document


def _lane_identity(record: dict[str, Any]) -> tuple[str, str]:
    expression = record.get("expression")
    lane = record.get("lane")
    if not isinstance(expression, str) or not re.fullmatch(r"E\d{2}_M\d{2}", expression):
        raise VersionManagerError("recovery lane has an invalid expression pair")
    eye, mouth = expression.split("_")
    if lane == "E_only":
        return eye, "E"
    if lane == "M_only":
        return mouth, "M"
    raise VersionManagerError(f"recovery lane has an invalid owner: {lane}")


def plan_female_em_recovery(
    *,
    v5_root: Path | str,
    profile: dict[str, Any],
    lane_registry_path: Path | str,
    recovery_root: Path | str,
    frozen_inventory_path: Path | str | None = None,
    target_identities: list[str],
    revision: str,
    plan_id: str,
) -> dict[str, Any]:
    if profile.get("gender") != "female":
        raise VersionManagerError("female recovery requires a female profile")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", revision):
        raise VersionManagerError("revision is not a safe directory name")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", plan_id):
        raise VersionManagerError("plan id is not a safe identifier")
    if (
        not target_identities
        or len(set(target_identities)) != len(target_identities)
        or any(identity not in profile.get("identities", []) for identity in target_identities)
    ):
        raise VersionManagerError("target identities are empty, duplicated, or outside the profile")

    v5_root = Path(v5_root).resolve()
    recovery_root = Path(recovery_root).resolve()
    lane_registry_path = Path(lane_registry_path).resolve()
    component_root = v5_root / "female" / "component_library_v1"
    manifest_path = component_root / "_metadata" / "current" / "authority_manifest.json"
    manifest = _load_json_object(manifest_path, "female authority manifest")
    approved = manifest.get("approved_authorities")
    if not isinstance(approved, dict):
        raise VersionManagerError("female authority manifest has no approved_authorities")
    registry = _load_json_object(lane_registry_path, "recovery lane registry")
    lanes = registry.get("lanes")
    if not isinstance(lanes, list):
        raise VersionManagerError("recovery lane registry has no lanes")

    frozen_hashes: dict[tuple[str, str, str, str], str] = {}
    frozen_inventory_record: dict[str, str] | None = None
    if frozen_inventory_path is not None:
        frozen_path = Path(frozen_inventory_path).resolve()
        frozen = _load_json_object(frozen_path, "frozen recovery inventory")
        frozen_records = frozen.get("records")
        if not isinstance(frozen_records, list):
            raise VersionManagerError("frozen recovery inventory has no records")
        for record in frozen_records:
            if not isinstance(record, dict) or record.get("origin") != "latest_v04_fresh_removal":
                continue
            key = (
                record.get("S"),
                record.get("expression"),
                record.get("group"),
                record.get("lane"),
            )
            digest = record.get("clean_rgba_sha256")
            if not all(isinstance(value, str) and value for value in key) or not isinstance(digest, str):
                raise VersionManagerError("frozen recovery inventory has a malformed latest record")
            if key in frozen_hashes and frozen_hashes[key] != digest.casefold():
                raise VersionManagerError(f"conflicting frozen recovery hashes: {key}")
            frozen_hashes[key] = digest.casefold()
        frozen_inventory_record = {
            "path": str(frozen_path),
            "sha256": file_sha256(frozen_path),
        }

    retained_by_identity: dict[str, dict[str, dict[str, str]]] = {}
    missing_by_identity: dict[str, set[str]] = {}
    for identity in sorted(target_identities):
        category = identity[0]
        record = approved.get(category, {}).get(identity) if isinstance(approved.get(category), dict) else None
        if not isinstance(record, dict):
            raise VersionManagerError(f"missing approved authority for {identity}")
        raw_path = record.get("path")
        hashes = record.get("files_sha256")
        if not isinstance(raw_path, str) or Path(raw_path).is_absolute() or not isinstance(hashes, dict):
            raise VersionManagerError(f"malformed approved authority for {identity}")
        revision_root = _inside(component_root / Path(raw_path), component_root)
        expected = expected_em_paths(profile, identity)
        if not set(hashes).issubset(expected):
            raise VersionManagerError(f"approved authority has out-of-profile files for {identity}")
        retained: dict[str, dict[str, str]] = {}
        for relative, expected_hash in sorted(hashes.items()):
            if not isinstance(relative, str) or not isinstance(expected_hash, str):
                raise VersionManagerError(f"invalid retained authority entry for {identity}")
            source = _inside(revision_root / Path(relative), revision_root)
            if not source.is_file() or file_sha256(source) != expected_hash.casefold():
                raise VersionManagerError(f"retained authority hash mismatch: {identity}/{relative}")
            retained[relative] = {"path": str(source), "sha256": expected_hash.casefold()}
        retained_by_identity[identity] = retained
        missing_by_identity[identity] = expected - set(retained)

        candidate_root = component_root / category / identity / "current" / "candidates" / revision
        if candidate_root.exists():
            raise VersionManagerError(f"candidate revision already exists: {identity}/{revision}")

    recovered_by_identity: dict[str, dict[str, dict[str, str]]] = {
        identity: {} for identity in target_identities
    }
    recovery_evidence_modes: set[str] = set()
    for raw_lane in lanes:
        if not isinstance(raw_lane, dict):
            raise VersionManagerError("recovery lane entry must be an object")
        identity, category = _lane_identity(raw_lane)
        if identity not in recovered_by_identity:
            continue
        skin = raw_lane.get("S")
        group = raw_lane.get("group")
        if skin not in profile["skins"] or group not in profile["groups"]:
            raise VersionManagerError(f"out-of-profile recovery lane: {identity}/{skin}/{group}")
        relative = f"{skin}/{group}/{profile['filenames'][category]}"
        if relative not in missing_by_identity[identity]:
            continue
        source_text = raw_lane.get("path")
        expected_hash = raw_lane.get("sha256")
        if not isinstance(source_text, str) or not isinstance(expected_hash, str):
            raise VersionManagerError(f"recovery lane lacks path or hash: {identity}/{relative}")
        direct_source = Path(source_text).resolve()
        direct_inside_recovery = False
        try:
            direct_source.relative_to(recovery_root)
            direct_inside_recovery = direct_source.is_file()
        except ValueError:
            direct_inside_recovery = False
        if direct_inside_recovery:
            if raw_lane.get("resolution") != "exact_sha_recovered_copy":
                raise VersionManagerError(f"recovery lane is not exact-hash evidence: {identity}/{relative}")
            source = direct_source
            recovery_evidence_modes.add("exact_recovered_path")
        else:
            frozen_key = (skin, raw_lane.get("expression"), group, raw_lane.get("lane"))
            if (
                raw_lane.get("origin") != "latest_v04_fresh_removal"
                or frozen_hashes.get(frozen_key) != expected_hash.casefold()
            ):
                raise VersionManagerError(
                    f"legacy recovery lane lacks frozen-inventory proof: {identity}/{relative}"
                )
            source = (
                recovery_root
                / "reconstructed"
                / "removal"
                / "inspyrenet_1024_v01"
                / skin
                / raw_lane["expression"]
                / group
                / raw_lane["lane"]
                / "rgba_hidden_rgb_zero.png"
            ).resolve()
            _inside(source, recovery_root)
            recovery_evidence_modes.add("legacy_frozen_inventory_crosscheck")
        if not source.is_file() or file_sha256(source) != expected_hash.casefold():
            raise VersionManagerError(f"recovery lane hash mismatch: {identity}/{relative}")
        if relative in recovered_by_identity[identity]:
            raise VersionManagerError(f"duplicate recovery lane: {identity}/{relative}")
        recovered_by_identity[identity][relative] = {
            "path": str(source),
            "sha256": expected_hash.casefold(),
        }

    files: list[dict[str, str]] = []
    identity_trees: dict[str, str] = {}
    retained_count = 0
    recovered_count = 0
    for identity in sorted(target_identities):
        category = identity[0]
        missing = missing_by_identity[identity]
        recovered = recovered_by_identity[identity]
        if set(recovered) != missing:
            absent = sorted(missing - set(recovered))
            surplus = sorted(set(recovered) - missing)
            raise VersionManagerError(
                f"recovery coverage mismatch for {identity}: missing={absent}, surplus={surplus}"
            )
        combined = {**retained_by_identity[identity], **recovered}
        identity_trees[identity] = _tree_hash_from_records(
            {relative: source["sha256"] for relative, source in combined.items()}
        )
        for relative, source in sorted(combined.items()):
            source_role = (
                "recovered_exact" if relative in recovered else "retained_approved"
            )
            retained_count += source_role == "retained_approved"
            recovered_count += source_role == "recovered_exact"
            files.append(
                {
                    "identity": identity,
                    "category": category,
                    "relative_path": relative,
                    "source_path": source["path"],
                    "source_sha256": source["sha256"],
                    "source_role": source_role,
                    "destination_relative": (
                        f"female/component_library_v1/{category}/{identity}/current/"
                        f"candidates/{revision}/{relative}"
                    ),
                }
            )

    plan: dict[str, Any] = {
        "schema": "portrait-recovery-adoption-plan-v1",
        "status": "READY",
        "plan_id": plan_id,
        "gender": "female",
        "profile": profile,
        "v5_root": str(v5_root),
        "recovery_root": str(recovery_root),
        "recovery_evidence_mode": (
            next(iter(recovery_evidence_modes))
            if len(recovery_evidence_modes) == 1
            else "+".join(sorted(recovery_evidence_modes))
        ),
        "lane_registry": {
            "path": str(lane_registry_path),
            "sha256": file_sha256(lane_registry_path),
        },
        "authority_manifest": {
            "path": str(manifest_path),
            "sha256": file_sha256(manifest_path),
        },
        "revision": revision,
        "target_identities": sorted(target_identities),
        "identity_tree_sha256": identity_trees,
        "summary": {
            "identity_count": len(target_identities),
            "file_count": len(files),
            "retained_count": retained_count,
            "recovered_count": recovered_count,
        },
        "files": files,
    }
    if frozen_inventory_record is not None:
        plan["frozen_inventory"] = frozen_inventory_record
    plan["plan_sha256"] = _canonical_sha256(plan, "plan_sha256")
    verify_adoption_plan(plan)
    return plan


def plan_existing_candidate_promotion(
    *,
    v5_root: Path | str,
    profile: dict[str, Any],
    identity: str,
    revision: str,
    plan_id: str,
    evidence_root: Path | str,
    acceptance_evidence_path: Path | str,
) -> dict[str, Any]:
    if profile.get("gender") != "female":
        raise VersionManagerError("existing candidate promotion requires a female profile")
    if identity not in profile.get("identities", []) or identity[:1] not in {"E", "M"}:
        raise VersionManagerError("identity is outside the coverage profile")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", revision):
        raise VersionManagerError("revision is not a safe directory name")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", plan_id):
        raise VersionManagerError("plan id is not a safe identifier")

    v5_root = Path(v5_root).resolve()
    component_root = v5_root / "female" / "component_library_v1"
    category = identity[0]
    candidate_root = (
        component_root
        / category
        / identity
        / "current"
        / "candidates"
        / revision
    ).resolve()
    if not candidate_root.is_dir():
        raise VersionManagerError(f"complete candidate revision is missing: {identity}/{revision}")

    evidence_root = _inside(Path(evidence_root).resolve(), component_root)
    evidence_relative = evidence_root.relative_to(component_root)
    if not evidence_relative.parts or evidence_relative.parts[0] != "_work_history":
        raise VersionManagerError("candidate evidence root must be under _work_history")
    if evidence_root == candidate_root or not evidence_root.is_dir():
        raise VersionManagerError("candidate evidence must be a distinct complete directory")

    acceptance_evidence_path = _inside(
        Path(acceptance_evidence_path).resolve(), component_root
    )
    acceptance_relative = acceptance_evidence_path.relative_to(component_root)
    if (
        not acceptance_relative.parts
        or acceptance_relative.parts[0] != "_work_history"
        or not acceptance_evidence_path.is_file()
    ):
        raise VersionManagerError("acceptance evidence must be a file under _work_history")

    manifest_path = (
        component_root / "_metadata" / "current" / "authority_manifest.json"
    ).resolve()
    manifest = _load_json_object(manifest_path, "female authority manifest")
    approved = manifest.get("approved_authorities")
    record = (
        approved.get(category, {}).get(identity)
        if isinstance(approved, dict) and isinstance(approved.get(category), dict)
        else None
    )
    if not isinstance(record, dict):
        raise VersionManagerError(f"missing approved authority for {identity}")
    raw_approved_path = record.get("path")
    approved_hashes = record.get("files_sha256")
    if (
        not isinstance(raw_approved_path, str)
        or Path(raw_approved_path).is_absolute()
        or not isinstance(approved_hashes, dict)
    ):
        raise VersionManagerError(f"malformed approved authority for {identity}")
    approved_root = _inside(component_root / Path(raw_approved_path), component_root)

    expected = expected_em_paths(profile, identity)
    candidate_physical = {
        path.relative_to(candidate_root).as_posix()
        for path in candidate_root.rglob("*")
        if path.is_file()
    }
    evidence_physical = {
        path.relative_to(evidence_root).as_posix()
        for path in evidence_root.rglob("*")
        if path.is_file()
    }
    if candidate_physical != expected:
        raise VersionManagerError(f"candidate coverage mismatch: {identity}")
    if evidence_physical != expected:
        raise VersionManagerError(f"candidate evidence coverage mismatch: {identity}")
    if set(approved_hashes) != expected:
        raise VersionManagerError(f"approved authority coverage mismatch: {identity}")

    files: list[dict[str, str]] = []
    candidate_hashes: dict[str, str] = {}
    changed: list[str] = []
    retained_count = 0
    recovered_count = 0
    for relative in sorted(expected):
        approved_hash = approved_hashes.get(relative)
        if not isinstance(approved_hash, str):
            raise VersionManagerError(f"invalid approved hash: {identity}/{relative}")
        approved_source = _inside(approved_root / Path(relative), approved_root)
        candidate_source = _inside(candidate_root / Path(relative), candidate_root)
        evidence_source = _inside(evidence_root / Path(relative), evidence_root)
        if (
            not approved_source.is_file()
            or file_sha256(approved_source) != approved_hash.casefold()
        ):
            raise VersionManagerError(f"approved authority hash mismatch: {identity}/{relative}")
        candidate_hash = file_sha256(candidate_source)
        if file_sha256(evidence_source) != candidate_hash:
            raise VersionManagerError(f"candidate evidence hash mismatch: {identity}/{relative}")
        candidate_hashes[relative] = candidate_hash
        is_changed = candidate_hash != approved_hash.casefold()
        source = evidence_source if is_changed else approved_source
        source_role = "recovered_exact" if is_changed else "retained_approved"
        if is_changed:
            changed.append(relative)
            recovered_count += 1
        else:
            retained_count += 1
        files.append(
            {
                "identity": identity,
                "category": category,
                "relative_path": relative,
                "source_path": str(source),
                "source_sha256": candidate_hash,
                "source_role": source_role,
                "destination_relative": (
                    f"female/component_library_v1/{category}/{identity}/current/"
                    f"candidates/{revision}/{relative}"
                ),
            }
        )
    if not changed:
        raise VersionManagerError("candidate is byte-identical to the current approved revision")

    candidate_tree = _tree_hash_from_records(candidate_hashes)
    if tree_sha256(candidate_root) != candidate_tree or tree_sha256(evidence_root) != candidate_tree:
        raise VersionManagerError("candidate and evidence tree hashes are not identical")

    plan: dict[str, Any] = {
        "schema": "portrait-recovery-adoption-plan-v1",
        "status": "READY",
        "plan_kind": "existing_complete_candidate_promotion",
        "plan_id": plan_id,
        "gender": "female",
        "profile": profile,
        "v5_root": str(v5_root),
        "recovery_root": str(evidence_root),
        "recovery_evidence_mode": "exact_existing_candidate_evidence_copy",
        "authority_manifest": {
            "path": str(manifest_path),
            "sha256": file_sha256(manifest_path),
        },
        "revision": revision,
        "target_identities": [identity],
        "identity_tree_sha256": {identity: candidate_tree},
        "existing_candidate": {
            "path": str(candidate_root),
            "tree_sha256": candidate_tree,
            "evidence_path": str(evidence_root),
            "evidence_tree_sha256": candidate_tree,
        },
        "acceptance_evidence": {
            "path": str(acceptance_evidence_path),
            "sha256": file_sha256(acceptance_evidence_path),
        },
        "changed_relative_paths": changed,
        "summary": {
            "identity_count": 1,
            "file_count": len(files),
            "retained_count": retained_count,
            "recovered_count": recovered_count,
        },
        "files": files,
    }
    plan["plan_sha256"] = _canonical_sha256(plan, "plan_sha256")
    verify_adoption_plan(plan, allow_existing_destinations=True)
    return plan


def verify_adoption_plan(
    plan: dict[str, Any], *, allow_existing_destinations: bool = False
) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("schema") != "portrait-recovery-adoption-plan-v1":
        raise VersionManagerError("unsupported adoption plan")
    expected_plan_hash = plan.get("plan_sha256")
    if not isinstance(expected_plan_hash, str) or _canonical_sha256(plan, "plan_sha256") != expected_plan_hash.casefold():
        raise VersionManagerError("adoption plan hash mismatch")
    if plan.get("status") != "READY" or plan.get("gender") != "female":
        raise VersionManagerError("adoption plan is not a ready female recovery")
    profile = plan.get("profile")
    revision = plan.get("revision")
    plan_id = plan.get("plan_id")
    targets = plan.get("target_identities")
    if not isinstance(profile, dict) or profile.get("gender") != "female":
        raise VersionManagerError("adoption plan has no female coverage profile")
    if not isinstance(revision, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*", revision
    ):
        raise VersionManagerError("adoption plan has an unsafe revision")
    if not isinstance(plan_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*", plan_id
    ):
        raise VersionManagerError("adoption plan has an unsafe plan id")
    if (
        not isinstance(targets, list)
        or not targets
        or len(set(targets)) != len(targets)
        or any(not isinstance(identity, str) for identity in targets)
    ):
        raise VersionManagerError("adoption plan has invalid target identities")
    try:
        expected_by_identity = {
            identity: expected_em_paths(profile, identity) for identity in targets
        }
    except (KeyError, TypeError) as exc:
        raise VersionManagerError("adoption plan has malformed coverage") from exc

    v5_text = plan.get("v5_root")
    recovery_text = plan.get("recovery_root")
    if not isinstance(v5_text, str) or not v5_text or not isinstance(
        recovery_text, str
    ) or not recovery_text:
        raise VersionManagerError("adoption plan has invalid lifecycle roots")
    v5_root = Path(v5_text).resolve()
    recovery_root = Path(recovery_text).resolve()
    component_root = v5_root / "female" / "component_library_v1"
    if not v5_root.is_dir() or not recovery_root.is_dir():
        raise VersionManagerError("adoption plan lifecycle root is missing")

    authority_binding = plan.get("authority_manifest")
    expected_manifest = (
        component_root / "_metadata" / "current" / "authority_manifest.json"
    ).resolve()
    if not isinstance(authority_binding, dict):
        raise VersionManagerError("adoption plan has no authority binding")
    authority_path_text = authority_binding.get("path")
    authority_hash = authority_binding.get("sha256")
    if (
        not isinstance(authority_path_text, str)
        or Path(authority_path_text).resolve() != expected_manifest
        or not isinstance(authority_hash, str)
        or not re.fullmatch(r"[0-9a-fA-F]{64}", authority_hash)
        or not expected_manifest.is_file()
        or file_sha256(expected_manifest) != authority_hash.casefold()
    ):
        raise VersionManagerError("adoption plan authority binding is invalid")
    authority = _load_json_object(expected_manifest, "plan-bound authority manifest")
    approved = authority.get("approved_authorities")
    if not isinstance(approved, dict):
        raise VersionManagerError("plan-bound authority has no approved authorities")

    files = plan.get("files")
    summary = plan.get("summary")
    if not isinstance(files, list) or not isinstance(summary, dict):
        raise VersionManagerError("adoption plan lacks files or summary")
    destinations: set[str] = set()
    identities: dict[str, dict[str, str]] = {}
    source_role_counts = {"retained_approved": 0, "recovered_exact": 0}
    for item in files:
        if not isinstance(item, dict):
            raise VersionManagerError("adoption plan file entry must be an object")
        destination = item.get("destination_relative")
        source_path = item.get("source_path")
        expected_hash = item.get("source_sha256")
        identity = item.get("identity")
        category = item.get("category")
        relative = item.get("relative_path")
        source_role = item.get("source_role")
        if not all(
            isinstance(value, str) and value
            for value in (
                destination,
                source_path,
                expected_hash,
                identity,
                category,
                relative,
                source_role,
            )
        ):
            raise VersionManagerError("adoption plan file entry is incomplete")
        if (
            identity not in expected_by_identity
            or category != identity[0]
            or relative not in expected_by_identity[identity]
            or source_role not in source_role_counts
            or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash)
        ):
            raise VersionManagerError("adoption plan file entry breaks coverage")
        expected_destination = (
            f"female/component_library_v1/{category}/{identity}/current/"
            f"candidates/{revision}/{relative}"
        )
        if destination.replace("\\", "/") != expected_destination:
            raise VersionManagerError(
                f"adoption destination breaks the lifecycle contract: {destination}"
            )
        if destination in destinations:
            raise VersionManagerError(f"duplicate adoption destination: {destination}")
        destinations.add(destination)
        destination_path = _inside(v5_root / Path(destination), v5_root)
        if destination_path.exists() and not allow_existing_destinations:
            raise VersionManagerError(f"adoption destination already exists: {destination}")
        source = Path(source_path).resolve()
        if source_role == "recovered_exact":
            _inside(source, recovery_root)
        else:
            record = (
                approved.get(category, {}).get(identity)
                if isinstance(approved.get(category), dict)
                else None
            )
            if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                raise VersionManagerError(f"retained authority is missing: {identity}")
            retained_root = _inside(
                component_root / Path(record["path"]), component_root
            )
            if source != _inside(retained_root / Path(relative), retained_root):
                raise VersionManagerError(
                    f"retained source is outside selected authority: {identity}/{relative}"
                )
            hashes = record.get("files_sha256")
            retained_hash = hashes.get(relative) if isinstance(hashes, dict) else None
            if (
                not isinstance(retained_hash, str)
                or retained_hash.casefold() != expected_hash.casefold()
            ):
                raise VersionManagerError(
                    f"retained source is not authority hash-bound: {identity}/{relative}"
                )
        if not source.is_file() or file_sha256(source) != expected_hash.casefold():
            raise VersionManagerError(f"adoption source hash mismatch: {source}")
        source_role_counts[source_role] += 1
        identities.setdefault(identity, {})[relative] = expected_hash.casefold()
    if set(identities) != set(targets) or any(
        set(identities.get(identity, {})) != expected
        for identity, expected in expected_by_identity.items()
    ):
        raise VersionManagerError("adoption plan does not have exact target coverage")
    expected_summary = {
        "identity_count": len(targets),
        "file_count": len(files),
        "retained_count": source_role_counts["retained_approved"],
        "recovered_count": source_role_counts["recovered_exact"],
    }
    if summary != expected_summary:
        raise VersionManagerError("adoption plan summary does not match its files")
    planned_trees = plan.get("identity_tree_sha256")
    if not isinstance(planned_trees, dict) or set(planned_trees) != set(targets):
        raise VersionManagerError("adoption plan lacks identity tree hashes")
    for identity, identity_files in identities.items():
        if _tree_hash_from_records(identity_files) != planned_trees.get(identity):
            raise VersionManagerError(f"planned identity tree hash mismatch: {identity}")
    plan_kind = plan.get("plan_kind")
    if plan_kind not in {None, "existing_complete_candidate_promotion"}:
        raise VersionManagerError("unsupported adoption plan kind")
    if plan_kind == "existing_complete_candidate_promotion":
        if len(targets) != 1:
            raise VersionManagerError("existing candidate promotion supports one identity")
        identity = targets[0]
        category = identity[0]
        candidate_binding = plan.get("existing_candidate")
        evidence_binding = plan.get("acceptance_evidence")
        if not isinstance(candidate_binding, dict) or not isinstance(evidence_binding, dict):
            raise VersionManagerError("existing candidate plan lacks evidence bindings")
        expected_candidate = (
            component_root
            / category
            / identity
            / "current"
            / "candidates"
            / revision
        ).resolve()
        candidate_text = candidate_binding.get("path")
        candidate_tree = candidate_binding.get("tree_sha256")
        candidate_evidence_text = candidate_binding.get("evidence_path")
        candidate_evidence_tree = candidate_binding.get("evidence_tree_sha256")
        candidate_evidence_root = _inside(recovery_root, component_root)
        candidate_evidence_relative = candidate_evidence_root.relative_to(component_root)
        if (
            not isinstance(candidate_text, str)
            or Path(candidate_text).resolve() != expected_candidate
            or not isinstance(candidate_tree, str)
            or candidate_tree != planned_trees[identity]
            or not expected_candidate.is_dir()
            or tree_sha256(expected_candidate) != candidate_tree
        ):
            raise VersionManagerError("existing candidate binding is invalid")
        if (
            not isinstance(candidate_evidence_text, str)
            or Path(candidate_evidence_text).resolve() != candidate_evidence_root
            or not isinstance(candidate_evidence_tree, str)
            or candidate_evidence_tree != candidate_tree
            or not candidate_evidence_relative.parts
            or candidate_evidence_relative.parts[0] != "_work_history"
            or not candidate_evidence_root.is_dir()
            or tree_sha256(candidate_evidence_root) != candidate_evidence_tree
        ):
            raise VersionManagerError("complete candidate evidence binding is invalid")
        expected_changed = sorted(
            item["relative_path"]
            for item in files
            if item["source_role"] == "recovered_exact"
        )
        if plan.get("changed_relative_paths") != expected_changed:
            raise VersionManagerError("existing candidate changed-file list is invalid")
        evidence_text = evidence_binding.get("path")
        evidence_hash = evidence_binding.get("sha256")
        if not isinstance(evidence_text, str) or not isinstance(evidence_hash, str):
            raise VersionManagerError("acceptance evidence binding is incomplete")
        evidence_path = _inside(Path(evidence_text).resolve(), component_root)
        evidence_relative = evidence_path.relative_to(component_root)
        if (
            not evidence_relative.parts
            or evidence_relative.parts[0] != "_work_history"
            or not evidence_path.is_file()
            or file_sha256(evidence_path) != evidence_hash.casefold()
        ):
            raise VersionManagerError("acceptance evidence binding is invalid")
    return {"status": "PASS", "verified_files": len(files)}


def _write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _replace_with_retry(temporary, path)


def _replace_with_retry(source: Path, destination: Path) -> None:
    for attempt in range(8):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.05 * (attempt + 1))


def _candidate_roots(plan: dict[str, Any]) -> dict[str, Path]:
    v5_root = Path(plan["v5_root"]).resolve()
    roots: dict[str, Path] = {}
    for item in plan["files"]:
        destination = _inside(v5_root / Path(item["destination_relative"]), v5_root)
        relative_parts = Path(item["relative_path"]).parts
        root = destination
        for _ in relative_parts:
            root = root.parent
        identity = item["identity"]
        if identity in roots and roots[identity] != root:
            raise VersionManagerError(f"identity has multiple candidate roots: {identity}")
        roots[identity] = root
    return roots


def apply_recovery_plan(plan: dict[str, Any]) -> dict[str, Any]:
    verify_adoption_plan(plan)
    v5_root = Path(plan["v5_root"]).resolve()
    component_root = v5_root / "female" / "component_library_v1"
    journal_path = (
        component_root
        / "_work_history"
        / "current"
        / plan["plan_id"]
        / "transactions"
        / "apply_transaction_v1.json"
    )
    if journal_path.exists():
        raise VersionManagerError(f"apply transaction already exists: {journal_path}")

    candidate_roots = _candidate_roots(plan)
    staging_roots = {
        identity: root.with_name(f".{root.name}.{plan['plan_id']}.staging")
        for identity, root in candidate_roots.items()
    }
    for identity, root in staging_roots.items():
        if root.exists():
            raise VersionManagerError(f"classified apply staging already exists: {identity}")

    journal: dict[str, Any] = {
        "schema": "portrait-version-manager-apply-transaction-v1",
        "status": "PREPARED",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_roots": {
            identity: str(root) for identity, root in sorted(candidate_roots.items())
        },
        "staging_roots": {
            identity: str(root) for identity, root in sorted(staging_roots.items())
        },
        "moved_candidates": [],
    }
    _write_json_atomic(journal_path, journal)

    try:
        journal["status"] = "COPYING_CLASSIFIED_STAGING"
        _write_json_atomic(journal_path, journal)
        for item in plan["files"]:
            identity = item["identity"]
            destination = staging_roots[identity] / Path(item["relative_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(item["source_path"]), destination)

        files_by_identity: dict[str, int] = {}
        for item in plan["files"]:
            files_by_identity[item["identity"]] = files_by_identity.get(item["identity"], 0) + 1
        for identity, root in staging_roots.items():
            physical = [path for path in root.rglob("*") if path.is_file()]
            if len(physical) != files_by_identity[identity]:
                raise VersionManagerError(f"staged candidate file count mismatch: {identity}")
            if tree_sha256(root) != plan["identity_tree_sha256"][identity]:
                raise VersionManagerError(f"staged candidate tree hash mismatch: {identity}")

        journal["status"] = "MOVING_COMPLETE_CANDIDATES"
        _write_json_atomic(journal_path, journal)
        for identity in sorted(candidate_roots):
            target = candidate_roots[identity]
            target.parent.mkdir(parents=True, exist_ok=True)
            staging_roots[identity].rename(target)
            journal["moved_candidates"].append(identity)
            _write_json_atomic(journal_path, journal)
        journal["status"] = "APPLIED"
        journal["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(journal_path, journal)
    except Exception as exc:
        journal["status"] = "APPLY_NEEDS_RECOVERY"
        journal["error"] = f"{type(exc).__name__}: {exc}"
        _write_json_atomic(journal_path, journal)
        if isinstance(exc, VersionManagerError):
            raise
        raise VersionManagerError(f"candidate apply failed; inspect {journal_path}") from exc

    return {
        "status": "APPLIED",
        "journal_path": str(journal_path),
        "candidates": [str(candidate_roots[key]) for key in sorted(candidate_roots)],
    }


def _verify_candidate_tree(
    root: Path, identity: str, plan: dict[str, Any], expected_count: int
) -> None:
    if not root.is_dir():
        raise VersionManagerError(f"candidate tree is missing: {identity}")
    physical = [path for path in root.rglob("*") if path.is_file()]
    if len(physical) != expected_count:
        raise VersionManagerError(f"candidate file count mismatch: {identity}")
    if tree_sha256(root) != plan["identity_tree_sha256"][identity]:
        raise VersionManagerError(f"candidate tree hash mismatch: {identity}")


def resume_apply_recovery_plan(plan: dict[str, Any]) -> dict[str, Any]:
    verify_adoption_plan(plan, allow_existing_destinations=True)
    v5_root = Path(plan["v5_root"]).resolve()
    component_root = v5_root / "female" / "component_library_v1"
    journal_path = (
        component_root
        / "_work_history"
        / "current"
        / plan["plan_id"]
        / "transactions"
        / "apply_transaction_v1.json"
    )
    journal = _load_json_object(journal_path, "apply transaction journal")
    if (
        journal.get("schema") != "portrait-version-manager-apply-transaction-v1"
        or journal.get("status") != "APPLY_NEEDS_RECOVERY"
        or journal.get("plan_sha256") != plan["plan_sha256"]
    ):
        raise VersionManagerError("apply transaction is not a resumable plan-bound failure")

    candidate_roots = _candidate_roots(plan)
    staging_roots = {
        identity: root.with_name(f".{root.name}.{plan['plan_id']}.staging")
        for identity, root in candidate_roots.items()
    }
    if journal.get("candidate_roots") != {
        identity: str(root) for identity, root in sorted(candidate_roots.items())
    } or journal.get("staging_roots") != {
        identity: str(root) for identity, root in sorted(staging_roots.items())
    }:
        raise VersionManagerError("apply journal roots do not match the plan")

    counts: dict[str, int] = {}
    for item in plan["files"]:
        counts[item["identity"]] = counts.get(item["identity"], 0) + 1
    ready_staging: list[str] = []
    complete_candidates: list[str] = []
    for identity in sorted(candidate_roots):
        candidate_exists = candidate_roots[identity].exists()
        staging_exists = staging_roots[identity].exists()
        if candidate_exists == staging_exists:
            raise VersionManagerError(
                f"resume requires exactly one classified tree for {identity}"
            )
        if candidate_exists:
            _verify_candidate_tree(
                candidate_roots[identity], identity, plan, counts[identity]
            )
            complete_candidates.append(identity)
        else:
            _verify_candidate_tree(
                staging_roots[identity], identity, plan, counts[identity]
            )
            ready_staging.append(identity)

    failed_atomic_dir = journal_path.parent / "failed_atomic_writes"
    stale_atomic_temps = sorted(
        journal_path.parent.glob(f".{journal_path.name}.*.tmp")
    )
    classified_failed_writes: list[str] = []
    for stale in stale_atomic_temps:
        destination = failed_atomic_dir / stale.name
        if destination.exists():
            raise VersionManagerError(
                f"failed atomic-write evidence collision: {destination}"
            )
    if stale_atomic_temps:
        failed_atomic_dir.mkdir(parents=True, exist_ok=True)
        for stale in stale_atomic_temps:
            destination = failed_atomic_dir / stale.name
            stale.rename(destination)
            classified_failed_writes.append(str(destination))

    journal["status"] = "RESUMING_VERIFIED_APPLY"
    journal["resume_started_at"] = datetime.now(timezone.utc).isoformat()
    journal["moved_candidates"] = complete_candidates
    journal["classified_failed_atomic_writes"] = classified_failed_writes
    _write_json_atomic(journal_path, journal)
    try:
        for identity in ready_staging:
            staging_roots[identity].rename(candidate_roots[identity])
            journal["moved_candidates"].append(identity)
            _write_json_atomic(journal_path, journal)
        journal["moved_candidates"] = sorted(journal["moved_candidates"])
        journal["status"] = "APPLIED"
        journal["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(journal_path, journal)
    except Exception as exc:
        journal["status"] = "APPLY_NEEDS_RECOVERY"
        journal["error"] = f"{type(exc).__name__}: {exc}"
        _write_json_atomic(journal_path, journal)
        if isinstance(exc, VersionManagerError):
            raise
        raise VersionManagerError(f"candidate resume failed; inspect {journal_path}") from exc
    return {
        "status": "APPLIED",
        "journal_path": str(journal_path),
        "candidates": [str(candidate_roots[key]) for key in sorted(candidate_roots)],
        "resumed": True,
    }


def _validate_acceptance_record(
    path: Path, component_root: Path, plan: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    path = _inside(path, component_root)
    record = _load_json_object(path, "acceptance record")
    if (
        record.get("schema") != "portrait-recovery-acceptance-v1"
        or record.get("decision") != "accepted"
        or record.get("plan_sha256") != plan["plan_sha256"]
        or not isinstance(record.get("record_id"), str)
        or not record["record_id"]
        or not isinstance(record.get("accepted_by"), str)
        or not record["accepted_by"]
        or not isinstance(record.get("accepted_at"), str)
        or not record["accepted_at"]
    ):
        raise VersionManagerError("acceptance record is incomplete or does not bind this plan")
    return record, file_sha256(path)


def promote_recovery_plan(
    plan: dict[str, Any], *, acceptance_record_path: Path | str
) -> dict[str, Any]:
    verify_adoption_plan(plan, allow_existing_destinations=True)
    v5_root = Path(plan["v5_root"]).resolve()
    component_root = v5_root / "female" / "component_library_v1"
    manifest_path = Path(plan["authority_manifest"]["path"]).resolve()
    _inside(manifest_path, component_root)
    if file_sha256(manifest_path) != plan["authority_manifest"]["sha256"]:
        raise VersionManagerError("authority changed after the adoption plan was created")
    acceptance_path = Path(acceptance_record_path).resolve()
    acceptance, acceptance_sha = _validate_acceptance_record(
        acceptance_path, component_root, plan
    )

    manifest = _load_json_object(manifest_path, "authority manifest")
    approved = manifest.get("approved_authorities")
    if not isinstance(approved, dict):
        raise VersionManagerError("authority manifest has no approved_authorities")
    candidate_roots = _candidate_roots(plan)
    files_by_identity: dict[str, dict[str, str]] = {}
    for item in plan["files"]:
        files_by_identity.setdefault(item["identity"], {})[item["relative_path"]] = item[
            "source_sha256"
        ].casefold()

    operations: dict[str, dict[str, Path]] = {}
    for identity in sorted(plan["target_identities"]):
        category = identity[0]
        candidate = candidate_roots[identity]
        if not candidate.is_dir():
            raise VersionManagerError(f"candidate revision is missing: {identity}")
        physical = {
            path.relative_to(candidate).as_posix()
            for path in candidate.rglob("*")
            if path.is_file()
        }
        if physical != set(files_by_identity[identity]):
            raise VersionManagerError(f"candidate coverage mismatch: {identity}")
        if tree_sha256(candidate) != plan["identity_tree_sha256"][identity]:
            raise VersionManagerError(f"candidate tree hash mismatch: {identity}")
        for relative, expected_hash in files_by_identity[identity].items():
            if file_sha256(candidate / Path(relative)) != expected_hash:
                raise VersionManagerError(f"candidate file hash mismatch: {identity}/{relative}")

        record = approved.get(category, {}).get(identity) if isinstance(approved.get(category), dict) else None
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise VersionManagerError(f"current authority is missing: {identity}")
        old_approved = _inside(component_root / Path(record["path"]), component_root)
        approved_root = component_root / category / identity / "current" / "approved"
        revisions = sorted(path for path in approved_root.iterdir() if path.is_dir()) if approved_root.is_dir() else []
        if revisions != [old_approved]:
            raise VersionManagerError(f"approved revision invariant failed: {identity}")
        superseded = (
            component_root
            / category
            / identity
            / "old_versions"
            / "superseded"
            / old_approved.name
        )
        new_approved = approved_root / plan["revision"]
        if superseded.exists() or new_approved.exists():
            raise VersionManagerError(f"promotion destination collision: {identity}")
        operations[identity] = {
            "candidate": candidate,
            "old_approved": old_approved,
            "superseded": superseded,
            "new_approved": new_approved,
        }

    new_manifest = deepcopy(manifest)
    coverage = (
        f"{plan['profile']['skins'][0]}-{plan['profile']['skins'][-1]} "
        + "/".join(plan["profile"]["groups"])
    )
    acceptance_relative = acceptance_path.relative_to(component_root).as_posix()
    for identity in sorted(plan["target_identities"]):
        category = identity[0]
        new_manifest["approved_authorities"][category][identity] = {
            "path": f"{category}/{identity}/current/approved/{plan['revision']}",
            "tree_sha256": plan["identity_tree_sha256"][identity],
            "files_sha256": dict(sorted(files_by_identity[identity].items())),
            "payload_source_revision": plan["revision"],
            "accepted_by_record_id": acceptance["record_id"],
            "accepted_record_sha256": acceptance_sha,
            "accepted_record_time": acceptance["accepted_at"],
            "coverage": coverage,
            "accepted_record_path": acceptance_relative,
        }

    transaction_root = (
        component_root
        / "_work_history"
        / "current"
        / plan["plan_id"]
        / "transactions"
    )
    journal_path = transaction_root / "promotion_transaction_v1.json"
    backup_path = transaction_root / (
        f"authority_manifest.before.{plan['authority_manifest']['sha256']}.json"
    )
    staged_manifest_path = transaction_root / "authority_manifest.promoted.pending.json"
    if journal_path.exists() or backup_path.exists() or staged_manifest_path.exists():
        raise VersionManagerError("promotion transaction artifacts already exist")
    transaction_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_path, backup_path)
    _write_json_atomic(staged_manifest_path, new_manifest)
    journal: dict[str, Any] = {
        "schema": "portrait-version-manager-promotion-transaction-v1",
        "status": "PREPARED",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "acceptance_record_path": str(acceptance_path),
        "acceptance_record_sha256": acceptance_sha,
        "authority_manifest_path": str(manifest_path),
        "authority_backup_path": str(backup_path),
        "operations": {
            identity: {key: str(value) for key, value in operation.items()}
            for identity, operation in operations.items()
        },
        "moved_old": [],
        "moved_new": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json_atomic(journal_path, journal)

    manifest_replaced = False
    try:
        journal["status"] = "MOVING_REVISIONS"
        _write_json_atomic(journal_path, journal)
        for identity in sorted(operations):
            operation = operations[identity]
            operation["superseded"].parent.mkdir(parents=True, exist_ok=True)
            operation["old_approved"].rename(operation["superseded"])
            journal["moved_old"].append(identity)
            _write_json_atomic(journal_path, journal)
            operation["new_approved"].parent.mkdir(parents=True, exist_ok=True)
            operation["candidate"].rename(operation["new_approved"])
            journal["moved_new"].append(identity)
            _write_json_atomic(journal_path, journal)
        _replace_with_retry(staged_manifest_path, manifest_path)
        manifest_replaced = True
        journal["status"] = "PROMOTED"
        journal["authority_manifest_sha256_after"] = file_sha256(manifest_path)
        journal["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(journal_path, journal)
    except Exception as exc:
        rollback_errors: list[str] = []
        try:
            if manifest_replaced:
                restore = transaction_root / "authority_manifest.rollback.pending.json"
                shutil.copy2(backup_path, restore)
                _replace_with_retry(restore, manifest_path)
        except Exception as rollback_exc:
            rollback_errors.append(f"authority: {rollback_exc}")
        for identity in reversed(journal["moved_new"]):
            operation = operations[identity]
            try:
                if operation["new_approved"].exists() and not operation["candidate"].exists():
                    operation["new_approved"].rename(operation["candidate"])
            except Exception as rollback_exc:
                rollback_errors.append(f"new {identity}: {rollback_exc}")
        for identity in reversed(journal["moved_old"]):
            operation = operations[identity]
            try:
                if operation["superseded"].exists() and not operation["old_approved"].exists():
                    operation["superseded"].rename(operation["old_approved"])
            except Exception as rollback_exc:
                rollback_errors.append(f"old {identity}: {rollback_exc}")
        journal["status"] = "ROLLED_BACK" if not rollback_errors else "PROMOTION_NEEDS_RECOVERY"
        journal["error"] = f"{type(exc).__name__}: {exc}"
        journal["rollback_errors"] = rollback_errors
        _write_json_atomic(journal_path, journal)
        if isinstance(exc, VersionManagerError):
            raise
        raise VersionManagerError(f"promotion failed; inspect {journal_path}") from exc

    return {
        "status": "PROMOTED",
        "journal_path": str(journal_path),
        "authority_manifest_path": str(manifest_path),
        "authority_manifest_sha256": file_sha256(manifest_path),
    }


def _verify_evidence_manifest(path: Path, component_root: Path) -> dict[str, str]:
    path = _inside(path.resolve(), component_root)
    document = _load_json_object(path, "evidence manifest")
    files = document.get("files")
    if not isinstance(files, list) or not files:
        raise VersionManagerError(f"evidence manifest has no files: {path}")
    for item in files:
        if not isinstance(item, dict):
            raise VersionManagerError(f"invalid evidence file record: {path}")
        relative = item.get("path")
        expected_hash = item.get("sha256")
        expected_bytes = item.get("bytes")
        if not isinstance(relative, str) or Path(relative).is_absolute() or not isinstance(expected_hash, str) or not isinstance(expected_bytes, int):
            raise VersionManagerError(f"invalid evidence file binding: {path}")
        payload = _inside(path.parent / Path(relative), path.parent)
        if (
            not payload.is_file()
            or payload.stat().st_size != expected_bytes
            or file_sha256(payload) != expected_hash.casefold()
        ):
            raise VersionManagerError(f"evidence file mismatch: {payload}")
    return {"path": str(path), "sha256": file_sha256(path)}


def build_cleanup_protection(
    plan: dict[str, Any],
    *,
    evidence_manifest_paths: list[Path | str],
    public_export: dict[str, Any],
) -> dict[str, Any]:
    if (
        not isinstance(plan, dict)
        or plan.get("schema") != "portrait-recovery-adoption-plan-v1"
        or plan.get("plan_sha256") != _canonical_sha256(plan, "plan_sha256")
    ):
        raise VersionManagerError("cleanup builder requires an exact adoption plan")
    if not evidence_manifest_paths:
        raise VersionManagerError("cleanup builder requires immutable evidence manifests")
    v5_root = Path(plan["v5_root"]).resolve()
    component_root = v5_root / "female" / "component_library_v1"
    manifest_path = component_root / "_metadata" / "current" / "authority_manifest.json"
    authority = _load_json_object(manifest_path, "current female authority")
    approved = authority.get("approved_authorities")
    if not isinstance(approved, dict):
        raise VersionManagerError("current female authority has no approved_authorities")

    transaction_root = (
        component_root
        / "_work_history"
        / "current"
        / plan["plan_id"]
        / "transactions"
    )
    promotion_journal_path = transaction_root / "promotion_transaction_v1.json"
    promotion = _load_json_object(promotion_journal_path, "promotion transaction")
    if (
        promotion.get("status") != "PROMOTED"
        or promotion.get("plan_sha256") != plan["plan_sha256"]
        or promotion.get("authority_manifest_sha256_after") != file_sha256(manifest_path)
    ):
        raise VersionManagerError("promotion transaction is not complete or authority-bound")
    acceptance_path = Path(promotion.get("acceptance_record_path", "")).resolve()
    if (
        not acceptance_path.is_file()
        or file_sha256(acceptance_path) != promotion.get("acceptance_record_sha256")
    ):
        raise VersionManagerError("promotion acceptance record is missing or mismatched")

    evidence = [
        _verify_evidence_manifest(Path(path), component_root)
        for path in evidence_manifest_paths
    ]
    artifacts: list[dict[str, Any]] = []
    unclassified: list[str] = []
    for item in plan["files"]:
        if item.get("source_role") != "recovered_exact":
            continue
        identity = item["identity"]
        category = item["category"]
        relative = item["relative_path"]
        expected_hash = item["source_sha256"].casefold()
        source = Path(item["source_path"]).resolve()
        approved_copy = (
            component_root
            / category
            / identity
            / "current"
            / "approved"
            / plan["revision"]
            / Path(relative)
        ).resolve()
        record = approved.get(category, {}).get(identity) if isinstance(approved.get(category), dict) else None
        files_sha256 = record.get("files_sha256") if isinstance(record, dict) else None
        selected_hash = (
            files_sha256.get(relative) if isinstance(files_sha256, dict) else None
        )
        if (
            not isinstance(record, dict)
            or record.get("path")
            != f"{category}/{identity}/current/approved/{plan['revision']}"
            or not isinstance(selected_hash, str)
            or selected_hash.casefold() != expected_hash
        ):
            raise VersionManagerError(f"formal authority does not select recovered file: {identity}/{relative}")
        for copy in (source, approved_copy):
            if not copy.is_file() or file_sha256(copy) != expected_hash:
                raise VersionManagerError(f"protected cleanup copy mismatch: {copy}")
        artifacts.append(
            {
                "id": f"female/{category}/{identity}/{relative}",
                "kind": "full_canvas_component",
                "sha256": expected_hash,
                "registry_bound": True,
                "copies": [str(source), str(approved_copy)],
            }
        )

    candidate_roots = _candidate_roots(plan)
    for identity, candidate in candidate_roots.items():
        staging = candidate.with_name(
            f".{candidate.name}.{plan['plan_id']}.staging"
        )
        if candidate.exists():
            unclassified.append(str(candidate))
        if staging.exists():
            unclassified.append(str(staging))
    return {
        "schema": "portrait-cleanup-protection-v1",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "protected_artifacts": artifacts,
        "formal_state_complete": True,
        "evidence_complete": True,
        "acceptance_complete": True,
        "promotion_complete": True,
        "public_export": public_export,
        "unclassified_staging": sorted(unclassified),
        "evidence_manifests": evidence,
        "promotion_transaction": {
            "path": str(promotion_journal_path),
            "sha256": file_sha256(promotion_journal_path),
        },
    }


def cleanup_check(manifest: dict[str, Any] | Path | str) -> dict[str, Any]:
    if isinstance(manifest, (Path, str)):
        manifest = _load_json_object(Path(manifest), "cleanup protection manifest")
    if not isinstance(manifest, dict) or manifest.get("schema") != "portrait-cleanup-protection-v1":
        raise VersionManagerError("unsupported cleanup protection manifest")

    blockers: list[dict[str, str]] = []

    def block(code: str, detail: str) -> None:
        item = {"code": code, "detail": detail}
        if item not in blockers:
            blockers.append(item)

    artifacts = manifest.get("protected_artifacts")
    verified_artifacts = 0
    if not isinstance(artifacts, list) or not artifacts:
        block("protected_registry_missing", "no protected artifacts are registered")
        artifacts = []
    seen_ids: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            block("protected_registry_invalid", "artifact entry is not an object")
            continue
        artifact_id = artifact.get("id")
        expected_hash = artifact.get("sha256")
        if not isinstance(artifact_id, str) or not artifact_id or artifact_id in seen_ids:
            block("protected_registry_invalid", "artifact id is missing or duplicated")
            continue
        seen_ids.add(artifact_id)
        if artifact.get("kind") != "full_canvas_component":
            block("thumbnail_is_not_source", artifact_id)
        if artifact.get("registry_bound") is not True or not isinstance(expected_hash, str):
            block("artifact_not_hash_bound", artifact_id)
            continue
        copies = artifact.get("copies")
        verified_paths: set[Path] = set()
        if isinstance(copies, list):
            for path_text in copies:
                if not isinstance(path_text, str):
                    continue
                path = Path(path_text).resolve()
                if path in verified_paths:
                    continue
                if path.is_file() and file_sha256(path) == expected_hash.casefold():
                    verified_paths.add(path)
        if len(verified_paths) < 2:
            block("insufficient_verified_copies", artifact_id)
        elif artifact.get("kind") == "full_canvas_component":
            verified_artifacts += 1

    lifecycle_checks = {
        "formal_state_complete": "formal_state_incomplete",
        "evidence_complete": "evidence_incomplete",
        "acceptance_complete": "acceptance_pending",
        "promotion_complete": "promotion_pending",
    }
    for field, code in lifecycle_checks.items():
        if manifest.get(field) is not True:
            block(code, field)

    unclassified = manifest.get("unclassified_staging")
    if not isinstance(unclassified, list):
        block("unclassified_staging", "unclassified_staging must be a list")
    elif unclassified:
        block("unclassified_staging", ", ".join(str(item) for item in unclassified))

    public_export = manifest.get("public_export")
    if not isinstance(public_export, dict):
        block("public_export_pending", "public export state is missing")
    elif public_export.get("status") == "pushed":
        commit = public_export.get("commit")
        if not isinstance(commit, str) or not re.fullmatch(
            r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", commit
        ):
            block("public_export_pending", "pushed export has no full commit hash")
    elif public_export.get("status") == "private_only":
        exemption = public_export.get("exemption")
        if not (
            isinstance(exemption, dict)
            and isinstance(exemption.get("reason"), str)
            and exemption.get("reason")
            and isinstance(exemption.get("approved_by"), str)
            and exemption.get("approved_by")
            and isinstance(exemption.get("record_sha256"), str)
            and re.fullmatch(r"[0-9a-fA-F]{64}", exemption["record_sha256"])
        ):
            block("private_only_exemption_invalid", "private-only exemption is incomplete")
    else:
        block("public_export_pending", "public export is not pushed")

    blockers.sort(key=lambda item: (item["code"], item["detail"]))
    return {
        "schema": "portrait-cleanup-check-report-v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "verified_artifacts": verified_artifacts,
        "blockers": blockers,
        "deletes_performed": 0,
    }


def _emit_result(result: dict[str, Any], output: Path | None) -> None:
    if output is not None:
        _write_json_atomic(output.resolve(), result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    default_profiles = (
        Path(__file__).resolve().parents[1] / "references" / "version-management.json"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, default=default_profiles)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="audit a gender E/M authority")
    audit.add_argument("v5_root", type=Path)
    audit.add_argument("gender", choices=("female", "male"))
    audit.add_argument("profile")
    audit.add_argument("--output", type=Path)

    plan = subparsers.add_parser(
        "plan-recovery", help="build a deterministic no-write female recovery plan"
    )
    plan.add_argument("v5_root", type=Path)
    plan.add_argument("lane_registry", type=Path)
    plan.add_argument("recovery_root", type=Path)
    plan.add_argument("revision")
    plan.add_argument("plan_id")
    plan.add_argument("profile")
    plan.add_argument("targets", nargs="+")
    plan.add_argument("--frozen-inventory", type=Path)
    plan.add_argument("--output", type=Path, required=True)

    plan_candidate = subparsers.add_parser(
        "plan-candidate",
        help="bind an existing complete candidate and its QC evidence for promotion",
    )
    plan_candidate.add_argument("v5_root", type=Path)
    plan_candidate.add_argument("evidence_root", type=Path)
    plan_candidate.add_argument("revision")
    plan_candidate.add_argument("plan_id")
    plan_candidate.add_argument("profile")
    plan_candidate.add_argument("identity")
    plan_candidate.add_argument("acceptance_evidence", type=Path)
    plan_candidate.add_argument("--output", type=Path, required=True)

    apply = subparsers.add_parser(
        "apply-recovery", help="create complete candidates from a verified plan"
    )
    apply.add_argument("plan", type=Path)
    apply.add_argument("--output", type=Path)

    resume = subparsers.add_parser(
        "resume-apply", help="resume a hash-verified classified partial apply"
    )
    resume.add_argument("plan", type=Path)
    resume.add_argument("--output", type=Path)

    promote = subparsers.add_parser(
        "promote", help="archive current revisions and promote accepted candidates"
    )
    promote.add_argument("plan", type=Path)
    promote.add_argument("acceptance_record", type=Path)
    promote.add_argument("--output", type=Path)

    cleanup = subparsers.add_parser(
        "cleanup-check", help="report whether protected staging is safe to clean"
    )
    cleanup.add_argument("manifest", type=Path)
    cleanup.add_argument("--output", type=Path)

    build_cleanup = subparsers.add_parser(
        "build-cleanup-manifest",
        help="build two-copy cleanup protection from a promoted recovery plan",
    )
    build_cleanup.add_argument("plan", type=Path)
    build_cleanup.add_argument("evidence_manifests", type=Path, nargs="+")
    build_cleanup.add_argument(
        "--public-export-status", choices=("pending", "pushed"), default="pending"
    )
    build_cleanup.add_argument("--commit")
    build_cleanup.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            profiles = load_profiles(args.profiles)
            if args.profile not in profiles:
                raise VersionManagerError(f"unknown coverage profile: {args.profile}")
            result = audit_authority(
                args.v5_root, args.gender, profiles[args.profile]
            )
        elif args.command == "plan-recovery":
            profiles = load_profiles(args.profiles)
            if args.profile not in profiles:
                raise VersionManagerError(f"unknown coverage profile: {args.profile}")
            result = plan_female_em_recovery(
                v5_root=args.v5_root,
                profile=profiles[args.profile],
                lane_registry_path=args.lane_registry,
                recovery_root=args.recovery_root,
                frozen_inventory_path=args.frozen_inventory,
                target_identities=args.targets,
                revision=args.revision,
                plan_id=args.plan_id,
            )
        elif args.command == "plan-candidate":
            profiles = load_profiles(args.profiles)
            if args.profile not in profiles:
                raise VersionManagerError(f"unknown coverage profile: {args.profile}")
            result = plan_existing_candidate_promotion(
                v5_root=args.v5_root,
                profile=profiles[args.profile],
                identity=args.identity,
                revision=args.revision,
                plan_id=args.plan_id,
                evidence_root=args.evidence_root,
                acceptance_evidence_path=args.acceptance_evidence,
            )
        elif args.command == "apply-recovery":
            result = apply_recovery_plan(_load_json_object(args.plan, "adoption plan"))
        elif args.command == "resume-apply":
            result = resume_apply_recovery_plan(
                _load_json_object(args.plan, "adoption plan")
            )
        elif args.command == "promote":
            result = promote_recovery_plan(
                _load_json_object(args.plan, "adoption plan"),
                acceptance_record_path=args.acceptance_record,
            )
        elif args.command == "build-cleanup-manifest":
            public_export = {"status": args.public_export_status}
            if args.commit:
                public_export["commit"] = args.commit
            result = build_cleanup_protection(
                _load_json_object(args.plan, "adoption plan"),
                evidence_manifest_paths=args.evidence_manifests,
                public_export=public_export,
            )
        else:
            result = cleanup_check(args.manifest)
        _emit_result(result, args.output)
        return 0 if result.get("status") not in {"BLOCKED", "ERROR"} else 2
    except VersionManagerError as exc:
        result = {
            "schema": "portrait-version-manager-error-v1",
            "status": "ERROR",
            "error": str(exc),
        }
        output = getattr(args, "output", None)
        _emit_result(result, output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
