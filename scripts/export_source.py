"""Build a small source-only ZIP; never traverse the production work folder."""

import argparse
from pathlib import Path
import sys
import zipfile

from publication import public_files
from check_repository import main as check

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "work/exports/minetrek-cutaway-source.zip")
    args = p.parse_args(argv)
    if check():
        return 1
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "work"):
        p.error("Source exports must be written under work/.")
    output.parent.mkdir(parents=True, exist_ok=True)
    files = public_files(ROOT)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for source in files:
            relative = source.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo("minetrek-cutaway/" + relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, source.read_bytes())
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(files)
    print(f"Exported {len(files)} files, {output.stat().st_size:,} bytes: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
