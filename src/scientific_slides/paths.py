from __future__ import annotations

from pathlib import Path


PACKAGE_APP_ROOT = Path(__file__).resolve().parent / "app"
SOURCE_APP_ROOT = Path(__file__).resolve().parents[2] / "app"
APP_ROOT = PACKAGE_APP_ROOT if PACKAGE_APP_ROOT.is_dir() else SOURCE_APP_ROOT


def inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
