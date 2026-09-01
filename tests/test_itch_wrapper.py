from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from hashlib import sha256
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import build_itch_wrapper  # noqa: E402


class ItchWrapperBuildTests(unittest.TestCase):
    def make_release(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        (root / "LICENSE").write_text("CC0-1.0\n", encoding="utf-8")
        provenance = root / "provenance"
        provenance.mkdir()
        payload = b"fixture-image"
        manifest = {
            "schema": "modular-portrait-assets-cc0-v1",
            "license": "CC0-1.0",
            "asset_count": 1,
            "total_bytes": len(payload),
            "assets": [
                {
                    "release_path": "assets/female/E/E01/S01/N00/eye_brow.png",
                    "sha256": sha256(payload).hexdigest(),
                    "bytes": len(payload),
                }
            ],
        }
        (provenance / "asset-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return root

    def test_builds_deterministic_sub_1000_file_wrapper_for_github_pages(self) -> None:
        root = self.make_release()
        first = root / "first.zip"
        second = root / "second.zip"

        first_summary = build_itch_wrapper.build_wrapper(root, first)
        second_summary = build_itch_wrapper.build_wrapper(root, second)

        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first_summary, second_summary)
        self.assertLessEqual(first_summary["archive_file_count"], 1000)
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(
                archive.namelist(), ["LICENSE", "build-summary.json", "index.html"]
            )
            index = archive.read("index.html").decode("utf-8")
            packaged_summary = json.loads(archive.read("build-summary.json"))

        self.assertIn(
            'src="https://harvey831.github.io/modular-portrait-assets/"', index
        )
        self.assertIn('title="Modular Portrait Mixer"', index)
        self.assertIn("allowfullscreen", index)
        self.assertEqual(
            packaged_summary["target_url"],
            "https://harvey831.github.io/modular-portrait-assets/",
        )
        self.assertEqual(packaged_summary, first_summary)

    def test_refuses_to_overwrite_a_directory_or_non_zip_target(self) -> None:
        root = self.make_release()
        directory_target = root / "wrapper.zip"
        directory_target.mkdir()

        with self.assertRaises(build_itch_wrapper.ItchWrapperError):
            build_itch_wrapper.build_wrapper(root, directory_target)
        with self.assertRaises(build_itch_wrapper.ItchWrapperError):
            build_itch_wrapper.build_wrapper(root, root / "wrapper.bin")

    def test_cli_runs_with_an_embedded_python_runtime(self) -> None:
        root = self.make_release()
        output = root / "wrapper.zip"

        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS_DIR / "build_itch_wrapper.py"),
                str(root),
                str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"},
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(output.is_file())
        self.assertEqual(json.loads(completed.stdout)["archive_file_count"], 3)


if __name__ == "__main__":
    unittest.main()
