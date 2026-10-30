# Architecture and reproducibility

The public package has no project-specific script loader or callbacks. Rendering
inputs are volumes, textures, JSON camera/cut/overlay plans and optional audio.
Research, branding and other project content belongs in a separate working folder.

`Project` validates JSON and compiles shots into frames. `Sources` decodes Classic
maps or voxel files, applying only configured operations. The CPU/GPU engine
receives geometry jobs. Pillow composes drawing layers and complete-view
dissolves. FFmpeg encodes the RGB frames and audio.

Frame plans are separate from the renderer. A project can retain an exact plan
while changing its source scripts, and the renderer can accept plans produced
by another application.

Every render writes verification JSON with frame indices, raw RGBA model hashes
and final RGB pixel hashes. Compare these uncompressed outputs to avoid video
compression differences. Use explicit camera scale/center, traversal settings
and prepared textures for exact reference comparisons.

The synthetic demo exercises small world dimensions, geometry at Y=0, selected
roof removal, orbiting cameras, overlays and crossfades. Analytic C# checks verify
slabs and shadows. Python tests cover import layout, transformations, validation
and timeline compilation.

CPU and GPU use related algorithms but different glass treatment. Exact pixel
equivalence is a same-backend/settings comparison; it is not a promise of equal
floating-point results across different GPU drivers.
