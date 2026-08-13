"""Check that a PyInstaller bundle contains required runtime and notice files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REQUIRED_SUFFIXES = (
    "scientific_slides/app/index.html",
    "scientific_slides/app/modules/parser.js",
    "scientific_slides/app/modules/render.js",
    "scientific_slides/app/vendor/katex/fonts/KaTeX_Main-Regular.woff2",
    "scientific_slides/app/vendor/katex/LICENSE",
    "scientific_slides/app/vendor/reveal/LICENSE",
    "scientific_slides/app/vendor/marked/LICENSE.md",
    "scientific_slides/app/vendor/yaml/LICENSE",
    "THIRD_PARTY_LICENSES.md",
)


def verify(root: Path) -> None:
    files = [path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()]
    missing = [suffix for suffix in REQUIRED_SUFFIXES if not any(path.endswith(suffix) for path in files)]
    if sys.platform == "linux" and not any(path.endswith("quarkfoil.png") for path in files):
        missing.append("quarkfoil.png")
    if missing:
        raise SystemExit("Desktop bundle is missing:\n" + "\n".join(f"- {item}" for item in missing))
    count = len(REQUIRED_SUFFIXES) + (1 if sys.platform == "linux" else 0)
    print(f"Verified {count} required desktop bundle resources in {root}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    verify(args.bundle)


if __name__ == "__main__":
    main()
