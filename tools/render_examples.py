#!/usr/bin/env python3
"""Render deterministic public QC examples from the release manifest.

No generative model is called. Every portrait is ordinary alpha composition
of hash-bound files already present in ``assets/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFont


MASTER_SEED = 3186449067
CANVAS = (1254, 1254)
MIXED_GENDER_COUNTS = {"female": 24, "male": 24}
CURRENT_HAIRS = {
    "female": ("H01", "H02", "H03", "H04", "H05"),
    "male": ("H01", "H02", "H04"),
}
EXPRESSIONS = {
    "female": ("N00", "G01", "G02", "G03", "G04", "X01", "X02", "X03"),
    "male": ("N00", "G01", "G02", "G03", "G04"),
}
FACES = ("F01", "F02", "F03", "F04", "F05")
SKINS = ("S01", "S02", "S03", "S04")
EYES = ("E01", "E02", "E03", "E04", "E05", "E06")
MOUTHS = ("M01", "M02", "M03", "M04", "M05", "M06")
CLOTHING = ("C01", "C02", "C03", "C04", "C05")
EARS = ("human", "elf")
ALLOWED_IMAGE_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg"}
HAIR_ROLES = {"hair_back", "hair_front", "hair_ear_cover"}

MIXED_COLUMNS = 6
MIXED_ROWS = 8
MIXED_CELL_WIDTH = 512
MIXED_CELL_HEIGHT = 496
MIXED_PREVIEW_SIZE = 430

EXPRESSION_COLUMNS = 4
EXPRESSION_ROWS = 4
EXPRESSION_HEADER = 128
EXPRESSION_CELL_WIDTH = 512
EXPRESSION_CELL_HEIGHT = 480
EXPRESSION_PREVIEW_SIZE = 400

PALETTE_ALGORITHM = "oklch-five-anchor-darker-per-character-random-v06"
TONE_POLICY = {
    "shadow_lightness": [0.14, 0.30],
    "midtone_lightness": [0.32, 0.52],
    "highlight_lightness": [0.52, 0.70],
    "specular_lightness_ceiling": 0.74,
    "terminal_anchor": "same-hue-coloured-specular-never-pure-white",
}


class ExampleRenderError(RuntimeError):
    """Raised when an example cannot be reproduced from the public release."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _linear_to_srgb(value: float) -> float:
    if value <= 0.0031308:
        return 12.92 * value
    return 1.055 * (value ** (1.0 / 2.4)) - 0.055


def _oklch_to_srgb8(
    lightness: float,
    chroma: float,
    hue_degrees: float,
) -> tuple[int, int, int]:
    hue = math.radians(hue_degrees)
    a = chroma * math.cos(hue)
    b = chroma * math.sin(hue)
    l_root = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_root = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_root = lightness - 0.0894841775 * a - 1.2914855480 * b
    l_value, m_value, s_value = l_root**3, m_root**3, s_root**3
    linear = (
        4.0767416621 * l_value - 3.3077115913 * m_value + 0.2309699292 * s_value,
        -1.2684380046 * l_value + 2.6097574011 * m_value - 0.3413193965 * s_value,
        -0.0041960863 * l_value - 0.7034186147 * m_value + 1.7076147010 * s_value,
    )
    return tuple(
        max(0, min(255, round(_linear_to_srgb(channel) * 255.0)))
        for channel in linear
    )


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in rgb)


def _stop(lightness: float, chroma: float, hue: int) -> dict[str, object]:
    rgb = _oklch_to_srgb8(lightness, chroma, hue)
    return {
        "oklch": [lightness, chroma, hue],
        "srgb8": list(rgb),
        "hex": _hex(rgb),
    }


def _record_palette_seed(master_seed: int, gender: str, owner_key: str) -> int:
    payload = f"{master_seed}:{gender}:{owner_key}:per-character-palette-v05"
    return int.from_bytes(hashlib.sha256(payload.encode("ascii")).digest()[:8], "big")


