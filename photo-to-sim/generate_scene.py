"""
Auto-generate scene.xml from SAM3D meshes + Gemini semantics.
No manual XML writing — everything computed from the data.
"""
import json
import os
import trimesh
import numpy as np
import xml.etree.ElementTree as ET
from pathlib import Path

ASSET_DIR = r"C:\Users\brind\Downloads\photo_to_sim_output"

# Load Gemini semantics
with open(os.path.join(ASSET_DIR, "scene_semantics.json")) as f:
    scene_data = json.load(f)

room = scene_data["room"]
objects = scene_data["objects"]

# Analyze all meshes to compute proper scaling
print("=== Analyzing meshes ===")
mesh_info = []
for i, obj in enumerate(objects):
    vis_path = os.path.join(ASSET_DIR, f"object_{i}_visual.obj")
    col_path = os.path.join(ASSET_DIR, f"object_{i}_collision.obj")
    
    mesh = trimesh.load(vis_path, force="mesh")
    raw_bbox = mesh.bounding_box.extents  # [x, y, z] in mesh units
    raw_center = mesh.centroid
    
    # Target real-world size from Gemini (meters)
    target_w = obj["dimensions_m"]["width"]
    target_h = obj["dimensions_m"]["height"]
    target_d = obj["dimensions_m"]["depth"]
    target_max = max(target_w, target_h, target_d)
    raw_max = max(raw_bbox)
    
    # UNIFORM scale factor = target largest dimension / raw largest dimension
    uniform_scale = target_max / raw_max
    
    # Actual real-world size after uniform scaling
    real_size = raw_bbox * uniform_scale
    
    print(f"  {obj['label']:25s} | raw={raw_bbox.round(3)} | scale={uniform_scale:.4f} | real={real_size.round(3)}m")
    
    mesh_info.append({
        "label": obj["label"],
        "obj_id": f"object_{i}",
        "raw_bbox": raw_bbox,
        "raw_center": raw_center,
        "uniform_scale": uniform_scale,
        "real_size": real_size,
        "position": obj["position_m"],
        "mass": obj["mass_kg"],
        "friction": obj["friction"],
        "is_static": obj["is_static"],
        "material": obj["material"],
    })

# Check if texture exists
has_texture = os.path.exists(os.path.join(ASSET_DIR, "material_0.png"))
print(f"\nTexture atlas found: {has_texture}")

# Build MJCF XML
print("\n=== Building scene.xml ===")
root = ET.Element("mujoco", model="photo_to_sim")

# Compiler
ET.SubElement(root, "compiler", angle="radian", meshdir=".", texturedir=".")

# Visual
vis = ET.SubElement(root, "visual")
ET.SubElement(vis, "global", offwidth="1280", offheight="720")

# Asset
asset = ET.SubElement(root, "asset")

# Skybox
ET.SubElement(asset, "texture", type="skybox", builtin="gradient",
              rgb1="0.45 0.6 0.8", rgb2="0.08 0.08 0.15", width="512", height="512")

# Floor texture
ET.SubElement(asset, "texture", name="floor_tex", type="2d", builtin="checker",
              rgb1="0.9 0.88 0.85", rgb2="0.8 0.78 0.75", width="512", height="512")
ET.SubElement(asset, "material", name="floor_mat", texture="floor_tex", texrepeat="6 6")

# Wall material
ET.SubElement(asset, "material", name="wall_mat", rgba="0.93 0.92 0.89 1")

# SAM3D texture (if it exists)
if has_texture:
    ET.SubElement(asset, "texture", name="sam3d_tex", type="2d", file="material_0.png")
    ET.SubElement(asset, "material", name="sam3d_mat", texture="sam3d_tex")

# Register meshes with uniform scale
for info in mesh_info:
    s = info["uniform_scale"]
    scale_str = f"{s:.6f} {s:.6f} {s:.6f}"
    
    # Clean label for XML name (no spaces)
    clean = info["label"].replace(" ", "_").replace("-", "_")
    info["clean_name"] = clean
    
    ET.SubElement(asset, "mesh", name=f"{clean}_vis",
                  file=f"{info['obj_id']}_visual.obj", scale=scale_str)
    ET.SubElement(asset, "mesh", name=f"{clean}_col",
                  file=f"{info['obj_id']}_collision.obj", scale=scale_str)

# Worldbody
worldbody = ET.SubElement(root, "worldbody")

# Lighting
rw = max(room["width"], 2.0)
rd = max(room["depth"], 1.5)
rh = room["height"]
ET.SubElement(worldbody, "light", pos=f"{rw/2} {rd/2} {rh-0.2}",
              dir="0 0 -1", diffuse="0.9 0.9 0.9", specular="0.3 0.3 0.3")
ET.SubElement(worldbody, "light", pos=f"{rw/4} {rd} {rh/2}",
              dir="0.2 -0.5 -0.3", diffuse="0.4 0.4 0.4")

# Floor
ET.SubElement(worldbody, "geom", name="floor", type="plane",
              size=f"{rw} {rd} 0.01", material="floor_mat")

# Back wall
ET.SubElement(worldbody, "geom", name="wall_back", type="box",
              size=f"{rw} 0.02 {rh/2}", pos=f"0 {-rd/2} {rh/2}", material="wall_mat")

# Place objects
for info in mesh_info:
    clean = info["clean_name"]
    pos = info["position"]
    pos_str = f"{pos['x']} {pos['y']} {pos['z']}"
    
    body = ET.SubElement(worldbody, "body", name=clean, pos=pos_str)
    
    # Freejoint for dynamic objects
    if not info["is_static"]:
        ET.SubElement(body, "freejoint", name=f"{clean}_jnt")
    
    # Visual geom (rendered, no collision)
    vis_attrs = {
        "name": f"{clean}_visual",
        "type": "mesh",
        "mesh": f"{clean}_vis",
        "contype": "0",
        "conaffinity": "0",
    }
    if has_texture:
        vis_attrs["material"] = "sam3d_mat"
    else:
        vis_attrs["rgba"] = "0.7 0.7 0.7 1"
    ET.SubElement(body, "geom", **vis_attrs)
    
    # Collision geom (invisible, handles physics)
    ET.SubElement(body, "geom",
                  name=f"{clean}_collision",
                  type="mesh",
                  mesh=f"{clean}_col",
                  mass=str(info["mass"]),
                  friction=f"{info['friction']} 0.005 0.001",
                  rgba="0 0 0 0")

# Write XML
ET.indent(root, space="  ")
xml_path = os.path.join(ASSET_DIR, "scene.xml")
tree = ET.ElementTree(root)
tree.write(xml_path, encoding="unicode", xml_declaration=True)

print(f"\n✅ scene.xml written to {xml_path}")
print(f"   Objects: {len(mesh_info)}")
print(f"   Textured: {has_texture}")

# Print the XML
with open(xml_path) as f:
    print(f.read())
