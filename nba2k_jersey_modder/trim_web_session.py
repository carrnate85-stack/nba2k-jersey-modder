from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import shutil
import uuid

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

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
    sourcePath: str | None = None
    imported: bool = False
    cropTop: int = 0
    cropBottom: int = 0
    correct: bool = True
    sharpen: bool = False
    colorCorrect: bool = False
    scale: int = 1
    featherLeft: int = 0
    featherRight: int = 0
    featherTop: int = 0
    featherBottom: int = 0
    flipVertical: bool = False


class TrimWebSession:
    def __init__(self, reference: Path, state_path: Path, initial_state: dict | None = None):
        self.reference = reference.resolve()
        self.state_path = state_path.resolve()
        self.folder = self.state_path.parent / "trims"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.items: list[StagedTrim] = []
        self.selected_id: str | None = None
        self.return_requested = False
        self.preview_paths: dict[str, Path] = {}
        self.dirty_ids: set[str] = set()
        with Image.open(self.reference) as opened:
            self.reference_size = ImageOps.exif_transpose(opened).size
        self._restore_initial(initial_state or {})
        self._write_state()

    def _restore_initial(self, state: dict) -> None:
        for raw in state.get("items") or []:
            source = Path(str(raw.get("path") or ""))
            if not source.is_file():
                continue
            item_id = str(raw.get("id") or uuid.uuid4().hex)
            source_path = Path(str(raw.get("sourcePath") or ""))
            restored_source = str(source_path) if source_path.is_file() else None
            imported = bool(raw.get("imported", False))
            try:
                start = self._point(raw.get("start"))
                end = self._point(raw.get("end"))
            except ValueError:
                imported = True
                restored_source = str(source)
                with Image.open(source) as opened:
                    width, height = ImageOps.exif_transpose(opened).size
                start = {"x": 0, "y": height // 2}
                end = {"x": max(0, width - 1), "y": height // 2}
            target, label = self._type(raw)
            item = StagedTrim(
                id=item_id, typeLabel=label, target=target,
                path=str(self.folder / f"{item_id}.png"),
                thumbnailPath=str(self.folder / f"{item_id}.thumb.png"),
                start=start, end=end, sourcePath=restored_source, imported=imported,
            )
            self._apply_options(item, raw)
            shutil.copyfile(source, item.path)
            with Image.open(item.path) as opened:
                thumbnail = ImageOps.exif_transpose(opened).convert("RGBA")
            thumbnail.thumbnail((240, 100), Image.Resampling.LANCZOS)
            thumbnail.save(item.thumbnailPath, "PNG", compress_level=1)
            self.items.append(item)
        requested = str(state.get("selectedId") or "")
        self.selected_id = requested if any(item.id == requested for item in self.items) else (self.items[-1].id if self.items else None)

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
        item = self._find(item_id)
        preview = self.preview_paths.get(item.id)
        path = preview if preview is not None and preview.is_file() else Path(item.path)
        return path.read_bytes(), "image/png"

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

    def import_image(self, payload: dict) -> dict:
        source = Path(str(payload.get("path") or "")).resolve()
        if not source.is_file():
            raise ValueError("Choose a trim image that still exists.")
        with Image.open(source) as opened:
            width, height = ImageOps.exif_transpose(opened).size
        if width < 1 or height < 1:
            raise ValueError("The imported trim image is empty.")
        target, label = self._type(payload)
        item_id = uuid.uuid4().hex
        middle = height // 2
        item = StagedTrim(
            id=item_id,
            typeLabel=label,
            target=target,
            path=str(self.folder / f"{item_id}.png"),
            thumbnailPath=str(self.folder / f"{item_id}.thumb.png"),
            start={"x": 0, "y": middle},
            end={"x": width - 1, "y": middle},
            sourcePath=str(source),
            imported=True,
            correct=False,
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
        self._render(item, preview_only=bool(payload.get("previewOnly", False)))
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
        preview = self.preview_paths.pop(item.id, None)
        if preview is not None:
            preview.unlink(missing_ok=True)
        self.dirty_ids.discard(item.id)
        self.selected_id = self.items[-1].id if self.items else None
        self._write_state()
        return self.project()

    def clear(self) -> dict:
        for item in self.items:
            Path(item.path).unlink(missing_ok=True)
            Path(item.thumbnailPath).unlink(missing_ok=True)
            preview = self.preview_paths.pop(item.id, None)
            if preview is not None:
                preview.unlink(missing_ok=True)
        self.items.clear()
        self.dirty_ids.clear()
        self.selected_id = None
        self._write_state()
        return self.project()

    def request_return(self) -> dict:
        for item in self.items:
            if item.id in self.dirty_ids:
                self._render(item)
        self.return_requested = True
        self._write_state()
        return {"ok": True, "items": len(self.items)}

    def _render(self, item: StagedTrim, *, preview_only: bool = False) -> None:
        output = self.folder / f"{item.id}.preview.png" if preview_only else Path(item.path)
        working = output.with_suffix(".working.png")
        if item.imported and item.sourcePath:
            with Image.open(item.sourcePath) as opened:
                imported = ImageOps.exif_transpose(opened).convert("RGBA")
            top_crop = max(0, item.cropTop)
            bottom_crop = max(0, item.cropBottom)
            bottom = max(top_crop + 1, imported.height - bottom_crop)
            imported = imported.crop((0, top_crop, imported.width, bottom))
            if item.cropTop < 0 or item.cropBottom < 0:
                imported = ImageOps.expand(
                    imported,
                    border=(0, max(0, -item.cropTop), 0, max(0, -item.cropBottom)),
                    fill=(0, 0, 0, 0),
                )
            imported.save(working, "PNG", compress_level=1)
        else:
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
        if item.scale > 1 and not preview_only:
            image = upscale_logo_image(image, scale_factor=item.scale, sharpen=item.sharpen)
        if item.flipVertical:
            image = ImageOps.flip(image)
        image = self._apply_feather(image, item)
        temporary = output.with_suffix(".writing")
        image.save(temporary, "PNG", compress_level=1)
        temporary.replace(output)
        working.unlink(missing_ok=True)
        if preview_only:
            self.preview_paths[item.id] = output
            self.dirty_ids.add(item.id)
            return
        preview = self.preview_paths.pop(item.id, None)
        if preview is not None and preview != output:
            preview.unlink(missing_ok=True)
        self.dirty_ids.discard(item.id)
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
        item.featherLeft = max(0, min(256, int(payload.get("featherLeft", item.featherLeft))))
        item.featherRight = max(0, min(256, int(payload.get("featherRight", item.featherRight))))
        item.featherTop = max(0, min(256, int(payload.get("featherTop", item.featherTop))))
        item.featherBottom = max(0, min(256, int(payload.get("featherBottom", item.featherBottom))))
        item.flipVertical = bool(payload.get("flipVertical", item.flipVertical))

    @staticmethod
    def _apply_feather(image: Image.Image, item: StagedTrim) -> Image.Image:
        values = (item.featherLeft, item.featherRight, item.featherTop, item.featherBottom)
        if not any(values):
            return image
        fade = Image.new("L", image.size, 255)
        draw = ImageDraw.Draw(fade)
        left, right, top, bottom = values
        for x in range(min(left, image.width)):
            draw.line((x, 0, x, image.height), fill=round(255 * x / max(1, left)))
        for offset in range(min(right, image.width)):
            x = image.width - 1 - offset
            draw.line((x, 0, x, image.height), fill=round(255 * offset / max(1, right)))
        for y in range(min(top, image.height)):
            row = Image.new("L", (image.width, 1), round(255 * y / max(1, top)))
            fade.paste(ImageChops.darker(fade.crop((0, y, image.width, y + 1)), row), (0, y))
        for offset in range(min(bottom, image.height)):
            y = image.height - 1 - offset
            row = Image.new("L", (image.width, 1), round(255 * offset / max(1, bottom)))
            fade.paste(ImageChops.darker(fade.crop((0, y, image.width, y + 1)), row), (0, y))
        result = image.copy()
        result.putalpha(ImageChops.multiply(result.getchannel("A"), fade))
        return result

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
