# Photo-to-Sim Architecture (2026)

## The Actual Problem We Hit

Our prototype (SAM3D → trimesh → MuJoCo) failed because:

| Bug | Root Cause | What We Missed |
|---|---|---|
| Gray objects | trimesh merged all GLB textures into one shared atlas | Each GLB has its **own** embedded PBR texture — must convert individually |
| Squished shapes | Non-uniform scaling (width→X, depth→Y, height→Z) | SAM3D meshes have **arbitrary axis alignment** — use uniform scale only |
| Wrong positions | Gemini guessed from photo (gave counter dims as "room") | SAM3D API outputs camera-relative transforms (scale, rotation quat, translation) |
| No OpenGL on Colab | MuJoCo Renderer needs GPU | Skip Colab rendering, view locally |
| Y-up vs Z-up | GLB is Y-up, MuJoCo is Z-up, no rotation applied | Apply -90° X rotation during conversion |

---

## Tool Landscape (2026)

### Perception Layer
| Tool | What It Does | Output | License |
|---|---|---|---|
| **Grounding DINO** | Open-vocabulary object detection | Boxes + labels | Apache 2.0 |
| **SAM-2/3** | Promptable instance segmentation | Per-object masks | Apache-like |
| **ZoeDepth** | Monocular depth estimation | Depth map | MIT |

### 3D Reconstruction Layer
| Tool | What It Does | Output | Notes |
|---|---|---|---|
| **Meta SAM-3D Objects** | Single image+mask → 3D shape + texture | Gaussian Splat PLY, GLB | Each object gets transform: scale, rotation(quat), translation |
| **NVIDIA Lyra** (ICLR 2026) | Video diffusion → 3D Gaussian field | Gaussian Splat | Heavy: multi-GPU |
| **WorldLabs Marble** | Image/text → complete 3D scene | Gaussian PLY + **GLB colliders** | Cloud service, outputs environment+objects |
| **COLMAP** | Multi-view SfM → dense 3D | Point cloud + mesh | GPLv3, 10+ years mature |
| **Nerfstudio** | NeRF from multiple views | Mesh, novel views | Apache 2.0 |

### Physics & Articulation Layer
| Tool | What It Does | Output | Notes |
|---|---|---|---|
| **PhysX-Anything** | VLM → full articulated mesh | URDF with joints | Vision-LLM predicts material, size, joints |
| **Articulate AnyMesh** | GPT-4 infers hinge axes from geometry | Joint definitions | Works on doors, drawers, etc. |
| **Gemini/Qwen VLM** | Estimate mass, friction, material | JSON properties | Simple API call |

### Conversion & Simulation Layer
| Tool | What It Does | Output | Notes |
|---|---|---|---|
| **3DGRUT (NuRec)** | Gaussian PLY → USDZ | USDZ (neural volume) | NVIDIA's converter for Isaac Sim |
| **obj2mjcf** | OBJ+MTL → MJCF with textures | Per-object MJCF XML | Splits sub-meshes, preserves materials |
| **Isaac Sim** | Full GPU sim with RTX rendering | USD scene | Import USDZ (visual) + GLB (collider) |
| **MuJoCo** | Fast CPU/GPU physics | MJCF scene | Best for robotics, lighter than Isaac |

---

## Two Pipeline Options

### Option A: Isaac Sim (Best Visual Quality)
```
Photo → SAM-3D → Gaussian PLY per object
                     ↓
            3DGRUT (PLY → USDZ)     ← neural volume rendering
                     ↓
         Isaac Sim (import USDZ visual)
                     ↓
         SAM-3D GLB → Isaac Sim (import as collider, align)
                     ↓
         PhysX-Anything VLM → mass, friction, joints
                     ↓
       Full photorealistic sim with PhysX dynamics
```
**Pros:** Photorealistic rendering, native Gaussian support, RTX
**Cons:** Heavy (16GB+ VRAM), NVIDIA-only, complex setup

