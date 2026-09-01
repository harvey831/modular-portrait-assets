from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any


LFS_HEADER = b"version https://git-lfs.github.com/spec/v1\n"
CANVAS = [1254, 1254, "RGBA"]
IMAGE_SUFFIXES = {".png", ".webp"}
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
EXPRESSION_PATTERN = r"(?:N00|G0[1-4]|X0[1-3])"

FEATURE_PATH = re.compile(
    rf"^assets/(?P<gender>female|male)/(?P<family>E|M)/"
    rf"(?P<component>[EM]0[1-6])/(?P<skin>S0[1-4])/"
    rf"(?P<expression>{EXPRESSION_PATTERN})/(?P<role>eye_brow|mouth)\.(?:png|webp)$"
)
BASE_PATH = re.compile(
    r"^assets/(?P<gender>female|male)/base/(?P<face>F0[1-5])/"
    r"(?P<skin>S0[1-4])/(?P<filename>[^/]+)\.(?:png|webp)$"
)
EXPRESSION_PATH = re.compile(
    rf"^assets/(?P<gender>female|male)/expression/"
    rf"(?P<face>F0[1-5])_(?P<skin>S0[1-4])_(?P<expression>{EXPRESSION_PATTERN})/"
    rf"(?P<role>face_expression_base|face_expression_head)\.(?:png|webp)$"
)
HAIR_PATH = re.compile(
    r"^assets/(?P<gender>female|male)/hair/(?P<component>H0[1-5])/"
    r"(?P<role>hair_back|hair_front|hair_ear_cover|hair_tint_mask)\.(?:png|webp)$"
)
CLOTHING_PATH = re.compile(
    r"^assets/(?P<gender>female|male)/clothing/(?P<component>C0[1-5])/"
    r"(?P<role>clothing_back|clothing_main|clothing_front|clothing_tint_mask)\.(?:png|webp)$"
)
EFFECT_PATH = re.compile(
    rf"^assets/(?P<gender>female|male)/effects/(?P<effect>blush|sweat)/"
    rf"(?P<face>F0[1-5])_(?P<skin>S0[1-4])_(?P<expression>{EXPRESSION_PATTERN})/"
    rf"(?P<role>blush|sweat|ear_blush_human|ear_blush_elf|ear_sweat_human|ear_sweat_elf)"
    rf"\.(?:png|webp)$"
)
EAR_PATH = re.compile(
    r"^assets/shared/ears/(?P<ear>human|elf)/(?P<face>F01)/(?P<skin>S0[1-4])/"
    r"(?P<filename>F01_S0[1-4]_(?:human|elf)_ear_module)\.(?:png|webp)$"
)


