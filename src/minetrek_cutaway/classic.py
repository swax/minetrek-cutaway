"""Read the preserved gzip + Java-serialized Minecraft Classic levels as data."""

from __future__ import annotations

import gzip
import struct
from pathlib import Path

import numpy as np


def read_level(path: Path):
    raw = gzip.decompress(path.read_bytes())
    if raw[:11] != bytes.fromhex("271bb78802aced00057372"):
        raise ValueError(f"Unsupported level header: {path.name}")
    pos = 11

    def utf():
        nonlocal pos
        length = struct.unpack_from(">H", raw, pos)[0]
        pos += 2
        value = raw[pos : pos + length].decode("utf-8")
        pos += length
        return value

    if utf() != "com.mojang.minecraft.level.Level":
        raise ValueError("Unexpected serialized root class")
    pos += 9  # serialVersionUID + flags
    field_count = struct.unpack_from(">H", raw, pos)[0]
    pos += 2
    fields = []
    for _ in range(field_count):
        kind = chr(raw[pos])
        pos += 1
        name = utf()
        fields.append((kind, name))
        if kind in "L[":
            token = raw[pos]
            pos += 1
            if token == 0x74:
                utf()
            elif token == 0x71:
                pos += 4
            else:
                raise ValueError("Unexpected field type descriptor")
    if raw[pos : pos + 2] != b"\x78\x70":
        raise ValueError("Unexpected root class annotations or superclass")
    pos += 2
    metadata = {}
    for kind, name in fields:
        if kind in "L[":
            break
        fmt = {"I": ">i", "J": ">q", "Z": ">?", "F": ">f"}[kind]
        metadata[name] = struct.unpack_from(fmt, raw, pos)[0]
        pos += struct.calcsize(fmt)
    width, length, height = (metadata[k] for k in ("width", "height", "depth"))
    volume = width * length * height
    if min(width, length, height) < 1 or volume > 268_435_456:
        raise ValueError("Invalid or unsupported Classic world dimensions")
    signature = b"\x75\x72\x00\x02[B"
    candidate = raw.find(signature, pos)
    while candidate >= 0:
        start = candidate + 23
        if (
            raw[candidate + 14 : candidate + 19] == b"\x02\x00\x00\x78\x70"
            and struct.unpack_from(">i", raw, candidate + 19)[0] == volume
            and start + volume <= len(raw)
        ):
            blocks = np.frombuffer(raw, dtype=np.uint8, count=volume, offset=start)
            return blocks.reshape(height, length, width), metadata
        candidate = raw.find(signature, candidate + 1)
    raise ValueError(f"Could not identify the block array: {path.name}")


def classic_palette():
    # Representative colors for the original Classic block IDs.
    # IDs 21..36 are the sixteen Classic wool colors (not modern block IDs).
    colors = [
        (0, 0, 0),
        (109, 111, 112),
        (111, 174, 69),
        (113, 84, 62),
        (85, 85, 85),
        (170, 138, 85),
        (112, 117, 33),
        (64, 64, 64),
        (86, 105, 174),
        (86, 105, 174),
        (251, 69, 13),
        (251, 69, 13),
        (217, 208, 158),
        (136, 126, 125),
        (179, 172, 109),
        (209, 184, 167),
        (95, 95, 95),
        (86, 68, 41),
        (45, 145, 32),
        (165, 164, 56),
        (212, 255, 255),
        (226, 52, 52),
        (219, 134, 50),
        (227, 227, 52),
        (135, 222, 51),
        (49, 221, 49),
        (50, 222, 135),
        (51, 221, 221),
        (104, 162, 221),
        (121, 121, 224),
        (135, 50, 222),
        (173, 73, 221),
        (224, 51, 224),
        (216, 48, 132),
        (116, 116, 116),
        (160, 160, 160),
        (217, 217, 217),
        (169, 188, 0),
        (162, 31, 12),
        (167, 126, 98),
        (138, 31, 34),
        (223, 164, 43),
        (194, 194, 194),
        (169, 169, 169),
        (169, 169, 169),
        (208, 128, 105),
        (218, 65, 23),
        (109, 106, 87),
        (149, 161, 149),
        (31, 31, 39),
    ]
    palette = np.full((256, 3), (170, 145, 170), dtype=np.uint8)
    palette[: len(colors)] = colors
    return palette
