from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import tempfile
import uuid

from PIL import Image, ImageDraw, ImageOps

from .generator import (
    remove_detected_background,
    remove_image_background,
    upscale_logo_image,
)


LOGO_TYPES = (
    ("Center Chest Logo", "front_center_chest_logo"),
    ("Left Chest Logo", "front_left_chest_logo"),
    ("Right Chest Logo", "front_right_chest_logo"),
    ("Front Wordmark", "front_wordmark"),
    ("Wrap Logo", "wrap_across_front_back_logo"),
    ("Back Neck Logo", "back_neck_logo"),
    ("Back Center Logo", "back_center_logo"),
    ("Belt Buckle Logo", "shorts_belt_buckle_logo"),
)


@dataclass
class StagedLogo:
    id: str
    typeLabel: str
    target: str
    path: str
    points: list[dict[str, int]]
    auto: bool = False
    removeWhite: bool = False
    removeBlack: bool = False
    outsideOnly: bool = True
    tolerance: int = 32
    scale: int = 1


class LogoWebSession:
    def __init__(self, reference: Path, state_path: Path):
        self.reference = reference.resolve()
        self.state_path = state_path.resolve()
        self.folder = self.state_path.parent / "logos"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.items: list[StagedLogo] = []
        self.selected_id: str | None = None
        self._reference_size = self._read_reference_size()
        self._write_state()

    def _read_reference_size(self) -> tuple[int, int]:
        with Image.open(self.reference) as opened:
            return ImageOps.exif_transpose(opened).size

    def project(self) -> dict:
        return {
            "hasImage": True,
            "width": self._reference_size[0],
            "height": self._reference_size[1],
            "imageUrl": "/api/reference",
            "sourceVersion": int(self.reference.stat().st_mtime_ns),
            "selectedId": self.selected_id,
            "logoTypes": [
                {"label": label, "target": target}
                for label, target in LOGO_TYPES
            ],
            "items": [self._public_item(item) for item in self.items],
        }

    def reference_bytes(self) -> tuple[bytes, str]:
        suffix = self.reference.suffix.lower()
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
        }.get(suffix, "application/octet-stream")
        return self.reference.read_bytes(), content_type

    def preview_bytes(self, item_id: str) -> tuple[bytes, str]:
        item = self._find(item_id)
        return Path(item.path).read_bytes(), "image/png"

    def stage(self, payload: dict) -> dict:
        points = self._clean_points(payload.get("points"))
        if len(points) < 3:
            raise ValueError("Draw a lasso or box around a logo first.")
        target, type_label = self._type(payload)
        item = StagedLogo(
            id=uuid.uuid4().hex,
            typeLabel=type_label,
            target=target,
            path="",
            points=points,
        )
        self._apply_options(item, payload)
        item.path = str(self.folder / f"{item.id}.png")
        self._render(item)
        self.items.append(item)
        self.selected_id = item.id
        self._write_state()
        return self.project()

    def update(self, payload: dict) -> dict:
        item = self._find(str(payload.get("id") or self.selected_id or ""))
        item.target, item.typeLabel = self._type(payload, item.target, item.typeLabel)
        self._apply_options(item, payload)
        self._render(item)
        self.selected_id = item.id
        self._write_state()
        return self.project()

    def select(self, payload: dict) -> dict:
        item = self._find(str(payload.get("id") or ""))
        self.selected_id = item.id
        self._write_state()
        return self.project()

    def remove(self, payload: dict) -> dict:
        item = self._find(str(payload.get("id") or self.selected_id or ""))
        self.items.remove(item)
        Path(item.path).unlink(missing_ok=True)
        self.selected_id = self.items[-1].id if self.items else None
        self._write_state()
        return self.project()

    def clear(self) -> dict:
        for item in self.items:
            Path(item.path).unlink(missing_ok=True)
        self.items.clear()
        self.selected_id = None
        self._write_state()
        return self.project()

    def _render(self, item: StagedLogo) -> None:
        with Image.open(self.reference) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGBA")
        xs = [point["x"] for point in item.points]
        ys = [point["y"] for point in item.points]
        left = max(0, min(xs))
        top = max(0, min(ys))
        right = min(source.width, max(xs) + 1)
        bottom = min(source.height, max(ys) + 1)
        if right <= left or bottom <= top:
            raise ValueError("The selected area is empty.")
        logo = source.crop((left, top, right, bottom))
        mask = Image.new("L", logo.size, 0)
        relative = [(point["x"] - left, point["y"] - top) for point in item.points]
        ImageDraw.Draw(mask).polygon(relative, fill=255)
        alpha = logo.getchannel("A")
        logo.putalpha(Image.composite(alpha, Image.new("L", logo.size, 0), mask))
        if item.auto:
            logo = remove_detected_background(logo, tolerance=item.tolerance)
        logo = remove_image_background(
            logo,
            remove_white=item.removeWhite,
            remove_black=item.removeBlack,
            outside_only=item.outsideOnly,
            tolerance=item.tolerance,
        )
        if item.scale > 1:
            logo = upscale_logo_image(logo, scale_factor=item.scale, sharpen=True)
        logo.save(item.path, "PNG", compress_level=1)

    def _apply_options(self, item: StagedLogo, payload: dict) -> None:
        item.auto = bool(payload.get("auto", item.auto))
        item.removeWhite = bool(payload.get("removeWhite", item.removeWhite))
        item.removeBlack = bool(payload.get("removeBlack", item.removeBlack))
        item.outsideOnly = bool(payload.get("outsideOnly", item.outsideOnly))
        item.tolerance = max(0, min(255, int(payload.get("tolerance", item.tolerance))))
        item.scale = int(payload.get("scale", item.scale))
        if item.scale not in (1, 2, 4):
            item.scale = 1

    @staticmethod
    def _clean_points(raw_points) -> list[dict[str, int]]:
        points = []
        for value in raw_points or []:
            try:
                points.append({"x": int(round(float(value["x"]))), "y": int(round(float(value["y"])))})
            except (KeyError, TypeError, ValueError):
                continue
        return points

    @staticmethod
    def _type(payload: dict, fallback_target: str | None = None, fallback_label: str | None = None) -> tuple[str, str]:
        requested = str(payload.get("target") or fallback_target or LOGO_TYPES[0][1])
        for label, target in LOGO_TYPES:
            if target == requested:
                return target, label
        return fallback_target or LOGO_TYPES[0][1], fallback_label or LOGO_TYPES[0][0]

    def _find(self, item_id: str) -> StagedLogo:
        for item in self.items:
            if item.id == item_id:
                return item
        raise ValueError("Select a staged logo first.")

    @staticmethod
    def _public_item(item: StagedLogo) -> dict:
        value = asdict(item)
        value.pop("points", None)
        value["previewUrl"] = f"/api/preview/{item.id}"
        value["fileName"] = Path(item.path).name
        return value

    def _write_state(self) -> None:
        payload = {
            "reference": str(self.reference),
            "selectedId": self.selected_id,
            "items": [asdict(item) for item in self.items],
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)


def default_state_path() -> Path:
    return Path(tempfile.gettempdir()) / "nba2k_jersey_modder" / "logo_web" / "state.json"
