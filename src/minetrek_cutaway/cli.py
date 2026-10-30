"""Command-line interface for configuration-driven cutaway rendering."""

import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

from .paths import PACKAGE, WORK


def select_frames(value, count):
    if value is None:
        return [0]
    if ":" in value:
        a, b = value.split(":", 1)
        indices = list(range(int(a or 0), int(b or count)))
    else:
        indices = [int(v) for v in value.split(",")]
    if not indices or indices != sorted(set(indices)) or indices[0] < 0 or indices[-1] >= count:
        raise ValueError("Choose sorted, distinct frame indices inside the timeline.")
    return indices


def parser():
    p = argparse.ArgumentParser(
        prog="minetrek-cutaway",
        description="MineTrek Cutaway Renderer - JSON projects, stills and videos.",
    )
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Show dependency and working-directory information")
    inspect = commands.add_parser(
        "inspect", help="Inspect a preserved Java-serialized Classic save"
    )
    inspect.add_argument("save", type=Path)
    compiler = commands.add_parser("build-engine", help="Compile the CPU and GPU engines")
    compiler.add_argument("--target", choices=["all", "cpu", "gpu", "checks"], default="all")
    compiler.add_argument("--force", action="store_true")
    validate = commands.add_parser(
        "validate", help="Resolve project inputs and validate every frame"
    )
    validate.add_argument("project", type=Path)
    for name in ["render", "demo"]:
        render = commands.add_parser(
            name,
            help="Render a JSON project"
            if name == "render"
            else "Render the synthetic example project",
        )
        if name == "render":
            render.add_argument("project", type=Path)
        render.add_argument(
            "--frames", help="Comma-separated indices, or start:end (end exclusive)"
        )
        render.add_argument(
            "--video",
            type=Path,
            help="Encode a contiguous frame range; defaults to the full timeline",
        )
        render.add_argument("--output", type=Path, help="New directory for lossless still frames")
        render.add_argument("--backend", choices=["cpu", "gpu"])
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.command == "doctor":
            from .build import compiler_path

            packages = {}
            for name in ["numpy", "Pillow"]:
                try:
                    packages[name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    packages[name] = None
            print(
                json.dumps(
                    dict(
                        python=sys.version.split()[0],
                        packages=packages,
                        compiler=str(compiler_path()),
                        compiler_found=compiler_path().is_file(),
                        ffmpeg=shutil.which("ffmpeg"),
                        ffprobe=shutil.which("ffprobe"),
                        work=str(WORK),
                        gpu="Run demo --backend gpu to test the OpenGL driver.",
                    ),
                    indent=2,
                )
            )
            return 0 if all(packages.values()) else 1
        if args.command == "inspect":
            import numpy as np
            from .classic import read_level

            blocks, meta = read_level(args.save)
            ids, counts = np.unique(blocks, return_counts=True)
            print(
                json.dumps(
                    dict(
                        size_xyz=[blocks.shape[2], blocks.shape[0], blocks.shape[1]],
                        metadata=meta,
                        blocks=dict(zip(map(str, ids.tolist()), counts.tolist())),
                    ),
                    indent=2,
                )
            )
        elif args.command == "build-engine":
            from .build import build

            for name, path in build(args.target, args.force).items():
                print(f"{name}: {path}")
        else:
            from .project import Project

            path = PACKAGE / "data/demo.json" if args.command == "demo" else args.project
            project = Project(path)
            if args.command == "validate":
                print(json.dumps(project.validate(), indent=2))
            else:
                from .pipeline import render

                if args.backend:
                    project.backend = args.backend
                if (
                    project.backend == "cpu"
                    and project.renderer.get("lighting", "studio") != "studio"
                ):
                    raise ValueError("CPU rendering supports studio lighting only.")
                frames = (
                    list(range(len(project.frames)))
                    if args.video and not args.frames
                    else select_frames(args.frames, len(project.frames))
                )
                output = args.video or args.output or WORK / "renders" / path.stem
                report = render(project, frames, output, video=bool(args.video))
                print(f"Wrote {len(report['frames'])} frame(s): {output.resolve()}")
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