class PagesBuildError(RuntimeError):
    """Raised when a Pages artifact cannot be proven safe and reproducible."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _canonical_digest(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _parsed(
    *,
    gender: str,
    family: str,
    component: str | None = None,
    face: str | None = None,
    skin: str | None = None,
    expression: str | None = None,
    role: str,
    ear: str | None = None,
) -> dict[str, str | None]:
    return {
        "gender": gender,
        "family": family,
        "component": component,
        "face": face,
        "skin": skin,
        "expression": expression,
        "role": role,
        "ear": ear,
    }


def parse_release_path(path: str) -> dict[str, str | None]:
    if not isinstance(path, str) or not path or "\\" in path:
        raise PagesBuildError(f"unsafe release path: {path!r}")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != path:
        raise PagesBuildError(f"unsafe release path: {path}")
    if pure.suffix.casefold() not in IMAGE_SUFFIXES:
        raise PagesBuildError(f"unsupported release asset: {path}")

    match = FEATURE_PATH.fullmatch(path)
    if match:
        fields = match.groupdict()
        expected_prefix = fields["family"]
        expected_role = "eye_brow" if expected_prefix == "E" else "mouth"
        if not fields["component"].startswith(expected_prefix) or fields["role"] != expected_role:
            raise PagesBuildError(f"feature path has mismatched owner: {path}")
        return _parsed(
            gender=fields["gender"],
            family=fields["family"],
            component=fields["component"],
            skin=fields["skin"],
            expression=fields["expression"],
            role=fields["role"],
        )

    match = BASE_PATH.fullmatch(path)
    if match:
        fields = match.groupdict()
        if fields["gender"] == "female":
            prefix = f"{fields['face']}_{fields['skin']}_"
            valid = {
                f"{prefix}earless_head_body_rgba": "earless_head_body",
                f"{prefix}earless_head_rgba": "earless_head",
            }
        else:
            valid = {
                "earless_head_body": "earless_head_body",
                "earless_head": "earless_head",
            }
        role = valid.get(fields["filename"])
        if role is None:
            raise PagesBuildError(f"unknown base owner layer: {path}")
        return _parsed(
            gender=fields["gender"],
            family="base",
            component=fields["face"],
            face=fields["face"],
            skin=fields["skin"],
            role=role,
        )

    match = EXPRESSION_PATH.fullmatch(path)
    if match:
        fields = match.groupdict()
        return _parsed(
            gender=fields["gender"],
            family="expression",
            component=fields["face"],
            face=fields["face"],
            skin=fields["skin"],
            expression=fields["expression"],
            role=fields["role"],
        )

    match = HAIR_PATH.fullmatch(path)
    if match:
        fields = match.groupdict()
        return _parsed(
            gender=fields["gender"],
            family="hair",
            component=fields["component"],
            role=fields["role"],
        )

    match = CLOTHING_PATH.fullmatch(path)
    if match:
        fields = match.groupdict()
        return _parsed(
            gender=fields["gender"],
            family="clothing",
            component=fields["component"],
            role=fields["role"],
        )

    match = EFFECT_PATH.fullmatch(path)
    if match:
        fields = match.groupdict()
        effect_roles = {
            "blush": {"blush", "ear_blush_human", "ear_blush_elf"},
            "sweat": {"sweat", "ear_sweat_human", "ear_sweat_elf"},
        }
        if fields["role"] not in effect_roles[fields["effect"]]:
            raise PagesBuildError(f"effect path has mismatched owner: {path}")
        return _parsed(
            gender=fields["gender"],
            family=fields["effect"],
            component=fields["face"],
            face=fields["face"],
            skin=fields["skin"],
            expression=fields["expression"],
            role=fields["role"],
        )

    match = EAR_PATH.fullmatch(path)
    if match:
        fields = match.groupdict()
        expected_filename = f"{fields['face']}_{fields['skin']}_{fields['ear']}_ear_module"
        if fields["filename"] != expected_filename:
            raise PagesBuildError(f"ear path has mismatched owner: {path}")
        return _parsed(
            gender="shared",
            family="ears",
            component=fields["face"],
            face=fields["face"],
            skin=fields["skin"],
            role="ear_pair",
            ear=fields["ear"],
        )

    raise PagesBuildError(f"unrecognized release asset path: {path}")


def _read_manifest(repo_root: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = repo_root / "provenance" / "asset-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PagesBuildError(f"cannot read release manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), list):
        raise PagesBuildError("release manifest must contain an assets array")
    return manifest_path, manifest


def build_catalog(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    manifest_path, manifest = _read_manifest(root)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entry in manifest["assets"]:
        if not isinstance(entry, dict):
            raise PagesBuildError("release manifest asset must be an object")
        release_path = entry.get("release_path")
        expected_hash = entry.get("sha256")
        expected_bytes = entry.get("bytes")
        if not isinstance(release_path, str) or release_path in seen:
            raise PagesBuildError(f"duplicate or invalid release path: {release_path!r}")
        if not isinstance(expected_hash, str) or not HASH_PATTERN.fullmatch(expected_hash):
            raise PagesBuildError(f"invalid SHA-256 for {release_path}")
        if not isinstance(expected_bytes, int) or isinstance(expected_bytes, bool) or expected_bytes < 0:
            raise PagesBuildError(f"invalid byte count for {release_path}")
        seen.add(release_path)
        records.append(
            {
                "path": release_path,
                "sha256": expected_hash,
                "bytes": expected_bytes,
                **parse_release_path(release_path),
            }
        )

    records.sort(key=lambda record: record["path"])
    asset_count = len(records)
    total_bytes = sum(record["bytes"] for record in records)
    if manifest.get("asset_count") != asset_count:
        raise PagesBuildError("release manifest asset_count does not match assets")
    if manifest.get("total_bytes") != total_bytes:
        raise PagesBuildError("release manifest total_bytes does not match assets")

    catalog = {
        "schema": "modular-portrait-web-catalog-v1",
        "license": "CC0-1.0",
        "source_manifest_sha256": sha256(manifest_path),
        "canvas": list(CANVAS),
        "asset_count": asset_count,
        "total_bytes": total_bytes,
        "assets": records,
    }
    catalog["catalog_sha256"] = _canonical_digest(catalog)
    return catalog


def _safe_join(root: Path, relative: str) -> Path:
    target = (root / Path(relative)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise PagesBuildError(f"path escapes root: {relative}") from exc
    return target


def _checked_asset(repo_root: Path, record: dict[str, Any]) -> Path:
    source = _safe_join(repo_root, record["path"])
    if not source.is_file():
        raise PagesBuildError(f"release asset is missing: {record['path']}")
    with source.open("rb") as stream:
        if stream.read(len(LFS_HEADER)) == LFS_HEADER:
            raise PagesBuildError(f"Git LFS pointer was not resolved: {record['path']}")
    actual_bytes = source.stat().st_size
    if actual_bytes != record["bytes"]:
        raise PagesBuildError(
            f"asset size drift: {record['path']}: expected {record['bytes']}, got {actual_bytes}"
        )
    actual_hash = sha256(source)
    if actual_hash != record["sha256"]:
        raise PagesBuildError(
            f"asset hash drift: {record['path']}: expected {record['sha256']}, got {actual_hash}"
        )
    return source


def _prepare_output(repo_root: Path, output_dir: Path) -> Path:
    root = repo_root.resolve()
    output = output_dir.resolve()
    if output.parent != root or not output.name.startswith(".pages-"):
        raise PagesBuildError("output must be a .pages-* directory directly under the repository root")
    if output.exists():
        if output.is_symlink() or not output.is_dir():
            raise PagesBuildError(f"unsafe existing output target: {output}")
        shutil.rmtree(output)
    output.mkdir()
    return output


def _copy_site_source(site_dir: Path, output_dir: Path) -> None:
    if not site_dir.is_dir():
        raise PagesBuildError(f"site source is missing: {site_dir}")
    for source in sorted(site_dir.rglob("*")):
        if source.is_symlink():
            raise PagesBuildError(f"site source contains a symlink: {source}")
        if not source.is_file():
            continue
        relative = source.relative_to(site_dir)
        if relative.parts[0] == "tests":
            continue
        destination = output_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _write_canonical_json(path: Path, payload: object) -> None:
    path.write_text(
        _canonical_json(payload),
        encoding="utf-8",
        newline="\n",
    )


def build_site(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    catalog = build_catalog(root)
    checked_assets = [
        (record, _checked_asset(root, record)) for record in catalog["assets"]
    ]
    license_path = root / "LICENSE"
    if not license_path.is_file():
        raise PagesBuildError("LICENSE is missing")

    output = _prepare_output(root, output_dir)
    _copy_site_source(root / "site", output)
    for record, source in checked_assets:
        destination = _safe_join(output, record["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    catalog_path = output / "catalog.json"
    _write_canonical_json(catalog_path, catalog)
    (output / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copyfile(license_path, output / "LICENSE")

    summary = {
        "schema": "modular-portrait-pages-build-v1",
        "catalog_sha256": catalog["catalog_sha256"],
        "asset_count": catalog["asset_count"],
        "total_bytes": catalog["total_bytes"],
        "lfs_pointer_count": 0,
        "canvas": list(CANVAS),
    }
    _write_canonical_json(output / "build-summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the validated GitHub Pages artifact.")
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    summary = build_site(args.repo_root, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
