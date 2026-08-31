#!/usr/bin/env python3
"""Validate a modular portrait CC0 release against its hash manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # pragma: no cover - exercised by users without requirements
    Image = None
    UnidentifiedImageError = OSError


ALLOWED_ASSET_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg"}
FORBIDDEN_PARTS = {"_work_history", "old_versions", "candidates", "tmp", "qc", "current", "approved"}
MODEL_SUFFIXES = {".safetensors", ".ckpt", ".pth", ".pt", ".onnx", ".bin"}


class ReleaseValidationError(RuntimeError):
    """Raised when the release no longer matches its public manifest."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_release_path(root: Path, relative_text: str) -> Path:
    relative = Path(relative_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise ReleaseValidationError(f"unsafe manifest path: {relative_text}")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ReleaseValidationError(f"manifest path escapes release: {relative_text}") from exc
    return path


def validate_release(release_root: Path | str) -> dict[str, Any]:
    release_root = Path(release_root).resolve()
    manifest_path = release_root / "provenance" / "asset-manifest.json"
    if not manifest_path.is_file():
        raise ReleaseValidationError("provenance/asset-manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("license") != "CC0-1.0":
        raise ReleaseValidationError("asset manifest is not marked CC0-1.0")
    records = manifest.get("assets")
    if not isinstance(records, list):
        raise ReleaseValidationError("asset manifest has no assets array")
    if Image is None:
        raise ReleaseValidationError(
            "Pillow is required for image integrity checks; install requirements.txt"
        )

    expected_paths: set[str] = set()
    total_bytes = 0
    for record in records:
        if not isinstance(record, dict):
            raise ReleaseValidationError("invalid asset manifest record")
        relative_text = record.get("release_path")
        expected_sha = record.get("sha256")
        if not isinstance(relative_text, str) or not isinstance(expected_sha, str):
            raise ReleaseValidationError("asset record lacks release_path or sha256")
        relative = Path(relative_text)
        lowered = [part.casefold() for part in relative.parts]
        if not lowered or lowered[0] != "assets":
            raise ReleaseValidationError(f"asset is outside assets/: {relative_text}")
        if (
            any(part in FORBIDDEN_PARTS for part in lowered)
            or any("candidate" in part for part in lowered)
            or any("rmbg" in part for part in lowered)
        ):
            raise ReleaseValidationError(f"forbidden release path: {relative_text}")
        if relative.suffix.casefold() in MODEL_SUFFIXES:
            raise ReleaseValidationError(f"model weight found in release: {relative_text}")
        if relative.suffix.casefold() not in ALLOWED_ASSET_SUFFIXES:
            raise ReleaseValidationError(f"unsupported release asset: {relative_text}")
        if relative_text in expected_paths:
            raise ReleaseValidationError(f"duplicate release path: {relative_text}")
        expected_paths.add(relative_text)

        path = _safe_release_path(release_root, relative_text)
        if not path.is_file():
            raise ReleaseValidationError(f"manifest asset is missing: {relative_text}")
        actual_sha = file_sha256(path)
        if actual_sha != expected_sha.lower():
            raise ReleaseValidationError(
                f"asset hash mismatch for {relative_text}: expected {expected_sha}, got {actual_sha}"
            )
        try:
            with Image.open(path) as image:
                image.load()
                if image.size != (1254, 1254):
                    raise ReleaseValidationError(
                        f"asset canvas must be 1254x1254: {relative_text} is {image.size}"
                    )
                if image.mode != "RGBA":
                    raise ReleaseValidationError(
                        f"asset must decode as RGBA: {relative_text} is {image.mode}"
                    )
        except (UnidentifiedImageError, OSError) as exc:
            raise ReleaseValidationError(f"asset cannot be decoded: {relative_text}") from exc
        total_bytes += path.stat().st_size

    assets_root = release_root / "assets"
    actual_paths = {
        path.relative_to(release_root).as_posix()
        for path in assets_root.rglob("*")
        if path.is_file()
    }
    unexpected = sorted(actual_paths - expected_paths)
    missing = sorted(expected_paths - actual_paths)
    if unexpected:
        raise ReleaseValidationError(f"unexpected assets not in manifest: {unexpected[:5]}")
    if missing:
        raise ReleaseValidationError(f"manifest assets missing from tree: {missing[:5]}")
    if manifest.get("asset_count") != len(records):
        raise ReleaseValidationError("asset_count does not match manifest records")
    if manifest.get("total_bytes") != total_bytes:
        raise ReleaseValidationError("total_bytes does not match exported assets")

    return {"status": "PASS", "asset_count": len(records), "total_bytes": total_bytes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = validate_release(args.release_root)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
