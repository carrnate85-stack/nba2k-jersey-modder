from __future__ import annotations

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
    jersey_materials = [mat for mat in materials if "jersey" in mat.name.lower()]
    return jersey_materials or materials[:1]


def _image_node(nodes, image_path: Path, label: str, colorspace: str):
    node = nodes.new("ShaderNodeTexImage")
    node.name = label
    node.label = label
    image = bpy.data.images.load(str(image_path), check_existing=True)
    image.reload()
    image.colorspace_settings.name = colorspace
    node.image = image
    return node


def _apply_material_textures(material: bpy.types.Material, color_path: Path, normal_path: Path) -> None:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")

    color_node = _image_node(nodes, color_path, "NBA 2K Preview Color", "sRGB")
    normal_image_node = _image_node(nodes, normal_path, "NBA 2K Preview Normal", "Non-Color")
    normal_node = nodes.new("ShaderNodeNormalMap")
    normal_node.name = "NBA 2K Preview Normal Map"
    normal_node.label = "NBA 2K Preview Normal Map"
    normal_node.inputs["Strength"].default_value = 0.75

    links.new(color_node.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(normal_image_node.outputs["Color"], normal_node.inputs["Color"])
    links.new(normal_node.outputs["Normal"], bsdf.inputs["Normal"])


def _setup_view() -> None:
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            area.spaces.active.shading.type = "MATERIAL"
    if not bpy.context.scene.camera and bpy.data.objects:
        bpy.ops.object.light_add(type="AREA", location=(0, -3, 4))
        bpy.context.object.name = "NBA 2K Preview Light"
        bpy.context.object.data.energy = 450
        bpy.context.object.data.size = 4


def main() -> None:
    args = _argv_after_double_dash()
    if len(args) < 2:
        raise SystemExit("Expected color texture path and normal texture path after --")
    color_path = Path(args[0])
    normal_path = Path(args[1])
    if not color_path.exists():
        raise SystemExit(f"Color texture not found: {color_path}")
    if not normal_path.exists():
        raise SystemExit(f"Normal texture not found: {normal_path}")

    materials = _material_targets()
    if not materials:
        raise SystemExit("No mesh material found to apply preview textures.")
    for material in materials:
        _apply_material_textures(material, color_path, normal_path)
        print(f"[NBA 2K Preview] Applied textures to material: {material.name}")
    _setup_view()


main()
