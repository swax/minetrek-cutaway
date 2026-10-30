"""Compile the Windows CPU and OpenGL compute renderers."""

import os
from pathlib import Path
import shutil
import subprocess

from .paths import PACKAGE, binary_path

TARGETS = {
    "cpu": ("DeckOrbitRenderer", ["DeckOrbitRenderer.cs"]),
    "gpu": ("GpuDeckRenderer", ["GpuDeckRenderer.cs", "DeckOrbitRenderer.cs"]),
    "checks": ("ClassicGeometryChecks", ["ClassicGeometryChecks.cs", "DeckOrbitRenderer.cs"]),
}


def compiler_path():
    configured = os.environ.get("MINETREK_CUTAWAY_CSC") or os.environ.get("CLASSIC_CUTAWAY_CSC")
    if configured:
        return Path(configured)
    return Path(
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    )


def build(target="all", force=False):
    if os.name != "nt":
        raise RuntimeError(
            "Rendering requires Windows x64; save inspection and configuration validation are portable."
        )
    compiler = compiler_path()
    if not compiler.is_file():
        raise FileNotFoundError(f"C# compiler missing: {compiler}. Set MINETREK_CUTAWAY_CSC.")
    selected = TARGETS if target == "all" else {target: TARGETS[target]}
    result = {}
    for key, (entry, names) in selected.items():
        sources = [PACKAGE / "engine/csharp" / name for name in names]
        output = binary_path(entry + ".exe")
        output.parent.mkdir(parents=True, exist_ok=True)
        if (
            force
            or not output.is_file()
            or any(p.stat().st_mtime_ns > output.stat().st_mtime_ns for p in sources)
        ):
            subprocess.run(
                [
                    str(compiler),
                    "/nologo",
                    "/optimize+",
                    "/platform:x64",
                    "/r:System.Web.Extensions.dll",
                    "/main:" + entry,
                    "/out:" + str(output),
                    *map(str, sources),
                ],
                check=True,
            )
        result[key] = output
    shutil.copyfile(PACKAGE / "engine/shaders/voxel.comp", binary_path("voxel.comp"))
    return result
