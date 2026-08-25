from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image

from ..dds import save_bc1_dds
from ..generator import generate_layered_jersey_psd, render_jersey_normal_map, render_jersey_region_map, render_jersey_texture
from ..template import (JERSEY_NORMAL_TEMPLATE_IMAGE, JERSEY_REGION_TEMPLATE_IMAGE,
                        JERSEY_UV_TEMPLATE_IMAGE, MASTER_TEMPLATE_ZONES,
                        SHORTS_TEMPLATE_OPTIONS, SHORTS_TEMPLATE_RETRO_UV_IMAGE, load_template)
from .document import ProjectDocument

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHORTS_RETRO_NORMAL_IMAGE = PROJECT_ROOT / "blendermodels" / "shorts_retro_normal.png"
BLENDER_PREVIEW_SCRIPT = PROJECT_ROOT / "tools" / "blender_apply_jersey_preview.py"
BLENDER_PREVIEW_MODELS = {
    "jersey": PROJECT_ROOT / "blendermodels" / "jerseyretroU.blend",
    "shorts": PROJECT_ROOT / "blendermodels" / "retroshorts.blend",
}
BLENDER_CANDIDATES = (
    Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"),
)


class GeneratorService:
    project_root = PROJECT_ROOT
    blender_script = BLENDER_PREVIEW_SCRIPT

    def template(self, document: ProjectDocument):
        if document.garment == "Shorts":
            return load_template(SHORTS_TEMPLATE_OPTIONS.get(document.template_name, SHORTS_TEMPLATE_OPTIONS["Retro shorts"])[1])
        return load_template(MASTER_TEMPLATE_ZONES)

    def uv_path(self, document: ProjectDocument) -> Path:
        return SHORTS_TEMPLATE_RETRO_UV_IMAGE if document.garment == "Shorts" else JERSEY_UV_TEMPLATE_IMAGE

    def render_color(self, document: ProjectDocument):
        return render_jersey_texture(self.template(document), document.to_generator_inputs())

    def render_preview(self, document: ProjectDocument):
        image = self.render_color(document).convert("RGB")
        uv, path = document.generator["uvOverlay"], self.uv_path(document)
        opacity = max(0, min(100, int(uv.get("opacity", 45))))
        if not uv.get("enabled", True) or opacity <= 0 or not path.exists():
            return image
        with Image.open(path) as opened: overlay = opened.convert("RGBA")
        if overlay.size != image.size: overlay = overlay.resize(image.size, Image.Resampling.LANCZOS)
        alpha = overlay.getchannel("A").point(lambda value: round(value * opacity / 100))
        return Image.composite(Image.new("RGB", image.size, (0, 0, 0)), image, alpha)

    def render_texture(self, document: ProjectDocument, texture_type: str, strength: int = 15):
        if texture_type == "Color Texture": return self.render_color(document)
        if texture_type == "Region Texture":
            if document.garment != "Jersey": raise ValueError("Region textures are currently available for jerseys.")
            return render_jersey_region_map(self.template(document), document.to_generator_inputs(), JERSEY_REGION_TEMPLATE_IMAGE)
        if texture_type == "Normal Map":
            base = SHORTS_RETRO_NORMAL_IMAGE if document.garment == "Shorts" else JERSEY_NORMAL_TEMPLATE_IMAGE
            return render_jersey_normal_map(self.template(document), document.to_generator_inputs(), base,
                                            normal_strength=max(0, min(100, strength)))
        raise ValueError(f"Unknown texture type: {texture_type}")

    def save_png(self, document: ProjectDocument, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True); self.render_color(document).save(path, "PNG", compress_level=1); return path

    def save_dds(self, document: ProjectDocument, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True); save_bc1_dds(self.render_color(document), path); return path

    def save_psd(self, document: ProjectDocument, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        generate_layered_jersey_psd(self.template(document), document.to_generator_inputs(), path); return path

    def export_package(self, document: ProjectDocument, parent: Path) -> Path:
        package = _available(parent / f"nba2k_export_{datetime.now():%Y%m%d_%H%M%S}")
        textures, previews, source = package / "textures", package / "previews", package / "source"
        for folder in (textures, previews, source): folder.mkdir(parents=True)
        stem = "shorts_color" if document.garment == "Shorts" else "jersey_color"
        color = self.render_color(document); color.save(previews / f"{stem}.png", "PNG", compress_level=1)
        save_bc1_dds(color, textures / f"{stem}.dds")
        if document.garment == "Jersey":
            for name, kind in (("jersey_region", "Region Texture"), ("jersey_normal", "Normal Map")):
                image = self.render_texture(document, kind); image.save(previews / f"{name}.png", "PNG", compress_level=1)
                save_bc1_dds(image, textures / f"{name}.dds")
        (source / "project.nba2kproject.json").write_text(json.dumps(document.payload, indent=2), encoding="utf-8")
        (package / "install_notes.txt").write_text("NBA 2K Jersey Modder export package\n\nReview previews before importing DDS textures.\n", encoding="utf-8")
        return package

    def find_blender(self) -> Path | None:
        executable = shutil.which("blender")
        if executable:
            return Path(executable)
        return next((path for path in BLENDER_CANDIDATES if path.exists()), None)

    def prepare_blender_preview(self, document: ProjectDocument) -> tuple[Path, Path, Path, Path]:
        missing = [path for path in (*BLENDER_PREVIEW_MODELS.values(), BLENDER_PREVIEW_SCRIPT) if not path.exists()]
        if missing:
            raise FileNotFoundError("Missing Blender preview file(s):\n" + "\n".join(str(path) for path in missing))
        output = Path(tempfile.gettempdir()) / "nba2k_jersey_modder" / "blender_preview" / "modern_uniform"
        output.mkdir(parents=True, exist_ok=True)
        jersey = ProjectDocument(document.clone_payload())
        jersey.generator["garment"] = "Jersey"
        jersey.generator["jerseyCut"] = "Retro U"
        shorts = ProjectDocument(document.clone_payload())
        shorts.generator["garment"] = "Shorts"
        shorts.generator["shortsTemplate"] = "Retro shorts"
        paths = {
            "jersey_color": output / "jersey_color.png",
            "jersey_normal": output / "jersey_normal.png",
            "shorts_color": output / "shorts_color.png",
            "shorts_normal": output / "shorts_normal.png",
            "settings": output / "preview_settings.json",
        }
        self.render_color(jersey).save(paths["jersey_color"], "PNG", compress_level=1)
        self.render_texture(jersey, "Normal Map", 15).save(paths["jersey_normal"], "PNG", compress_level=1)
        self.render_color(shorts).save(paths["shorts_color"], "PNG", compress_level=1)
        self.render_texture(shorts, "Normal Map", 15).save(paths["shorts_normal"], "PNG", compress_level=1)
        paths["settings"].write_text(json.dumps({
            "garment": "Uniform",
            "template_name": "Retro U + Retro shorts",
            "append_blend": str(BLENDER_PREVIEW_MODELS["shorts"]),
            "parts": [
                {"name": "Jersey", "material_keyword": "jersey", "color_path": str(paths["jersey_color"]), "normal_path": str(paths["jersey_normal"]), "normal_strength": 0.35},
                {"name": "Shorts", "material_keyword": "shorts", "color_path": str(paths["shorts_color"]), "normal_path": str(paths["shorts_normal"]), "normal_strength": 0.35},
            ],
        }, indent=2), encoding="utf-8")
        active_color = paths["shorts_color"] if document.garment == "Shorts" else paths["jersey_color"]
        active_normal = paths["shorts_normal"] if document.garment == "Shorts" else paths["jersey_normal"]
        return BLENDER_PREVIEW_MODELS["jersey"], active_color, active_normal, paths["settings"]


def _available(path: Path) -> Path:
    if not path.exists(): return path
    index = 2
    while (candidate := path.with_name(f"{path.name}_{index}")).exists(): index += 1
    return candidate
