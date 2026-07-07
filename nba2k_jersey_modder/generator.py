from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import struct
from pathlib import Path

from .template import JerseyTemplate, TemplateZone


DEFAULT_LOGO_TARGETS: tuple[TemplateZone, ...] = (
    TemplateZone(
        "wrap_across_front_back_logo",
        "logo",
        0,
        700,
        2048,
        260,
        "#ffffff",
        50,
    ),
    TemplateZone(
        "front_left_chest_logo",
        "logo",
        1010,
        610,
        180,
        180,
        "#ffffff",
        50,
    ),
    TemplateZone(
        "front_right_chest_logo",
        "logo",
        1515,
        610,
        180,
        180,
        "#ffffff",
        50,
    ),
    TemplateZone(
        "front_center_chest_logo",
        "logo",
        1224,
        610,
        260,
        180,
        "#ffffff",
        50,
    ),
    TemplateZone(
        "back_neck_logo",
        "logo",
        350,
        470,
        180,
        180,
        "#ffffff",
        50,
    ),
    TemplateZone(
        "back_center_logo",
        "logo",
        300,
        720,
        260,
        220,
        "#ffffff",
        50,
    ),
)

FABRIC_OVERLAY_EXCLUDED_ZONE_NAMES = {
    "collar_background",
    "left_arm_hole_trim",
    "right_arm_hole_trim",
    "collar_trim",
    "shorts_waistband_top",
    "shorts_waistband_bottom",
}

JERSEY_REGION_SIDE_PANEL_COLOR = (192, 0, 102, 255)
JERSEY_REGION_DECAL_COLOR = (132, 0, 216, 255)


@dataclass(frozen=True)
class RenderLayer:
    name: str
    image: object
    blend_mode: str = "normal"


@dataclass(frozen=True)
class LogoPlacement:
    path: Path
    target_name: str
    offset_x: int = 0
    offset_y: int = 0
    scale_percent: int = 100
    stretch_x: bool = False


@dataclass(frozen=True)
class BackgroundCleanupSettings:
    auto_background: bool = False
    remove_white: bool = False
    remove_black: bool = False
    outside_only: bool = True
    tolerance: int = 32


@dataclass(frozen=True)
class TrimPlacementSettings:
    offset_x: int = 0
    offset_y: int = 0
    scale_percent: int = 100
    flip_x: bool = False


@dataclass(frozen=True)
class ImagePlacement:
    key: str
    label: str
    x: int
    y: int
    width: int
    height: int
    clip_x: int | None = None
    clip_y: int | None = None
    clip_width: int | None = None
    clip_height: int | None = None


@dataclass(frozen=True)
class GeneratorInputs:
    front_color: str
    back_color: str
    left_panel_color: str
    right_panel_color: str
    collar_background_color: str = "#ffffff"
    left_arm_hole_trim_color: str = "#ffffff"
    right_arm_hole_trim_color: str = "#ffffff"
    collar_trim_color: str = "#ffffff"
    left_panel_image: Path | None = None
    right_panel_image: Path | None = None
    front_wordmark_image: Path | None = None
    left_arm_hole_trim_image: Path | None = None
    right_arm_hole_trim_image: Path | None = None
    collar_trim_image: Path | None = None
    front_wordmark_offset_x: int = 0
    front_wordmark_offset_y: int = 0
    front_wordmark_scale_percent: int = 100
    logo_placements: tuple[LogoPlacement, ...] = ()
    fabric_overlay_image: Path | None = None
    fabric_overlay_opacity: int = 0
    fabric_overlay_blend_mode: str = "multiply"
    dynamic_layer_order: tuple[str, ...] = ()
    layer_background_cleanup: dict[str, BackgroundCleanupSettings] = field(default_factory=dict)
    trim_placements: dict[str, TrimPlacementSettings] = field(default_factory=dict)
    remove_white_background: bool = False
    remove_black_background: bool = False
    remove_outside_background_only: bool = True
    background_tolerance: int = 32


def generate_jersey_texture(
    template: JerseyTemplate,
    inputs: GeneratorInputs,
    output_path: Path,
    size: tuple[int, int] = (2048, 2048),
) -> Path:
    image = render_jersey_texture(template, inputs, size)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def render_jersey_texture(
    template: JerseyTemplate,
    inputs: GeneratorInputs,
    size: tuple[int, int] = (2048, 2048),
):
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Jersey generation requires Pillow.") from exc

    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for layer in render_jersey_layers(template, inputs, size):
        _composite_render_layer(image, layer)
    return image


