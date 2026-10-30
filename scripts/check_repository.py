"""Check the publishable tree without reading or scanning the working media."""

import ast
import json
from pathlib import Path
import re
import sys

from publication import public_files, ROOT_FILES

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = public_files(ROOT)
    errors = []
    for name in ROOT_FILES:
        if not (ROOT / name).is_file():
            errors.append(f"Missing root file: {name}")
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if path.stat().st_size >= 8_000_000:
            errors.append(f"Unexpected large source file: {relative}")
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            errors.append(f"Unexpected binary in public tree: {relative}")
            continue
        if path.suffix == ".py":
            try:
                ast.parse(text, filename=relative)
            except SyntaxError as e:
                errors.append(str(e))
        if path.suffix == ".json":
            try:
                json.loads(text)
            except ValueError as e:
                errors.append(f"{relative}: {e}")
        if re.search(r"[A-Za-z]:[/\\]Users[/\\][^/\\\s]+", text):
            errors.append(f"Personal user path in {relative}")
        if re.search(
            r"(?i)(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})",
            text,
        ):
            errors.append(f"Credential-shaped value in {relative}")
    package = ROOT / "src/minetrek_cutaway"
    if not (package / "project.py").is_file():
        errors.append("Missing project compiler")
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("production")
            ):
                errors.append(f"Private production import in {path.relative_to(ROOT)}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(
        f"Checked {len(files)} public files ({sum(p.stat().st_size for p in files):,} bytes). No working media included."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