def derive_palette(master_seed: int, gender: str, owner_key: str) -> dict[str, Any]:
    record_seed = _record_palette_seed(master_seed, gender, owner_key)
    rng = random.Random(record_seed)
    hue = rng.randrange(360)
    midtone_lightness = round(rng.uniform(0.38, 0.68), 3)
    midtone_chroma = round(rng.uniform(0.07, 0.20), 3)
    shadow_lightness = round(
        max(0.16, midtone_lightness - rng.uniform(0.16, 0.25)), 3
    )
    highlight_lightness = round(
        min(0.88, midtone_lightness + rng.uniform(0.18, 0.28)), 3
    )
    shadow_chroma = round(midtone_chroma * rng.uniform(0.45, 0.75), 3)
    highlight_chroma = round(midtone_chroma * rng.uniform(0.35, 0.60), 3)

    dark_shadow_l = round(max(0.14, min(0.30, shadow_lightness - 0.08)), 3)
    dark_midtone_l = round(max(0.32, min(0.52, midtone_lightness - 0.12)), 3)
    dark_highlight_l = round(max(0.52, min(0.70, highlight_lightness - 0.16)), 3)
    dark_highlight_c = round(max(highlight_chroma, midtone_chroma * 0.65), 3)
    specular_l = round(min(0.74, dark_highlight_l + 0.04), 3)
    specular_c = round(max(dark_highlight_c * 0.90, midtone_chroma * 0.55), 3)
    stops = {
        "shadow": _stop(dark_shadow_l, shadow_chroma, hue),
        "midtone": _stop(dark_midtone_l, midtone_chroma, hue),
        "highlight": _stop(dark_highlight_l, dark_highlight_c, hue),
        "specular": _stop(specular_l, specular_c, hue),
    }
    canonical = {
        "algorithm_revision": PALETTE_ALGORITHM,
        "master_seed": master_seed,
        "record_seed": record_seed,
        "gender": gender,
        "owner_key": owner_key,
        "hue_degrees": hue,
        "tone_policy": TONE_POLICY,
        "stops": stops,
    }
    return {
        **canonical,
        "shadow_hex": stops["shadow"]["hex"],
        "midtone_hex": stops["midtone"]["hex"],
        "highlight_hex": stops["highlight"]["hex"],
        "specular_hex": stops["specular"]["hex"],
        "palette_digest": _canonical_digest(canonical),
    }


def _balanced_assignments(values: Iterable[str], target: int, rng: random.Random) -> list[str]:
    values = list(values)
    assignments = [values[index % len(values)] for index in range(target)]
    rng.shuffle(assignments)
    return assignments


def _expression_assignments(gender: str, rng: random.Random) -> list[str]:
    expressions = list(EXPRESSIONS[gender])
    target = MIXED_GENDER_COUNTS[gender]
    assignments: list[str] = []
    while len(assignments) < target:
        cycle = expressions.copy()
        rng.shuffle(cycle)
        assignments.extend(cycle)
    assignments = assignments[:target]
    rng.shuffle(assignments)
    return assignments


def _plan_gender(gender: str, master_seed: int) -> list[dict[str, Any]]:
    rng = random.Random(f"{master_seed}:{gender}:combined-random-qc-v01")
    expressions = _expression_assignments(gender, rng)
    hairs = _balanced_assignments(
        CURRENT_HAIRS[gender], MIXED_GENDER_COUNTS[gender], rng
    )
    used: set[tuple[str, ...]] = set()
    records: list[dict[str, Any]] = []
    for index, (expression, hair) in enumerate(zip(expressions, hairs, strict=True), 1):
        for _attempt in range(1000):
            skin = rng.choice(SKINS)
            sparse_female_lane = gender == "female" and skin != "S01" and expression != "N00"
            selection = {
                "gender": gender,
                "F": rng.choice(FACES),
                "S": skin,
                "expression": expression,
                "E": "E01" if sparse_female_lane else rng.choice(EYES),
                "M": "M01" if sparse_female_lane else rng.choice(MOUTHS),
                "H": hair,
                "C": rng.choice(CLOTHING),
                "ear": rng.choice(EARS),
            }
            key = tuple(str(selection[field]) for field in selection)
            if key in used:
                continue
            used.add(key)
            record_id = f"{gender}_random_{index:03d}"
            palette = derive_palette(
                master_seed, gender, f"combined-cell:{record_id}"
            )
            records.append(
                {
                    "record_id": record_id,
                    **selection,
                    "hair_hue": palette["hue_degrees"],
                    "palette": palette,
                }
            )
            break
        else:
            raise ExampleRenderError(f"could not derive unique record {gender}/{index}")
    return records