def render_jersey_layers(
    template: JerseyTemplate,
    inputs: GeneratorInputs,
    size: tuple[int, int] = (2048, 2048),
) -> list[RenderLayer]:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Jersey generation requires Pillow.") from exc

    layers: list[RenderLayer] = []
    zones = sorted(template.zones, key=lambda zone: zone.layer)
    front_wordmark_zone: TemplateZone | None = None
    for zone in zones:
        fill = _fill_for_zone(zone, inputs)
        if fill is not None:
            layer = Image.new("RGBA", size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).rectangle(_zone_box(zone), fill=fill)
            layers.append(RenderLayer(_human_zone_name(zone.name), layer))

        if zone.name == "front_wordmark":
            front_wordmark_zone = zone
            continue

        overlay = _overlay_for_zone(zone, inputs)
        if overlay is not None and overlay.exists():
            layer = Image.new("RGBA", size, (0, 0, 0, 0))
            _paste_image_fit(layer, overlay, zone, inputs, cleanup_key=zone.name)
            layers.append(RenderLayer(f"{_human_zone_name(zone.name)} Image", layer))

    dynamic_layers: list[tuple[str, RenderLayer]] = []
    logo_targets = {zone.name: zone for zone in logo_target_zones(template)}
    for index, logo in enumerate(inputs.logo_placements, start=1):
        target = logo_targets.get(logo.target_name)
        if target is None or not logo.path.exists():
            continue
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        logo_key = f"logo:{index - 1}"
        _paste_image_fit(layer, logo.path, target, inputs, logo=logo, cleanup_key=logo_key)
        dynamic_layers.append(
            (
                logo_key,
                RenderLayer(
                    f"Logo {index} - {_human_zone_name(target.name)}",
                    layer,
                ),
            )
        )

    fabric_layer = fabric_overlay_layer(template, inputs, size)
    if fabric_layer is not None:
        dynamic_layers.append(("fabric_overlay", fabric_layer))

    layers.extend(
        layer
        for _key, layer in _ordered_dynamic_layers(
            dynamic_layers,
            inputs.dynamic_layer_order,
        )
    )

    if (
        front_wordmark_zone is not None
        and inputs.front_wordmark_image
        and inputs.front_wordmark_image.exists()
    ):
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        _paste_image_fit(
            layer,
            inputs.front_wordmark_image,
            front_wordmark_zone,
            inputs,
            cleanup_key="front_wordmark",
        )
        layers.append(RenderLayer("Front Wordmark Image", layer))

    return layers


def fabric_overlay_layer(
    template: JerseyTemplate,
    inputs: GeneratorInputs,
    size: tuple[int, int],
) -> RenderLayer | None:
    if (
        inputs.fabric_overlay_image is None
        or not inputs.fabric_overlay_image.exists()
        or inputs.fabric_overlay_opacity <= 0
    ):
        return None
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Fabric overlays require Pillow.") from exc

    opacity = max(0, min(100, int(inputs.fabric_overlay_opacity)))
    overlay = Image.open(inputs.fabric_overlay_image).convert("RGBA")
    overlay = overlay.resize(size, Image.Resampling.LANCZOS)
    if opacity < 100:
        alpha = overlay.getchannel("A").point(lambda value: round(value * opacity / 100))
        overlay.putalpha(alpha)
    blend_mode = inputs.fabric_overlay_blend_mode
    if blend_mode not in {"normal", "multiply", "overlay"}:
        blend_mode = "multiply"
    if blend_mode == "multiply":
        _clear_fabric_overlay_excluded_zones(overlay, template)
    return RenderLayer("Fabric / Wrinkle Overlay", overlay, blend_mode)


def _ordered_dynamic_layers(
    layers: list[tuple[str, RenderLayer]],
    layer_order: tuple[str, ...],
) -> list[tuple[str, RenderLayer]]:
    if not layer_order:
        return layers
    by_key = {key: layer for key, layer in layers}
    ordered: list[tuple[str, RenderLayer]] = []
    seen: set[str] = set()
    for key in layer_order:
        layer = by_key.get(key)
        if layer is None or key in seen:
            continue
        ordered.append((key, layer))
        seen.add(key)
    ordered.extend((key, layer) for key, layer in layers if key not in seen)
    return ordered


