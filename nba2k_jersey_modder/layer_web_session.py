from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import threading
import uuid

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .generator import (
    BackgroundCleanupSettings,
    TrimPlacementSettings,
    fabric_overlay_layer,
    generate_jersey_texture,
    image_placement_rects,
    jersey_background_layer,
    remove_detected_background,
    remove_image_background,
)
from .modern.document import ProjectDocument
from .modern.services import GeneratorService
from .web_editor import image_content_type


TRIM_KEYS = {
    "left_arm_hole_trim": "left_arm_hole_trim_image",
    "right_arm_hole_trim": "right_arm_hole_trim_image",
    "collar_trim": "collar_trim_image",
}
SIDE_PANEL_KEYS = {
    "left_side_panel": "left_panel_image",
    "right_side_panel": "right_panel_image",
    "shorts_left_panel": "shorts_left_panel_image",
    "shorts_right_panel": "shorts_right_panel_image",
}
WAISTBAND_KEYS = {
    "shorts_waistband_left": "waistband_image",
    "shorts_waistband_right": "waistband_image",
}


class LayerWebSession:
    """Browser layer editor adapter for the WPF project document."""

    def __init__(self, project_path: Path, state_path: Path, project_folder: Path | None = None) -> None:
        self.document = ProjectDocument.load(project_path)
        self.state_path = state_path
        self.project_folder = project_folder or project_path.parent
        self.service = GeneratorService()
        self._lock = threading.RLock()
        self._revision = 0
        self._return_requested = False
        self._paint_history: list[tuple[str, Path, Path]] = []
        self._base_paint_history: list[tuple[str, object]] = []
        self._write_state()

    def _run_on_ui_thread(self, callback):
        with self._lock:
            return callback()

    @property
    def generator(self) -> dict:
        return self.document.generator

    def _active_trim_entries(self) -> list[tuple[int, dict]]:
        result = []
        for index, item in enumerate(self.generator.get("trimPathLayers", [])):
            if not isinstance(item, dict) or not Path(str(item.get("path") or "")).exists():
                continue
            if str(item.get("garment") or "Shorts") != self.document.garment:
                continue
            if str(item.get("templateName") or self.document.template_name) != self.document.template_name:
                continue
            result.append((index, item))
        return result

    def _cleanup(self, key: str) -> BackgroundCleanupSettings:
        item = self.generator["webEditor"].get("layerCleanup", {}).get(key)
        if not isinstance(item, dict):
            item = self.generator.get("backgroundCleanup", {})
        return BackgroundCleanupSettings(
            auto_background=bool(item.get("autoBackground", False)),
            remove_white=bool(item.get("removeWhite", False)),
            remove_black=bool(item.get("removeBlack", False)),
            outside_only=bool(item.get("outsideOnly", True)),
            tolerance=_int(item.get("tolerance"), 32, 0, 255),
        )

    def _cleanup_payload(self, key: str) -> dict:
        cleanup = self._cleanup(key)
        return {
            "autoBackground": cleanup.auto_background,
            "removeWhite": cleanup.remove_white,
            "removeBlack": cleanup.remove_black,
            "outsideOnly": cleanup.outside_only,
            "tolerance": cleanup.tolerance,
            "isOverride": key in self.generator["webEditor"].get("layerCleanup", {}),
        }

    def _web_editor_project(self) -> dict:
        template = self.service.template(self.document)
        inputs = self.document.to_generator_inputs()
        waistband_boxes = [
            {"x": zone.x, "y": zone.y, "width": zone.width, "height": zone.height}
            for zone in template.zones if zone.name.startswith("shorts_waistband")
        ]
        overlays: list[dict] = []
        if jersey_background_layer(template, inputs, (2048, 2048)) is not None:
            overlays.append(self._overlay(
                "jersey_background", "Background Jersey Image", 0, 0, 2048, 2048,
                can_transform=False, can_cleanup=False, can_paint=True,
                layer_label="Background layer",
            ))

        for active_index, (_stored_index, item) in enumerate(self._active_trim_entries()):
            key = f"trim_path:{active_index}"
            overlay = self._overlay(
                key, str(item.get("name") or f"Trim Path {active_index + 1}"),
                _int(item.get("x"), 0, -8192, 8192), _int(item.get("y"), 0, -8192, 8192),
                _int(item.get("width"), 2048, 1, 8192), _int(item.get("height"), 2048, 1, 8192),
                rotation=_float(item.get("rotationDegrees"), 0, -360, 360),
                can_rotate=True, can_cleanup=False, can_reorder=True,
                can_paint=False,
                lock_aspect=False, exclude_boxes=waistband_boxes,
                layer_label=f"Trim path layer {active_index + 1}",
            )
            overlays.append(overlay)

        placements = sorted(
            image_placement_rects(template, inputs),
            key=lambda value: 0 if value.key in SIDE_PANEL_KEYS else 1 if value.key in WAISTBAND_KEYS else 2,
        )
        for placement in placements:
            key = placement.key
            is_trim = key in TRIM_KEYS
            is_side = key in SIDE_PANEL_KEYS
            is_waistband = key in WAISTBAND_KEYS
            is_logo = key.startswith("logo:")
            can_lock_aspect = key == "front_wordmark" or is_logo
            if key == "front_wordmark":
                lock_aspect = self.generator["frontWordmark"].get("lockAspect", True) is not False
            elif is_logo:
                logo_index = _int(key.split(":", 1)[1], -1, -1, 9999)
                logos = self.generator.get("logos", [])
                lock_aspect = not (0 <= logo_index < len(logos) and logos[logo_index].get("lockAspect", True) is False)
            else:
                lock_aspect = not (is_side or is_waistband)
            guide = None
            clip = None
            if placement.clip_x is not None:
                box = {"x": placement.clip_x, "y": placement.clip_y, "width": placement.clip_width, "height": placement.clip_height}
                guide, clip = (box, None) if is_side else (None, box)
            item = self._overlay(
                key, placement.label, placement.x, placement.y, placement.width, placement.height,
                rotation=placement.rotation_degrees, can_rotate=is_side, can_flip=is_trim,
                flip_x=bool(self.generator["trimPlacements"].get(key, {}).get("flipX", False)) if is_trim else False,
                can_reorder=is_logo, lock_aspect=lock_aspect, can_lock_aspect=can_lock_aspect,
                can_paint=key == "front_wordmark" or is_logo or is_trim or is_side or is_waistband,
                clip_box=clip, guide_box=guide,
                layer_label=("Top layer" if key == "front_wordmark" else "Side panel layer" if is_side else "Waistband image layer" if is_waistband else "Trim layer" if is_trim else "Logo layer" if is_logo else "Layer"),
            )
            overlays.append(item)

        fabric = fabric_overlay_layer(template, inputs, (2048, 2048))
        if fabric is not None:
            item = self._overlay("fabric_overlay", "Fabric / Wrinkle Overlay", 0, 0, 2048, 2048,
                                 can_transform=False, can_cleanup=False, can_reorder=True,
                                 layer_label=f"{fabric.blend_mode.title()} layer")
            item["blendMode"] = fabric.blend_mode
            overlays.append(item)

        overlays = self._order_layers(overlays)
        uv = self.generator["uvOverlay"]
        uv_path = self.service.uv_path(self.document)
        return {
            "textureSize": 2048,
            "baseUrl": "/api/base.png",
            "uvOverlay": {"available": uv_path.exists(), "imageUrl": "/api/uv.png", "enabled": bool(uv.get("enabled", True)), "opacity": _int(uv.get("opacity"), 45, 0, 100)},
            "canUndoBasePaint": bool(self._base_paint_history),
            "overlays": overlays,
        }

    def _overlay(self, key: str, label: str, x: int, y: int, width: int, height: int, *,
                 rotation: float = 0, can_transform: bool = True, can_rotate: bool = False,
                 can_flip: bool = False, flip_x: bool = False, can_cleanup: bool = True,
                 can_reorder: bool = False, lock_aspect: bool = True,
                 can_lock_aspect: bool = False, clip_box=None,
                 guide_box=None, exclude_boxes=None, can_paint: bool = False,
                 layer_label="Layer") -> dict:
        return {
            "key": key, "label": label, "x": x, "y": y, "width": width, "height": height,
            "imageUrl": f"/api/image/{key}", "blendMode": "normal", "lockX": False,
            "lockWidth": False, "lockAspect": lock_aspect, "canLockAspect": can_lock_aspect,
            "canTransform": can_transform,
            "canRotate": can_rotate, "rotation": rotation, "canFlip": can_flip, "flipX": flip_x,
            "clipBox": clip_box, "guideBox": guide_box, "excludeBoxes": exclude_boxes or [],
            "canCleanup": can_cleanup, "cleanup": self._cleanup_payload(key),
            "canPaint": can_paint,
            "canUndoPaint": any(history_key == key for history_key, _old, _new in self._paint_history),
            "canReorder": can_reorder, "layerLabel": layer_label,
        }

    def _order_layers(self, overlays: list[dict]) -> list[dict]:
        top = [item for item in overlays if item["key"] == "front_wordmark"]
        fixed = [item for item in overlays if item["key"] != "front_wordmark" and not item.get("canReorder")]
        movable = [item for item in overlays if item["key"] != "front_wordmark" and item.get("canReorder")]
        current = [item["key"] for item in movable]
        saved = [key for key in self.generator["webEditor"].get("layerOrder", []) if key in current]
        saved.extend(key for key in current if key not in saved)
        by_key = {item["key"]: item for item in movable}
        ordered = fixed + [by_key[key] for key in saved]
        ordered.extend(top)
        return ordered

    def _web_editor_base_png(self) -> bytes:
        inputs = replace(
            self.document.to_generator_inputs(), left_panel_image=None, right_panel_image=None,
            waistband_image=None, jersey_background_image=None, front_wordmark_image=None,
            left_arm_hole_trim_image=None, right_arm_hole_trim_image=None, collar_trim_image=None,
            logo_placements=(), trim_path_layers=(), fabric_overlay_image=None, fabric_overlay_opacity=0,
        )
        output = self.state_path.parent / "base.png"
        generate_jersey_texture(self.service.template(self.document), inputs, output)
        return output.read_bytes()

    def _web_editor_region_png(self) -> bytes:
        image = self.service.render_texture(self.document, "Region Texture") if self.document.garment == "Jersey" else self.service.render_color(self.document)
        return _png_bytes(image)

    def _web_editor_uv_png(self) -> bytes:
        path = self.service.uv_path(self.document)
        if not path.exists(): raise FileNotFoundError("No UV map is available for this template.")
        return path.read_bytes()

    def _web_editor_image(self, key: str) -> tuple[bytes, str]:
        path: Path | None = None
        if key.startswith("trim_path:"):
            active = _int(key.split(":", 1)[1], -1, -1, 9999)
            entries = self._active_trim_entries()
            path = Path(str(entries[active][1].get("path"))) if 0 <= active < len(entries) else None
        elif key == "jersey_background":
            layer = jersey_background_layer(self.service.template(self.document), self.document.to_generator_inputs(), (2048, 2048))
            if layer is None: raise FileNotFoundError("No background jersey image is active.")
            return _png_bytes(layer.image), "image/png"
        elif key == "fabric_overlay":
            layer = fabric_overlay_layer(self.service.template(self.document), self.document.to_generator_inputs(), (2048, 2048))
            if layer is None: raise FileNotFoundError("No fabric overlay is active.")
            return _png_bytes(layer.image), "image/png"
        elif key == "front_wordmark":
            path = _path(self.generator["images"].get("front_wordmark_image"))
        elif key.startswith("logo:"):
            index = _int(key.split(":", 1)[1], -1, -1, 9999)
            logos = self.generator.get("logos", [])
            path = _path(logos[index].get("path")) if 0 <= index < len(logos) else None
        else:
            image_key = TRIM_KEYS.get(key) or SIDE_PANEL_KEYS.get(key) or WAISTBAND_KEYS.get(key)
            path = _path(self.generator["images"].get(image_key)) if image_key else None
        if path is None or not path.exists(): raise FileNotFoundError(f"No image found for {key}.")
        if key.startswith("trim_path:"): return path.read_bytes(), image_content_type(path)
        cleanup = self._cleanup(key)
        flip = bool(self.generator["trimPlacements"].get(key, {}).get("flipX", False)) if key in TRIM_KEYS else False
        if not (cleanup.auto_background or cleanup.remove_white or cleanup.remove_black or flip):
            return path.read_bytes(), image_content_type(path)
        image = Image.open(path).convert("RGBA")
        if cleanup.auto_background: image = remove_detected_background(image, tolerance=cleanup.tolerance)
        image = remove_image_background(image, remove_white=cleanup.remove_white, remove_black=cleanup.remove_black,
                                        outside_only=cleanup.outside_only, tolerance=cleanup.tolerance)
        if flip: image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        return _png_bytes(image), "image/png"

    def _web_editor_update(self, payload: dict) -> dict | None:
        key = str(payload.get("key") or "")
        x, y = float(payload.get("x", 0)), float(payload.get("y", 0))
        width, height = max(1, float(payload.get("width", 1))), max(1, float(payload.get("height", 1)))
        rotation = _float(payload.get("rotation"), 0, -360, 360)
        if key.startswith("trim_path:"):
            active = _int(key.split(":", 1)[1], -1, -1, 9999)
            entries = self._active_trim_entries()
            if not 0 <= active < len(entries): return None
            item = entries[active][1]
            item.update({"x": round(x), "y": round(y), "width": round(width), "height": round(height), "rotationDegrees": rotation})
            self._write_state()
            return {"x": round(x), "y": round(y), "width": round(width), "height": round(height), "rotation": rotation}

        current = next((item for item in image_placement_rects(self.service.template(self.document), self.document.to_generator_inputs()) if item.key == key), None)
        if current is None: return None
        dx, dy = round(x - current.x), round(y - current.y)
        saved_lock_aspect = None
        if key == "front_wordmark":
            item = self.generator["frontWordmark"]
            saved_lock_aspect = payload.get("lockAspect", item.get("lockAspect", True)) is not False
            item["lockAspect"] = saved_lock_aspect
            item["offsetX"] = _int(item.get("offsetX"), 0, -9999, 9999) + dx
            item["offsetY"] = _int(item.get("offsetY"), 0, -9999, 9999) + dy
            item["scaleWidthPercent"] = _scaled(item.get("scaleWidthPercent", item.get("scalePercent", 100)), width, current.width)
            item["scaleHeightPercent"] = _scaled(item.get("scaleHeightPercent", item.get("scalePercent", 100)), height, current.height)
        elif key.startswith("logo:"):
            index = _int(key.split(":", 1)[1], -1, -1, 9999)
            logos = self.generator.get("logos", [])
            if not 0 <= index < len(logos): return None
            item = logos[index]
            saved_lock_aspect = payload.get("lockAspect", item.get("lockAspect", True)) is not False
            item["lockAspect"] = saved_lock_aspect
            item["offsetX"] = _int(item.get("offsetX"), 0, -9999, 9999) + dx
            item["offsetY"] = _int(item.get("offsetY"), 0, -9999, 9999) + dy
            item["scaleWidthPercent"] = _scaled(item.get("scaleWidthPercent", item.get("scalePercent", 100)), width, current.width)
            item["scaleHeightPercent"] = _scaled(item.get("scaleHeightPercent", item.get("scalePercent", 100)), height, current.height)
        else:
            item = self.generator["trimPlacements"].setdefault(key, {})
            item["offsetX"] = _int(item.get("offsetX"), 0, -9999, 9999) + dx
            item["offsetY"] = _int(item.get("offsetY"), 0, -9999, 9999) + dy
            if key in SIDE_PANEL_KEYS or key in WAISTBAND_KEYS:
                item["scaleWidthPercent"] = _scaled(item.get("scaleWidthPercent", item.get("scalePercent", 100)), width, current.width)
                item["scaleHeightPercent"] = _scaled(item.get("scaleHeightPercent", item.get("scalePercent", 100)), height, current.height)
                item["overrideWidth"] = round(width)
                item["overrideHeight"] = round(height)
                item["rotationDegrees"] = rotation
            else:
                item["scalePercent"] = _scaled(item.get("scalePercent", 100), width, current.width)
        self._write_state()
        updated = next((item for item in image_placement_rects(self.service.template(self.document), self.document.to_generator_inputs()) if item.key == key), None)
        if updated is None:
            return None
        result = {"x": updated.x, "y": updated.y, "width": updated.width,
                  "height": updated.height, "rotation": updated.rotation_degrees}
        if saved_lock_aspect is not None:
            result["lockAspect"] = saved_lock_aspect
        return result

    def _web_editor_reorder(self, payload: dict) -> None:
        key, direction = str(payload.get("key") or ""), str(payload.get("direction") or "")
        current = [f"trim_path:{index}" for index, _ in enumerate(self._active_trim_entries())]
        current.extend(f"logo:{index}" for index, _ in enumerate(self.generator.get("logos", [])))
        saved = [entry for entry in self.generator["webEditor"].get("layerOrder", []) if entry in current]
        saved.extend(entry for entry in current if entry not in saved)
        if key not in saved: return
        index = saved.index(key); target = index + (1 if direction == "up" else -1)
        if not 0 <= target < len(saved): return
        saved[index], saved[target] = saved[target], saved[index]
        self.generator["webEditor"]["layerOrder"] = saved
        self._write_state()

    def _web_editor_transparency(self, payload: dict) -> None:
        key = str(payload.get("key") or "")
        cleanup = self.generator["webEditor"].setdefault("layerCleanup", {})
        if payload.get("clearOverride"): cleanup.pop(key, None)
        else: cleanup[key] = {name: payload.get(name) for name in ("autoBackground", "removeWhite", "removeBlack", "outsideOnly", "tolerance")}
        self._write_state()

    def _web_editor_paint(self, payload: dict) -> dict:
        key = str(payload.get("key") or "")
        color = _hex_color(payload.get("color"))
        if key == "base_colors":
            return self._paint_base_color(payload, color)
        source = self._source_path(key)
        if source is None:
            return {"changed": False, "message": "The selected layer cannot be painted."}
        tolerance = _int(payload.get("tolerance"), 24, 0, 255)
        normalized_x = _float(payload.get("x"), 0.5, 0.0, 1.0)
        normalized_y = _float(payload.get("y"), 0.5, 0.0, 1.0)
        if key in TRIM_KEYS and bool(self.generator["trimPlacements"].get(key, {}).get("flipX", False)):
            normalized_x = 1.0 - normalized_x

        with Image.open(source) as opened:
            image = opened.convert("RGBA")
        if key == "jersey_background" and bool(self.generator["jerseyBackground"].get("tile", False)):
            tile_scale = _int(self.generator["jerseyBackground"].get("tileScalePercent"), 100, 10, 200)
            tile_width = max(1, round(image.width * tile_scale / 100))
            tile_height = max(1, round(image.height * tile_scale / 100))
            rendered_x = normalized_x * 2048
            rendered_y = normalized_y * 2048
            normalized_x = (rendered_x % tile_width) / tile_width
            normalized_y = (rendered_y % tile_height) / tile_height
        seed = (
            min(image.width - 1, max(0, round(normalized_x * (image.width - 1)))),
            min(image.height - 1, max(0, round(normalized_y * (image.height - 1)))),
        )
        seed_pixel = image.getpixel(seed)
        if seed_pixel[3] < 8:
            return {"changed": False, "message": "That point is transparent. Click inside a colored area."}
        replacement = (*color, seed_pixel[3])
        if seed_pixel == replacement:
            return {"changed": False, "message": "That area already uses the selected color."}
        ImageDraw.floodfill(image, seed, replacement, thresh=tolerance)

        output_dir = source.parent / "painted"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{source.stem}_paint_{uuid.uuid4().hex[:8]}.png"
        image.save(output, "PNG", compress_level=1)
        self._set_source_path(key, output)
        self._paint_history.append((key, source, output))
        self._write_state()
        return {"changed": True, "path": str(output), "label": self._paint_label(key)}

    def _web_editor_undo_paint(self, payload: dict) -> dict:
        key = str(payload.get("key") or "")
        if key == "base_colors":
            if not self._base_paint_history:
                return {"ok": False, "message": "No base color fill is available to undo."}
            kind, previous = self._base_paint_history.pop()
            if kind == "raster":
                previous_path = str(previous)
                self.generator["paintFillLayers"] = [
                    item for item in self.generator.get("paintFillLayers", [])
                    if not isinstance(item, dict) or str(item.get("path") or "") != previous_path
                ]
            else:
                color_key, previous_color = previous
                self.generator["colors"][str(color_key)] = str(previous_color)
            self._write_state()
            return {"ok": True}
        for index in range(len(self._paint_history) - 1, -1, -1):
            history_key, previous, _painted = self._paint_history[index]
            if history_key != key:
                continue
            self._paint_history.pop(index)
            self._set_source_path(key, previous)
            self._write_state()
            return {"ok": True}
        return {"ok": False, "message": "No Paint Bucket change is available to undo for this layer."}

    def _paint_base_color(self, payload: dict, color: tuple[int, int, int]) -> dict:
        if self._active_trim_entries():
            return self._paint_raster_region(payload, color)
        normalized_x = _float(payload.get("x"), 0.5, 0.0, 1.0)
        normalized_y = _float(payload.get("y"), 0.5, 0.0, 1.0)
        template = self.service.template(self.document)
        design_width = max(2048, max((zone.x + zone.width for zone in template.zones), default=2048))
        design_height = max(2048, max((zone.y + zone.height for zone in template.zones), default=2048))
        point_x = normalized_x * design_width
        point_y = normalized_y * design_height
        matching = [
            zone for zone in template.zones
            if _color_key_for_zone(zone.name) is not None
            and zone.x <= point_x <= zone.x + zone.width
            and zone.y <= point_y <= zone.y + zone.height
        ]
        if not matching:
            return {"changed": False, "message": "No editable color zone is under that point."}
        zone = max(matching, key=lambda item: item.layer)
        color_key = _color_key_for_zone(zone.name)
        if color_key is None:
            return {"changed": False, "message": "That template area is not paintable."}
        value = "#{:02x}{:02x}{:02x}".format(*color)
        previous = str(self.generator["colors"].get(color_key) or "")
        if previous.lower() == value:
            return {"changed": False, "message": "That area already uses the selected color."}
        self._base_paint_history.append(("color", (color_key, previous)))
        self.generator["colors"][color_key] = value
        self._write_state()
        return {"changed": True, "label": _paint_zone_label(zone.name)}

    def _paint_raster_region(self, payload: dict, color: tuple[int, int, int]) -> dict:
        normalized_x = _float(payload.get("x"), 0.5, 0.0, 1.0)
        normalized_y = _float(payload.get("y"), 0.5, 0.0, 1.0)
        tolerance = min(96, _int(payload.get("tolerance"), 24, 0, 255))
        composite = self.service.render_color(self.document).convert("RGBA")
        seed = (
            min(composite.width - 1, max(0, round(normalized_x * (composite.width - 1)))),
            min(composite.height - 1, max(0, round(normalized_y * (composite.height - 1)))),
        )
        template = self.service.template(self.document)
        design_width = max(2048, max((zone.x + zone.width for zone in template.zones), default=2048))
        design_height = max(2048, max((zone.y + zone.height for zone in template.zones), default=2048))
        point_x = normalized_x * design_width
        point_y = normalized_y * design_height
        matching = [
            zone for zone in template.zones
            if _color_key_for_zone(zone.name) is not None
            and zone.x <= point_x <= zone.x + zone.width
            and zone.y <= point_y <= zone.y + zone.height
        ]
        if not matching:
            return {"changed": False, "message": "No editable color zone is under that point."}
        zone = max(matching, key=lambda item: item.layer)
        color_key = _color_key_for_zone(zone.name)
        allowed = Image.new("L", composite.size, 0)
        allowed_draw = ImageDraw.Draw(allowed)
        for candidate in template.zones:
            if _color_key_for_zone(candidate.name) != color_key:
                continue
            allowed_draw.rectangle((
                round(candidate.x * composite.width / design_width),
                round(candidate.y * composite.height / design_height),
                round((candidate.x + candidate.width) * composite.width / design_width),
                round((candidate.y + candidate.height) * composite.height / design_height),
            ), fill=255)

        barrier = ImageChops.lighter(
            self._trim_path_barrier_mask(composite.size),
            allowed.point(lambda value: 255 - value),
        )
        if barrier.getpixel(seed) >= 8:
            return {"changed": False, "message": "Click beside the trim path, not directly on its edge."}

        seed_pixel = composite.getpixel(seed)
        barrier_color = tuple(255 if channel < 128 else 0 for channel in seed_pixel[:3]) + (255,)
        working = composite.copy()
        working.paste(barrier_color, (0, 0), barrier)
        prepared = working.copy()
        marker = (
            (seed_pixel[0] + 113) % 256,
            (seed_pixel[1] + 71) % 256,
            (seed_pixel[2] + 157) % 256,
            255,
        )
        ImageDraw.floodfill(working, seed, marker, thresh=tolerance)
        difference = ImageChops.difference(prepared, working).convert("L")
        mask = difference.point(lambda value: 255 if value else 0)
        safe_area = barrier.point(lambda value: 0 if value >= 128 else 255)
        for _step in range(3):
            mask = ImageChops.multiply(mask.filter(ImageFilter.MaxFilter(3)), safe_area)
        if mask.getbbox() is None:
            return {"changed": False, "message": "No connected area could be filled."}

        overlay = Image.new("RGBA", composite.size, (*color, 0))
        overlay.putalpha(mask)
        output_dir = self.project_folder / "assets" / "paint"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{self.document.garment.lower()}_paint_{uuid.uuid4().hex[:8]}.png"
        overlay.save(output, "PNG", compress_level=1)
        item = {
            "path": str(output),
            "name": f"{_paint_zone_label(zone.name)} Paint Fill",
            "garment": self.document.garment,
            "templateName": self.document.template_name,
        }
        self.generator.setdefault("paintFillLayers", []).append(item)
        self._base_paint_history.append(("raster", output))
        self._write_state()
        return {"changed": True, "label": item["name"]}

    def _trim_path_barrier_mask(self, size: tuple[int, int]) -> Image.Image:
        mask = Image.new("L", size, 0)
        scale_x = size[0] / 2048
        scale_y = size[1] / 2048
        for _index, item in self._active_trim_entries():
            path = Path(str(item.get("path") or ""))
            if not path.exists():
                continue
            with Image.open(path) as opened:
                alpha = opened.convert("RGBA").getchannel("A")
            target_width = max(1, round(_int(item.get("width"), 2048, 1, 8192) * scale_x))
            target_height = max(1, round(_int(item.get("height"), 2048, 1, 8192) * scale_y))
            alpha = alpha.resize((target_width, target_height), Image.Resampling.LANCZOS)
            x = round(_int(item.get("x"), 0, -8192, 8192) * scale_x)
            y = round(_int(item.get("y"), 0, -8192, 8192) * scale_y)
            rotation = _float(item.get("rotationDegrees"), 0, -360, 360)
            if rotation:
                center_x = x + alpha.width / 2
                center_y = y + alpha.height / 2
                alpha = alpha.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
                x = round(center_x - alpha.width / 2)
                y = round(center_y - alpha.height / 2)
            placed = Image.new("L", size, 0)
            placed.paste(alpha, (x, y))
            mask = ImageChops.lighter(mask, placed)

        template = self.service.template(self.document)
        design_width = max(2048, max((zone.x + zone.width for zone in template.zones), default=2048))
        design_height = max(2048, max((zone.y + zone.height for zone in template.zones), default=2048))
        draw = ImageDraw.Draw(mask)
        for zone in template.zones:
            if not zone.name.startswith("shorts_waistband"):
                continue
            draw.rectangle((
                round(zone.x * size[0] / design_width),
                round(zone.y * size[1] / design_height),
                round((zone.x + zone.width) * size[0] / design_width),
                round((zone.y + zone.height) * size[1] / design_height),
            ), fill=0)
        # Close one-pixel breaks without growing the visible barrier outward.
        # Low-alpha edge pixels remain paintable because the trim is composited
        # above this fill layer and supplies its own antialiasing.
        binary = mask.point(lambda value: 255 if value >= 64 else 0)
        return binary.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))

    @staticmethod
    def _paint_label(key: str) -> str:
        if key == "jersey_background":
            return "Background Jersey Image"
        if key == "front_wordmark":
            return "Front Wordmark"
        if key.startswith("logo:"):
            return "Logo"
        return key.replace("_", " ").title()

    def _source_path(self, key: str) -> Path | None:
        if key == "jersey_background":
            return _path(self.generator["images"].get("jersey_background_image"))
        if key == "front_wordmark":
            return _path(self.generator["images"].get("front_wordmark_image"))
        if key.startswith("logo:"):
            index = _int(key.split(":", 1)[1], -1, -1, 9999)
            logos = self.generator.get("logos", [])
            return _path(logos[index].get("path")) if 0 <= index < len(logos) else None
        image_key = TRIM_KEYS.get(key) or SIDE_PANEL_KEYS.get(key) or WAISTBAND_KEYS.get(key)
        return _path(self.generator["images"].get(image_key)) if image_key else None

    def _set_source_path(self, key: str, path: Path) -> None:
        if key == "jersey_background":
            self.generator["images"]["jersey_background_image"] = str(path)
            return
        if key == "front_wordmark":
            self.generator["images"]["front_wordmark_image"] = str(path)
            return
        if key.startswith("logo:"):
            index = _int(key.split(":", 1)[1], -1, -1, 9999)
            logos = self.generator.get("logos", [])
            if not 0 <= index < len(logos):
                raise ValueError("The selected logo no longer exists.")
            logos[index]["path"] = str(path)
            return
        image_key = TRIM_KEYS.get(key) or SIDE_PANEL_KEYS.get(key) or WAISTBAND_KEYS.get(key)
        if not image_key:
            raise ValueError("The selected layer cannot be painted.")
        self.generator["images"][image_key] = str(path)

    def _web_editor_flip(self, payload: dict) -> None:
        key = str(payload.get("key") or "")
        if key not in TRIM_KEYS: return
        item = self.generator["trimPlacements"].setdefault(key, {})
        item["flipX"] = not bool(item.get("flipX", False))
        self._write_state()

    def _web_editor_reset(self) -> None:
        self.generator["frontWordmark"].update({"offsetX": 0, "offsetY": 0, "scalePercent": 100, "scaleWidthPercent": 100, "scaleHeightPercent": 100, "lockAspect": True})
        for logo in self.generator.get("logos", []):
            logo.update({"offsetX": 0, "offsetY": 0, "scalePercent": 100, "scaleWidthPercent": 100, "scaleHeightPercent": 100, "lockAspect": True})
        self.generator["trimPlacements"] = {}
        for item in self.generator.get("trimPathLayers", []):
            item.update({"x": item.get("defaultX", 0), "y": item.get("defaultY", 0), "width": item.get("defaultWidth", 2048), "height": item.get("defaultHeight", 2048), "rotationDegrees": 0})
        self.generator["webEditor"] = {"layerOrder": [], "layerCleanup": {}}
        self._write_state()

    def _web_editor_return(self) -> None:
        self._return_requested = True
        self._write_state()

    def _write_state(self) -> None:
        self._revision += 1
        payload = {"revision": self._revision, "returnRequested": self._return_requested, "project": self.document.clone_payload()}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(self.state_path)