def _showcase_records(master_seed: int) -> list[dict[str, Any]]:
    identities = {
        "female": {
            "F": "F03", "S": "S01", "E": "E04", "M": "M03",
            "H": "H05", "C": "C02", "ear": "elf",
        },
        "male": {
            "F": "F02", "S": "S01", "E": "E03", "M": "M04",
            "H": "H04", "C": "C02", "ear": "human",
        },
    }
    records: list[dict[str, Any]] = []
    for gender in ("female", "male"):
        palette = derive_palette(
            master_seed, gender, f"expression-showcase:{gender}"
        )
        for expression in EXPRESSIONS[gender]:
            records.append(
                {
                    "record_id": f"{gender}_showcase_{expression}",
                    "gender": gender,
                    **identities[gender],
                    "expression": expression,
                    "hair_hue": palette["hue_degrees"],
                    "palette": palette,
                }
            )
    return records


def _validate_plan(records: list[dict[str, Any]]) -> None:
    if len(records) != 48:
        raise ExampleRenderError(f"mixed record count must be 48, got {len(records)}")
    genders = Counter(record["gender"] for record in records)
    if dict(genders) != MIXED_GENDER_COUNTS:
        raise ExampleRenderError(f"gender balance drift: {dict(genders)}")
    complete = {
        tuple(
            str(record[field])
            for field in ("gender", "F", "S", "expression", "E", "M", "H", "C", "ear", "hair_hue")
        )
        for record in records
    }
    if len(complete) != 48:
        raise ExampleRenderError("mixed records are not unique")
    for gender in ("female", "male"):
        selected = [record for record in records if record["gender"] == gender]
        if {record["expression"] for record in selected} != set(EXPRESSIONS[gender]):
            raise ExampleRenderError(f"{gender} expression coverage drift")
        if {record["H"] for record in selected} != set(CURRENT_HAIRS[gender]):
            raise ExampleRenderError(f"{gender} hair coverage drift")


def build_plan(repo_root: Path | str, master_seed: int = MASTER_SEED) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    if not (repo_root / "provenance" / "asset-manifest.json").is_file():
        raise ExampleRenderError(f"release manifest is missing: {repo_root}")
    mixed = [*_plan_gender("female", master_seed), *_plan_gender("male", master_seed)]
    random.Random(f"{master_seed}:cross-gender-grid-order-v01").shuffle(mixed)
    _validate_plan(mixed)
    return {
        "schema": "modular-portrait-public-example-plan-v1",
        "master_seed": master_seed,
        "mixed_qc": {"columns": 6, "rows": 8, "records": mixed},
        "expression_showcase": {"columns": 4, "rows": 4, "records": _showcase_records(master_seed)},
    }