### Option B: MuJoCo (Fastest, Lighter)
```
Photo → SAM-3D → GLB per object (with embedded textures)
                     ↓
         Per-object: GLB → OBJ+MTL+PNG (trimesh, Y→Z rotation)
                     ↓
         Per-object: obj2mjcf → MJCF XML with proper texture binding
                     ↓
         Gemini VLM → mass, friction, static/dynamic per object
                     ↓
         Assembly script → scene.xml (SAM3D transforms for positions)
                     ↓
         MuJoCo viewer (local, interactive)
```
**Pros:** Lightweight, fast, CPU-capable, great for robotics
**Cons:** Less photorealistic, mesh-based only (no Gaussians)

### Option C: Hybrid (Best of Both)
```
Photo → WorldLabs Marble → full 3D scene
         ↓ Gaussian PLY (visuals)    ↓ GLB (colliders)
         3DGRUT → USDZ              obj2mjcf → MJCF
         ↓                           ↓
    Isaac Sim (visual)          MuJoCo (physics)
```

---

## What Was Wrong With Our Approach (Specifically)

### 1. Texture Handling
**What we did:** `trimesh.load(glb).dump(concatenate=True).export('object.obj')` — this merges all mesh nodes and creates a **single shared** `material_0.png` texture atlas.

**What we should do:**
```python
# Per-object conversion preserving individual textures
import trimesh
scene = trimesh.load('object_3.glb')
for name, geom in scene.geometry.items():
    # Each geometry has its own texture
    geom.export(f'object_3_{name}.obj')
    # This creates: object_3_geometry_0.obj + object_3_geometry_0.mtl + texture_0.png
```
Then run `obj2mjcf` on each individual OBJ to generate proper MJCF with texture binding.

### 2. Position/Scale/Rotation
**What we did:** Asked Gemini to guess positions from the photo → got 2D-projected guesses.

**What we should do:** Use **SAM3D API's prediction dictionary** which contains:
- `scale`: float (real-world scale)
- `rotation`: quaternion (camera-relative)  
- `translation`: vec3 (camera-relative position)

The playground uses these exact values to compose the 3D scene. Individual GLB downloads strip them.

### 3. Collision Meshes
**What we did:** Simple `mesh.convex_hull` — one convex shape per object.

**What we should do:** Use **CoACD** (Convex Approximate Convex Decomposition) to break complex shapes into multiple convex parts. This gives much better collision for concave objects (mugs, chairs, etc.).

---

## Immediate Fix for Current Prototype

Given what we have right now (7 GLBs + image.jpg), the fastest fix:

1. **Convert each GLB individually** (not batch) to preserve per-object textures
2. **Use `obj2mjcf`** on each OBJ to generate MJCF fragments with correct texture mapping
3. **Apply uniform scaling** (single scale factor per object)
4. **Apply Y→Z rotation** (-90° around X axis)
5. **Use Gemini positions** (they're approximate but reasonable for the counter layout)
6. **Assemble** the MJCF fragments into one scene.xml

### For the Full Pipeline (Next Iteration)
1. Run **SAM3D Python API** directly (not web playground) to get transforms
2. Or use **WorldLabs Marble** for the complete scene (gives both PLY visuals + GLB colliders)
3. Use **PhysX-Anything** for automated physics/joints
4. Target **Isaac Sim** for photorealistic rendering, **MuJoCo** for fast physics

---

## Implementation Priority

| Priority | Task | Effort |
|---|---|---|
| P0 | Fix per-object texture extraction from GLBs | 1 day |
| P0 | Fix uniform scaling + Y→Z rotation | 1 day |
| P1 | Integrate obj2mjcf for proper MJCF generation | 1 day |
| P1 | Run SAM3D Python API for transforms | 2 days |
| P2 | Add CoACD collision decomposition | 1 day |
| P2 | Evaluate Isaac Sim + 3DGRUT pathway | 3 days |
| P3 | Integrate PhysX-Anything for auto-physics | 1 week |
| P3 | Evaluate Marble for full scene generation | 1 week |
