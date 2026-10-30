"""Run with Blender 5.0 in background to build independent Lite fixtures."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=("initial", "gold", "wrong-width"), required=True)
    args = parser.parse_args(argv)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "Lamp_Lite_Review"
    scene.unit_settings.system = "METRIC"
    def material(name, color):
        value = bpy.data.materials.new(name)
        value.diffuse_color = color
        return value

    bronze = material("Mat_Bronze", (0.48, 0.28, 0.10, 1.0))
    warm = material("Mat_Warm_Glass", (1.0, 0.72, 0.30, 1.0))
    green = material("Mat_Deep_Green", (0.04, 0.22, 0.13, 1.0))
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=0.12,
                                        location=(0, 0, 0.06))
    base = bpy.context.object
    base.name = "Lamp_Base"
    base.data.materials.append(bronze)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.25,
                                         location=(0, 0, 1.70))
    bulb = bpy.context.object
    bulb.name = "Lamp_Bulb"
    bulb.data.materials.append(warm)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.60, depth=0.60,
                                        location=(0, 0, 1.70))
    shade = bpy.context.object
    shade.name = "Lamp_Shade"
    shade.data.materials.append(green)
    shade.display_type = "WIRE"
    width = {"initial": 1.20, "gold": 1.46, "wrong-width": 1.30}[args.variant]
    shade.dimensions = (width, width, 0.60)
    bpy.context.view_layer.update()
    bpy.ops.object.camera_add(location=(3.2, -4.8, 2.6))
    camera = bpy.context.object
    camera.name = "Camera_Main"
    scene.camera = camera
    direction = Vector((0, 0, 1.0)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    shade.select_set(True)
    bpy.context.view_layer.objects.active = shade
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.show_region_ui = True
                area.spaces.active.region_3d.view_location = (0.0, 0.0, 1.2)
                area.spaces.active.region_3d.view_distance = 5.0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()), compress=True)
    print(f"SAVED {args.output} {args.variant} {width}")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
