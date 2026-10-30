"""Run the source checkout without installing it as a package."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from minetrek_cutaway.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