class AssetCatalog:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        manifest_path = self.repo_root / "provenance" / "asset-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.hashes = {
            str(record["release_path"]): str(record["sha256"]).lower()
            for record in manifest["assets"]
        }
        self._verified: set[str] = set()

    def find(self, parent: Path | str, stem: str, *, optional: bool = False) -> str | None:
        parent_text = Path(parent).as_posix().rstrip("/")
        matches = [
            relative
            for relative in self.hashes
            if Path(relative).parent.as_posix() == parent_text
            and Path(relative).stem.casefold() == stem.casefold()
            and Path(relative).suffix.casefold() in ALLOWED_IMAGE_SUFFIXES
        ]
        if not matches and optional:
            return None
        if len(matches) != 1:
            raise ExampleRenderError(
                f"expected one public asset for {parent_text}/{stem}, got {matches}"
            )
        return matches[0]

    def only_file(self, parent: Path | str) -> str:
        parent_text = Path(parent).as_posix().rstrip("/")
        matches = [
            relative
            for relative in self.hashes
            if Path(relative).parent.as_posix() == parent_text
            and Path(relative).suffix.casefold() in ALLOWED_IMAGE_SUFFIXES
        ]
        if len(matches) != 1:
            raise ExampleRenderError(f"expected one public asset under {parent_text}, got {matches}")
        return matches[0]

    def load(self, relative: str) -> Image.Image:
        expected = self.hashes.get(relative)
        if expected is None:
            raise ExampleRenderError(f"asset is not in release manifest: {relative}")
        path = (self.repo_root / Path(relative)).resolve()
        try:
            path.relative_to(self.repo_root)
        except ValueError as exc:
            raise ExampleRenderError(f"asset escapes release root: {relative}") from exc
        if relative not in self._verified:
            actual = sha256(path)
            if actual != expected:
                raise ExampleRenderError(
                    f"asset hash drift: {relative}: expected {expected}, got {actual}"
                )
            self._verified.add(relative)
        with Image.open(path) as source:
            image = source.convert("RGBA")
        if image.size != CANVAS:
            raise ExampleRenderError(f"asset canvas drift: {relative}: {image.size}")
        return image


def _binding(catalog: AssetCatalog, role: str, relative: str, tint_mask: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": role,
        "path": relative,
        "sha256": catalog.hashes[relative],
    }
    if tint_mask:
        payload["tint_mask"] = {
            "path": tint_mask,
            "sha256": catalog.hashes[tint_mask],
        }
    return payload


def _resolve_layers(catalog: AssetCatalog, record: dict[str, Any]) -> list[dict[str, Any]]:
    gender = str(record["gender"])
    face, skin, expression = str(record["F"]), str(record["S"]), str(record["expression"])
    eye, mouth, hair, clothing, ear = (
        str(record["E"]), str(record["M"]), str(record["H"]), str(record["C"]), str(record["ear"])
    )
    hair_parent = Path("assets") / gender / "hair" / hair
    clothing_parent = Path("assets") / gender / "clothing" / clothing
    hair_mask = catalog.find(hair_parent, "hair_tint_mask")
    hair_back = catalog.find(hair_parent, "hair_back")
    hair_front = catalog.find(hair_parent, "hair_front")
    clothing_back = catalog.find(clothing_parent, "clothing_back")
    clothing_main = catalog.find(clothing_parent, "clothing_main")
    clothing_front = catalog.find(clothing_parent, "clothing_front")

    expression_parent = Path("assets") / gender / "expression" / f"{face}_{skin}_{expression}"
    face_base = catalog.find(expression_parent, "face_expression_base", optional=True)
    face_head = catalog.find(expression_parent, "face_expression_head", optional=True)
    if (face_base is None) != (face_head is None):
        raise ExampleRenderError(f"incomplete expression face pair: {expression_parent}")
    if face_base is None:
        base_parent = Path("assets") / gender / "base" / face / skin
        if gender == "female":
            face_base = catalog.find(base_parent, f"{face}_{skin}_earless_head_body_rgba")
            face_head = catalog.find(base_parent, f"{face}_{skin}_earless_head_rgba")
        else:
            face_base = catalog.find(base_parent, "earless_head_body")
            face_head = catalog.find(base_parent, "earless_head")

    eye_path = catalog.find(Path("assets") / gender / "E" / eye / skin / expression, "eye_brow")
    mouth_path = catalog.find(Path("assets") / gender / "M" / mouth / skin / expression, "mouth")
    ear_path = catalog.only_file(Path("assets") / "shared" / "ears" / ear / "F01" / skin)
    layers = [
        _binding(catalog, "hair_back", hair_back, hair_mask),
        _binding(catalog, "clothing_back", clothing_back),
        _binding(catalog, "face_expression_base", face_base),
        _binding(catalog, "clothing_main", clothing_main),
        _binding(catalog, "face_expression_head", face_head),
    ]
    effect_key = f"{face}_{skin}_{expression}"
    blush_parent = Path("assets") / gender / "effects" / "blush" / effect_key
    sweat_parent = Path("assets") / gender / "effects" / "sweat" / effect_key
    blush = catalog.find(blush_parent, "blush", optional=True)
    sweat = catalog.find(sweat_parent, "sweat", optional=True)
    if (blush is None) != (sweat is None):
        raise ExampleRenderError(f"incomplete effect pair: {effect_key}")
    if blush:
        layers.append(_binding(catalog, "blush", blush))
    layers.extend([
        _binding(catalog, "eye_brow", eye_path),
        _binding(catalog, "mouth", mouth_path),
    ])
    if sweat:
        layers.append(_binding(catalog, "sweat", sweat))
    layers.extend([
        _binding(catalog, "hair_front", hair_front, hair_mask),
        _binding(catalog, "ear_pair", ear_path),
    ])
    if blush and sweat:
        ear_blush = catalog.find(blush_parent, f"ear_blush_{ear}")
        ear_sweat = catalog.find(sweat_parent, f"ear_sweat_{ear}")
        layers.extend([
            _binding(catalog, "ear_blush", ear_blush),
            _binding(catalog, "ear_sweat", ear_sweat),
        ])
    ear_cover = catalog.find(hair_parent, "hair_ear_cover", optional=True)
    if ear_cover:
        layers.append(_binding(catalog, "hair_ear_cover", ear_cover, hair_mask))
    layers.append(_binding(catalog, "clothing_front", clothing_front))
    return layers


