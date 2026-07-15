from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


def _argv_after_double_dash() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def _material_targets(keyword: str | None = None) -> list[bpy.types.Material]:
    mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    preferred_objects = [obj for obj in mesh_objects if obj.name.lower() == "player"]
    objects = mesh_objects if keyword else (preferred_objects or mesh_objects)
    if keyword:
        normalized_keyword = keyword.casefold()
        objects = [
            obj
            for obj in objects
            if normalized_keyword in obj.name.casefold()
            or any(
                slot.material
                and normalized_keyword in slot.material.name.casefold()
                for slot in obj.material_slots
            )
        ]
    materials: list[bpy.types.Material] = []
    for obj in objects:
        for slot in obj.material_slots:
            if slot.material and slot.material not in materials:
                materials.append(slot.material)
    if keyword:
        return materials
    if preferred_objects:
        return materials
    uniform_materials = [
        mat
        for mat in materials
        if "jersey" in mat.name.lower() or "shorts" in mat.name.lower()
    ]
    return uniform_materials or materials[:1]


def _image_node(nodes, image_path: Path, label: str, colorspace: str):
    node = nodes.new("ShaderNodeTexImage")
    node.name = label
    node.label = label
    image = bpy.data.images.load(str(image_path), check_existing=True)
    image.reload()
    image.colorspace_settings.name = colorspace
    node.image = image
    return node


def _clear_preview_nodes(material: bpy.types.Material) -> None:
    nodes = material.node_tree.nodes
    for node in list(nodes):
        if node.name.startswith("NBA 2K Preview"):
            nodes.remove(node)


def _apply_material_textures(
    material: bpy.types.Material,
    color_path: Path,
    normal_path: Path | None,
    normal_strength: float,
) -> None:
    material.use_nodes = True
    _clear_preview_nodes(material)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")

    color_node = _image_node(nodes, color_path, "NBA 2K Preview Color", "sRGB")
    links.new(color_node.outputs["Color"], bsdf.inputs["Base Color"])

    if normal_path is None or normal_strength <= 0:
        return

    normal_image_node = _image_node(nodes, normal_path, "NBA 2K Preview Normal", "Non-Color")
    normal_node = nodes.new("ShaderNodeNormalMap")
    normal_node.name = "NBA 2K Preview Normal Map"
    normal_node.label = "NBA 2K Preview Normal Map"
    normal_node.inputs["Strength"].default_value = normal_strength
    links.new(normal_image_node.outputs["Color"], normal_node.inputs["Color"])
    links.new(normal_node.outputs["Normal"], bsdf.inputs["Normal"])


def _preview_settings_from_scene() -> dict:
    scene = bpy.context.scene
    settings_path = scene.get("nba2k_preview_settings_path", "")
    if settings_path:
        path = Path(settings_path)
        if path.exists():
            try:
                settings = json.loads(path.read_text(encoding="utf-8"))
                scene["nba2k_preview_garment"] = str(
                    settings.get("garment", "Uniform")
                )
                scene["nba2k_preview_template_name"] = str(
                    settings.get("template_name", "")
                )
                parts = settings.get("parts")
                if isinstance(parts, list) and parts:
                    first_part = parts[0]
                    scene["nba2k_preview_color_path"] = str(first_part.get("color_path", ""))
                    scene["nba2k_preview_normal_path"] = str(first_part.get("normal_path", ""))
                    scene["nba2k_preview_normal_strength"] = float(
                        first_part.get("normal_strength", 0.0)
                    )
                    return settings
                color_path = Path(settings.get("color_path", ""))
                if color_path.exists():
                    settings["parts"] = [
                        {
                            "name": str(settings.get("garment", "Uniform")),
                            "material_keyword": "",
                            "color_path": str(color_path),
                            "normal_path": str(settings.get("normal_path", "")),
                            "normal_strength": float(
                                settings.get("normal_strength", 0.0)
                            ),
                        }
                    ]
                    return settings
            except Exception as exc:  # noqa: BLE001 - Blender operator boundary.
                print(f"[NBA 2K Preview] Could not read preview settings: {exc}")

    return {
        "parts": [
            {
                "name": "Uniform",
                "material_keyword": "",
                "color_path": str(scene.get("nba2k_preview_color_path", "")),
                "normal_path": str(scene.get("nba2k_preview_normal_path", "")),
                "normal_strength": float(
                    scene.get("nba2k_preview_normal_strength", 0.0)
                ),
            }
        ]
    }


def _ensure_appended_preview_model(settings: dict) -> None:
    append_value = str(settings.get("append_blend", "")).strip()
    if not append_value or _material_targets("shorts"):
        return
    append_path = Path(append_value)
    if not append_path.exists():
        raise FileNotFoundError(f"Additional preview model not found: {append_path}")
    with bpy.data.libraries.load(str(append_path), link=False) as (source, destination):
        destination.objects = source.objects
    appended_count = 0
    for obj in destination.objects:
        if obj is None or obj.type != "MESH":
            continue
        obj.name = f"NBA 2K Preview {obj.name}"
        bpy.context.scene.collection.objects.link(obj)
        appended_count += 1
    if not appended_count:
        raise RuntimeError(
            f"No mesh objects found in additional preview model: {append_path}"
        )
    print(
        f"[NBA 2K Preview] Added {appended_count} mesh object(s) "
        f"from {append_path.name}"
    )


