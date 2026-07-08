from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
MASTER_TEMPLATE_IMAGE = PACKAGE_ROOT / "assets" / "templates" / "mastertemplate-jerseyretroU.png"
MASTER_TEMPLATE_ZONES = PACKAGE_ROOT / "assets" / "templates" / "mastertemplate-jerseyretroU.zones.json"
JERSEY_REGION_TEMPLATE_IMAGE = PACKAGE_ROOT / "assets" / "templates" / "jersey_region.template.png"
JERSEY_REGION_TEMPLATE_ZONES = PACKAGE_ROOT / "assets" / "templates" / "jersey_region.template.zones.json"
JERSEY_NORMAL_TEMPLATE_IMAGE = PACKAGE_ROOT / "assets" / "templates" / "jersey_normal.template.png"
JERSEY_UV_TEMPLATE_IMAGE = PACKAGE_ROOT / "assets" / "templates" / "mastertemplate-jerseyretroU.uv.png"
JERSEY_TEMPLATE_OPTIONS = {
    "Jersey color": (MASTER_TEMPLATE_IMAGE, MASTER_TEMPLATE_ZONES),
    "Jersey region": (JERSEY_REGION_TEMPLATE_IMAGE, JERSEY_REGION_TEMPLATE_ZONES),
    "Jersey normal": (JERSEY_NORMAL_TEMPLATE_IMAGE, MASTER_TEMPLATE_ZONES),
    "Jersey UV": (JERSEY_UV_TEMPLATE_IMAGE, MASTER_TEMPLATE_ZONES),
}
SHORTS_TEMPLATE_RETRO_IMAGE = PACKAGE_ROOT / "assets" / "templates" / "shortstemplate1.png"
SHORTS_TEMPLATE_RETRO_ZONES = PACKAGE_ROOT / "assets" / "templates" / "shortstemplate1.zones.json"
SHORTS_TEMPLATE_OPTIONS = {
    "Retro shorts": (SHORTS_TEMPLATE_RETRO_IMAGE, SHORTS_TEMPLATE_RETRO_ZONES),
    "Classic shorts": (SHORTS_TEMPLATE_RETRO_IMAGE, SHORTS_TEMPLATE_RETRO_ZONES),
    "Modern shorts": (SHORTS_TEMPLATE_RETRO_IMAGE, SHORTS_TEMPLATE_RETRO_ZONES),
}


V1_COLOR_ZONE_PROFILE = {
    "left_side_panel": {
        "zone_type": "stripe",
        "color": "#1820c9",
        "rgb": (24, 32, 201),
        "tolerance": 4,
    },
    "right_side_panel": {
        "zone_type": "stripe",
        "color": "#c92918",
        "rgb": (201, 41, 24),
        "tolerance": 4,
    },
    "front_wordmark": {
        "zone_type": "wordmark",
        "color": "#000000",
        "rgb": (0, 0, 0),
        "tolerance": 4,
    },
    "collar_background": {
        "zone_type": "trim",
        "color": "#efad1e",
        "rgb": (239, 173, 30),
        "tolerance": 8,
    },
    "left_arm_hole_trim": {
        "zone_type": "trim",
        "color": "#12d7e3",
        "rgb": (18, 215, 227),
        "tolerance": 4,
    },
    "right_arm_hole_trim": {
        "zone_type": "trim",
        "color": "#12e32f",
        "rgb": (18, 227, 47),
        "tolerance": 4,
    },
    "collar_trim": {
        "zone_type": "trim",
        "color": "#cd12e3",
        "rgb": (205, 18, 227),
        "tolerance": 4,
    },
}

V3_COLOR_ZONE_PROFILE = {
    "front_jersey_base": {
        "zone_type": "base",
        "color": "#05ff05",
        "rgb": (5, 255, 5),
        "tolerance": 5,
        "mode": "largest_component",
    },
    "back_jersey_base": {
        "zone_type": "base",
        "color": "#05f0ff",
        "rgb": (5, 240, 255),
        "tolerance": 5,
        "mode": "components",
        "min_area": 10000,
    },
    "front_wordmark": {
        "zone_type": "wordmark",
        "color": "#000000",
        "rgb": (0, 0, 0),
        "tolerance": 4,
        "mode": "largest_component",
    },
    "left_side_panel": {
        "zone_type": "stripe",
        "color": "#1820c9",
        "rgb": (24, 32, 201),
        "tolerance": 4,
        "mode": "largest_component",
    },
    "right_side_panel": {
        "zone_type": "stripe",
        "color": "#c92918",
        "rgb": (201, 41, 24),
        "tolerance": 4,
        "mode": "largest_component",
    },
    "collar_background": {
        "zone_type": "trim",
        "color": "#efad1e",
        "rgb": (239, 173, 30),
        "tolerance": 8,
        "mode": "bbox",
    },
    "left_arm_hole_trim": {
        "zone_type": "trim",
        "color": "#12d7e3",
        "rgb": (18, 215, 227),
        "tolerance": 4,
        "mode": "bbox",
    },
    "right_arm_hole_trim": {
        "zone_type": "trim",
        "color": "#12e32f",
        "rgb": (18, 227, 47),
        "tolerance": 4,
        "mode": "bbox",
    },
    "collar_trim": {
        "zone_type": "trim",
        "color": "#cd12e3",
        "rgb": (205, 18, 227),
        "tolerance": 4,
        "mode": "bbox",
    },
}


