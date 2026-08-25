from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import traceback
import uuid
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nba2k_jersey_modder.app import _recolor_font_image
from nba2k_jersey_modder.font_iff import (
    extract_number_sheet_from_font_iff,
    inspect_font_number_texture,
    split_number_sheet_digits,
    write_number_sheet_to_font_iff,
)
from nba2k_jersey_modder.game_manifest import ManifestEntry
from nba2k_jersey_modder.generator import (
    remove_detected_background,
    remove_image_background,
    upscale_logo_image,
)
from nba2k_jersey_modder.iff_patch import Replacement, apply_replacements
from nba2k_jersey_modder.modern.document import ProjectDocument
from nba2k_jersey_modder.modern.font_catalog import FontCatalog, describe_manifest_font
from nba2k_jersey_modder.modern.services import GeneratorService
from nba2k_jersey_modder.scanner import ResourceHit, scan_iff
from nba2k_jersey_modder.template import (
    JERSEY_TEMPLATE_OPTIONS,
    SHORTS_TEMPLATE_MAP_OPTIONS,
    SHORTS_TEMPLATE_OPTIONS,
    SHORTS_TEMPLATE_RETRO_UV_IMAGE,
    JerseyTemplate,
    TemplateZone,
    load_template,
    save_template,
)
from nba2k_jersey_modder.trim_creator import correct_trim_strip, create_trim_strip_from_line
from nba2k_jersey_modder.tweak_iff import inspect_front_number_tweak, write_front_number_tweak


WORK = Path(tempfile.gettempdir()) / "nba2k_jersey_modder" / "wpf"
WORK.mkdir(parents=True, exist_ok=True)
SERVICE = GeneratorService()


def _output(name: str, suffix: str = ".png") -> Path:
    folder = WORK / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{uuid.uuid4().hex}{suffix}"


def _document(params: dict) -> ProjectDocument:
    return ProjectDocument(params.get("project") or {})


def render(params: dict):
    document = _document(params)
    kind = str(params.get("kind") or "preview")
    strength = int(params.get("strength") or 15)
    image = SERVICE.render_preview(document) if kind == "preview" else SERVICE.render_texture(document, kind, strength)
    output = _output("renders")
    image.save(output, "PNG", compress_level=1)
    return {"path": str(output), "width": image.width, "height": image.height}


def export_package(params: dict):
    path = SERVICE.export_package(_document(params), Path(params["folder"]))
    return {"path": str(path)}


def save_texture(params: dict):
    document = _document(params)
    path = Path(params["path"])
    kind = str(params.get("kind") or "Color Texture")
    fmt = str(params.get("format") or path.suffix.lower())
    strength = int(params.get("strength") or 15)
    if kind == "Color Texture" and fmt == ".psd": SERVICE.save_psd(document, path)
    elif kind == "Color Texture" and fmt == ".dds": SERVICE.save_dds(document, path)
    else:
        image = SERVICE.render_texture(document, kind, strength)
        if fmt == ".dds":
            from nba2k_jersey_modder.dds import save_bc1_dds
            save_bc1_dds(image, path)
        else: image.save(path, "PNG", compress_level=1)
    return {"path": str(path)}


def logo_process(params: dict):
    with Image.open(params["path"]) as opened: image = opened.convert("RGBA")
    box = params.get("box")
    if box and len(box) == 4:
        x1, y1, x2, y2 = map(int, box)
        x1, x2 = sorted((max(0, x1), min(image.width, x2)))
        y1, y2 = sorted((max(0, y1), min(image.height, y2)))
        if x2 > x1 and y2 > y1: image = image.crop((x1, y1, x2, y2))
    tolerance = int(params.get("tolerance") or 32)
    if params.get("auto"): image = remove_detected_background(image, tolerance=tolerance)
    image = remove_image_background(
        image,
        remove_white=bool(params.get("removeWhite")),
        remove_black=bool(params.get("removeBlack")),
        outside_only=bool(params.get("outsideOnly", True)),
        tolerance=tolerance,
    )
    scale = int(params.get("scale") or 1)
    if scale > 1: image = upscale_logo_image(image, scale_factor=scale, sharpen=True)
    output = _output("logos")
    image.save(output, "PNG")
    return {"path": str(output), "width": image.width, "height": image.height}


def trim_process(params: dict):
    output = _output("trims")
    start = tuple(map(int, params["start"]))
    end = tuple(map(int, params["end"]))
    create_trim_strip_from_line(
        Path(params["path"]), output, start, end,
        crop_top=int(params.get("cropTop") or 0),
        crop_bottom=int(params.get("cropBottom") or 0),
    )
    if params.get("correct", True): correct_trim_strip(output, output, max_gap=3)
    with Image.open(output) as image: size = image.size
    return {"path": str(output), "width": size[0], "height": size[1]}


