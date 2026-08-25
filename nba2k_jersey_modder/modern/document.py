from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from .. import __app_name__
from ..generator import (
    BackgroundCleanupSettings,
    GeneratorInputs,
    LogoPlacement,
    TrimPathLayer,
    TrimPlacementSettings,
)


GENERATOR_DEFAULT_COLORS = {
    "front_color": "#ffffff",
    "back_color": "#ffffff",
    "left_panel_color": "",
    "right_panel_color": "",
    "collar_background_color": "#ffffff",
    "waistband_color": "#ffffff",
    "left_arm_hole_trim_color": "#ffffff",
    "right_arm_hole_trim_color": "#ffffff",
    "collar_trim_color": "#ffffff",
}
GENERATOR_IMAGE_KEYS = (
    "left_panel_image", "right_panel_image", "shorts_left_panel_image",
    "shorts_right_panel_image", "waistband_image", "jersey_background_image",
    "front_wordmark_image", "left_arm_hole_trim_image",
    "right_arm_hole_trim_image", "collar_trim_image",
)


def new_project_payload() -> dict:
    return {
        "app": __app_name__, "projectVersion": 2,
        "generator": {
            "garment": "Jersey", "jerseyCut": "Retro U",
            "shortsTemplate": "Retro shorts",
            "colors": dict(GENERATOR_DEFAULT_COLORS),
            "images": {key: None for key in GENERATOR_IMAGE_KEYS},
            "frontWordmark": {"offsetX": 0, "offsetY": 0, "scalePercent": 100,
                              "scaleWidthPercent": 100, "scaleHeightPercent": 100},
            "jerseyBackground": {"tile": False, "tileScalePercent": 100},
            "logos": [], "trimPathLayers": [], "trimPlacements": {},
            "backgroundCleanup": {"removeWhite": False, "removeBlack": False,
                                  "outsideOnly": True, "tolerance": 32},
            "fabricOverlay": {"preset": "None", "customPath": None,
                              "blendMode": "multiply", "opacity": 0},
            "uvOverlay": {"enabled": True, "opacity": 45},
            "numberPreview": {"enabled": True, "text": "15", "x": 1160,
                              "y": 780, "scale": 100, "scaleWidth": 100,
                              "scaleHeight": 100},
            "webEditor": {"layerOrder": [], "layerCleanup": {}},
        },
    }