@dataclass(frozen=True)
class TemplateZone:
    name: str
    zone_type: str
    x: int
    y: int
    width: int
    height: int
    color: str
    layer: int = 0


@dataclass(frozen=True)
class JerseyTemplate:
    image_path: str
    zones: tuple[TemplateZone, ...]


def save_template(path: Path, template: JerseyTemplate) -> None:
    data = {
        "image_path": template.image_path,
        "zones": [asdict(zone) for zone in template.zones],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_template(path: Path) -> JerseyTemplate:
    data = json.loads(path.read_text(encoding="utf-8"))
    zones = tuple(TemplateZone(**zone) for zone in data.get("zones", []))
    return JerseyTemplate(image_path=data.get("image_path", ""), zones=zones)


def detect_v1_color_zones(image_path: Path) -> list[TemplateZone]:
    return _detect_color_zones(image_path, V1_COLOR_ZONE_PROFILE)


def detect_v3_color_zones(image_path: Path) -> list[TemplateZone]:
    zones = _detect_color_zones(image_path, V3_COLOR_ZONE_PROFILE)
    return _split_v3_back_around_front(zones)


def find_hex_color_zone_bbox(
    image_path: Path,
    hex_color: str,
    *,
    tolerance: int = 4,
) -> tuple[int, int, int, int] | None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Color detection requires Pillow.") from exc

    rgb = _hex_to_rgb(hex_color)
    image = Image.open(image_path).convert("RGB")
    pixels = image.load()
    bbox = _find_color_bbox(pixels, image.width, image.height, rgb, tolerance)
    if bbox is None:
        return None
    left, top, right, bottom, _area = bbox
    return left, top, right - left + 1, bottom - top + 1


def create_uv_overlay_from_template(
    image_path: Path,
    output_path: Path,
    *,
    contrast_threshold: int = 14,
) -> None:
    try:
        from PIL import Image, ImageChops, ImageFilter
    except ImportError as exc:
        raise RuntimeError("UV map creation requires Pillow.") from exc

    with Image.open(image_path) as opened:
        image = opened.convert("RGBA")

    alpha = image.getchannel("A")
    grayscale = image.convert("L")
    local_average = grayscale.filter(ImageFilter.GaussianBlur(radius=3))
    darker_than_area = ImageChops.subtract(local_average, grayscale)
    mask = darker_than_area.point(
        lambda value: 0 if value < contrast_threshold else min(220, (value - contrast_threshold) * 8)
    )
    mask = ImageChops.multiply(mask, alpha)
    mask = mask.filter(ImageFilter.MaxFilter(size=3))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay.putalpha(mask)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path)


def _detect_color_zones(image_path: Path, profile: dict) -> list[TemplateZone]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Color detection requires Pillow.") from exc

    image = Image.open(image_path).convert("RGB")
    pixels = image.load()
    width, height = image.size
    zones: list[TemplateZone] = []

    for name, spec in profile.items():
        target = spec["rgb"]
        tolerance = spec["tolerance"]
        mode = spec.get("mode", "bbox")
        if mode == "components":
            bboxes = _find_color_components(
                pixels,
                width,
                height,
                target,
                tolerance,
                min_area=spec.get("min_area", 1),
            )
        elif mode == "largest_component":
            bboxes = _find_color_components(
                pixels,
                width,
                height,
                target,
                tolerance,
                min_area=spec.get("min_area", 1),
            )[:1]
        else:
            bbox = _find_color_bbox(pixels, width, height, target, tolerance)
            bboxes = [bbox] if bbox else []

        for index, bbox in enumerate(bboxes, start=1):
            left, top, right, bottom, _area = bbox
            zone_name = name if len(bboxes) == 1 else f"{name}_{index}"
            zones.append(
                TemplateZone(
                    name=zone_name,
                    zone_type=spec["zone_type"],
                    x=left,
                    y=top,
                    width=right - left + 1,
                    height=bottom - top + 1,
                    color=spec["color"],
                    layer=_zone_layer(spec["zone_type"]),
                )
            )
    return zones


