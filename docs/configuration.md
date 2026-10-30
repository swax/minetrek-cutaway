# JSON project format (version 1)

Top-level settings: `version`, `output`, `renderer`, `sources`, exactly one of
`shots` / `frames` / `frames_file`, optional `overlays` / `overlays_file`, and
optional `audio`. Unknown top-level/source/renderer settings are rejected.

Paths are relative to the project JSON. Frame plans and drawing layouts can live
in separate JSON files without requiring Python code.

## Output and renderer

```json
{
  "version": 1,
  "output": {"width": 3840, "height": 2160, "fps": 24, "background": [9, 17, 28]},
  "renderer": {"backend": "gpu", "lighting": "studio"}
}
```

Dimensions and fps are positive integers; limits are 32 megapixels and 120 fps.
H.264 needs even dimensions. Lighting is `studio`, `flat` or `dramatic` on GPU;
CPU currently supports `studio` only.

Advanced settings are `ray_offset`, `shadow_distance`, `ray_steps`, `shadow_steps`.
Defaults scale to the world size. Set these explicitly to match an existing
renderer's camera arithmetic and traversal budgets.

## Sources

Every source has an identifier and a `type`:

```json
{
  "sources": {
    "save": {"type": "classic", "path": "inputs/world.dat"},
    "prepared": {"type": "vox", "path": "inputs/prepared.vox"},
    "cropped": {
      "type": "derived", "base": "save",
      "include_bounds": [0, 64, 0, 32, 0, 64],
      "exclude_boxes": [[0, 64, 0, 1, 0, 64]],
      "mark_boxes": [[0, 64, 20, 21, 0, 64]]
    }
  }
}
```

Sizes use **X,Y,Z**. Bounds use **xmin,xmax,ymin,ymax,zmin,zmax**, with exclusive
upper limits. Internal arrays are Y,Z,X. Crops/exclusions write derived working
volumes; originals are preserved. Disconnected blocks are retained unless excluded.

`mark_boxes` sets a selection bit on occupied cells for progressive removal.
Pre-encoded selections declare `marked_blocks: true`. Selection encoding requires
ordinary IDs below 128; unmarked sources preserve all byte IDs. Atlas mapping
covers Classic IDs 0–49; other IDs use palette colors.

An optional `sha256` pins a file input. `synthetic` sources provide a `size` and
`boxes`, each with `bounds` and `block`; see the demo.

Voxel format: little-endian int32 **width, length, height**, then 256 RGB palette
entries (768 bytes), then width*length*height uint8 cells ordered Y,Z,X. No padding
or world border is implicit.

## Shots

Each shot has `source`, frame-aligned `duration`, optional `camera`, `clip`,
`textures`, `overlay`, `full_cube_slabs`, `transition`, `ease`.

Camera `center` is X,Y,Z; `scale` is pixels per block. Omit center/scale to fit the
configured bounds. Azimuth/elevation/scale accept `[start,end]` pairs. `center_end`
animates a pan. `ease` is `smooth` by default or `linear`.

Clip fields: `bounds`, `height`, `closed_height`, `sweep_x`, `floor`, `mode`,
`context_alpha`, `focus_bounds`, `closed_focus_bounds`. Height is an exclusive
horizontal cut. `remaining` preserves lower blocks. `slice` also hides blocks
below `floor`; `ghost` uses the focus rectangle and context opacity. Focus
rectangles use xmin,xmax,zmin,zmax.

`sweep_x` selects open/closed height on either side of a plane. Marked cells
disappear on the closed side. Moving the plane from low X to high X strips
selected cells progressively; the demo removes a roof while keeping its walls.

`transition` dissolves the complete view, including its overlay, into the next
shot over the final seconds of this shot. It does not change total duration.

## Explicit frame plans

For precise reproduction, provide `frames` or `frames_file`:

```json
{
  "frames": [
    {"parts": [{"source": "save", "camera": {"center": [32, 16, 32], "scale": 10, "azimuth": 45, "elevation": 40}, "clip": {"height": 20}}]},
    {"parts": [{"source": "save"}, {"source": "cropped"}], "blend": 0.5, "fade": 0}
  ]
}
```

Each frame has one or two parts, accepting the same static view settings as shots.
The first part blends into the second using `blend` in [0,1]. `fade` in [0,1]
then fades the complete image to black. Time is frame index/fps.

## Textures and overlays

Part/shot `textures` points to a 16x16 Classic `terrain.png` atlas or prepared
`.mttex`. PNG conversion generates isolated mipmaps and premultiplied glass
coverage. Prepared atlases retain their original bytes.

An overlay is an object with `stages`, or an ID in `overlays`. An `over` stage
draws RGBA operations onto a transparent layer and alpha-composites it over the
model; a `draw` stage draws directly onto the RGB result. Operations:

- Rectangle: `type`, `bounds`, `fill`.
- Text: `type`, `position`, `text`, `font`, `size`, `fill`; optional `anchor`,
  `stroke_width`, `stroke_fill`, `align`, `spacing`.

`font: "default"` uses Pillow's default font. A file path uses a supplied font.
Keep backend, fonts, assets and Pillow version consistent for exact comparisons.

## Audio

`audio` accepts `path`, optional source `offset` seconds, `volume`, and `fade_out`
as `[start,end]` on the project timeline. Excerpts start audio at the selected
timeline position. Omit `audio` for silence. Video is newly encoded: compressed
bytes need not match an earlier export when uncompressed frames are identical.
