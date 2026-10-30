"""Format only publishable source files; use --check for a read-only CI check."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from publication import public_files

ROOT = Path(__file__).resolve().parents[1]
MARKUP_SUFFIXES = {".json", ".jsonc", ".yaml", ".yml", ".md", ".toml"}


def targets(root=ROOT):
    files = public_files(root)
    return {
        "python": [p for p in files if p.suffix == ".py"],
        "clang": [p for p in files if p.suffix in {".cs", ".comp"}],
        "prettier": [p for p in files if p.suffix in MARKUP_SUFFIXES or p.name == ".clang-format"],
    }


def clang_binary():
    try:
        distribution = importlib.metadata.distribution("clang-format")
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError(
            "Install the Python development tools: python -m pip install -r requirements-dev.txt"
        ) from error
    filename = "clang-format.exe" if os.name == "nt" else "clang-format"
    for relative in distribution.files or []:
        if relative.name == filename and "data" in relative.parts:
            path = Path(distribution.locate_file(relative))
            if path.is_file():
                return path
    raise RuntimeError("The installed clang-format package has no formatter binary.")


def prettier_command():
    node = shutil.which("node")
    manifest = ROOT / "node_modules/prettier/package.json"
    if not node or not manifest.is_file():
        raise RuntimeError(
            "Install Node.js and restore the formatting tools with npm ci --ignore-scripts."
        )
    binary = json.loads(manifest.read_text())["bin"]
    if isinstance(binary, dict):
        binary = binary["prettier"]
    return [node, str(manifest.parent / binary)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Report formatting changes without editing files"
    )
    args = parser.parse_args(argv)
    try:
        selected = targets()
        try:
            importlib.metadata.version("ruff")
        except importlib.metadata.PackageNotFoundError as error:
            raise RuntimeError(
                "Install the Python development tools: python -m pip install -r requirements-dev.txt"
            ) from error
        clang = clang_binary()
        prettier = prettier_command()
        python_command = [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--config",
            str(ROOT / "pyproject.toml"),
        ]
        if args.check:
            python_command.append("--check")
        subprocess.run(python_command + list(map(str, selected["python"])), cwd=ROOT, check=True)
        changed = []
        for path in selected["clang"]:
            # GLSL shares clang-format's C++ syntax; the filename selects that mode.
            assumed = path.with_suffix(".cpp") if path.suffix == ".comp" else path
            before = path.read_bytes()
            after = subprocess.check_output(
                [
                    str(clang),
                    "--style=file:" + str(ROOT / ".clang-format"),
                    "--assume-filename=" + str(assumed),
                ],
                input=before,
                cwd=ROOT,
            )
            if before != after:
                changed.append(path.relative_to(ROOT).as_posix())
                if not args.check:
                    path.write_bytes(after)
        if changed:
            print(
                ("Would format: " if args.check else "Formatted: ") + ", ".join(changed), flush=True
            )
        subprocess.run(
            prettier
            + [
                "--check" if args.check else "--write",
                "--log-level",
                "warn",
                *map(str, selected["prettier"]),
            ],
            cwd=ROOT,
            check=True,
        )
        if args.check and changed:
            return 1
        print(
            f"Formatting {'check passed' if args.check else 'complete'}: "
            + ", ".join(f"{name}={len(paths)}" for name, paths in selected.items())
        )
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Formatting failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