def _png_bytes(image) -> bytes:
    stream = BytesIO(); image.save(stream, "PNG"); return stream.getvalue()


def _path(value) -> Path | None:
    path = Path(str(value)) if value else None
    return path if path and path.exists() else None


def _int(value, default: int, minimum: int, maximum: int) -> int:
    try: parsed = int(float(value))
    except (TypeError, ValueError): parsed = default
    return max(minimum, min(maximum, parsed))


def _float(value, default: float, minimum: float, maximum: float) -> float:
    try: parsed = float(value)
    except (TypeError, ValueError): parsed = default
    return max(minimum, min(maximum, parsed))


def _scaled(current, requested: float, rendered: int) -> int:
    return _int(round(float(current or 100) * requested / max(1, rendered)), 100, 1, 500)


def _hex_color(value: object) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        raise ValueError("Choose a valid six-digit paint color.")
    try:
        return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError as exc:
        raise ValueError("Choose a valid six-digit paint color.") from exc


def _color_key_for_zone(name: str) -> str | None:
    if name.startswith("shorts_waistband"):
        return "waistband_color"
    if name == "shorts_left_panel":
        return "shorts_left_panel_color"
    if name == "shorts_right_panel":
        return "shorts_right_panel_color"
    if name.startswith("front_jersey_base"):
        return "front_color"
    if name.startswith("back_jersey_base"):
        return "back_color"
    return {
        "left_side_panel": "left_panel_color",
        "right_side_panel": "right_panel_color",
        "collar_background": "collar_background_color",
        "left_arm_hole_trim": "left_arm_hole_trim_color",
        "right_arm_hole_trim": "right_arm_hole_trim_color",
        "collar_trim": "collar_trim_color",
    }.get(name)


def _paint_zone_label(name: str) -> str:
    if name.startswith("front_jersey_base"):
        return "Front Base"
    if name.startswith("back_jersey_base"):
        return "Back Base"
    return name.replace("shorts_", "").replace("_", " ").title()
