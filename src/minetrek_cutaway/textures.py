"""Prepare 16x16 Classic texture atlases with isolated mipmaps."""

from pathlib import Path
import struct

import numpy as np
from PIL import Image


def prepare(source, target):
    source, target = Path(source), Path(target)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() == ".mttex":
        return source
    image = Image.open(source).convert("RGBA")
    size = image.width // 16
    if image.width != image.height or image.width % 16 or size < 1 or size & (size - 1):
        raise ValueError("Texture atlas must be square, with 16x16 power-of-two tiles.")
    tiles = [
        image.crop(((i % 16) * size, (i // 16) * size, (i % 16 + 1) * size, (i // 16 + 1) * size))
        for i in range(256)
    ]
    glass = np.asarray(tiles[49]).astype("f8") / 255
    glass[:, :, :3] *= glass[:, :, 3:4]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as f:
        f.write(struct.pack("<3i", size, 256, size.bit_length()))
        for level in range(size.bit_length()):
            side = max(1, size >> level)
            factor = size // side
            for index, tile in enumerate(tiles):
                if index == 49:
                    pixels = glass.reshape(side, factor, side, factor, 4).mean((1, 3))
                    f.write(np.rint(np.clip(pixels, 0, 1) * 255).astype("u1").tobytes())
                else:
                    f.write(tile.resize((side, side), Image.Resampling.BOX).tobytes())
    return target
