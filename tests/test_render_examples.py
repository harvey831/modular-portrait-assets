from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import render_examples  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RenderExamplesTests(unittest.TestCase):
    def test_default_plan_is_balanced_unique_and_covers_current_lanes(self) -> None:
        plan = render_examples.build_plan(REPO_ROOT)
        records = plan["mixed_qc"]["records"]

        self.assertEqual(len(records), 48)
        self.assertEqual(
            {gender: sum(r["gender"] == gender for r in records) for gender in ("female", "male")},
            {"female": 24, "male": 24},
        )
        tuples = {
            (
                r["gender"],
                r["F"],
                r["S"],
                r["expression"],
                r["E"],
                r["M"],
                r["H"],
                r["C"],
                r["ear"],
                r["hair_hue"],
            )
            for r in records
        }
        self.assertEqual(len(tuples), 48)
        self.assertEqual(
            {r["expression"] for r in records if r["gender"] == "female"},
            {"N00", "G01", "G02", "G03", "G04", "X01", "X02", "X03"},
        )
        self.assertEqual(
            {r["expression"] for r in records if r["gender"] == "male"},
            {"N00", "G01", "G02", "G03", "G04"},
        )
        self.assertEqual(
            {r["H"] for r in records if r["gender"] == "female"},
            {"H01", "H02", "H03", "H04", "H05"},
        )
        self.assertEqual(
            {r["H"] for r in records if r["gender"] == "male"},
            {"H01", "H02", "H04"},
        )

    def test_expression_showcase_changes_only_expression_within_each_gender(self) -> None:
        plan = render_examples.build_plan(REPO_ROOT)
        records = plan["expression_showcase"]["records"]
        identity_keys = ("F", "S", "E", "M", "H", "C", "ear", "hair_hue")

        female = [r for r in records if r["gender"] == "female"]
        male = [r for r in records if r["gender"] == "male"]
        self.assertEqual([r["expression"] for r in female], ["N00", "G01", "G02", "G03", "G04", "X01", "X02", "X03"])
        self.assertEqual([r["expression"] for r in male], ["N00", "G01", "G02", "G03", "G04"])
        self.assertEqual(len({tuple(r[key] for key in identity_keys) for r in female}), 1)
        self.assertEqual(len({tuple(r[key] for key in identity_keys) for r in male}), 1)

    def test_composite_is_repeatable_registered_rgba(self) -> None:
        record = render_examples.build_plan(REPO_ROOT)["mixed_qc"]["records"][0]

        first, first_layers = render_examples.compose_record(REPO_ROOT, record)
        second, second_layers = render_examples.compose_record(REPO_ROOT, record)

        self.assertEqual(first.mode, "RGBA")
        self.assertEqual(first.size, (1254, 1254))
        self.assertIsNotNone(first.getchannel("A").getbbox())
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(first_layers, second_layers)
        self.assertGreaterEqual(len(first_layers), 9)

    def test_rendered_examples_match_declared_dimensions_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            result = render_examples.render_examples(REPO_ROOT, output)

            mixed = output / "mixed-character-qc-48.webp"
            expressions = output / "expression-showcase.png"
            manifest_path = output / "manifest.json"
            self.assertEqual(result["mixed_cells"], 48)
            self.assertEqual(result["expression_cells"], 13)
            with Image.open(mixed) as image:
                self.assertEqual((image.format, image.mode, image.size), ("WEBP", "RGB", (3072, 3968)))
            with Image.open(expressions) as image:
                self.assertEqual((image.format, image.mode, image.size), ("PNG", "RGB", (2048, 2048)))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["generation_backend"], "deterministic-alpha-composition")
            self.assertEqual(manifest["outputs"]["mixed-character-qc-48.webp"]["sha256"], sha256(mixed))
            self.assertEqual(manifest["outputs"]["expression-showcase.png"]["sha256"], sha256(expressions))


if __name__ == "__main__":
    unittest.main()