def _clear_fabric_overlay_excluded_zones(overlay, template: JerseyTemplate) -> None:
    try:
        from PIL import ImageDraw
    except ImportError as exc:
        raise RuntimeError("Fabric overlay masking requires Pillow.") from exc

    design_width, design_height = _template_design_size(template, overlay.size)
    scale_x = overlay.width / design_width
    scale_y = overlay.height / design_height
    alpha = overlay.getchannel("A")
    draw = ImageDraw.Draw(alpha)
    for zone in template.zones:
        if (
            zone.name not in FABRIC_OVERLAY_EXCLUDED_ZONE_NAMES
            and not zone.name.startswith("shorts_waistband")
        ):
            continue
        left = round(zone.x * scale_x)
        top = round(zone.y * scale_y)
        right = round((zone.x + zone.width) * scale_x)
        bottom = round((zone.y + zone.height) * scale_y)
        draw.rectangle((left, top, right, bottom), fill=0)
    overlay.putalpha(alpha)


def _template_design_size(
    template: JerseyTemplate,
    output_size: tuple[int, int],
) -> tuple[int, int]:
    max_x = max((zone.x + zone.width for zone in template.zones), default=output_size[0])
    max_y = max((zone.y + zone.height for zone in template.zones), default=output_size[1])
    if max_x <= output_size[0] and max_y <= output_size[1]:
        return output_size
    return max(max_x, 2048), max(max_y, 2048)


def generate_layered_jersey_psd(
    template: JerseyTemplate,
    inputs: GeneratorInputs,
    output_path: Path,
    size: tuple[int, int] = (2048, 2048),
) -> Path:
    composite = render_jersey_texture(template, inputs, size)
    layers = render_jersey_layers(template, inputs, size)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_layered_psd(output_path, composite, layers)
    return output_path


def render_jersey_region_map(
    template: JerseyTemplate,
    inputs: GeneratorInputs,
    region_template_path: Path,
    size: tuple[int, int] = (1024, 1024),
):
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Jersey region generation requires Pillow.") from exc

    base = Image.open(region_template_path).convert("RGBA")
    if base.size != size:
        base = base.resize(size, Image.Resampling.NEAREST)

    design_width, design_height = _template_design_size(template, (2048, 2048))
    scale_x = size[0] / design_width
    scale_y = size[1] / design_height

    draw = ImageDraw.Draw(base)
    for zone in sorted(template.zones, key=lambda candidate: candidate.layer):
        if zone.name not in {"left_side_panel", "right_side_panel"}:
            continue
        if not _region_side_panel_is_active(zone.name, inputs):
            continue
        left = round(zone.x * scale_x)
        top = round(zone.y * scale_y)
        right = round((zone.x + zone.width) * scale_x)
        bottom = round((zone.y + zone.height) * scale_y)
        draw.rectangle((left, top, right, bottom), fill=JERSEY_REGION_SIDE_PANEL_COLOR)

    front = next((zone for zone in template.zones if zone.name == "front_wordmark"), None)
    if front is not None and inputs.front_wordmark_image and inputs.front_wordmark_image.exists():
        overlay = _prepared_overlay(inputs.front_wordmark_image, inputs, "front_wordmark")
        overlay, x, y = _overlay_at_zone(overlay, front, inputs)
        _paint_region_overlay(base, overlay, x, y, scale_x, scale_y)

    logo_targets = {zone.name: zone for zone in logo_target_zones(template)}
    for index, logo in enumerate(inputs.logo_placements):
        target = logo_targets.get(logo.target_name)
        if target is None or not logo.path.exists():
            continue
        logo_key = f"logo:{index}"
        overlay = _prepared_overlay(logo.path, inputs, logo_key)
        overlay, x, y = _overlay_at_zone(overlay, target, inputs, logo=logo)
        _paint_region_overlay(base, overlay, x, y, scale_x, scale_y)

    return base


def _region_side_panel_is_active(zone_name: str, inputs: GeneratorInputs) -> bool:
    image_path = (
        inputs.left_panel_image
        if zone_name == "left_side_panel"
        else inputs.right_panel_image
    )
    if image_path is not None and image_path.exists():
        return True

    panel_color = _active_color(
        inputs.left_panel_color
        if zone_name == "left_side_panel"
        else inputs.right_panel_color
    )
    if panel_color is None:
        return False

    base_colors = [
        color.lower()
        for color in (_active_color(inputs.front_color), _active_color(inputs.back_color))
        if color is not None
    ]
    if not base_colors:
        return True
    return all(panel_color.lower() != base_color for base_color in base_colors)