def _build_luminance_lut(palette: dict[str, Any]) -> np.ndarray:
    stops = palette["stops"]
    colours = (
        np.asarray((0, 0, 0), dtype=np.float64),
        np.asarray(stops["shadow"]["srgb8"], dtype=np.float64),
        np.asarray(stops["midtone"]["srgb8"], dtype=np.float64),
        np.asarray(stops["highlight"]["srgb8"], dtype=np.float64),
        np.asarray(stops["specular"]["srgb8"], dtype=np.float64),
    )
    anchors = (0, 32, 128, 224, 255)
    lut = np.empty((256, 3), dtype=np.uint8)
    for segment in range(len(anchors) - 1):
        start_index, end_index = anchors[segment], anchors[segment + 1]
        for index in range(start_index, end_index + 1):
            weight = (index - start_index) / (end_index - start_index)
            lut[index] = np.clip(
                np.rint(colours[segment] * (1.0 - weight) + colours[segment + 1] * weight),
                0,
                255,
            ).astype(np.uint8)
    return lut


def _linear_luminance(rgb: np.ndarray) -> np.ndarray:
    normalized = rgb.astype(np.float64) / 255.0
    linear = np.where(
        normalized <= 0.04045,
        normalized / 12.92,
        np.power((normalized + 0.055) / 1.055, 2.4),
    )
    return 0.2126 * linear[:, :, 0] + 0.7152 * linear[:, :, 1] + 0.0722 * linear[:, :, 2]


def _luminance_indices(source: Image.Image) -> np.ndarray:
    pixels = np.asarray(source.convert("RGBA"), dtype=np.uint8)
    linear = _linear_luminance(pixels[:, :, :3])
    perceptual = np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    )
    return np.clip(np.rint(perceptual * 255.0), 0, 255).astype(np.uint8)


def _build_tone_map(sources: list[Image.Image], mask: Image.Image) -> np.ndarray:
    combined = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for source in sources:
        combined = Image.alpha_composite(combined, source.convert("RGBA"))
    pixels = np.asarray(combined, dtype=np.uint8)
    mask_owned = np.asarray(mask.convert("RGBA"), dtype=np.uint8)[:, :, 3] > 0
    profile = mask_owned & (pixels[:, :, 3] >= 128)
    if not np.any(profile):
        profile = mask_owned & (pixels[:, :, 3] > 0)
    indices = _luminance_indices(combined)
    histogram = np.bincount(indices[profile], minlength=256).astype(np.float64)
    occupied = np.flatnonzero(histogram)
    if occupied.size < 2:
        raise ExampleRenderError("hair sources do not contain a usable luminance range")
    midpoints = np.cumsum(histogram) - histogram * 0.5
    first, last = float(midpoints[occupied[0]]), float(midpoints[occupied[-1]])
    normalized = (midpoints[occupied] - first) * (255.0 / (last - first))
    interpolated = np.interp(
        np.arange(256, dtype=np.float64), occupied.astype(np.float64), normalized,
        left=0.0, right=255.0,
    )
    return np.clip(np.rint(interpolated), 0, 255).astype(np.uint8)