def refresh_preview_from_scene() -> int:
    settings = _preview_settings_from_scene()
    _ensure_appended_preview_model(settings)
    parts = settings.get("parts")
    if not isinstance(parts, list) or not parts:
        raise RuntimeError("Preview settings do not contain any uniform parts.")
    refreshed = 0
    for part in parts:
        name = str(part.get("name", "Uniform"))
        keyword = str(part.get("material_keyword", ""))
        color_path = Path(str(part.get("color_path", "")))
        normal_value = str(part.get("normal_path", ""))
        normal_path = Path(normal_value) if normal_value else None
        normal_strength = float(part.get("normal_strength", 0.0))
        if not color_path.exists():
            raise FileNotFoundError(f"{name} color texture not found: {color_path}")
        if normal_strength <= 0:
            normal_path = None
        elif normal_path is None or not normal_path.exists():
            raise FileNotFoundError(f"{name} normal texture not found: {normal_path}")
        materials = _material_targets(keyword)
        if not materials:
            raise RuntimeError(f"No {name.lower()} material found in the preview model.")
        for material in materials:
            _apply_material_textures(material, color_path, normal_path, normal_strength)
            refreshed += 1
            print(f"[NBA 2K Preview] Refreshed {name} material: {material.name}")
    _setup_view()
    return refreshed


class NBA2K_OT_refresh_preview(bpy.types.Operator):
    bl_idname = "nba2k.refresh_preview"
    bl_label = "Refresh Preview"
    bl_description = "Reload the latest preview texture files exported by NBA 2K Jersey Modder"

    def execute(self, context):
        try:
            count = refresh_preview_from_scene()
        except Exception as exc:  # noqa: BLE001 - Blender operator boundary.
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Refreshed {count} material(s).")
        return {"FINISHED"}


class NBA2K_PT_preview_panel(bpy.types.Panel):
    bl_label = "NBA 2K Preview"
    bl_idname = "NBA2K_PT_preview_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Jersey Modder"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.operator("nba2k.refresh_preview", icon="FILE_REFRESH")
        garment = str(scene.get("nba2k_preview_garment", "Uniform"))
        template_name = str(scene.get("nba2k_preview_template_name", ""))
        model_label = (
            f"Model: {garment} / {template_name}"
            if template_name
            else f"Model: {garment}"
        )
        layout.label(text=model_label)
        color_path = Path(scene.get("nba2k_preview_color_path", ""))
        normal_strength = float(scene.get("nba2k_preview_normal_strength", 0.0))
        if color_path:
            layout.label(text="Jersey and shorts textures loaded")
        layout.label(
            text="Normal: On" if normal_strength > 0 else "Normal: Off"
        )


PREVIEW_CLASSES = (
    NBA2K_OT_refresh_preview,
    NBA2K_PT_preview_panel,
)


def register_preview_ui() -> None:
    for cls in PREVIEW_CLASSES:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
        bpy.utils.register_class(cls)


def _setup_view() -> None:
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            area.spaces.active.shading.type = "MATERIAL"
    _frame_uniform_once()
    _ensure_preview_light()


def _frame_uniform_once() -> None:
    scene = bpy.context.scene
    if scene.get("nba2k_preview_framed", False):
        return
    mesh_objects = [obj for obj in scene.objects if obj.type == "MESH"]
    if not mesh_objects:
        return
    selected_before = list(bpy.context.selected_objects)
    active_before = bpy.context.view_layer.objects.active
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    for obj in mesh_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_objects[0]
    for area in bpy.context.screen.areas:
        if area.type != "VIEW_3D":
            continue
        region = next((item for item in area.regions if item.type == "WINDOW"), None)
        if region is None:
            continue
        with bpy.context.temp_override(area=area, region=region):
            bpy.ops.view3d.view_selected(use_all_regions=False)
    for obj in mesh_objects:
        obj.select_set(False)
    for obj in selected_before:
        if obj.name in scene.objects:
            obj.select_set(True)
    if active_before and active_before.name in scene.objects:
        bpy.context.view_layer.objects.active = active_before
    scene["nba2k_preview_framed"] = True


def _ensure_preview_light() -> None:
    if not bpy.data.objects:
        return
    light = bpy.data.objects.get("NBA 2K Preview Light")
    if light is None:
        bpy.ops.object.light_add(type="AREA", location=(0, -3, 4))
        light = bpy.context.object
        light.name = "NBA 2K Preview Light"
    light.location = (0, -3, 4)
    if light.type == "LIGHT":
        light.data.type = "AREA"
        light.data.energy = 450
        light.data.size = 4


def main() -> None:
    args = _argv_after_double_dash()
    if len(args) < 2:
        raise SystemExit("Expected color texture path and normal texture path after --")
    color_path = Path(args[0])
    normal_path = Path(args[1])
    normal_strength = float(args[2]) if len(args) >= 3 else 0.0
    settings_path = Path(args[3]) if len(args) >= 4 else None
    if not color_path.exists():
        raise SystemExit(f"Color texture not found: {color_path}")
    if normal_strength > 0 and not normal_path.exists():
        raise SystemExit(f"Normal texture not found: {normal_path}")

    scene = bpy.context.scene
    scene["nba2k_preview_color_path"] = str(color_path)
    scene["nba2k_preview_normal_path"] = str(normal_path)
    scene["nba2k_preview_normal_strength"] = normal_strength
    if settings_path is not None:
        scene["nba2k_preview_settings_path"] = str(settings_path)
    register_preview_ui()
    refresh_preview_from_scene()


main()
