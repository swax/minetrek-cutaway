"""The public source-file inventory shared by checks and ZIP export."""

from pathlib import Path

ROOT_FILES = {
    "README.md",
    "LICENSE",
    "THIRD_PARTY.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-tested.txt",
    "requirements-dev.txt",
    "run.py",
    ".gitignore",
    ".gitattributes",
    "package.json",
    "package-lock.json",
    ".clang-format",
    ".editorconfig",
    ".prettierrc.json",
    ".prettierignore",
}
ROOT_FOLDERS = {"src", "docs", "examples", "scripts", "tests", ".github"}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".exe",
    ".dll",
    ".vox",
    ".rgba",
    ".mttex",
    ".mp4",
    ".m4a",
    ".zip",
    ".log",
}


def public_files(root):
    root = Path(root).resolve()
    result = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for folder in ROOT_FOLDERS:
        directory = root / folder
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            relative = path.relative_to(root)
            if (
                not path.is_file()
                or "__pycache__" in relative.parts
                or any(p.endswith(".egg-info") for p in relative.parts)
            ):
                continue
            if (
                path.suffix.lower() in EXCLUDED_SUFFIXES
                or path.name == ".env"
                or path.name.startswith(".env.")
            ):
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError(f"Public source must be a regular in-project file: {relative}")
            result.append(path)
    return sorted(result, key=lambda p: p.relative_to(root).as_posix())
