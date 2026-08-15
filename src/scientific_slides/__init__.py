"""Quarkfoil command-line dispatch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _export(arguments: list[str]) -> int:
    from .exporter import export_presentation

    parser = argparse.ArgumentParser(
        prog="quarkfoil export",
        description="Export a Quarkfoil presentation as a static website",
    )
    parser.add_argument("deck", type=Path, help="Markdown presentation to export")
    parser.add_argument("--output", "-o", type=Path, required=True, help="New directory to create")
    assets = parser.add_mutually_exclusive_group()
    assets.add_argument("--assets", choices=("local", "cdn"), default="local", help="Dependency source (default: local)")
    assets.add_argument("--cdn", dest="assets", action="store_const", const="cdn", help="Use pinned jsDelivr dependencies")
    args = parser.parse_args(arguments)
    destination = export_presentation(args.deck, args.output, assets=args.assets)
    print(f"Exported Quarkfoil presentation to {destination}")
    print(f"Serve {destination / 'index.html'} from any static web server")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["export"]:
        return _export(arguments[1:])
    from .server import main as serve

    return serve(arguments)

__all__ = ["main"]
