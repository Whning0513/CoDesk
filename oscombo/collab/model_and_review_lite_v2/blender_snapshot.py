"""Read-only Blender-side scene snapshot for the Lite evaluator."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy


def vector(values):
    return [round(float(value), 6) for value in values]


def snapshot():
    objects = {}
    for obj in bpy.context.scene.objects:
        row = {"type": obj.type, "location": vector(obj.location),
               "dimensions": vector(obj.dimensions), "rotation": vector(obj.rotation_euler)}
        if obj.type == "MESH":
            vertices = sorted(tuple(vector(vertex.co)) for vertex in obj.data.vertices)
            row["mesh_sha256"] = hashlib.sha256(
                json.dumps(vertices, separators=(",", ":")).encode()).hexdigest()
            row["materials"] = [material.name for material in obj.data.materials]
        if obj.type == "CAMERA":
            row["lens_mm"] = round(float(obj.data.lens), 6)
        objects[obj.name] = row
    return {"scene_name": bpy.context.scene.name,
            "active_object": bpy.context.view_layer.objects.active.name
            if bpy.context.view_layer.objects.active else None,
            "objects": objects}


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.write_text(json.dumps(snapshot(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
