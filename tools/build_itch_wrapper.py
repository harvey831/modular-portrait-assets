from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from build_pages_site import build_catalog


TARGET_URL = "https://harvey831.github.io/modular-portrait-assets/"
ARCHIVE_FILE_COUNT = 3
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class ItchWrapperError(RuntimeError):
    pass


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _index_html() -> bytes:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Modular Portrait Mixer</title>
  <style>
    html, body {{ width: 100%; height: 100%; margin: 0; background: #121016; overflow: hidden; }}
    iframe {{ display: block; width: 100%; height: 100%; border: 0; }}
  </style>
</head>
<body>
  <iframe
    src="{TARGET_URL}"
    title="Modular Portrait Mixer"
    allow="clipboard-write; fullscreen"
    allowfullscreen
    loading="eager"
    referrerpolicy="strict-origin-when-cross-origin"
  ></iframe>
  <noscript><a href="{TARGET_URL}">Open Modular Portrait Mixer</a></noscript>
</body>
</html>
""".encode("utf-8")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def build_wrapper(repo_root: Path | str, output_zip: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    output = Path(output_zip).resolve()
    if output.suffix.casefold() != ".zip":
        raise ItchWrapperError("itch wrapper output must be a .zip file")
    if output.exists() and not output.is_file():
        raise ItchWrapperError("itch wrapper output must not be a directory")

    license_path = root / "LICENSE"
    if not license_path.is_file():
        raise ItchWrapperError("LICENSE is missing")
    catalog = build_catalog(root)
    summary = {
        "schema": "modular-portrait-itch-wrapper-v1",
        "archive_file_count": ARCHIVE_FILE_COUNT,
        "target_url": TARGET_URL,
        "source_catalog_sha256": catalog["catalog_sha256"],
        "source_asset_count": catalog["asset_count"],
        "source_total_bytes": catalog["total_bytes"],
    }
    entries = {
        "LICENSE": license_path.read_bytes(),
        "build-summary.json": _canonical_json(summary),
        "index.html": _index_html(),
    }
    if len(entries) != ARCHIVE_FILE_COUNT:
        raise ItchWrapperError("itch wrapper file count contract drifted")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        with zipfile.ZipFile(
            temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for name in sorted(entries):
                archive.writestr(_zip_info(name), entries[name], compresslevel=9)
        os.replace(temporary_path, output)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic itch.io wrapper for the GitHub Pages app."
    )
    parser.add_argument("repo_root", type=Path)
    parser.add_argument("output_zip", type=Path)
    args = parser.parse_args()
    summary = build_wrapper(args.repo_root, args.output_zip)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