def _split_v3_back_around_front(zones: list[TemplateZone]) -> list[TemplateZone]:
    front = next((zone for zone in zones if zone.name == "front_jersey_base"), None)
    back = next((zone for zone in zones if zone.name == "back_jersey_base"), None)
    split_back_zones = [
        zone for zone in zones if zone.name.startswith("back_jersey_base_")
    ]
    if split_back_zones:
        ordered = sorted(split_back_zones, key=lambda zone: zone.x)
        renamed: list[TemplateZone] = []
        for zone in zones:
            if not zone.name.startswith("back_jersey_base_"):
                renamed.append(zone)
                continue
            side = "left" if zone is ordered[0] else "right"
            renamed.append(
                TemplateZone(
                    name=f"back_jersey_base_{side}",
                    zone_type=zone.zone_type,
                    x=zone.x,
                    y=zone.y,
                    width=zone.width,
                    height=zone.height,
                    color=zone.color,
                    layer=zone.layer,
                )
            )
        return renamed

    if front is None or back is None:
        return zones

    split_zones: list[TemplateZone] = []
    for zone in zones:
        if zone.name != "back_jersey_base":
            split_zones.append(zone)
            continue

        if front.x > back.x:
            split_zones.append(
                TemplateZone(
                    name="back_jersey_base_left",
                    zone_type=back.zone_type,
                    x=back.x,
                    y=back.y,
                    width=front.x - back.x,
                    height=back.height,
                    color=back.color,
                    layer=back.layer,
                )
            )

        back_right = back.x + back.width
        front_right = front.x + front.width
        if front_right < back_right:
            split_zones.append(
                TemplateZone(
                    name="back_jersey_base_right",
                    zone_type=back.zone_type,
                    x=front_right,
                    y=back.y,
                    width=back_right - front_right,
                    height=back.height,
                    color=back.color,
                    layer=back.layer,
                )
            )
    return split_zones


def _zone_layer(zone_type: str) -> int:
    return {
        "base": 0,
        "pattern": 10,
        "stripe": 20,
        "trim": 30,
        "wordmark": 40,
        "number": 40,
        "name": 40,
        "logo": 50,
        "patch": 50,
        "mask": 60,
    }.get(zone_type, 10)


def _find_color_bbox(pixels, width: int, height: int, target, tolerance: int):
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    tr, tg, tb = target

    for y in range(height):
        for x in range(width):
            if _pixel_matches(pixels[x, y], target, tolerance):
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x == -1:
        return None
    return min_x, min_y, max_x, max_y, (max_x - min_x + 1) * (max_y - min_y + 1)


def _find_color_components(
    pixels,
    width: int,
    height: int,
    target,
    tolerance: int,
    min_area: int = 1,
) -> list[tuple[int, int, int, int, int]]:
    visited: set[tuple[int, int]] = set()
    components: list[tuple[int, int, int, int, int]] = []

    for y in range(height):
        for x in range(width):
            if (x, y) in visited:
                continue
            if not _pixel_matches(pixels[x, y], target, tolerance):
                continue
            bbox = _flood_fill_bbox(pixels, width, height, x, y, target, tolerance, visited)
            if bbox[4] >= min_area:
                components.append(bbox)

    return sorted(components, key=lambda item: item[4], reverse=True)


def _flood_fill_bbox(
    pixels,
    width: int,
    height: int,
    start_x: int,
    start_y: int,
    target,
    tolerance: int,
    visited: set[tuple[int, int]],
) -> tuple[int, int, int, int, int]:
    stack = [(start_x, start_y)]
    visited.add((start_x, start_y))
    min_x = max_x = start_x
    min_y = max_y = start_y
    area = 0

    while stack:
        x, y = stack.pop()
        area += 1
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)

        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            if (nx, ny) in visited:
                continue
            visited.add((nx, ny))
            if _pixel_matches(pixels[nx, ny], target, tolerance):
                stack.append((nx, ny))

    return min_x, min_y, max_x, max_y, area


def _pixel_matches(pixel, target, tolerance: int) -> bool:
    r, g, b = pixel
    tr, tg, tb = target
    return (
        abs(r - tr) <= tolerance
        and abs(g - tg) <= tolerance
        and abs(b - tb) <= tolerance
    )


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().removeprefix("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    if len(value) != 6:
        raise ValueError("Hex color must be 3 or 6 digits.")
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError as exc:
        raise ValueError("Hex color contains invalid characters.") from exc
