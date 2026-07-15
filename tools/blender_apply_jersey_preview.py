from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


def _argv_after_double_dash() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def _material_targets() -> list[bpy.types.Material]:
    mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    preferred_objects = [obj for obj in mesh_objects if obj.name.lower() == "player"]
    objects = preferred_objects or mesh_objects
    materials: list[bpy.types.Material] = []
    for obj in objects:
        for slot in obj.material_slots:
            if slot.material and slot.material not in materials:
                materials.append(slot.material)
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


def _preview_settings_from_scene() -> tuple[Path, Path | None, float]:
    scene = bpy.context.scene
    settings_path = scene.get("nba2k_preview_settings_path", "")
    if settings_path:
        path = Path(settings_path)
        if path.exists():
            try:
                settings = json.loads(path.read_text(encoding="utf-8"))
                color_path = Path(settings.get("color_path", ""))
                normal_path = Path(settings.get("normal_path", ""))
                normal_strength = float(settings.get("normal_strength", 0.0))
                scene["nba2k_preview_garment"] = str(
                    settings.get("garment", "Uniform")
                )
                scene["nba2k_preview_template_name"] = str(
                    settings.get("template_name", "")
                )
                scene["nba2k_preview_color_path"] = str(color_path)
                scene["nba2k_preview_normal_path"] = str(normal_path)
                scene["nba2k_preview_normal_strength"] = normal_strength
                if color_path.exists():
                    return color_path, normal_path, normal_strength
            except Exception as exc:  # noqa: BLE001 - Blender operator boundary.
                print(f"[NBA 2K Preview] Could not read preview settings: {exc}")

    color_path = Path(scene.get("nba2k_preview_color_path", ""))
    normal_path = Path(scene.get("nba2k_preview_normal_path", ""))
    normal_strength = float(scene.get("nba2k_preview_normal_strength", 0.0))
    return color_path, normal_path, normal_strength


def refresh_preview_from_scene() -> int:
    color_path, normal_path, normal_strength = _preview_settings_from_scene()
    if not color_path.exists():
        raise FileNotFoundError(f"Color texture not found: {color_path}")
    if normal_strength <= 0:
        normal_path = None
    elif normal_path is not None and not normal_path.exists():
        raise FileNotFoundError(f"Normal texture not found: {normal_path}")

    materials = _material_targets()
    if not materials:
        raise RuntimeError("No mesh material found to apply preview textures.")
    for material in materials:
        _apply_material_textures(material, color_path, normal_path, normal_strength)
        print(f"[NBA 2K Preview] Refreshed material: {material.name}")
    _setup_view()
    return len(materials)


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
            layout.label(text=f"Color: {color_path.name}")
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
    _ensure_preview_light()


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