def _paint_region_overlay(base, overlay, x: int, y: int, scale_x: float, scale_y: float) -> None:
    from PIL import Image

    width = max(1, round(overlay.width * scale_x))
    height = max(1, round(overlay.height * scale_y))
    mask = overlay.getchannel("A").resize((width, height), Image.Resampling.LANCZOS)
    mask = mask.point(lambda value: 255 if value >= 16 else 0)
    region = Image.new("RGBA", (width, height), JERSEY_REGION_DECAL_COLOR)
    region.putalpha(mask)
    base.alpha_composite(region, (round(x * scale_x), round(y * scale_y)))


def _fill_for_zone(zone: TemplateZone, inputs: GeneratorInputs) -> str | None:
    if zone.name.startswith("shorts_waistband"):
        return _active_color(inputs.collar_background_color)
    if zone.name == "shorts_left_panel":
        return _active_color(inputs.left_panel_color)
    if zone.name == "shorts_right_panel":
        return _active_color(inputs.right_panel_color)
    if zone.name == "front_jersey_base":
        return _active_color(inputs.front_color)
    if zone.name.startswith("back_jersey_base"):
        return _active_color(inputs.back_color)
    if zone.name == "left_side_panel":
        return _active_color(inputs.left_panel_color)
    if zone.name == "right_side_panel":
        return _active_color(inputs.right_panel_color)
    if zone.name == "collar_background":
        return _active_color(inputs.collar_background_color)
    if zone.name == "left_arm_hole_trim":
        return _active_color(inputs.left_arm_hole_trim_color)
    if zone.name == "right_arm_hole_trim":
        return _active_color(inputs.right_arm_hole_trim_color)
    if zone.name == "collar_trim":
        return _active_color(inputs.collar_trim_color)
    return None


def _active_color(color: str) -> str | None:
    color = color.strip()
    return color or None


def _overlay_for_zone(zone: TemplateZone, inputs: GeneratorInputs) -> Path | None:
    if zone.name in {"left_side_panel", "shorts_left_panel"}:
        return inputs.left_panel_image
    if zone.name in {"right_side_panel", "shorts_right_panel"}:
        return inputs.right_panel_image
    if zone.name == "front_wordmark":
        return inputs.front_wordmark_image
    if zone.name == "left_arm_hole_trim":
        return inputs.left_arm_hole_trim_image
    if zone.name == "right_arm_hole_trim":
        return inputs.right_arm_hole_trim_image
    if zone.name == "collar_trim":
        return inputs.collar_trim_image
    return None


def _zone_box(zone: TemplateZone) -> tuple[int, int, int, int]:
    return (zone.x, zone.y, zone.x + zone.width, zone.y + zone.height)


def _human_zone_name(name: str) -> str:
    if name == "back_jersey_base_left":
        return "Back Jersey Base Left"
    if name == "back_jersey_base_right":
        return "Back Jersey Base Right"
    return name.replace("_", " ").title()


def logo_target_zones(template: JerseyTemplate) -> tuple[TemplateZone, ...]:
    template_targets = {
        zone.name: zone
        for zone in template.zones
        if zone.zone_type.lower() in {"logo", "patch"}
    }
    if any(zone.name.startswith("shorts_") for zone in template.zones):
        return tuple(template_targets.values())
    targets = {zone.name: zone for zone in DEFAULT_LOGO_TARGETS}
    targets.update(template_targets)
    return tuple(targets.values())