def _tint_hair(source: Image.Image, mask: Image.Image, lut: np.ndarray, tone_map: np.ndarray) -> Image.Image:
    source_pixels = np.asarray(source.convert("RGBA"), dtype=np.uint8).copy()
    original_alpha = source_pixels[:, :, 3].copy()
    mask_owned = np.asarray(mask.convert("RGBA"), dtype=np.uint8)[:, :, 3] > 0
    visible = mask_owned & (original_alpha > 0)
    target_indices = tone_map[_luminance_indices(source)]
    source_pixels[:, :, :3][visible] = lut[target_indices[visible]]
    source_pixels[:, :, 3] = original_alpha
    return Image.fromarray(source_pixels, "RGBA")


def _compose(catalog: AssetCatalog, record: dict[str, Any]) -> tuple[Image.Image, list[dict[str, Any]]]:
    layers = _resolve_layers(catalog, record)
    hair_bindings = [binding for binding in layers if binding["role"] in HAIR_ROLES]
    mask_paths = {binding["tint_mask"]["path"] for binding in hair_bindings}
    if len(mask_paths) != 1:
        raise ExampleRenderError("hair layers must share one tint mask")
    mask = catalog.load(next(iter(mask_paths)))
    hair_sources = [catalog.load(binding["path"]) for binding in hair_bindings]
    tone_map = _build_tone_map(hair_sources, mask)
    lut = _build_luminance_lut(record["palette"])
    tinted = {
        binding["path"]: _tint_hair(source, mask, lut, tone_map)
        for binding, source in zip(hair_bindings, hair_sources, strict=True)
    }
    result = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    face_checkpoint: Image.Image | None = None
    for binding in layers:
        role = str(binding["role"])
        source = tinted.get(binding["path"])
        if source is None:
            source = catalog.load(binding["path"])
        if role == "face_expression_base":
            result = Image.alpha_composite(result, source)
            face_checkpoint = result.copy()
        elif role == "face_expression_head":
            if face_checkpoint is None:
                raise ExampleRenderError("face head occurs before face-base checkpoint")
            owner = np.asarray(source, dtype=np.uint8)[:, :, 3] > 0
            current = np.asarray(result, dtype=np.uint8).copy()
            checkpoint = np.asarray(face_checkpoint, dtype=np.uint8)
            current[owner] = checkpoint[owner]
            result = Image.fromarray(current, "RGBA")
        else:
            result = Image.alpha_composite(result, source)
    return result, layers


