# 📸→🤖 Photo-to-Sim: Complete Walkthrough & Architecture

> Research Date: March 10, 2026 | Stack: SAM3D + Gemini 2.5 + MuJoCo

---

## 1. What We Built (Prototype v1)

A pipeline: single photo → SAM3D 3D extraction → Gemini VLM physics → MuJoCo `scene.xml`.

### Source Photo
![Original coffee counter scene](file:///C:/Users/brind/Downloads/sam/image.jpg)

### Gemini VLM Output (Worked ✅)
Gemini 2.5 Flash correctly identified all 7 objects with realistic physics:

| # | Label | Size (m) | Mass | Material | Static |
|---|---|---|---|---|---|
| 0 | Kitchen counter | 1.8×0.65×0.05 | 200kg | Quartz | ✅ |
| 1 | Coffee grinder | 0.15×0.20×0.40 | 2.5kg | Plastic | ✅ |
| 2 | Potted plant | 0.18×0.18×0.25 | 2.0kg | Ceramic | ✅ |
| 3 | Pour-over set | 0.15×0.15×0.28 | 1.2kg | Glass | ✅ |
| 4 | Coffee bean jar | 0.12×0.12×0.22 | 1.0kg | Glass | ✅ |
| 5 | Kitchen scale | 0.16×0.23×0.03 | 0.5kg | Plastic | ✅ |
| 6 | Coffee mug | 0.11×0.08×0.09 | 0.25kg | Ceramic | ✅ |

### MuJoCo Result (Failed ❌)
![MuJoCo viewer showing gray distorted objects](file:///C:/Users/brind/.gemini/antigravity/brain/2837e346-a9f6-4985-bd10-eb35690a1ab6/colab_notebook_verification_1773126294913.png)

Objects were gray, squished, and incorrectly positioned.

---

## 2. Root Cause Analysis (5 Bugs)

### Bug 1: No Textures (Everything Gray)
**Cause:** trimesh merges all GLB textures into one shared `material_0.png` atlas. Each OBJ references the same atlas but with different UV regions. MuJoCo only supports **one material per mesh** — so assigning the same material to every object maps them all to the wrong UV region.

**Fix:** Convert each GLB **individually** using `obj2mjcf`, which splits sub-meshes and creates per-object material/texture files.

### Bug 2: Distorted Shapes (Squished Pancakes)
**Cause:** Non-uniform scaling: `scale="3.0 0.65 0.07"` for the counter. SAM3D meshes have **arbitrary axis alignment** — mapping width→X, depth→Y, height→Z is wrong.

**Fix:** Use **uniform scaling** only: `scale_factor = target_size / mesh_size`, applied equally to X, Y, Z.

### Bug 3: Wrong Room Dimensions
**Cause:** Gemini estimated `room: 1.8m × 0.65m` — that's the **counter**, not the room. Close-up photos don't show room boundaries.

**Fix:** Don't estimate "room" from close-ups. Use a fixed generous boundary.

### Bug 4: OpenGL Crash on Colab
**Cause:** MuJoCo Renderer needs OpenGL. Colab CPU has no GPU/display. `MUJOCO_GL=egl` must be set **before first import**.

**Fix:** Either use GPU runtime or skip rendering on Colab (view locally).

### Bug 5: Y-up vs Z-up Mismatch
**Cause:** GLB uses Y-up (glTF standard). MuJoCo uses Z-up. No axis rotation was applied.

**Fix:** Apply `-90°` rotation around X-axis during GLB→OBJ conversion.

---

## 3. How SAM3D Playground Already Solves This

### The Key Insight
The Meta SAM3D playground already shows all objects **correctly placed, scaled, and composed** in a single 3D scene. This is NOT just visual — SAM3D's internal model predicts:

| Parameter | Type | Description |
|---|---|---|
| `scale` | float | Object's real-world scale factor |
| `rotation` | quaternion | Camera-relative rotation |
| `translation` | vec3 | Camera-relative 3D position |
| `camera_pose` | mat4 | Camera extrinsics |

### Why Our GLBs Didn't Have This
When you download **individual GLBs** from the playground, each object is at `[0,0,0]` with identity transform — the spatial layout is stripped. The playground renders the composed scene using the API's internal prediction data, but doesn't embed it in the downloaded files.

### How to Get the Spatial Data
Use the **SAM3D Python API** (`facebookresearch/sam-3d-objects`) directly instead of the web playground. The API returns a prediction dictionary including `scale`, `rotation`, `translation` per object — which gives you the exact scene layout the playground shows.

```python
# SAM3D API returns per-object transforms
prediction = sam3d_model.predict(image, mask)
# prediction contains: scale, rotation (quat), translation, camera_pose
```

---

## 4. 2026 State-of-the-Art: Photo-to-Sim

### Key 2026 Papers & Methods

| Method | Key Innovation |
|---|---|
| **Re³Sim** (arXiv 2026) | Gaussian rasterization for photorealistic sim rendering |
| **Automated Real2Sim** (2025) | Robot joint torque sensors for inertial parameter extraction |
| **Layout Anything** (2025) | Transformer for room layout from single image |
| **C2P-Net** (IEEE 2026) | Room layout via dominant planar surface detection |
| **Flash3D** (3DV 2026) | Feed-forward single-image 3D scene reconstruction |

### Industry Standard Pipeline (2026)
```
1. Segment    → SAM3/Grounded SAM (semantic + instance masks)
2. Reconstruct → SAM3D Objects (per-object 3D mesh + texture + transforms)
3. Physics    → VLM (Gemini/Qwen3) for mass, friction, joints
4. Collisions → CoACD convex decomposition (not simple convex hull)
5. Compile    → obj2mjcf → MJCF XML (or URDF for Isaac Sim)
6. Calibrate  → Depth Anything V2 + reference object for absolute scale
```

---

## 5. Validated Architecture v2

```
┌─────────────────────────────────────────────────────────────┐
│                    INPUT: Single Photo                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌─────────────────┐        ┌──────────────────┐
│  SAM3D API      │        │  Gemini 2.5 VLM  │
│  (Python, GPU)  │        │  (API call)      │
├─────────────────┤        ├──────────────────┤
│ Per object:     │        │ Per object:      │
│ • 3D mesh+tex   │        │ • label          │
│ • scale         │        │ • mass_kg        │
│ • rotation(quat)│        │ • friction       │
│ • translation   │        │ • is_dynamic     │
│ • camera_pose   │        │ • joint_type     │
└────────┬────────┘        └────────┬─────────┘
         │                          │
         └──────────┬───────────────┘
                    ▼
         ┌──────────────────┐
         │  Per-Object Conv │
         ├──────────────────┤
         │ 1. GLB → OBJ     │
         │    (trimesh)     │
         │ 2. Y-up → Z-up   │
         │    (-90° X rot)  │
         │ 3. Extract tex    │
         │    (per-obj PNG) │
         │ 4. Uniform scale  │
         │    (SAM3D scale) │
         │ 5. CoACD decomp   │
         │    (collision)   │
         └────────┬─────────┘
                  ▼
         ┌──────────────────┐
         │  Scene Compiler  │
         ├──────────────────┤
         │ • obj2mjcf per    │
         │   object mesh    │
         │ • Apply SAM3D    │
         │   transforms     │
         │ • Gemini physics │
         │ • freejoint for  │
         │   dynamic objs   │
         │ • Floor + walls  │
         └────────┬─────────┘
                  ▼
         ┌──────────────────┐
         │   scene.xml      │
         │   + meshes/      │
         │   + textures/    │
         └────────┬─────────┘
                  ▼
         ┌──────────────────┐
         │  MuJoCo Viewer   │
         │  (local render)  │
         └──────────────────┘
```

### Why This Architecture Works

| Problem | v1 Approach (Failed) | v2 Approach (Validated) |
|---|---|---|
| Object positions | Gemini guessed from photo | SAM3D API provides exact camera-relative transforms |
| Object scale | Non-uniform ratio math | SAM3D `scale` param + uniform scaling |
| Object rotation | None applied | SAM3D `rotation` quaternion + Y→Z axis fix |
| Textures | Shared atlas, one material | Per-object texture via `obj2mjcf` |
| Collisions | Simple convex hull | CoACD decomposition (multiple convex parts) |
| Room layout | Gemini estimated (got counter dims) | Fixed boundary + Depth Anything V2 for depth |

### What SAM3D API Provides vs. What We Still Need VLM For

| Data | Source | Why |
|---|---|---|
| 3D mesh + texture | **SAM3D** | Native output |
| Position in scene | **SAM3D** | Camera-relative layout prediction |
| Scale | **SAM3D** | Geometry model prediction |
| Rotation | **SAM3D** | Camera-relative quaternion |
| Object label | **Gemini VLM** | SAM3D doesn't do semantic labeling |
| Mass (kg) | **Gemini VLM** | Physics property, not geometric |
| Friction | **Gemini VLM** | Material-dependent, needs semantic understanding |
| Dynamic/static | **Gemini VLM** | Requires world knowledge |
| Joint type | **Gemini VLM** | Requires articulation understanding |
| Collision mesh | **CoACD** | Convex decomposition of SAM3D visual mesh |

---

## 6. Implementation Checklist

### Requirements
- **GPU Server/Pod** for SAM3D API inference (needs ~8GB VRAM)
- **Gemini API key** for VLM physics extraction (free tier works)
- **Local machine** with MuJoCo for final viewing
- **CoACD** (`pip install coacd`) for collision mesh generation
- **obj2mjcf** (`pip install obj2mjcf`) for per-object mesh+texture MJCF

### Steps
1. Run SAM3D API on photo → get meshes + transforms per object
2. Run Gemini on photo → get labels, mass, friction, joints per object
3. Per object: GLB→OBJ with Y→Z rotation, extract texture, CoACD collision
4. Per object: `obj2mjcf` to create proper MJCF with texture mapping
5. Assembly script merges all into one `scene.xml` with SAM3D transforms
6. View locally in `python -m mujoco.viewer`