def image_placement_rects(
    template: JerseyTemplate,
    inputs: GeneratorInputs,
) -> tuple[ImagePlacement, ...]:
    placements: list[ImagePlacement] = []
    front = next((zone for zone in template.zones if zone.name == "front_wordmark"), None)
    if front is not None and inputs.front_wordmark_image and inputs.front_wordmark_image.exists():
        overlay = _prepared_overlay(inputs.front_wordmark_image, inputs, "front_wordmark")
        overlay, x, y = _overlay_at_zone(overlay, front, inputs)
        placements.append(
            ImagePlacement("front_wordmark", "Front Wordmark", x, y, overlay.width, overlay.height)
        )

    for zone in sorted(template.zones, key=lambda candidate: candidate.layer):
        overlay_path = _overlay_for_zone(zone, inputs)
        if (
            zone.name == "front_wordmark"
            or overlay_path is None
            or not overlay_path.exists()
            or not _zone_image_stretches(zone)
        ):
            continue
        overlay = _prepared_overlay(overlay_path, inputs, zone.name)
        overlay, x, y = _overlay_at_zone(overlay, zone, inputs)
        placements.append(
            ImagePlacement(
                zone.name,
                _human_zone_name(zone.name),
                x,
                y,
                overlay.width,
                overlay.height,
                zone.x,
                zone.y,
                zone.width,
                zone.height,
            )
        )

    logo_targets = {zone.name: zone for zone in logo_target_zones(template)}
    for index, logo in enumerate(inputs.logo_placements):
        target = logo_targets.get(logo.target_name)
        if target is None or not logo.path.exists():
            continue
        logo_key = f"logo:{index}"
        overlay = _prepared_overlay(logo.path, inputs, logo_key)
        overlay, x, y = _overlay_at_zone(overlay, target, inputs, logo=logo)
        placements.append(
            ImagePlacement(
                f"logo:{index}",
                f"Logo {index + 1}",
                x,
                y,
                overlay.width,
                overlay.height,
            )
        )
    return tuple(placements)


def _paste_image_fit(
    base,
    overlay_path: Path,
    zone: TemplateZone,
    inputs: GeneratorInputs,
    logo: LogoPlacement | None = None,
    cleanup_key: str | None = None,
) -> None:
    overlay = _prepared_overlay(overlay_path, inputs, cleanup_key)
    overlay, x, y = _overlay_at_zone(overlay, zone, inputs, logo=logo)
    clip_box = _zone_box(zone) if _zone_image_stretches(zone) else None
    _alpha_composite_at(base, overlay, x, y, clip_box=clip_box)


def _prepared_overlay(
    overlay_path: Path,
    inputs: GeneratorInputs,
    cleanup_key: str | None = None,
):
    from PIL import Image

    overlay = Image.open(overlay_path).convert("RGBA")
    cleanup = _background_cleanup_for_key(inputs, cleanup_key)
    if cleanup.auto_background:
        overlay = remove_detected_background(
            overlay,
            tolerance=cleanup.tolerance,
        )
    return remove_image_background(
        overlay,
        remove_white=cleanup.remove_white,
        remove_black=cleanup.remove_black,
        outside_only=cleanup.outside_only,
        tolerance=cleanup.tolerance,
    )


def _background_cleanup_for_key(
    inputs: GeneratorInputs,
    cleanup_key: str | None,
) -> BackgroundCleanupSettings:
    if cleanup_key is not None and cleanup_key in inputs.layer_background_cleanup:
        return inputs.layer_background_cleanup[cleanup_key]
    return BackgroundCleanupSettings(
        remove_white=inputs.remove_white_background,
        remove_black=inputs.remove_black_background,
        outside_only=inputs.remove_outside_background_only,
        tolerance=inputs.background_tolerance,
    )


def _overlay_at_zone(
    overlay,
    zone: TemplateZone,
    inputs: GeneratorInputs,
    logo: LogoPlacement | None = None,
):
    from PIL import Image

    if _zone_image_stretches(zone):
        trim = inputs.trim_placements.get(zone.name, TrimPlacementSettings())
        return (
            _transform_stretched_zone_image(overlay, zone, trim),
            zone.x + trim.offset_x,
            zone.y + trim.offset_y,
        )

    if logo is not None and logo.stretch_x:
        ratio = zone.width / max(1, overlay.width)
        scale = max(1, int(logo.scale_percent)) / 100
        overlay = overlay.resize(
            (zone.width, max(1, round(overlay.height * ratio * scale))),
            Image.Resampling.LANCZOS,
        )
        return (
            overlay,
            zone.x,
            zone.y + (zone.height - overlay.height) // 2 + logo.offset_y,
        )

    overlay.thumbnail((zone.width, zone.height), Image.Resampling.LANCZOS)
    overlay = _scale_zone_image(zone, overlay, inputs, logo=logo)
    offset_x, offset_y = _zone_image_offset(zone, inputs, logo=logo)
    x = zone.x + (zone.width - overlay.width) // 2 + offset_x
    y = zone.y + (zone.height - overlay.height) // 2 + offset_y
    return overlay, x, y


