"""Locations for reusable source and disposable working files."""

import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
_checkout = PACKAGE.parents[1]
REPOSITORY = _checkout if (_checkout / "pyproject.toml").is_file() else Path.cwd().resolve()
_configured_work = os.environ.get("MINETREK_CUTAWAY_WORK") or os.environ.get("CLASSIC_CUTAWAY_WORK")
WORK = Path(_configured_work or REPOSITORY / "work").expanduser().resolve()


def relative_path(base, value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (Path(base) / path).resolve()


def binary_path(name):
    return WORK / "generic-bin" / name
