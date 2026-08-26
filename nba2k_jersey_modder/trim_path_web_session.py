from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
import re
import threading
import uuid

from PIL import Image

from .modern.document import ProjectDocument
from .modern.services import GeneratorService
from .web_editor import image_content_type


class TrimPathWebSession:
    """Browser Trim Path Lab adapter for the WPF project document."""

    def __init__(
        self,
        project_path: Path,
        pattern_path: Path,
        state_path: Path,
        project_folder: Path,
    ) -> None:
        self.document = ProjectDocument.load(project_path)
        self.pattern_path = pattern_path
        self.state_path = state_path
        self.project_folder = project_folder
        self.service = GeneratorService()
        self.session_id = uuid.uuid4().hex
        self._lock = threading.RLock()
        self._revision = 0
        self._return_requested = False
        self._write_state()

    def _run_on_ui_thread(self, callback):
        with self._lock:
            return callback()

    def _trim_path_lab_web_project(self) -> dict:
        template = self.service.template(self.document)
        with Image.open(template.image_path) as template_image:
            width, height = template_image.size
        zones = {zone.name: zone for zone in template.zones}
        names = (
            ("left_side_panel", "right_side_panel")
            if self.document.garment == "Jersey"
            else ("shorts_left_panel", "shorts_right_panel")
        )
        panel_zones = {}
        for side, name in zip(("left", "right"), names):
            zone = zones.get(name)
            if zone is not None:
                panel_zones[side] = {
                    "x": zone.x,
                    "y": zone.y,
                    "width": zone.width,
                    "height": zone.height,
                }
        uv_path = self.service.uv_path(self.document)
        return {
            "hasPattern": self.pattern_path.exists(),
            "garment": self.document.garment,
            "sessionId": self.session_id,
            "width": width,
            "height": height,
            "backgroundUrl": "/api/trim-path/background",
            "uvOverlay": {
                "available": uv_path.exists(),
                "imageUrl": "/api/trim-path/uv",
            },
            "patternUrl": "/api/trim-path/pattern",
            "patternName": self.pattern_path.name,
            "templateName": self.document.template_name,
            "panelZones": panel_zones,
            "message": f"Using {self.pattern_path.name} from the project trim assets.",
        }

    def _trim_path_lab_background_image(self) -> tuple[bytes, str]:
        image = self.service.render_color(self.document)
        output = BytesIO()
        image.save(output, "PNG", compress_level=1)
        return output.getvalue(), "image/png"

    def _trim_path_lab_uv_image(self) -> tuple[bytes, str]:
        path = self.service.uv_path(self.document)
        if not path.exists():
            raise FileNotFoundError(f"UV overlay not found: {path}")
        return path.read_bytes(), image_content_type(path)

    def _trim_path_lab_pattern_image(self) -> tuple[bytes, str]:
        if not self.pattern_path.exists():
            raise FileNotFoundError(f"Trim source not found: {self.pattern_path}")
        return self.pattern_path.read_bytes(), image_content_type(self.pattern_path)

    def _trim_path_lab_send_to_generator(self, payload: dict) -> dict:
        raw_layers = payload.get("layers") if isinstance(payload, dict) else None
        if not isinstance(raw_layers, list) or not raw_layers:
            return {"ok": False, "message": "No trim layers were received."}

        garment = "Jersey" if str(payload.get("garment", "")).casefold() == "jersey" else "Shorts"
        template_name = str(payload.get("templateName") or self.document.template_name).strip()
        output_dir = self.project_folder / "assets" / "trims" / "paths"
        output_dir.mkdir(parents=True, exist_ok=True)
        received: list[dict] = []

        for index, item in enumerate(raw_layers, start=1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or f"Trim Path {index}").strip()
            encoded = str(item.get("png") or "")
            if not encoded.startswith("data:image/png;base64,"):
                continue
            try:
                image_data = base64.b64decode(encoded.split(",", 1)[1], validate=True)
                with Image.open(BytesIO(image_data)) as opened:
                    image = opened.convert("RGBA")
            except (OSError, ValueError, TypeError):
                continue
            bounds = image.getchannel("A").getbbox()
            if bounds is None:
                continue
            cropped = image.crop(bounds)
            filename = f"{index:02d}_{_safe_name(name)}_{uuid.uuid4().hex[:8]}.png"
            path = output_dir / filename
            cropped.save(path, "PNG", compress_level=1)
            received.append({
                "name": name,
                "path": str(path),
                "garment": garment,
                "templateName": template_name,
                "x": bounds[0],
                "y": bounds[1],
                "width": cropped.width,
                "height": cropped.height,
                "rotationDegrees": 0,
                "defaultX": bounds[0],
                "defaultY": bounds[1],
                "defaultWidth": cropped.width,
                "defaultHeight": cropped.height,
            })

        if not received:
            return {"ok": False, "message": "The trim layers did not contain valid PNG images."}

        generator = self.document.generator
        existing = generator.get("trimPathLayers", [])
        generator["trimPathLayers"] = [
            item for item in existing
            if not (
                isinstance(item, dict)
                and str(item.get("garment") or "Shorts") == garment
                and str(item.get("templateName") or template_name) == template_name
            )
        ] + received
        generator["garment"] = garment
        generator["jerseyCut" if garment == "Jersey" else "shortsTemplate"] = template_name
        self._write_state()
        return {"ok": True, "count": len(received)}

    def _trim_path_lab_return(self) -> dict:
        self._return_requested = True
        self._write_state()
        return {"ok": True}

    def _write_state(self) -> None:
        self._revision += 1
        payload = {
            "revision": self._revision,
            "returnRequested": self._return_requested,
            "project": self.document.clone_payload(),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(self.state_path)


def _safe_name(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return result or "trim_path"