def _transform_stretched_zone_image(overlay, zone: TemplateZone, trim: TrimPlacementSettings):
    from PIL import Image

    overlay = overlay.resize((zone.width, zone.height), Image.Resampling.LANCZOS)
    if trim.flip_x:
        overlay = overlay.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    scale = max(1, int(trim.scale_percent)) / 100
    if scale != 1:
        overlay = overlay.resize(
            (
                max(1, round(overlay.width * scale)),
                max(1, round(overlay.height * scale)),
            ),
            Image.Resampling.LANCZOS,
        )
    return overlay


def _zone_image_stretches(zone: TemplateZone) -> bool:
    return zone.name in {
        "left_arm_hole_trim",
        "right_arm_hole_trim",
        "collar_trim",
    }


def _zone_image_offset(
    zone: TemplateZone,
    inputs: GeneratorInputs,
    logo: LogoPlacement | None = None,
) -> tuple[int, int]:
    if logo is not None:
        if logo.stretch_x:
            return 0, logo.offset_y
        return logo.offset_x, logo.offset_y
    if zone.name == "front_wordmark":
        return inputs.front_wordmark_offset_x, inputs.front_wordmark_offset_y
    return 0, 0


def _scale_zone_image(
    zone: TemplateZone,
    image,
    inputs: GeneratorInputs,
    logo: LogoPlacement | None = None,
):
    if logo is not None:
        scale = max(1, int(logo.scale_percent)) / 100
    elif zone.name == "front_wordmark":
        scale = max(1, int(inputs.front_wordmark_scale_percent)) / 100
    else:
        return image
    if scale == 1:
        return image
    from PIL import Image

    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _alpha_composite_at(
    base,
    overlay,
    x: int,
    y: int,
    *,
    clip_box: tuple[int, int, int, int] | None = None,
) -> None:
    left = max(0, x)
    top = max(0, y)
    right = min(base.width, x + overlay.width)
    bottom = min(base.height, y + overlay.height)
    if clip_box is not None:
        clip_left, clip_top, clip_right, clip_bottom = clip_box
        left = max(left, clip_left)
        top = max(top, clip_top)
        right = min(right, clip_right)
        bottom = min(bottom, clip_bottom)
    if left >= right or top >= bottom:
        return
    crop_left = left - x
    crop_top = top - y
    crop_right = crop_left + (right - left)
    crop_bottom = crop_top + (bottom - top)
    base.alpha_composite(
        overlay.crop((crop_left, crop_top, crop_right, crop_bottom)),
        (left, top),
    )


def _composite_render_layer(base, layer: RenderLayer) -> None:
    if layer.blend_mode == "normal":
        base.alpha_composite(layer.image)
        return

    try:
        from PIL import Image, ImageChops
    except ImportError as exc:
        raise RuntimeError("Layer blending requires Pillow.") from exc

    overlay = layer.image.convert("RGBA")
    alpha = overlay.getchannel("A")
    if layer.blend_mode == "multiply":
        blended_rgb = ImageChops.multiply(base.convert("RGB"), overlay.convert("RGB"))
    elif layer.blend_mode == "overlay":
        blended_rgb = _overlay_blend(base.convert("RGB"), overlay.convert("RGB"))
    else:
        base.alpha_composite(overlay)
        return

    blended = Image.merge("RGBA", (*blended_rgb.split(), base.getchannel("A")))
    base_rgb = base.convert("RGBA")
    base.paste(Image.composite(blended, base_rgb, alpha))


def _overlay_blend(base_rgb, overlay_rgb):
    from PIL import Image, ImageChops

    double_base = ImageChops.multiply(base_rgb, ImageChops.constant(base_rgb, 2))
    multiply = ImageChops.multiply(double_base, overlay_rgb)
    inverted_base = ImageChops.invert(base_rgb)
    inverted_overlay = ImageChops.invert(overlay_rgb)
    screen_part = ImageChops.invert(
        ImageChops.multiply(
            ImageChops.multiply(inverted_base, ImageChops.constant(base_rgb, 2)),
            inverted_overlay,
        )
    )
    mask = base_rgb.convert("L").point(lambda value: 255 if value >= 128 else 0)
    return Image.composite(screen_part, multiply, mask)


def remove_image_background(
    image,
    *,
    remove_white: bool = False,
    remove_black: bool = False,
    outside_only: bool = True,
    tolerance: int = 32,
):
    if not remove_white and not remove_black:
        return image

    tolerance = max(0, min(255, int(tolerance)))
    cleaned = image.copy()
    pixels = cleaned.load()
    if outside_only:
        _remove_edge_connected_background(
            cleaned,
            pixels,
            remove_white=remove_white,
            remove_black=remove_black,
            tolerance=tolerance,
        )
        return cleaned

    for y in range(cleaned.height):
        for x in range(cleaned.width):
            red, green, blue, _alpha = pixels[x, y]
            if _matches_background(
                red,
                green,
                blue,
                remove_white=remove_white,
                remove_black=remove_black,
                tolerance=tolerance,
            ):
                pixels[x, y] = (red, green, blue, 0)
    return cleaned


