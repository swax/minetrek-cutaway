"""Portable tests for generic imports, source transforms and JSON frame plans."""

import copy
import gzip
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from minetrek_cutaway.classic import read_level
from minetrek_cutaway.cli import select_frames
from minetrek_cutaway.composite import compose, finish
from minetrek_cutaway.project import Project
from minetrek_cutaway.volumes import Sources, read_voxels, write_voxels


def temporary():
    parent = (ROOT / "work/test-tmp").resolve()
    assert parent.is_relative_to(ROOT / "work")
    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=parent)


def utf(value):
    return struct.pack(">H", len(value)) + value.encode()


def classic_bytes(length=12):
    raw = (
        bytes.fromhex("271bb78802aced00057372")
        + utf("com.mojang.minecraft.level.Level")
        + bytes(8)
        + b"\x02"
        + struct.pack(">H", 3)
    )
    raw += (
        b"I"
        + utf("width")
        + b"I"
        + utf("height")
        + b"I"
        + utf("depth")
        + b"\x78\x70"
        + struct.pack(">iii", 2, 3, 2)
    )
    descriptor = bytearray(23)
    descriptor[:6] = b"\x75\x72\x00\x02[B"
    descriptor[14:19] = b"\x02\x00\x00\x78\x70"
    descriptor[19:23] = struct.pack(">i", length)
    return gzip.compress(raw + descriptor + bytes(range(12)))


def minimal():
    return dict(
        version=1,
        output=dict(width=160, height=90, fps=24),
        sources=dict(
            scene=dict(
                type="synthetic",
                size=[13, 7, 9],
                boxes=[
                    dict(bounds=[0, 1, 0, 1, 0, 1], block=43),
                    dict(bounds=[12, 13, 6, 7, 8, 9], block=44),
                ],
            )
        ),
        frames=[dict(parts=[dict(source="scene")])],
    )


def project(folder, spec):
    path = Path(folder) / "project.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return Project(path)


class ClassicTests(unittest.TestCase):
    def test_axis_order(self):
        with temporary() as d:
            p = Path(d) / "input.dat"
            p.write_bytes(classic_bytes())
            blocks, _ = read_level(p)
            self.assertEqual(blocks.shape, (2, 3, 2))
            self.assertEqual(int(blocks[1, 2, 1]), 11)

    def test_wrong_array_length(self):
        with temporary() as d:
            p = Path(d) / "input.dat"
            p.write_bytes(classic_bytes(13))
            with self.assertRaisesRegex(ValueError, "block array"):
                read_level(p)

    def test_wrong_header(self):
        with temporary() as d:
            p = Path(d) / "input.dat"
            p.write_bytes(gzip.compress(b"unrelated format"))
            with self.assertRaisesRegex(ValueError, "header"):
                read_level(p)


class VolumeTests(unittest.TestCase):
    def test_arbitrary_dimensions_and_borders_preserved(self):
        with temporary() as d:
            p = project(d, minimal())
            p.validate()
            value = p.sources.prepared["scene"]
            blocks, _ = read_voxels(value["path"])
            self.assertEqual(value["size"], [13, 7, 9])
            self.assertEqual(blocks.shape, (7, 9, 13))
            self.assertEqual(int(blocks[0, 0, 0]), 43)
            self.assertEqual(int(blocks[6, 8, 12]), 44)
            self.assertEqual(np.count_nonzero(blocks), 2)

    def test_transform_does_not_change_base_source(self):
        with temporary() as d:
            spec = minimal()
            spec["sources"]["clipped"] = dict(
                type="derived",
                base="scene",
                exclude_boxes=[[0, 1, 0, 1, 0, 1]],
                mark_boxes=[[12, 13, 6, 7, 8, 9]],
            )
            spec["frames"][0]["parts"][0]["source"] = "clipped"
            p = project(d, spec)
            p.validate()
            derived, _ = read_voxels(p.sources.prepared["clipped"]["path"])
            original, _ = read_voxels(p.sources.prepared["scene"]["path"])
            self.assertEqual(int(derived[0, 0, 0]), 0)
            self.assertEqual(int(derived[6, 8, 12]), 44 | 128)
            self.assertEqual(int(original[0, 0, 0]), 43)
            self.assertEqual(int(original[6, 8, 12]), 44)

    def test_truncated_voxel_input(self):
        with temporary() as d:
            p = Path(d) / "bad.vox"
            p.write_bytes(bytes(780))
            with self.assertRaises(ValueError):
                read_voxels(p)

    def test_dependency_cycle(self):
        with temporary() as d:
            sources = Sources(
                dict(a=dict(type="derived", base="b"), b=dict(type="derived", base="a")),
                d,
                Path(d) / "cache",
            )
            with self.assertRaisesRegex(ValueError, "cycle"):
                sources.prepare("a")

    def test_outside_bounds_rejected(self):
        with temporary() as d:
            spec = minimal()
            spec["sources"]["scene"]["exclude_boxes"] = [[0, 14, 0, 1, 0, 1]]
            with self.assertRaisesRegex(ValueError, "exceed"):
                project(d, spec).validate()


