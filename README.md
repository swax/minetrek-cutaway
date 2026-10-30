# MineTrek Cutaway Renderer

A configuration-driven Minecraft Classic renderer for animated cutaways, deck
tours and snapshot time lapses. Cameras, clipping, block-removal masks, captions,
transitions and audio are declared in JSON configuration files.

Originally developed to create the MineTrek 1.0 Enterprise-D cutaway film, the
renderer can be used with other Minecraft Classic worlds. World geometry,
clipping rules and presentation are supplied through project configuration.

The renderer reads the original gzip/Java-serialized Classic `.dat` format directly.
It also accepts a simple voxel interchange format. It preserves input geometry
by default: there are no project-specific cleanup boxes, layer heights, world
dimensions, titles or camera paths built into the code.

## Quick start

Rendering requires Windows x64, Python 3.11+, and the .NET Framework 4.x C# compiler.
GPU rendering requires OpenGL 4.3 with double precision shader support. Video export
requires FFmpeg on PATH. Python source and configuration tests also run on Linux.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py doctor
.\.venv\Scripts\python.exe run.py build-engine
.\.venv\Scripts\python.exe run.py demo --backend cpu
```

The demo uses a small synthetic two-level room and needs no external map, texture
pack, font or soundtrack. It writes the first frame to `work/renders/demo`.
Choose a new output directory for subsequent runs:

```powershell
python run.py demo --backend gpu --frames 0,47,95,143 --output work/demo-stills
python run.py demo --video work/demo.mp4
```

The six-second demo shows a roof strip, an orbit and a dissolve to a lower section.
The complete project is in [examples/demo.json](examples/demo.json).

The repository and Python distribution are named `minetrek-cutaway`. An installed
copy provides the `minetrek-cutaway` command; the Python package is
`minetrek_cutaway`. See [installation details](docs/setup.md).

## Configuration-driven rendering

```powershell
python run.py inspect path/to/world.dat
python run.py validate path/to/project.json
python run.py render path/to/project.json --frames 0,120,240 --output work/stills
python run.py render path/to/project.json --frames 120:168 --video work/excerpt.mp4
python run.py render path/to/project.json --video work/full-video.mp4
```

Frame ranges use an exclusive end. Without `--frames` or `--video`, only the first
frame is rendered. Output files and directories must be new. Source files are
read only; optional crop, exclusion and selection-mask operations are explicit
configuration data.

A project can use short `shots` with interpolated cameras, or an explicit frame
plan in `frames` / `frames_file` for exact camera paths and transitions. The same
format supports JSON drawing layers for headers, text, statistics and captions.
No Python project hooks or application-specific plugins are required.

See [configuration](docs/configuration.md), [setup](docs/setup.md), and
[architecture](docs/architecture.md).

## Rendering features

- Arbitrary Classic world dimensions within the documented memory limit.
- Orthographic cameras with explicit center/scale or automatic bounding-box fit.
- Per-frame horizontal cuts, slice/ghost context and selected-block strip reveals.
- Original half-height Classic slabs and configurable full-cube diagnostics.
- Studio, flat and dramatic GPU lighting; studio CPU rendering.
- Optional 16x16 texture atlases with isolated tile mipmaps and filtered GPU glass.
- Complete-view crossfades, overlay layers and fades to black.
- H.264 video export with optional audio and timeline-relative excerpts.

CPU rendering uses cutout transparency; GPU rendering supports smoothed window
coverage. Their textured output can differ. Reference comparisons should use the
same backend, renderer settings and source assets.

## Source layout

```text
src/minetrek_cutaway/
  classic.py             Classic save decoder and palette
  volumes.py             Variable-sized volumes and configured transformations
  textures.py            Classic atlas preparation
  project.py             JSON validation and shot/frame compilation
  composite.py           Generic drawing layers and view transitions
  pipeline.py            Rendering, frame hashes and video/audio export
  engine/csharp/         CPU/GPU engines and analytic slab checks
  engine/shaders/        Generic voxel shader
examples/                Asset-free JSON project
docs/                    Setup, format and architecture
tests/                   Asset-free parser/configuration tests
scripts/                 Public-source checks and ZIP export
work/                    Local inputs, production records and outputs; ignored
```

## Checks and distribution

Development formatting is configured for Python, C#, GLSL, JSON, YAML, Markdown
and TOML. See [formatting setup and commands](docs/formatting.md).

```powershell
python -m unittest discover -s tests -v
python scripts/check_repository.py
python scripts/export_source.py
```

The source-only ZIP is written to `work/exports/minetrek-cutaway-source.zip`.
Only source, generic examples, docs, tests and the workflow are included. A public
file allowlist keeps local production files out of Git and source exports.

Software is [MIT licensed](LICENSE). Supply maps, textures, music and fonts under
their own terms; see [THIRD_PARTY.md](THIRD_PARTY.md). Modern Java region worlds,
Bedrock worlds and arbitrary Java serialization are outside the importer's scope.
