"""Keep formatting confined to the publishable source tree."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from format_code import targets


class FormattingScopeTests(unittest.TestCase):
    def test_private_and_dependency_files_are_never_formatter_targets(self):
        parent = (ROOT / "work/test-tmp").resolve()
        assert parent.is_relative_to(ROOT / "work")
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            root = Path(folder)
            files = [
                "src/example.py",
                "src/engine.cs",
                "src/shader.comp",
                "examples/scene.json",
                "docs/example.md",
                "pyproject.toml",
                "work/private.py",
                "work/project.json",
                "node_modules/vendor/example.py",
                "src/__pycache__/cached.pyc",
            ]
            for name in files:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture\n", encoding="utf-8")
            selected = targets(root)
            actual = {p.relative_to(root).as_posix() for paths in selected.values() for p in paths}
            self.assertEqual(actual, set(files[:6]))
            self.assertEqual(len(selected["python"]), 1)
            self.assertEqual(len(selected["clang"]), 2)
            self.assertEqual(len(selected["prettier"]), 3)


if __name__ == "__main__":
    unittest.main()
