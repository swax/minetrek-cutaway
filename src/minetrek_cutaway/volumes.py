"""Classic imports and explicit, project-configured volume transformations."""

import hashlib
import math
from pathlib import Path
import struct

import numpy as np

from .classic import classic_palette, read_level
from .paths import relative_path

MAX_CELLS = 268_435_456


def dimensions(size):
    if not isinstance(size, list) or len(size) != 3 or any(type(v) != int or v < 1 for v in size):
        raise ValueError("Volume size must be three positive integers in X,Y,Z order.")
    if math.prod(size) > MAX_CELLS:
        raise ValueError(f"Volume exceeds {MAX_CELLS:,} cells.")
    return size


def bounds(value, size):
    if not isinstance(value, list) or len(value) != 6 or any(type(v) != int for v in value):
        raise ValueError("Bounds must be [xmin,xmax,ymin,ymax,zmin,zmax] integers.")
    x0, x1, y0, y1, z0, z1 = value
    w, h, l = size
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h and 0 <= z0 < z1 <= l):
        raise ValueError(f"Bounds {value} exceed volume size {size}.")
    return slice(y0, y1), slice(z0, z1), slice(x0, x1)


def voxel_header(path):
    with Path(path).open("rb") as f:
        raw = f.read(780)
    if len(raw) != 780:
        raise ValueError(f"Truncated voxel header: {path}")
    w, l, h = struct.unpack("<3i", raw[:12])
    dimensions([w, h, l])
    if Path(path).stat().st_size != 780 + w * l * h:
        raise ValueError(f"Voxel byte count does not match its dimensions: {path}")
    return [w, h, l], np.frombuffer(raw[12:], dtype="u1").reshape(256, 3).copy()


def read_voxels(path):
    size, palette = voxel_header(path)
    w, h, l = size
    return np.memmap(path, mode="r", dtype="u1", offset=780, shape=(h, l, w)), palette


def write_voxels(path, blocks, palette=None):
    h, l, w = blocks.shape
    dimensions([w, h, l])
    with Path(path).open("wb") as f:
        f.write(struct.pack("<3i", w, l, h))
        f.write((classic_palette() if palette is None else palette).astype("u1").tobytes())
        f.write(blocks.tobytes())


class Sources:
    def __init__(self, definitions, base, cache):
        self.definitions = definitions
        self.base = Path(base)
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.prepared = {}
        self.visiting = set()

    def prepare(self, name):
        if name in self.prepared:
            return self.prepared[name]
        if name in self.visiting:
            raise ValueError(f"Source dependency cycle: {name}")
        if name not in self.definitions:
            raise ValueError(f"Unknown source: {name}")
        self.visiting.add(name)
        spec = self.definitions[name]
        kind = spec.get("type")
        if "marked_blocks" in spec and type(spec["marked_blocks"]) != bool:
            raise ValueError("marked_blocks must be a boolean.")
        allowed = {
            "type",
            "path",
            "size",
            "boxes",
            "base",
            "include_bounds",
            "exclude_boxes",
            "mark_boxes",
            "sha256",
            "marked_blocks",
        }
        if set(spec) - allowed:
            raise ValueError(f"Unknown source settings: {set(spec) - allowed}")
        palette = classic_palette()
        path = None
        if kind in {"classic", "vox"}:
            path = relative_path(self.base, spec["path"])
            if spec.get("sha256"):
                with path.open("rb") as f:
                    actual = hashlib.file_digest(f, "sha256").hexdigest()
                if actual != spec["sha256"]:
                    raise ValueError(f"Source hash differs: {name}")
            if kind == "vox":
                blocks, palette = read_voxels(path)
            else:
                blocks, _ = read_level(path)
        elif kind == "synthetic":
            w, h, l = dimensions(spec["size"])
            blocks = np.zeros((h, l, w), dtype="u1")
            for box in spec.get("boxes", []):
                block = box["block"]
                if type(block) != int or not 0 <= block <= 255:
                    raise ValueError("Block IDs must be integers from 0 through 255.")
                blocks[bounds(box["bounds"], [w, h, l])] = block
        elif kind == "derived":
            parent = self.prepare(spec["base"])
            blocks, palette = read_voxels(parent["path"])
        else:
            raise ValueError(f"Unknown source type: {kind}")
        h, l, w = blocks.shape
        size = dimensions([w, h, l])
        modified = any(key in spec for key in ["include_bounds", "exclude_boxes", "mark_boxes"])
        if modified:
            blocks = np.array(blocks)
            if "include_bounds" in spec:
                area = bounds(spec["include_bounds"], size)
                clean = np.zeros_like(blocks)
                clean[area] = blocks[area]
                blocks = clean
            for box in spec.get("exclude_boxes", []):
                blocks[bounds(box, size)] = 0
            for box in spec.get("mark_boxes", []):
                area = blocks[bounds(box, size)]
                if np.any(area >= 128):
                    raise ValueError("Selection masks require original block IDs below 128.")
                area[area != 0] |= np.uint8(128)
        if kind != "vox" or modified:
            path = self.cache / (name + ".vox")
            write_voxels(path, blocks, palette)
        result = dict(
            path=path, size=size, marked=bool(spec.get("marked_blocks") or spec.get("mark_boxes"))
        )
        if kind == "derived":
            result["marked"] = result["marked"] or self.prepared[spec["base"]]["marked"]
        self.prepared[name] = result
        self.visiting.remove(name)
        return result