class ConfigurationTests(unittest.TestCase):
    def test_world_bounds_are_configured(self):
        with temporary() as d:
            p = project(d, minimal())
            job = p.job(p.frames[0]["parts"][0], Path(d) / "out.rgba")
            self.assertEqual(
                (job["XMin"], job["XMax"], job["YMin"], job["YMax"], job["ZMin"], job["ZMax"]),
                (0, 13, 0, 7, 0, 9),
            )

    def test_demo_timing_and_crossfade(self):
        p = Project(ROOT / "examples/demo.json")
        self.assertEqual(len(p.frames), 144)
        self.assertEqual(len(p.frames[84]["parts"]), 2)
        self.assertEqual(p.frames[90]["blend"], 0.5)
        self.assertEqual(p.frames[0]["parts"][0]["clip"]["sweep_x"], 1)
        self.assertEqual(p.frames[47]["parts"][0]["clip"]["sweep_x"], 33)

    def test_unknown_setting_fails_instead_of_silent_default(self):
        with temporary() as d:
            spec = minimal()
            spec["frames"][0]["parts"][0]["camera"] = {"elevaton": 40}
            with self.assertRaisesRegex(ValueError, "camera"):
                project(d, spec).validate()

    def test_nonfinite_json_rejected(self):
        with temporary() as d:
            spec = minimal()
            spec["frames"][0]["blend"] = float("nan")
            with self.assertRaisesRegex(ValueError, "Non-finite"):
                project(d, spec)

    def test_overlapping_timeline_formats_rejected(self):
        with temporary() as d:
            spec = minimal()
            spec["shots"] = []
            with self.assertRaisesRegex(ValueError, "exactly one"):
                project(d, spec)

    def test_audio_settings_are_numeric_data(self):
        with temporary() as d:
            audio = Path(d) / "input.m4a"
            audio.write_bytes(b"placeholder")
            spec = minimal()
            spec["audio"] = dict(path="input.m4a", volume="1,another_filter")
            with self.assertRaisesRegex(ValueError, "finite number"):
                project(d, spec)

    def test_frame_selection(self):
        self.assertEqual(select_frames("2:5", 8), [2, 3, 4])
        with self.assertRaises(ValueError):
            select_frames("5,2", 8)
        with self.assertRaises(ValueError):
            select_frames("8", 8)

    def test_paths_resolve_from_config_in_another_directory(self):
        with temporary() as d:
            spec = minimal()
            path = Path(d) / "project.json"
            path.write_text(json.dumps(spec))
            env = dict(os.environ, MINETREK_CUTAWAY_WORK=str(Path(d) / "work"))
            result = subprocess.run(
                [sys.executable, str(ROOT / "run.py"), "validate", str(path)],
                cwd=d,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["frames"], 1)

    def test_bundled_demo_matches_documented_example(self):
        self.assertEqual(
            json.loads((ROOT / "examples/demo.json").read_text()),
            json.loads((ROOT / "src/minetrek_cutaway/data/demo.json").read_text()),
        )


class CompositeTests(unittest.TestCase):
    def test_alpha_band_then_complete_view_dissolve(self):
        image = Image.new("RGBA", (4, 4), (200, 100, 50, 255))
        overlay = dict(
            stages=[
                dict(
                    mode="over",
                    draw=[dict(type="rectangle", bounds=[0, 0, 3, 0], fill=[0, 0, 0, 128])],
                )
            ]
        )
        composed = compose(image, overlay, ROOT, [0, 0, 0])
        self.assertEqual(composed.getpixel((1, 0)), (100, 50, 25))
        self.assertEqual(composed.getpixel((1, 1)), (200, 100, 50))
        black = Image.new("RGB", (4, 4))
        result = finish([composed, black], 0.5, 0.5)
        self.assertEqual(result.getpixel((1, 1)), (50, 25, 12))


if __name__ == "__main__":
    unittest.main()