class ProjectDocument:
    """Version-tolerant state shared by all modern pages."""

    def __init__(self, payload: dict | None = None, path: Path | None = None) -> None:
        self.payload = self._normalize(payload or new_project_payload())
        self.path = path

    @property
    def generator(self) -> dict:
        return self.payload["generator"]

    @property
    def garment(self) -> str:
        return str(self.generator.get("garment") or "Jersey")

    @property
    def template_name(self) -> str:
        key = "shortsTemplate" if self.garment == "Shorts" else "jerseyCut"
        fallback = "Retro shorts" if self.garment == "Shorts" else "Retro U"
        return str(self.generator.get(key) or fallback)

    def clone_payload(self) -> dict:
        return deepcopy(self.payload)

    def save(self, path: Path | None = None) -> Path:
        destination = path or self.path
        if destination is None:
            raise ValueError("Choose a project file first.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.payload, indent=2), encoding="utf-8")
        self.path = destination
        return destination

    @classmethod
    def load(cls, path: Path) -> "ProjectDocument":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Project file must contain a JSON object.")
        return cls(payload, path)

    def to_generator_inputs(self) -> GeneratorInputs:
        g = self.generator
        colors, images = g["colors"], g["images"]
        wordmark, background = g["frontWordmark"], g["jerseyBackground"]
        cleanup, fabric, web = g["backgroundCleanup"], g["fabricOverlay"], g["webEditor"]
        garment = self.garment
        left_key = "shorts_left_panel_image" if garment == "Shorts" else "left_panel_image"
        right_key = "shorts_right_panel_image" if garment == "Shorts" else "right_panel_image"
        collar_key = "waistband_color" if garment == "Shorts" else "collar_background_color"
        logos = tuple(_logo(item) for item in g.get("logos", []) if _valid_path_item(item))
        trims = tuple(
            _trim_path(item) for item in g.get("trimPathLayers", [])
            if _valid_path_item(item)
            and str(item.get("garment") or "Shorts") == garment
            and str(item.get("templateName") or self.template_name) == self.template_name
        )
        placements = {
            str(key): _trim_placement(item)
            for key, item in g.get("trimPlacements", {}).items() if isinstance(item, dict)
        }
        layer_cleanup = {
            str(key): BackgroundCleanupSettings(
                auto_background=bool(item.get("autoBackground", False)),
                remove_white=bool(item.get("removeWhite", False)),
                remove_black=bool(item.get("removeBlack", False)),
                outside_only=bool(item.get("outsideOnly", True)),
                tolerance=_int(item.get("tolerance"), 32, 0, 255),
            ) for key, item in web.get("layerCleanup", {}).items() if isinstance(item, dict)
        }
        return GeneratorInputs(
            front_color=str(colors.get("front_color") or "#ffffff"),
            back_color=str(colors.get("back_color") or "#ffffff"),
            left_panel_color=str(colors.get("left_panel_color") or ""),
            right_panel_color=str(colors.get("right_panel_color") or ""),
            collar_background_color=str(colors.get(collar_key) or "#ffffff"),
            left_arm_hole_trim_color=str(colors.get("left_arm_hole_trim_color") or "#ffffff"),
            right_arm_hole_trim_color=str(colors.get("right_arm_hole_trim_color") or "#ffffff"),
            collar_trim_color=str(colors.get("collar_trim_color") or "#ffffff"),
            left_panel_image=_path(images.get(left_key)), right_panel_image=_path(images.get(right_key)),
            waistband_image=_path(images.get("waistband_image")),
            jersey_background_image=_path(images.get("jersey_background_image")) if garment == "Jersey" else None,
            jersey_background_tile=bool(background.get("tile", False)) if garment == "Jersey" else False,
            jersey_background_tile_scale_percent=_int(background.get("tileScalePercent"), 100, 10, 200),
            front_wordmark_image=_path(images.get("front_wordmark_image")) if garment == "Jersey" else None,
            left_arm_hole_trim_image=_path(images.get("left_arm_hole_trim_image")) if garment == "Jersey" else None,
            right_arm_hole_trim_image=_path(images.get("right_arm_hole_trim_image")) if garment == "Jersey" else None,
            collar_trim_image=_path(images.get("collar_trim_image")) if garment == "Jersey" else None,
            front_wordmark_offset_x=_int(wordmark.get("offsetX"), 0, -9999, 9999),
            front_wordmark_offset_y=_int(wordmark.get("offsetY"), 0, -9999, 9999),
            front_wordmark_scale_percent=_int(wordmark.get("scalePercent"), 100, 1, 500),
            front_wordmark_scale_width_percent=_int(wordmark.get("scaleWidthPercent"), 100, 1, 500),
            front_wordmark_scale_height_percent=_int(wordmark.get("scaleHeightPercent"), 100, 1, 500),
            logo_placements=logos, trim_path_layers=trims,
            fabric_overlay_image=_path(fabric.get("customPath")),
            fabric_overlay_opacity=_int(fabric.get("opacity"), 0, 0, 100),
            fabric_overlay_blend_mode=str(fabric.get("blendMode") or "multiply"),
            dynamic_layer_order=tuple(str(key) for key in web.get("layerOrder", [])),
            layer_background_cleanup=layer_cleanup, trim_placements=placements,
            remove_white_background=bool(cleanup.get("removeWhite", False)),
            remove_black_background=bool(cleanup.get("removeBlack", False)),
            remove_outside_background_only=bool(cleanup.get("outsideOnly", True)),
            background_tolerance=_int(cleanup.get("tolerance"), 32, 0, 255),
        )

    @staticmethod
    def _normalize(payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("Project data must be an object.")
        result, defaults = deepcopy(payload), new_project_payload()
        generator = result.setdefault("generator", {})
        if not isinstance(generator, dict):
            raise ValueError("Project file is missing generator data.")
        for key, value in defaults["generator"].items():
            if key not in generator:
                generator[key] = deepcopy(value)
            elif isinstance(value, dict) and isinstance(generator[key], dict):
                for child, child_value in value.items():
                    generator[key].setdefault(child, deepcopy(child_value))
        if generator.get("garment") not in {"Jersey", "Shorts"}:
            generator["garment"] = "Jersey"
        result.setdefault("app", __app_name__)
        result["projectVersion"] = max(2, _int(result.get("projectVersion"), 2, 1, 999))
        return result


def _path(value: object) -> Path | None:
    path = Path(str(value)) if value else None
    return path if path and path.exists() else None


def _valid_path_item(item: object) -> bool:
    return isinstance(item, dict) and _path(item.get("path")) is not None


def _int(value: object, default: int, minimum: int, maximum: int) -> int:
    try: parsed = int(float(value))
    except (TypeError, ValueError): parsed = default
    return max(minimum, min(maximum, parsed))


def _optional(value: object, minimum: int, maximum: int) -> int | None:
    return None if value is None else _int(value, minimum, minimum, maximum)


def _float(value: object, default: float, minimum: float, maximum: float) -> float:
    try: parsed = float(value)
    except (TypeError, ValueError): parsed = default
    return max(minimum, min(maximum, parsed))


def _logo(item: dict) -> LogoPlacement:
    return LogoPlacement(_path(item["path"]), str(item.get("targetName") or "front_center_chest_logo"),
                         _int(item.get("offsetX"), 0, -9999, 9999), _int(item.get("offsetY"), 0, -9999, 9999),
                         _int(item.get("scalePercent"), 100, 1, 500),
                         _optional(item.get("scaleWidthPercent"), 1, 500),
                         _optional(item.get("scaleHeightPercent"), 1, 500), bool(item.get("stretchX", False)))


def _trim_path(item: dict) -> TrimPathLayer:
    return TrimPathLayer(str(item.get("name") or "Trim Path"), _path(item["path"]),
                         str(item.get("garment") or "Shorts"), str(item.get("templateName") or ""),
                         _int(item.get("x"), 0, -8192, 8192), _int(item.get("y"), 0, -8192, 8192),
                         _int(item.get("width"), 2048, 1, 8192), _int(item.get("height"), 2048, 1, 8192),
                         _float(item.get("rotationDegrees"), 0, -360, 360),
                         _int(item.get("defaultX"), 0, -8192, 8192), _int(item.get("defaultY"), 0, -8192, 8192),
                         _int(item.get("defaultWidth"), 2048, 1, 8192), _int(item.get("defaultHeight"), 2048, 1, 8192))


def _trim_placement(item: dict) -> TrimPlacementSettings:
    return TrimPlacementSettings(_int(item.get("offsetX"), 0, -9999, 9999),
                                 _int(item.get("offsetY"), 0, -9999, 9999),
                                 _int(item.get("scalePercent"), 100, 1, 500),
                                 _optional(item.get("scaleWidthPercent"), 1, 500),
                                 _optional(item.get("scaleHeightPercent"), 1, 500),
                                 _optional(item.get("overrideWidth"), 1, 8192),
                                 _optional(item.get("overrideHeight"), 1, 8192),
                                 bool(item.get("flipX", False)),
                                 _float(item.get("rotationDegrees"), 0, -360, 360))

