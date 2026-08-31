from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "skill" / "modular-portrait-assets" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import export_release  # noqa: E402
import validate_release  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_sha256(files: dict[str, bytes]) -> str:
    records = "".join(
        f"{path}\0{sha256(data)}\n" for path, data in sorted(files.items())
    )
    return hashlib.sha256(records.encode("utf-8")).hexdigest()


def rgba_png(width: int = 1254, height: int = 1254) -> bytes:
    stream = io.BytesIO()
    Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(stream, format="PNG")
    return stream.getvalue()


class ReleaseToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source"
        self.release = self.root / "release"
        self.source.mkdir()
        self.release.mkdir()

    def write_manifest(self, gender: str, approved_authorities: dict) -> Path:
        path = (
            self.source
            / gender
            / "component_library_v1"
            / "_metadata"
            / "current"
            / "authority_manifest.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema": f"{gender}_authority",
                    "status": "ACTIVE_SINGLE_VERSION_MANAGER",
                    "approved_authorities": approved_authorities,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_exports_only_hash_bound_files_and_flattens_revision_path(self) -> None:
        approved = b"approved-image"
        revision = (
            self.source
            / "female"
            / "component_library_v1"
            / "base"
            / "F01"
            / "current"
            / "approved"
            / "r1"
        )
        revision.mkdir(parents=True)
        (revision / "earless_head.png").write_bytes(approved)
        (revision / "unlisted.png").write_bytes(b"must-not-export")
        candidate = (
            self.source
            / "female"
            / "component_library_v1"
            / "base"
            / "F01"
            / "current"
            / "candidates"
            / "bad"
        )
        candidate.mkdir(parents=True)
        (candidate / "candidate.png").write_bytes(b"candidate")

        self.write_manifest(
            "female",
            {
                "base": {
                    "F01": {
                        "path": "base/F01/current/approved/r1",
                        "files_sha256": {"earless_head.png": sha256(approved)},
                    }
                }
            },
        )
        self.write_manifest("male", {})

        result = export_release.build_release(self.source, self.release)

        exported = self.release / "assets" / "female" / "base" / "F01" / "earless_head.png"
        self.assertEqual(exported.read_bytes(), approved)
        self.assertFalse((exported.parent / "unlisted.png").exists())
        self.assertEqual(result["asset_count"], 1)
        self.assertNotIn("current", exported.relative_to(self.release).parts)
        manifest = json.loads(
            (self.release / "provenance" / "asset-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["license"], "CC0-1.0")
        self.assertEqual(manifest["assets"][0]["sha256"], sha256(approved))

    def test_rejects_forbidden_approved_source_path(self) -> None:
        bad = (
            self.source
            / "female"
            / "component_library_v1"
            / "_work_history"
            / "current"
            / "approved"
            / "r1"
        )
        bad.mkdir(parents=True)
        (bad / "asset.png").write_bytes(b"bad")
        self.write_manifest(
            "female",
            {
                "base": {
                    "F01": {
                        "path": "_work_history/current/approved/r1",
                        "files_sha256": {"asset.png": sha256(b"bad")},
                    }
                }
            },
        )
        self.write_manifest("male", {})

        with self.assertRaises(export_release.ReleasePolicyError):
            export_release.build_release(self.source, self.release)

    def test_normalizes_candidate_label_from_approved_public_filename(self) -> None:
        approved = b"approved-ear"
        revision = (
            self.source
            / "female"
            / "component_library_v1"
            / "ears"
            / "elf"
            / "current"
            / "approved"
            / "v03"
            / "F01"
            / "S01"
        )
        revision.mkdir(parents=True)
        source_name = "F01_S01_elf_ear_module_candidate_v1.png"
        (revision / source_name).write_bytes(approved)
        self.write_manifest(
            "female",
            {
                "ears": {
                    "elf": {
                        "path": "ears/elf/current/approved/v03",
                        "tree_sha256": tree_sha256(
                            {f"F01/S01/{source_name}": approved}
                        ),
                    }
                }
            },
        )
        self.write_manifest("male", {})

        export_release.build_release(self.source, self.release)

        public_file = (
            self.release
            / "assets"
            / "shared"
            / "ears"
            / "elf"
            / "F01"
            / "S01"
            / "F01_S01_elf_ear_module.png"
        )
        self.assertEqual(public_file.read_bytes(), approved)
        self.assertFalse((public_file.parent / source_name).exists())
        manifest = json.loads(
            (self.release / "provenance" / "asset-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["assets"][0]["release_path"], public_file.relative_to(self.release).as_posix())
        self.assertIn("candidate_v1", manifest["assets"][0]["source_ref"])

    def test_rejects_hash_mismatch(self) -> None:
        revision = (
            self.source
            / "female"
            / "component_library_v1"
            / "hair"
            / "H01"
            / "current"
            / "approved"
            / "r1"
        )
        revision.mkdir(parents=True)
        (revision / "hair_front.webp").write_bytes(b"actual")
        self.write_manifest(
            "female",
            {
                "hair": {
                    "H01": {
                        "path": "hair/H01/current/approved/r1",
                        "files_sha256": {"hair_front.webp": sha256(b"expected")},
                    }
                }
            },
        )
        self.write_manifest("male", {})

        with self.assertRaises(export_release.ReleasePolicyError):
            export_release.build_release(self.source, self.release)

    def test_exports_shared_female_ears_once_when_male_delegates_absolute_file(self) -> None:
        ear = b"shared-ear"
        ear_file = (
            self.source
            / "female"
            / "component_library_v1"
            / "ears"
            / "human"
            / "current"
            / "approved"
            / "r1"
            / "F01"
            / "S01"
            / "ear.png"
        )
        ear_file.parent.mkdir(parents=True)
        ear_file.write_bytes(ear)
        self.write_manifest(
            "female",
            {
                "ears": {
                    "human": {
                        "path": "ears/human/current/approved/r1",
                        "files_sha256": {"F01/S01/ear.png": sha256(ear)},
                    }
                }
            },
        )
        self.write_manifest(
            "male",
            {
                "ears": {
                    "delegated": {
                        "path": str(ear_file),
                        "sha256": sha256(ear),
                    }
                }
            },
        )

        result = export_release.build_release(self.source, self.release)

        exported = self.release / "assets" / "shared" / "ears" / "human" / "F01" / "S01" / "ear.png"
        self.assertEqual(exported.read_bytes(), ear)
        self.assertEqual(result["asset_count"], 1)

    def test_verifies_but_does_not_export_male_shared_ear_delegation_metadata(self) -> None:
        metadata = b'{"delegate":"female ears"}'
        delegate = (
            self.source
            / "male"
            / "component_library_v1"
            / "ears"
            / "shared"
            / "current"
            / "approved"
            / "delegate-v1"
        )
        delegate.mkdir(parents=True)
        (delegate / "manifest.json").write_bytes(metadata)
        self.write_manifest("female", {})
        self.write_manifest(
            "male",
            {
                "ears": {
                    "shared": {
                        "path": "ears/shared/current/approved/delegate-v1",
                        "tree_sha256": tree_sha256({"manifest.json": metadata}),
                    }
                }
            },
        )

        result = export_release.build_release(self.source, self.release)

        self.assertEqual(result["asset_count"], 0)
        self.assertFalse((self.release / "assets").exists())

    def test_validator_detects_tampering_and_unexpected_assets(self) -> None:
        approved = rgba_png()
        revision = (
            self.source
            / "female"
            / "component_library_v1"
            / "base"
            / "F01"
            / "current"
            / "approved"
            / "r1"
        )
        revision.mkdir(parents=True)
        (revision / "base.png").write_bytes(approved)
        self.write_manifest(
            "female",
            {
                "base": {
                    "F01": {
                        "path": "base/F01/current/approved/r1",
                        "files_sha256": {"base.png": sha256(approved)},
                    }
                }
            },
        )
        self.write_manifest("male", {})
        export_release.build_release(self.source, self.release)
        self.assertEqual(validate_release.validate_release(self.release)["status"], "PASS")

        exported = self.release / "assets" / "female" / "base" / "F01" / "base.png"
        exported.write_bytes(b"tampered")
        with self.assertRaises(validate_release.ReleaseValidationError):
            validate_release.validate_release(self.release)

        exported.write_bytes(approved)
        (exported.parent / "unexpected.png").write_bytes(b"unexpected")
        with self.assertRaises(validate_release.ReleaseValidationError):
            validate_release.validate_release(self.release)

    def test_validator_rejects_wrong_canvas_dimensions(self) -> None:
        wrong_size = rgba_png(32, 32)
        revision = (
            self.source
            / "female"
            / "component_library_v1"
            / "base"
            / "F01"
            / "current"
            / "approved"
            / "r1"
        )
        revision.mkdir(parents=True)
        (revision / "base.png").write_bytes(wrong_size)
        self.write_manifest(
            "female",
            {
                "base": {
                    "F01": {
                        "path": "base/F01/current/approved/r1",
                        "files_sha256": {"base.png": sha256(wrong_size)},
                    }
                }
            },
        )
        self.write_manifest("male", {})
        export_release.build_release(self.source, self.release)

        with self.assertRaises(validate_release.ReleaseValidationError):
            validate_release.validate_release(self.release)

    def test_validator_rejects_candidate_label_in_public_filename(self) -> None:
        approved = rgba_png()
        revision = (
            self.source
            / "female"
            / "component_library_v1"
            / "base"
            / "F01"
            / "current"
            / "approved"
            / "r1"
        )
        revision.mkdir(parents=True)
        (revision / "base.png").write_bytes(approved)
        self.write_manifest(
            "female",
            {
                "base": {
                    "F01": {
                        "path": "base/F01/current/approved/r1",
                        "files_sha256": {"base.png": sha256(approved)},
                    }
                }
            },
        )
        self.write_manifest("male", {})
        export_release.build_release(self.source, self.release)

        original = self.release / "assets" / "female" / "base" / "F01" / "base.png"
        candidate = original.with_name("base_candidate_v1.png")
        original.rename(candidate)
        manifest_path = self.release / "provenance" / "asset-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["assets"][0]["release_path"] = candidate.relative_to(self.release).as_posix()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaises(validate_release.ReleaseValidationError):
            validate_release.validate_release(self.release)


if __name__ == "__main__":
    unittest.main()
