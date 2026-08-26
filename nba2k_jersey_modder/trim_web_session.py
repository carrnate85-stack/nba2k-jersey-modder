from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import uuid

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .generator import upscale_logo_image
from .trim_creator import correct_trim_strip, create_trim_strip_from_line


TRIM_TYPES = (
    ("Collar Trim", "collar_trim_image"),
    ("Left Arm Hole Trim", "left_arm_hole_trim_image"),
    ("Right Arm Hole Trim", "right_arm_hole_trim_image"),
    ("Waistband", "waistband_image"),
)


@dataclass
class StagedTrim:
    id: str
    typeLabel: str
    target: str
    path: str
    thumbnailPath: str
    start: dict[str, int]
    end: dict[str, int]
    cropTop: int = 0
    cropBottom: int = 0
    correct: bool = True
    sharpen: bool = False
    colorCorrect: bool = False
    scale: int = 1


class TrimWebSession:
    def __init__(self, reference: Path, state_path: Path):
        self.reference = reference.resolve()
        self.state_path = state_path.resolve()
        self.folder = self.state_path.parent / "trims"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.items: list[StagedTrim] = []
        self.selected_id: str | None = None
        self.return_requested = False
        with Image.open(self.reference) as opened:
            self.reference_size = ImageOps.exif_transpose(opened).size
        self._write_state()

    def project(self) -> dict:
        return {
            "hasImage": True,
            "width": self.reference_size[0],
            "height": self.reference_size[1],
            "imageUrl": "/api/reference",
            "sourceVersion": int(self.reference.stat().st_mtime_ns),
            "selectedId": self.selected_id,
            "returnRequested": self.return_requested,
            "trimTypes": [{"label": label, "target": target} for label, target in TRIM_TYPES],
            "items": [self._public_item(item) for item in self.items],
        }

    def reference_bytes(self) -> tuple[bytes, str]:
        content_type = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
        }.get(self.reference.suffix.lower(), "application/octet-stream")
        return self.reference.read_bytes(), content_type

    def preview_bytes(self, item_id: str) -> tuple[bytes, str]:
        return Path(self._find(item_id).path).read_bytes(), "image/png"

    def stage(self, payload: dict) -> dict:
        start = self._point(payload.get("start"))
        end = self._point(payload.get("end"))
        if start == end:
            raise ValueError("Choose two different points across the trim.")
        target, label = self._type(payload)
        item_id = uuid.uuid4().hex
        item = StagedTrim(
            id=item_id,
            typeLabel=label,
            target=target,
            path=str(self.folder / f"{item_id}.png"),
            thumbnailPath=str(self.folder / f"{item_id}.thumb.png"),
            start=start,
            end=end,
        )
        self._apply_options(item, payload)
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
        Path(item.thumbnailPath).unlink(missing_ok=True)
        self.selected_id = self.items[-1].id if self.items else None
        self._write_state()
        return self.project()

    def clear(self) -> dict:
        for item in self.items:
            Path(item.path).unlink(missing_ok=True)
            Path(item.thumbnailPath).unlink(missing_ok=True)
        self.items.clear()
        self.selected_id = None
        self._write_state()
        return self.project()

    def request_return(self) -> dict:
        self.return_requested = True
        self._write_state()
        return {"ok": True, "items": len(self.items)}

    def _render(self, item: StagedTrim) -> None:
        output = Path(item.path)
        working = output.with_suffix(".working.png")
        create_trim_strip_from_line(
            self.reference,
            working,
            (item.start["x"], item.start["y"]),
            (item.end["x"], item.end["y"]),
            crop_top=item.cropTop,
            crop_bottom=item.cropBottom,
        )
        if item.correct:
            correct_trim_strip(working, working, max_gap=3)
        with Image.open(working) as opened:
            image = opened.convert("RGBA")
        if item.colorCorrect:
            alpha = image.getchannel("A")
            rgb = ImageEnhance.Color(image.convert("RGB")).enhance(1.08)
            rgb = ImageEnhance.Contrast(rgb).enhance(1.05)
            image = rgb.convert("RGBA")
            image.putalpha(alpha)
        if item.sharpen:
            image = image.filter(ImageFilter.UnsharpMask(radius=1.0, percent=70, threshold=3))
        if item.scale > 1:
            image = upscale_logo_image(image, scale_factor=item.scale, sharpen=item.sharpen)
        temporary = output.with_suffix(".writing")
        image.save(temporary, "PNG", compress_level=1)
        temporary.replace(output)
        working.unlink(missing_ok=True)
        thumbnail = image.copy()
        thumbnail.thumbnail((240, 100), Image.Resampling.LANCZOS)
        thumbnail.save(item.thumbnailPath, "PNG", compress_level=1)

    def _apply_options(self, item: StagedTrim, payload: dict) -> None:
        item.cropTop = max(-32, min(63, int(payload.get("cropTop", item.cropTop))))
        item.cropBottom = max(-32, min(63, int(payload.get("cropBottom", item.cropBottom))))
        item.correct = bool(payload.get("correct", item.correct))
        item.sharpen = bool(payload.get("sharpen", item.sharpen))
        item.colorCorrect = bool(payload.get("colorCorrect", item.colorCorrect))
        item.scale = int(payload.get("scale", item.scale))
        if item.scale not in (1, 2, 4):
            item.scale = 1

    def _point(self, value) -> dict[str, int]:
        try:
            x = int(round(float(value["x"])))
            y = int(round(float(value["y"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Select two points across the trim first.") from exc
        return {
            "x": max(0, min(self.reference_size[0] - 1, x)),
            "y": max(0, min(self.reference_size[1] - 1, y)),
        }

    @staticmethod
    def _type(payload: dict, fallback_target: str | None = None, fallback_label: str | None = None):
        requested = str(payload.get("target") or fallback_target or TRIM_TYPES[0][1])
        for label, target in TRIM_TYPES:
            if target == requested:
                return target, label
        return fallback_target or TRIM_TYPES[0][1], fallback_label or TRIM_TYPES[0][0]

    def _find(self, item_id: str) -> StagedTrim:
        for item in self.items:
            if item.id == item_id:
                return item
        raise ValueError("Select a staged trim first.")

    @staticmethod
    def _public_item(item: StagedTrim) -> dict:
        value = asdict(item)
        value["previewUrl"] = f"/api/preview/{item.id}"
        value["fileName"] = Path(item.path).name
        value["angle"] = round(math.degrees(math.atan2(
            item.end["y"] - item.start["y"], item.end["x"] - item.start["x"])), 1)
        return value

    def _write_state(self) -> None:
        payload = {
            "reference": str(self.reference),
            "selectedId": self.selected_id,
            "returnRequested": self.return_requested,
            "items": [asdict(item) for item in self.items],
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)