def trim_path_render(params: dict):
    width = int(params.get("canvasWidth") or 2048)
    height = int(params.get("canvasHeight") or 2048)
    trim_width = max(2, int(params.get("trimWidth") or 64))
    points = [tuple(map(float, point)) for point in params.get("points", [])]
    if len(points) < 2:
        raise ValueError("Select at least two path points.")
    with Image.open(params["pattern"]) as opened:
        pattern = opened.convert("RGBA")
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    segments = list(zip(points, points[1:]))
    if params.get("shape") == "T shape" and len(points) >= 3:
        segments = [(points[0], points[1]), (points[2], points[1])]
    for start, end in segments:
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = max(1, round(math.hypot(dx, dy)))
        strip = pattern.resize((length, trim_width), Image.Resampling.LANCZOS)
        angle = math.degrees(math.atan2(dy, dx))
        rotated = strip.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
        x = round((start[0] + end[0] - rotated.width) / 2)
        y = round((start[1] + end[1] - rotated.height) / 2)
        canvas.alpha_composite(rotated, (x, y))
    output = _output("trim_paths")
    canvas.save(output, "PNG")
    paths = [output]
    if params.get("mirrorPanel"):
        mirrored = _output("trim_paths"); canvas.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(mirrored, "PNG"); paths.append(mirrored)
    if params.get("mirrorX"):
        mirrored = _output("trim_paths"); canvas.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(mirrored, "PNG"); paths.append(mirrored)
    return {"paths": [str(path) for path in paths]}


def iff_scan(params: dict):
    result = scan_iff(params["path"])
    pairs = []
    for pair in result.texture_pairs:
        dds = asdict(pair.dds_hits[0]) if pair.dds_hits else None
        txtr = asdict(pair.txtr_hits[0]) if pair.txtr_hits else None
        pairs.append({"key": pair.key, "dds": dds, "txtr": txtr, "status": pair.status})
    return {"path": str(result.path), "size": result.size, "pairs": pairs}


def iff_export(params: dict):
    source = Path(params["source"]); hit = ResourceHit(**params["hit"]); destination = Path(params["destination"])
    if hit.archive_path:
        with zipfile.ZipFile(source) as archive: destination.write_bytes(archive.read(hit.archive_path))
    elif hit.size: destination.write_bytes(source.read_bytes()[hit.offset:hit.offset + hit.size])
    else: raise ValueError("This resource has no safe embedded byte range.")
    return {"path": str(destination)}


def iff_replace(params: dict):
    source = Path(params["source"]); destination = Path(params["destination"]); replacements = []
    for item in params.get("replacements", []): replacements.append(Replacement(ResourceHit(**item["hit"]), Path(item["path"])))
    apply_replacements(source, destination, replacements)
    return {"path": str(destination)}


def rdat_read(params: dict):
    path = Path(params["path"]); entry = None
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".rdat")]
            if not names: raise ValueError("No RDAT entry was found in this IFF.")
            entry = params.get("entry") or names[0]
            if params.get("listOnly"): return {"entries": names}
            data = archive.read(entry)
    else: data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try: text = data.decode(encoding); break
        except UnicodeDecodeError: continue
    return {"text": text, "encoding": encoding, "entry": entry}


def rdat_write(params: dict):
    source = Path(params["source"]); destination = Path(params.get("destination") or source); entry = params.get("entry"); data = params["text"].encode(params.get("encoding") or "utf-8")
    if entry:
        temporary = _output("rdat", ".iff")
        with zipfile.ZipFile(source) as old, zipfile.ZipFile(temporary, "w") as new:
            for info in old.infolist(): new.writestr(info, data if info.filename == entry else old.read(info.filename))
        shutil.copy2(temporary, destination)
    else: destination.write_bytes(data)
    return {"path": str(destination)}


def template_catalog(_params: dict):
    return {
        "Jersey": {"Retro U": list(JERSEY_TEMPLATE_OPTIONS)},
        "Shorts": {name: [*SHORTS_TEMPLATE_MAP_OPTIONS, "Shorts normal"] for name in SHORTS_TEMPLATE_OPTIONS},
    }


def template_load(params: dict):
    garment, variant, map_name = params["garment"], params["variant"], params["map"]
    if garment == "Jersey": image, zones_path = JERSEY_TEMPLATE_OPTIONS[map_name]
    else:
        base, zones_path = SHORTS_TEMPLATE_OPTIONS[variant]
        if map_name == "Shorts UV": image = SHORTS_TEMPLATE_RETRO_UV_IMAGE
        elif map_name == "Shorts normal": image = ROOT / "blendermodels" / "shorts_retro_normal.png"
        else: image = base
    template = load_template(zones_path)
    return {"image": str(image), "zonesPath": str(zones_path), "zones": [asdict(zone) for zone in template.zones]}


