from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image
import numpy as np


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
    def test_offline_cross_skin_binding_cannot_drop_expression_or_effects(self) -> None:
        catalog = render_examples.AssetCatalog(REPO_ROOT)
        for gender in ("female", "male"):
            record = dict(gender=gender, F="F03", S="S04", expression="G02",
                          E="E01", M="M01", H="H01", C="C01", ear="elf")
            layers = render_examples._resolve_layers(catalog, record)
            face = next(layer for layer in layers if layer["role"] == "face_expression_base")
            self.assertIn("paired_delta", face)
            self.assertIn("/S04/", face["path"])
            self.assertIn("F03_S01_G02", face["paired_delta"]["donor"]["path"])
            for role in ("blush", "sweat", "ear_blush", "ear_sweat"):
                effect = next((layer for layer in layers if layer["role"] == role), None)
                self.assertIsNotNone(effect, role)
                if "blush" in role:
                    self.assertIn("paired_delta", effect)
                    self.assertEqual(effect["paired_delta"]["strength"], 0.25)
                    if role == "ear_blush":
                        self.assertIn("shared/ears/elf/F01/S01", effect["paired_delta"]["dry"]["path"])
                else:
                    self.assertNotIn("paired_delta", effect)

    def test_blush_strength_is_independent_of_face_alpha(self) -> None:
        target = Image.fromarray(np.array([[[80, 60, 40, 255]]], dtype=np.uint8))
        dry = Image.fromarray(np.array([[[200, 150, 100, 255]]], dtype=np.uint8))
        overlay = Image.fromarray(np.array([[[200, 75, 50, 128]]], dtype=np.uint8))
        result = render_examples._apply_paired_effect(target, overlay, dry, strength=0.25)
        self.assertEqual(result.getpixel((0, 0)), (80, 51, 34, 255))
        self.assertEqual(target.getpixel((0, 0)), (80, 60, 40, 255))
        for invalid in (-0.1, 1.1, float("nan"), float("inf"), "0.25"):
            with self.assertRaisesRegex(render_examples.ExampleRenderError, "strength"):
                render_examples._apply_paired_effect(target, overlay, dry, strength=invalid)

    def test_paired_delta_keeps_alpha_and_does_not_amplify_small_light_skin_noise(self) -> None:
        self.assertTrue(hasattr(render_examples, "_apply_paired_effect"))
        target = Image.fromarray(np.array([[[70, 50, 30, 123]]], dtype=np.uint8))
        dry = Image.fromarray(np.array([[[253, 251, 249, 123]]], dtype=np.uint8))
        donor = Image.fromarray(np.array([[[254, 252, 250, 123]]], dtype=np.uint8))
        result = render_examples._apply_paired_effect(target, donor, dry, donor=True)
        self.assertEqual(result.getpixel((0, 0)), (71, 51, 31, 123))
        self.assertEqual(target.getpixel((0, 0)), (70, 50, 30, 123))
        donor.putpixel((0, 0), (254, 252, 250, 255))
        with self.assertRaisesRegex(render_examples.ExampleRenderError, "geometry"):
            render_examples._apply_paired_effect(target, donor, dry, donor=True)

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
