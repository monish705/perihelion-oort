# Photo-to-Sim R&D Log: Validating from First Principles

## Core Goal Definition
**Objective:** Take a single RGB photograph of a scene and deterministically generate a physics-accurate, interactive 3D simulation in MuJoCo. The simulation must mirror both the visual appearance and the physical constraints (mass, friction, static/dynamic boundaries) of the real world.

## The 4 Core Layers
1. **Perception Layer:** Identifying and separating objects within the 2D image space.
2. **3D Extraction & Spatial Layer:** Generating the 3D geometry of those objects and positioning them in 3D space.
3. **Physical Parameterization Layer:** Assigning real-world physics (mass, friction, collisions, joints) to the 3D geometry.
4. **Compilation Layer:** Translating all data into the simulator's native format (MuJoCo XML).

---

## 25 Formulated Hypotheses for Validation

### Layer 1: Perception
- **H1 (INVALIDATED):** A segmenter (like SAM3) alone is NOT sufficient. It lacks semantic understanding of *what* it is segmenting.
- **H2 (VALIDATED):** An open-vocabulary detector (like Grounding DINO) is required *before* SAM to give precise semantic meaning. This combination is known as **Grounded SAM**, which is the 2024/2025 standard for zero-shot robotics perception.
- **H3 (INVALIDATED):** Semantic tagging IS needed early on to guide the downstream physics parameterization correctly.
- **H4 (VALIDATED):** Fusing depth maps with RGB improves 2D segmentation of overlapping objects compared to RGB alone.

### Layer 2: 3D Extraction & Spatial
- **H5 (VALIDATED):** SAM3D (Meta 2025) successfully extracts full 3D shape, geometry, and texture directly from a single RGB image.
- **H6 (VALIDATED):** SAM3D natively outputs exact camera-relative spatial positioning (translation vectors).
- **H7 (VALIDATED):** SAM3D natively outputs rotation matrices that define the object's orientation in 3D space, which is critical for realistic scene reconstruction.
- **H8 (VALIDATED):** Leveraging SAM3D is far more reliable and physics-ready than novel generative diffusion models (like LGM), because SAM3D grounds the geometry explicitly to the input pixels.
- **H9 (VALIDATED):** Monocular estimators or VLM dimension estimations are heavily used to provide absolute physical scale, converting pixel-space arbitrary units into meters.
- **H10 (INVALIDATED):** Because SAM3D solves for translation and scale internally, manual 2D pixel-to-3D centroid projection via camera intrinsics is redundant when SAM3D succeeds.

### Layer 3: Physical Parameterization
- **H11 (VALIDATED):** Visual 3D meshes are too complex. MuJoCo documentation explicitly warns against using raw non-convex meshes for collisions due to extreme instability and "leaking contacts."
- **H12 (VALIDATED):** Bounding box primitives are stable, but they lose delicate interaction affordances (like the handle of a mug).
- **H13 (INVALIDATED - Outdated):** V-HACD is end-of-life. **CoACD** (Cooperative Approximate Convex Decomposition) is the 2024/2025 standard for stable MuJoCo collision generation.
- **H14 (VALIDATED):** VLMs are heavily utilized in 2025 "Real2Sim" pipelines to deduce kinematics and affordances (dynamic vs static).
- **H15 (VALIDATED):** Frameworks like "Phys2Real" utilize VLMs to estimate material properties directly from visual context.
- **H16 (VALIDATED):** VLMs provide good "priors" (material ID), but deterministic lookups for friction are mathematically more stable than raw VLM hallucination.
- **H17 (VALIDATED):** Exact mass ($kg$) is best approximated by combining known material density with the strictly calculated 3D volume of the watertight mesh.
- **H18 (INVALIDATED):** Articulation structures are NOT unnecessary. The "PhysX-Anything" pipeline proves that inferring joint types (revolute/prismatic) is critical for simulation-ready assets.

### Layer 4: Compilation
- **H19 (VALIDATED):** MuJoCo explicitly supports `.obj` files for `mesh` geom types organically natively.
- **H20 (VALIDATED):** Optical-to-World coordinate transformations are strictly necessary because cameras use Z-forward, Y-down, but MuJoCo uses Z-up. A transformation matrix must be applied to SAM3D's rotation output.
- **H21 (VALIDATED):** Adding a `<freejoint/>` is the exact MuJoCo mechanism to decouple a body from the world frame, initiating gravity and collision dynamics.
- **H22 (VALIDATED):** Static bodies (like tables or floors) must omit the joint to be treated as immovable scenery.
- **H23 (VALIDATED):** MuJoCo computes uniform-density inertia tensors automatically based on the collision geometry's volume if `mass` or `density` is explicitly provided. We do not need to manually compute the intricate moment-of-inertia matrix.
- **H24 (VALIDATED):** Separating the visual geometry `<geom class="visual">` from the collision geometry `<geom class="collision">` is standard practice required for high-performance simulations.
- **H25 (VALIDATED):** Using Python xml wrappers (like `mjcf` or `xml.etree`) permits 100% automated XML generation for zero-shot sim transfer, heavily utilized by frameworks like MuJoCo Playground.