def remove_detected_background(
    image,
    *,
    tolerance: int = 32,
    max_colors: int = 4,
):
    tolerance = max(0, min(255, int(tolerance)))
    cleaned = image.copy()
    pixels = cleaned.load()
    colors = _detected_edge_background_colors(cleaned, max_colors=max_colors)
    if not colors:
        return cleaned

    width, height = cleaned.size
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def matches(red: int, green: int, blue: int) -> bool:
        return any(
            abs(red - color[0]) <= tolerance
            and abs(green - color[1]) <= tolerance
            and abs(blue - color[2]) <= tolerance
            for color in colors
        )

    def maybe_queue(x: int, y: int) -> None:
        index = y * width + x
        if visited[index]:
            return
        red, green, blue, alpha = pixels[x, y]
        if alpha < 16 or not matches(red, green, blue):
            return
        visited[index] = 1
        queue.append((x, y))

    for x in range(width):
        maybe_queue(x, 0)
        maybe_queue(x, height - 1)
    for y in range(1, height - 1):
        maybe_queue(0, y)
        maybe_queue(width - 1, y)

    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 16:
                continue
            if _touches_transparent_neighbor(pixels, width, height, x, y):
                maybe_queue(x, y)

    while queue:
        x, y = queue.popleft()
        red, green, blue, _alpha = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)
        if x > 0:
            maybe_queue(x - 1, y)
        if x < width - 1:
            maybe_queue(x + 1, y)
        if y > 0:
            maybe_queue(x, y - 1)
        if y < height - 1:
            maybe_queue(x, y + 1)

    return cleaned


def upscale_logo_image(
    image,
    *,
    scale_factor: int = 1,
    sharpen: bool = True,
    max_dimension: int = 4096,
):
    scale_factor = max(1, int(scale_factor))
    if scale_factor == 1:
        return image
    try:
        from PIL import Image, ImageFilter
    except ImportError as exc:
        raise RuntimeError("Logo upscaling requires Pillow.") from exc

    width = image.width * scale_factor
    height = image.height * scale_factor
    largest = max(width, height)
    if largest > max_dimension:
        scale = max_dimension / largest
        width = max(1, round(width * scale))
        height = max(1, round(height * scale))
    upscaled = image.resize((width, height), Image.Resampling.LANCZOS)
    if sharpen:
        upscaled = upscaled.filter(
            ImageFilter.UnsharpMask(radius=1.2, percent=125, threshold=3)
        )
    return upscaled


