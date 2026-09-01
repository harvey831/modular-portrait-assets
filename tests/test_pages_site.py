from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import build_pages_site  # noqa: E402


LFS_HEADER = b"version https://git-lfs.github.com/spec/v1\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class PagesFixture:
    root: Path
    output_a: Path
    output_b: Path
    asset_path: Path


class PagesCatalogTests(unittest.TestCase):
    def test_parses_eye_mouth_hair_and_shared_ear_paths(self) -> None:
        self.assertEqual(
            build_pages_site.parse_release_path(
                "assets/female/E/E04/S02/G03/eye_brow.png"
            ),
            {
                "gender": "female",
                "family": "E",
                "component": "E04",
                "face": None,
                "skin": "S02",
                "expression": "G03",
                "role": "eye_brow",
                "ear": None,
            },
        )
        self.assertEqual(
            build_pages_site.parse_release_path(
                "assets/male/M/M06/S04/N00/mouth.webp"
            ),
            {
                "gender": "male",
                "family": "M",
                "component": "M06",
                "face": None,
                "skin": "S04",
                "expression": "N00",
                "role": "mouth",
                "ear": None,
            },
        )
        self.assertEqual(
            build_pages_site.parse_release_path(
                "assets/female/hair/H02/hair_ear_cover.png"
            )["role"],
            "hair_ear_cover",
        )
        self.assertEqual(
            build_pages_site.parse_release_path(
                "assets/female/effects/blush/F01_S01_G01/ear_blush_elf.png"
            )["role"],
            "ear_blush_elf",
        )
        self.assertEqual(
            build_pages_site.parse_release_path(
                "assets/shared/ears/elf/F01/S04/F01_S04_elf_ear_module.png"
            ),
            {
                "gender": "shared",
                "family": "ears",
                "component": "F01",
                "face": "F01",
                "skin": "S04",
                "expression": None,
                "role": "ear_pair",
                "ear": "elf",
            },
        )

    def test_parser_rejects_unknown_filename_and_unsafe_path(self) -> None:
        for path in (
            "assets/female/E/E01/S01/N00/not-an-eye.png",
            "assets/female/hair/H01/extra-layer.png",
            "assets/../private.png",
            "C:/private/asset.png",
        ):
            with self.subTest(path=path):
                with self.assertRaises(build_pages_site.PagesBuildError):
                    build_pages_site.parse_release_path(path)

    def test_actual_catalog_contains_all_hash_bound_assets(self) -> None:
        catalog = build_pages_site.build_catalog(REPO_ROOT)
        self.assertEqual(len(catalog["assets"]), 1184)
        self.assertEqual(catalog["canvas"], [1254, 1254, "RGBA"])
        self.assertEqual(catalog["asset_count"], 1184)
        self.assertEqual(catalog["total_bytes"], 183498531)
        self.assertRegex(catalog["catalog_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(
            catalog["catalog_sha256"], catalog["source_manifest_sha256"]
        )
        encoded = json.dumps(catalog)
        self.assertNotIn("source_ref", encoded)
        self.assertNotIn("source_authority", encoded)
        self.assertTrue(all(len(asset["sha256"]) == 64 for asset in catalog["assets"]))


class PagesArtifactTests(unittest.TestCase):
    def make_fixture(self, corrupt_mode: str | None = None) -> PagesFixture:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        (root / "site").mkdir()
        (root / "site" / "index.html").write_text(
            "<!doctype html><title>Fixture</title>", encoding="utf-8"
        )
        (root / "LICENSE").write_text("CC0-1.0", encoding="utf-8")

        asset_path = Path("assets/female/E/E01/S01/N00/eye_brow.png")
        released = b"resolved-image-bytes"
        stored = released
        expected_hash = sha256(released)
        release_path = asset_path.as_posix()
        if corrupt_mode == "lfs-pointer":
            stored = LFS_HEADER + b"oid sha256:abc\nsize 123\n"
            expected_hash = sha256(stored)
        elif corrupt_mode == "hash-drift":
            stored = b"changed-image-bytes"
        elif corrupt_mode == "traversal":
            release_path = "../outside.png"

        target = root / asset_path
        target.parent.mkdir(parents=True)
        target.write_bytes(stored)
        manifest = {
            "schema": "modular-portrait-assets-cc0-v1",
            "license": "CC0-1.0",
            "asset_count": 1,
            "total_bytes": len(released),
            "assets": [
                {
                    "release_path": release_path,
                    "sha256": expected_hash,
                    "bytes": len(stored),
                    "source_authority": "female",
                    "source_ref": "private/source/that/must/not/ship.png",
                }
            ],
        }
        provenance = root / "provenance"
        provenance.mkdir()
        (provenance / "asset-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return PagesFixture(
            root=root,
            output_a=root / ".pages-a",
            output_b=root / ".pages-b",
            asset_path=asset_path,
        )

    def test_build_rejects_lfs_pointer_hash_drift_and_path_traversal(self) -> None:
        for corrupt_mode in ("lfs-pointer", "hash-drift", "traversal"):
            with self.subTest(corrupt_mode=corrupt_mode):
                fixture = self.make_fixture(corrupt_mode=corrupt_mode)
                with self.assertRaises(build_pages_site.PagesBuildError):
                    build_pages_site.build_site(fixture.root, fixture.output_a)

    def test_build_copies_resolved_assets_and_is_deterministic(self) -> None:
        fixture = self.make_fixture()
        first = build_pages_site.build_site(fixture.root, fixture.output_a)
        second = build_pages_site.build_site(fixture.root, fixture.output_b)

        self.assertEqual(first["catalog_sha256"], second["catalog_sha256"])
        published_catalog = json.loads(
            (fixture.output_a / "catalog.json").read_text(encoding="utf-8")
        )
        self.assertEqual(first["catalog_sha256"], published_catalog["catalog_sha256"])
        self.assertEqual(first["asset_count"], 1)
        self.assertEqual(first["lfs_pointer_count"], 0)
        copied = (fixture.output_a / fixture.asset_path).read_bytes()
        self.assertEqual(copied, b"resolved-image-bytes")
        self.assertFalse(copied.startswith(LFS_HEADER))
        self.assertTrue((fixture.output_a / ".nojekyll").is_file())
        self.assertTrue((fixture.output_a / "catalog.json").is_file())
        self.assertTrue((fixture.output_a / "build-summary.json").is_file())
        self.assertTrue((fixture.output_a / "LICENSE").is_file())
        self.assertNotIn(
            "private/source",
            (fixture.output_a / "catalog.json").read_text(encoding="utf-8"),
        )

    def test_build_refuses_to_use_repository_root_as_output(self) -> None:
        fixture = self.make_fixture()
        with self.assertRaises(build_pages_site.PagesBuildError):
            build_pages_site.build_site(fixture.root, fixture.root)

    def test_build_excludes_site_test_sources_from_public_artifact(self) -> None:
        fixture = self.make_fixture()
        test_source = fixture.root / "site" / "tests" / "dev-only.test.mjs"
        test_source.parent.mkdir()
        test_source.write_text("throw new Error('not public')", encoding="utf-8")
        build_pages_site.build_site(fixture.root, fixture.output_a)
        self.assertFalse((fixture.output_a / "tests").exists())


class HtmlProbe(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.feed(html)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.elements.append((tag, dict(attrs)))

    def by_id(self, element_id: str) -> tuple[str, dict[str, str | None]]:
        try:
            return next(
                item for item in self.elements if item[1].get("id") == element_id
            )
        except StopIteration as exc:
            raise AssertionError(f"missing element #{element_id}") from exc

    def canvas_size(self, element_id: str) -> tuple[int, int]:
        tag, attrs = self.by_id(element_id)
        if tag != "canvas":
            raise AssertionError(f"{element_id} is not a canvas")
        return int(attrs["width"]), int(attrs["height"])

    def has_live_region(self, element_id: str) -> bool:
        return self.by_id(element_id)[1].get("aria-live") in {
            "polite",
            "assertive",
        }

    def interactive_ids(self) -> set[str]:
        interactive = {"button", "input", "select", "textarea"}
        return {
            attrs["id"]
            for tag, attrs in self.elements
            if tag in interactive and attrs.get("id")
        }

    def label_targets(self) -> set[str]:
        return {
            attrs["for"]
            for tag, attrs in self.elements
            if tag == "label" and attrs.get("for")
        }


class PagesShellTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html_path = REPO_ROOT / "site" / "index.html"
        self.styles_path = REPO_ROOT / "site" / "styles.css"

    def test_site_shell_has_required_accessible_controls(self) -> None:
        document = HtmlProbe(self.html_path.read_text(encoding="utf-8"))
        self.assertEqual(document.canvas_size("portrait-canvas"), (1254, 1254))
        self.assertTrue(document.has_live_region("status"))
        required = {
            "language",
            "gender",
            "face",
            "skin",
            "ear",
            "expression",
            "eyes",
            "mouth",
            "extended",
            "hair",
            "hair-hue",
            "clothing",
            "randomize",
            "reset",
            "download",
            "copy-recipe",
        }
        self.assertTrue(
            required.issubset(document.interactive_ids()),
            required - document.interactive_ids(),
        )
        labelled = required - {"randomize", "reset", "download", "copy-recipe"}
        self.assertTrue(
            labelled.issubset(document.label_targets()),
            labelled - document.label_targets(),
        )

    def test_site_shell_uses_local_assets_and_module_bootstrap(self) -> None:
        html = self.html_path.read_text(encoding="utf-8")
        styles = self.styles_path.read_text(encoding="utf-8")
        self.assertIn('type="module" src="./app.mjs"', html)
        self.assertIn('rel="stylesheet" href="./styles.css"', html)
        self.assertIn('rel="icon" href="data:image/svg+xml,', html)
        self.assertIn('http-equiv="Content-Security-Policy"', html)
        self.assertIn("object-src 'none'", html)
        self.assertNotRegex(html, r"https://(?:fonts|cdn|www\.google-analytics)")
        self.assertNotIn("@import", styles)
        self.assertIn("@media (max-width: 860px)", styles)
        self.assertIn("prefers-reduced-motion: reduce", styles)
        self.assertIn(":focus-visible", styles)
        self.assertNotRegex(html, r"\son[a-z]+=")


if __name__ == "__main__":
    unittest.main()