def template_save(params: dict):
    zones = tuple(TemplateZone(**zone) for zone in params["zones"])
    save_template(Path(params["path"]), JerseyTemplate(params.get("image") or "", zones))
    return {"path": params["path"]}


def font_catalog(params: dict):
    catalog = FontCatalog(Path(params["root"])); stems = catalog.cached_stems(); result = []
    for entry in catalog.entries():
        team, uniform, code = describe_manifest_font(entry)
        result.append({**asdict(entry), "displayName": entry.display_name, "team": team, "uniform": uniform, "code": code, "cached": catalog.cache_stem(entry) in stems})
    return {"entries": result, "cached": len(stems)}


def _entry(value: dict) -> ManifestEntry:
    return ManifestEntry(value["name"], value["archive_id"], int(value["offset"]), int(value["size"]))


def font_preview(params: dict):
    catalog = FontCatalog(Path(params["root"])); entry = _entry(params["entry"])
    path, label, cached = catalog.ensure_thumbnail(entry)
    return {"path": str(path), "label": label, "cached": cached}


def font_open_manifest(params: dict):
    catalog = FontCatalog(Path(params["root"])); entry = _entry(params["entry"]); path = catalog.ensure_working_iff(entry)
    return font_open({"path": str(path)})


def font_open(params: dict):
    path = Path(params["path"]); sheet = extract_number_sheet_from_font_iff(path); info = inspect_font_number_texture(path); output = _output("fonts")
    sheet.save(output, "PNG")
    return {"source": str(path), "preview": str(output), "width": info.width, "height": info.height, "format": info.format_label}


def _recolored_sheet(params: dict):
    source = Path(params["source"]); sheet = extract_number_sheet_from_font_iff(source); info = inspect_font_number_texture(source); digits = split_number_sheet_digits(sheet)
    outline = _rgb(params.get("outline")); fill = _rgb(params.get("fill")); edge = float(params.get("edge") or 0) / 100; thickness = int(params.get("thickness") or 0)
    changed = [_recolor_font_image(image, outline, fill, edge_protection=edge, outline_thickness=thickness) for image in digits]
    result = Image.new("RGBA", (info.width, info.height), (0, 0, 0, 0))
    for index, image in enumerate(changed): result.alpha_composite(image, (index * info.cell_width, 0))
    return result


def _rgb(value):
    if not value: return None
    text = str(value).lstrip("#")
    return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def font_recolor(params: dict):
    image = _recolored_sheet(params); output = _output("fonts"); image.save(output, "PNG")
    return {"path": str(output), "width": image.width, "height": image.height}


def font_save(params: dict):
    image = _recolored_sheet(params); write_number_sheet_to_font_iff(Path(params["source"]), Path(params["destination"]), image)
    return {"path": params["destination"]}


def tweak_open(params: dict):
    info = inspect_front_number_tweak(params["path"])
    return {"path": params["path"], **{key: asdict(getattr(info, key)) for key in ("x", "y", "width", "height")}}


def tweak_save(params: dict):
    write_front_number_tweak(params["source"], params["destination"], x=float(params["x"]), y=float(params["y"]), width=float(params["width"]), height=float(params["height"]))
    return {"path": params["destination"]}


def blender_prepare(params: dict):
    model, color, normal, settings = SERVICE.prepare_blender_preview(_document(params))
    return {"model": str(model), "color": str(color), "normal": str(normal), "settings": str(settings), "script": str(SERVICE.blender_script), "blender": str(SERVICE.find_blender() or "")}


METHODS = {
    "ping": lambda _params: {"version": 1}, "render": render, "export_package": export_package,
    "save_texture": save_texture, "logo_process": logo_process, "trim_process": trim_process, "trim_path_render": trim_path_render,
    "iff_scan": iff_scan, "iff_export": iff_export, "iff_replace": iff_replace,
    "rdat_read": rdat_read, "rdat_write": rdat_write,
    "template_catalog": template_catalog, "template_load": template_load, "template_save": template_save,
    "font_catalog": font_catalog, "font_preview": font_preview, "font_open_manifest": font_open_manifest,
    "font_open": font_open, "font_recolor": font_recolor, "font_save": font_save,
    "tweak_open": tweak_open, "tweak_save": tweak_save, "blender_prepare": blender_prepare,
}


def main() -> None:
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line); method = request.get("method")
            if method == "shutdown": break
            with redirect_stdout(sys.stderr): result = METHODS[method](request.get("params") or {})
            response = {"id": request.get("id"), "ok": True, "result": result}
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            response = {"id": request.get("id") if request else None, "ok": False, "error": str(exc)}
        print(json.dumps(response, separators=(",", ":")), flush=True)


if __name__ == "__main__": main()
