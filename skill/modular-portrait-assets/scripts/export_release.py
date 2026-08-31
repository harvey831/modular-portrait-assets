#!/usr/bin/env python3
"""Export only hash-bound current authority assets into a clean CC0 package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Iterator


ALLOWED_ASSET_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg"}
FORBIDDEN_SOURCE_PARTS = {"_work_history", "old_versions", "candidates", "tmp", "qc"}


class ReleasePolicyError(RuntimeError):
    """Raised when a source cannot safely enter the public release."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_path_records(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        if isinstance(node.get("path"), str):
            yield node
        for value in node.values():
            yield from _walk_path_records(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_path_records(value)


def _assert_inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ReleasePolicyError(f"authority source escapes project root: {path}") from exc
    return resolved


def _assert_source_policy(path: Path, source_root: Path) -> None:
    relative = path.relative_to(source_root)
    lowered = [part.casefold() for part in relative.parts]
    if any(part in FORBIDDEN_SOURCE_PARTS for part in lowered):
        raise ReleasePolicyError(f"forbidden source area in approved authority: {relative.as_posix()}")
    if any("rmbg" in part for part in lowered):
        raise ReleasePolicyError(f"RMBG-named source cannot enter the CC0 release: {relative.as_posix()}")


def _tree_sha256(directory: Path) -> str:
    lines: list[str] = []
    for file_path in sorted(p for p in directory.rglob("*") if p.is_file()):
        relative = file_path.relative_to(directory).as_posix()
        lines.append(f"{relative}\0{file_sha256(file_path).lower()}\n")
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def _files_for_record(record: dict[str, Any], source: Path) -> list[tuple[Path, str]]:
    if source.is_file():
        expected = record.get("sha256")
        if not isinstance(expected, str):
            raise ReleasePolicyError(f"file authority lacks sha256: {source}")
        return [(source, expected.lower())]

    if not source.is_dir():
        raise ReleasePolicyError(f"authority path does not exist: {source}")

    files_sha256 = record.get("files_sha256")
    if isinstance(files_sha256, dict) and files_sha256:
        selected: list[tuple[Path, str]] = []
        for relative_text, expected in sorted(files_sha256.items()):
            if not isinstance(relative_text, str) or not isinstance(expected, str):
                raise ReleasePolicyError(f"invalid files_sha256 entry under {source}")
            candidate = _assert_inside(source / Path(relative_text), source)
            if not candidate.is_file():
                raise ReleasePolicyError(f"hash-bound authority file is missing: {candidate}")
            selected.append((candidate, expected.lower()))
        return selected

    expected_tree = record.get("tree_sha256")
    if isinstance(expected_tree, str):
        actual_tree = _tree_sha256(source)
        if actual_tree != expected_tree.lower():
            raise ReleasePolicyError(
                f"authority tree hash mismatch for {source}: expected {expected_tree}, got {actual_tree}"
            )
        files = sorted(p for p in source.rglob("*") if p.is_file())
        if not files:
            raise ReleasePolicyError(f"authority tree is empty: {source}")
        return [(path, file_sha256(path)) for path in files]

    raise ReleasePolicyError(f"directory authority lacks files_sha256 or tree_sha256: {source}")


def _release_path(source_file: Path, source_root: Path) -> Path:
    relative = source_file.relative_to(source_root)
    parts = list(relative.parts)
    if len(parts) < 4 or parts[1].casefold() != "component_library_v1":
        raise ReleasePolicyError(f"unsupported authority layout: {relative.as_posix()}")

    source_gender = parts[0].casefold()
    component_parts = parts[2:]
    if source_gender not in {"female", "male"}:
        raise ReleasePolicyError(f"unsupported source gender: {relative.as_posix()}")

    try:
        current_index = next(
            index
            for index in range(len(component_parts) - 2)
            if component_parts[index].casefold() == "current"
            and component_parts[index + 1].casefold() == "approved"
        )
    except StopIteration as exc:
        raise ReleasePolicyError(f"source is not under current/approved: {relative.as_posix()}") from exc

    flattened = component_parts[:current_index] + component_parts[current_index + 3 :]
    if not flattened:
        raise ReleasePolicyError(f"empty release path for {relative.as_posix()}")

    release_gender = "shared" if flattened[0].casefold() == "ears" else source_gender
    release = Path("assets") / release_gender / Path(*flattened)
    public_stem = re.sub(r"_candidate_v\d+$", "", release.stem, flags=re.IGNORECASE)
    release = release.with_name(f"{public_stem}{release.suffix}")
    lowered = [part.casefold() for part in release.parts]
    if (
        any(part in FORBIDDEN_SOURCE_PARTS for part in lowered)
        or any("candidate" in part for part in lowered)
        or any("rmbg" in part for part in lowered)
    ):
        raise ReleasePolicyError(f"forbidden release path: {release.as_posix()}")
    if release.suffix.casefold() not in ALLOWED_ASSET_SUFFIXES:
        raise ReleasePolicyError(f"unsupported asset type in authority: {relative.as_posix()}")
    return release


def _is_male_shared_ear_delegation_metadata(source_file: Path, source_root: Path) -> bool:
    relative = source_file.relative_to(source_root)
    lowered = [part.casefold() for part in relative.parts]
    return (
        len(lowered) >= 5
        and lowered[:4] == ["male", "component_library_v1", "ears", "shared"]
        and source_file.suffix.casefold() == ".json"
    )


def build_release(source_root: Path | str, release_root: Path | str) -> dict[str, Any]:
    source_root = Path(source_root).resolve()
    release_root = Path(release_root).resolve()
    assets_root = release_root / "assets"
    manifest_path = release_root / "provenance" / "asset-manifest.json"
    authority_summary_path = release_root / "provenance" / "authority-summary.json"

    if assets_root.exists() or manifest_path.exists() or authority_summary_path.exists():
        raise ReleasePolicyError("managed release outputs already exist; export into a clean destination")

    export_records: dict[str, dict[str, Any]] = {}
    source_seen: set[Path] = set()
    authority_summaries: list[dict[str, Any]] = []

    for authority_gender in ("female", "male"):
        authority_path = (
            source_root
            / authority_gender
            / "component_library_v1"
            / "_metadata"
            / "current"
            / "authority_manifest.json"
        )
        if not authority_path.is_file():
            raise ReleasePolicyError(f"authority manifest is missing: {authority_path}")
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        approved = authority.get("approved_authorities")
        if not isinstance(approved, dict):
            raise ReleasePolicyError(f"approved_authorities is missing: {authority_path}")
        authority_summaries.append(
            {
                "gender": authority_gender,
                "schema": authority.get("schema"),
                "status": authority.get("status"),
                "effective_date": authority.get("effective_date"),
                "sha256": file_sha256(authority_path),
            }
        )

        gender_root = source_root / authority_gender / "component_library_v1"
        for record in _walk_path_records(approved):
            raw_path = Path(record["path"])
            source = raw_path if raw_path.is_absolute() else gender_root / raw_path
            source = _assert_inside(source, source_root)
            _assert_source_policy(source, source_root)

            for source_file, expected_sha in _files_for_record(record, source):
                source_file = _assert_inside(source_file, source_root)
                _assert_source_policy(source_file, source_root)
                actual_sha = file_sha256(source_file)
                if actual_sha != expected_sha:
                    raise ReleasePolicyError(
                        f"authority hash mismatch for {source_file}: expected {expected_sha}, got {actual_sha}"
                    )
                if _is_male_shared_ear_delegation_metadata(source_file, source_root):
                    continue
                if source_file in source_seen:
                    continue
                source_seen.add(source_file)

                release_path = _release_path(source_file, source_root)
                release_key = release_path.as_posix()
                existing = export_records.get(release_key)
                if existing and existing["sha256"] != actual_sha:
                    raise ReleasePolicyError(f"two authority files collide at {release_key}")
                export_records[release_key] = {
                    "release_path": release_key,
                    "sha256": actual_sha,
                    "bytes": source_file.stat().st_size,
                    "source_authority": authority_gender,
                    "source_ref": source_file.relative_to(source_root).as_posix(),
                }

    for release_key, record in sorted(export_records.items()):
        source_file = source_root / Path(record["source_ref"])
        destination = release_root / Path(release_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, destination)

    manifest = {
        "schema": "modular-portrait-assets-cc0-v1",
        "license": "CC0-1.0",
        "source_project": "MODULAR_PORTRAIT_LIBRARY_V5",
        "asset_count": len(export_records),
        "total_bytes": sum(item["bytes"] for item in export_records.values()),
        "authority_manifests": authority_summaries,
        "assets": [export_records[key] for key in sorted(export_records)],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    authority_summary_path.write_text(
        json.dumps(
            {
                "schema": "authority-summary-v1",
                "selection_rule": "Only exact hash-bound files named by approved_authorities were exported.",
                "manifests": authority_summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"asset_count": len(export_records), "total_bytes": manifest["total_bytes"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("release_root", type=Path)
    args = parser.parse_args()
    result = build_release(args.source_root, args.release_root)
    print(json.dumps({"status": "PASS", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