def compose_record(repo_root: Path | str, record: dict[str, Any]) -> tuple[Image.Image, list[dict[str, Any]]]:
    return _compose(AssetCatalog(Path(repo_root)), record)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = ("DejaVuSans-Bold.ttf", "segoeuib.ttf", "arialbd.ttf") if bold else (
        "DejaVuSans.ttf", "segoeui.ttf", "arial.ttf"
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _preview(image: Image.Image, size: int) -> Image.Image:
    background = Image.new("RGBA", CANVAS, (232, 232, 232, 255))
    background.paste((25, 28, 34, 255), (CANVAS[0] // 2, 0, *CANVAS))
    return Image.alpha_composite(background, image).convert("RGB").resize(
        (size, size), Image.Resampling.LANCZOS
    )


def _recipe(record: dict[str, Any]) -> str:
    return "/".join(str(record[field]) for field in ("F", "S", "E", "M", "H", "C", "ear"))


def _mixed_board(previews: list[tuple[dict[str, Any], Image.Image]]) -> Image.Image:
    board = Image.new(
        "RGB",
        (MIXED_COLUMNS * MIXED_CELL_WIDTH, MIXED_ROWS * MIXED_CELL_HEIGHT),
        (18, 20, 25),
    )
    draw = ImageDraw.Draw(board)
    label_font, detail_font = _font(18, True), _font(14)
    for index, (record, preview) in enumerate(previews):
        column, row = index % MIXED_COLUMNS, index // MIXED_COLUMNS
        x, y = column * MIXED_CELL_WIDTH, row * MIXED_CELL_HEIGHT
        fill = (34, 40, 49) if record["gender"] == "female" else (38, 35, 47)
        draw.rectangle(
            (x + 4, y + 4, x + MIXED_CELL_WIDTH - 5, y + MIXED_CELL_HEIGHT - 5),
            fill=fill, outline=(88, 96, 110), width=2,
        )
        board.paste(preview, (x + (MIXED_CELL_WIDTH - MIXED_PREVIEW_SIZE) // 2, y + 8))
        swatch = tuple(record["palette"]["stops"]["midtone"]["srgb8"])
        draw.rectangle((x + 18, y + 444, x + 46, y + 472), fill=swatch)
        tag = "F" if record["gender"] == "female" else "M"
        draw.text(
            (x + 56, y + 440),
            f"{index + 1:02d} {tag} {record['expression']}  HAIR {record['palette']['midtone_hex']}",
            fill=(244, 246, 250), font=label_font,
        )
        draw.text((x + 56, y + 468), _recipe(record), fill=(194, 200, 211), font=detail_font)
    return board


def _legend_card(board: Image.Image, slot: int, title: str, body: str) -> None:
    draw = ImageDraw.Draw(board)
    column, row = slot % EXPRESSION_COLUMNS, slot // EXPRESSION_COLUMNS
    x = column * EXPRESSION_CELL_WIDTH
    y = EXPRESSION_HEADER + row * EXPRESSION_CELL_HEIGHT
    draw.rounded_rectangle(
        (x + 22, y + 24, x + EXPRESSION_CELL_WIDTH - 22, y + EXPRESSION_CELL_HEIGHT - 24),
        radius=28, fill=(35, 40, 50), outline=(95, 105, 122), width=2,
    )
    draw.text((x + 52, y + 120), title, font=_font(27, True), fill=(245, 247, 252))
    draw.multiline_text((x + 52, y + 178), body, font=_font(19), fill=(195, 203, 216), spacing=8)


def _expression_board(previews: list[tuple[dict[str, Any], Image.Image]]) -> Image.Image:
    board = Image.new("RGB", (2048, 2048), (17, 20, 27))
    draw = ImageDraw.Draw(board)
    draw.text((42, 24), "Expression Showcase", font=_font(40, True), fill=(248, 249, 252))
    draw.text(
        (44, 78),
        "Fixed identity within each gender; expression modules are the changing axis.",
        font=_font(20), fill=(184, 193, 207),
    )
    for index, (record, preview) in enumerate(previews):
        column, row = index % EXPRESSION_COLUMNS, index // EXPRESSION_COLUMNS
        x = column * EXPRESSION_CELL_WIDTH
        y = EXPRESSION_HEADER + row * EXPRESSION_CELL_HEIGHT
        fill = (34, 42, 53) if record["gender"] == "female" else (43, 37, 50)
        draw.rectangle(
            (x + 6, y + 6, x + EXPRESSION_CELL_WIDTH - 7, y + EXPRESSION_CELL_HEIGHT - 7),
            fill=fill, outline=(86, 97, 115), width=2,
        )
        board.paste(preview, (x + (EXPRESSION_CELL_WIDTH - EXPRESSION_PREVIEW_SIZE) // 2, y + 12))
        tag = "FEMALE" if record["gender"] == "female" else "MALE"
        draw.text((x + 28, y + 418), f"{tag}  {record['expression']}", font=_font(23, True), fill=(248, 249, 252))
        draw.text((x + 28, y + 450), f"E {record['E']}  /  M {record['M']}", font=_font(15), fill=(192, 200, 213))
    for slot, title, body in (
        (13, "Female lanes", "N00, G01-G04\nX01-X03"),
        (14, "Male lanes", "N00, G01-G04"),
        (15, "Render mode", "Deterministic alpha\ncomposition only"),
    ):
        _legend_card(board, slot, title, body)
    return board


def _manifest_record(record: dict[str, Any], layers: list[dict[str, Any]]) -> dict[str, Any]:
    selection = {
        key: value
        for key, value in record.items()
        if key not in {"palette"}
    }
    return {"selection": selection, "palette": record["palette"], "layers": layers}


def render_examples(
    repo_root: Path | str,
    output_dir: Path | str,
    master_seed: int = MASTER_SEED,
) -> dict[str, Any]:
    repo_root, output_dir = Path(repo_root).resolve(), Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = build_plan(repo_root, master_seed)
    catalog = AssetCatalog(repo_root)
    evidence: dict[str, list[dict[str, Any]]] = {"mixed_qc": [], "expression_showcase": []}

    mixed_previews: list[tuple[dict[str, Any], Image.Image]] = []
    for record in plan["mixed_qc"]["records"]:
        image, layers = _compose(catalog, record)
        mixed_previews.append((record, _preview(image, MIXED_PREVIEW_SIZE)))
        evidence["mixed_qc"].append(_manifest_record(record, layers))
    mixed_board = _mixed_board(mixed_previews)
    mixed_path = output_dir / "mixed-character-qc-48.webp"
    mixed_board.save(mixed_path, "WEBP", lossless=True, method=6)

    expression_previews: list[tuple[dict[str, Any], Image.Image]] = []
    for record in plan["expression_showcase"]["records"]:
        image, layers = _compose(catalog, record)
        expression_previews.append((record, _preview(image, EXPRESSION_PREVIEW_SIZE)))
        evidence["expression_showcase"].append(_manifest_record(record, layers))
    expression_board = _expression_board(expression_previews)
    expression_path = output_dir / "expression-showcase.png"
    expression_board.save(expression_path, "PNG", optimize=True)

    manifest = {
        "schema": "modular-portrait-public-examples-v1",
        "scope": "QC_AND_SHOWCASE_DERIVATIVES_NOT_SOURCE_MODULES",
        "generation_backend": "deterministic-alpha-composition",
        "model_sampler_steps_cfg": "not-applicable",
        "master_seed": master_seed,
        "canvas_contract": [1254, 1254, "RGBA"],
        "source_manifest": {
            "path": "provenance/asset-manifest.json",
            "sha256": sha256(repo_root / "provenance" / "asset-manifest.json"),
        },
        "tool": {
            "path": "tools/render_examples.py",
            "sha256": sha256(Path(__file__).resolve()),
        },
        "coverage": {
            "mixed_cells": 48,
            "female_mixed_cells": 24,
            "male_mixed_cells": 24,
            "female_expressions": list(EXPRESSIONS["female"]),
            "male_expressions": list(EXPRESSIONS["male"]),
            "female_hair": list(CURRENT_HAIRS["female"]),
            "male_hair": list(CURRENT_HAIRS["male"]),
            "excluded": ["male/H03", "male/H05"],
        },
        "outputs": {
            mixed_path.name: {
                "sha256": sha256(mixed_path), "format": "lossless-webp", "mode": "RGB", "size": list(mixed_board.size),
            },
            expression_path.name: {
                "sha256": sha256(expression_path), "format": "png", "mode": "RGB", "size": list(expression_board.size),
            },
        },
        "records": evidence,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"mixed_cells": 48, "expression_cells": 13, "outputs": manifest["outputs"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("output_dir", nargs="?", type=Path, default=Path("examples"))
    parser.add_argument("--seed", type=int, default=MASTER_SEED)
    args = parser.parse_args()
    result = render_examples(args.repo_root, args.output_dir, args.seed)
    print(json.dumps({"status": "PASS", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