def _detected_edge_background_colors(image, *, max_colors: int) -> list[tuple[int, int, int]]:
    pixels = image.load()
    width, height = image.size
    buckets: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}

    def collect(x: int, y: int) -> None:
        red, green, blue, alpha = pixels[x, y]
        if alpha < 16:
            return
        if not (
            x == 0
            or y == 0
            or x == width - 1
            or y == height - 1
            or _touches_transparent_neighbor(pixels, width, height, x, y)
        ):
            return
        bucket = (red // 24, green // 24, blue // 24)
        buckets.setdefault(bucket, []).append((red, green, blue))

    for y in range(height):
        for x in range(width):
            collect(x, y)

    colors: list[tuple[int, int, int]] = []
    for samples in sorted(buckets.values(), key=len, reverse=True)[:max_colors]:
        colors.append(_average_rgb(samples))
    return colors


def _touches_transparent_neighbor(pixels, width: int, height: int, x: int, y: int) -> bool:
    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
        if nx < 0 or ny < 0 or nx >= width or ny >= height:
            return True
        if pixels[nx, ny][3] < 16:
            return True
    return False


def _average_rgb(samples: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    count = max(1, len(samples))
    return (
        round(sum(color[0] for color in samples) / count),
        round(sum(color[1] for color in samples) / count),
        round(sum(color[2] for color in samples) / count),
    )


def _remove_edge_connected_background(
    image,
    pixels,
    *,
    remove_white: bool,
    remove_black: bool,
    tolerance: int,
) -> None:
    width, height = image.size
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def maybe_queue(x: int, y: int) -> None:
        index = y * width + x
        if visited[index]:
            return
        red, green, blue, _alpha = pixels[x, y]
        if not _matches_background(
            red,
            green,
            blue,
            remove_white=remove_white,
            remove_black=remove_black,
            tolerance=tolerance,
        ):
            return
        visited[index] = 1
        queue.append((x, y))

    for x in range(width):
        maybe_queue(x, 0)
        maybe_queue(x, height - 1)
    for y in range(1, height - 1):
        maybe_queue(0, y)
        maybe_queue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        red, green, blue, _alpha = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)
        if x > 0:
            maybe_queue(x - 1, y)
        if x < width - 1:
            maybe_queue(x + 1, y)
        if y > 0:
            maybe_queue(x, y - 1)
        if y < height - 1:
            maybe_queue(x, y + 1)


def _matches_background(
    red: int,
    green: int,
    blue: int,
    *,
    remove_white: bool,
    remove_black: bool,
    tolerance: int,
) -> bool:
    is_white = (
        remove_white
        and red >= 255 - tolerance
        and green >= 255 - tolerance
        and blue >= 255 - tolerance
    )
    is_black = (
        remove_black
        and red <= tolerance
        and green <= tolerance
        and blue <= tolerance
    )
    return is_white or is_black


def _write_layered_psd(path: Path, composite, layers: list[RenderLayer]) -> None:
    composite = composite.convert("RGBA")
    width, height = composite.size
    records = []
    channel_data = []
    for layer in reversed(layers):
        cropped, rect = _crop_visible_layer(layer.image)
        if cropped is None:
            continue
        record, data = _psd_layer_record(layer.name, cropped, rect, layer.blend_mode)
        records.append(record)
        channel_data.append(data)

    layer_records = b"".join(records)
    layer_pixels = b"".join(channel_data)
    layer_count = struct.pack(">h", len(records))
    layer_info_data = layer_count + layer_records + layer_pixels
    if len(layer_info_data) % 2:
        layer_info_data += b"\0"

    layer_and_mask_data = (
        struct.pack(">I", len(layer_info_data))
        + layer_info_data
        + struct.pack(">I", 0)
    )
    composite_data = _raw_composite_data(composite)

    with path.open("wb") as handle:
        handle.write(b"8BPS")
        handle.write(struct.pack(">H", 1))
        handle.write(b"\0" * 6)
        handle.write(struct.pack(">HIIHH", 4, height, width, 8, 3))
        handle.write(struct.pack(">I", 0))
        handle.write(struct.pack(">I", 0))
        handle.write(struct.pack(">I", len(layer_and_mask_data)))
        handle.write(layer_and_mask_data)
        handle.write(composite_data)


def _crop_visible_layer(image):
    image = image.convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        return None, (0, 0, 0, 0)
    return image.crop(bbox), bbox


def _psd_layer_record(
    name: str,
    image,
    rect: tuple[int, int, int, int],
    blend_mode: str = "normal",
) -> tuple[bytes, bytes]:
    left, top, right, bottom = rect
    width, height = image.size
    channels = image.split()
    channel_ids = (0, 1, 2, -1)
    channel_infos = b"".join(
        struct.pack(">hI", channel_id, 2 + width * height)
        for channel_id in channel_ids
    )
    name_data = _pascal_layer_name(name)
    extra = struct.pack(">I", 0) + struct.pack(">I", 0) + name_data
    record = (
        struct.pack(">iiiiH", top, left, bottom, right, 4)
        + channel_infos
        + b"8BIM"
        + _psd_blend_mode_key(blend_mode)
        + struct.pack(">BBBBI", 255, 0, 8, 0, len(extra))
        + extra
    )
    data = b"".join(struct.pack(">H", 0) + channel.tobytes() for channel in channels)
    return record, data


def _psd_blend_mode_key(blend_mode: str) -> bytes:
    return {
        "multiply": b"mul ",
        "overlay": b"over",
    }.get(blend_mode, b"norm")


def _pascal_layer_name(name: str) -> bytes:
    encoded = name.encode("ascii", errors="replace")[:255]
    data = bytes((len(encoded),)) + encoded
    padding = (4 - (len(data) % 4)) % 4
    return data + (b"\0" * padding)


def _raw_composite_data(image) -> bytes:
    channels = image.split()
    return struct.pack(">H", 0) + b"".join(channel.tobytes() for channel in channels)
