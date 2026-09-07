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
    parser.add_argument("--output", "-o", type=Path, required=True, help="Directory to create or update")
    assets = parser.add_mutually_exclusive_group()
    assets.add_argument("--assets", choices=("local", "cdn"), default="local", help="Dependency source (default: local)")
    assets.add_argument("--cdn", dest="assets", action="store_const", const="cdn", help="Use pinned jsDelivr dependencies")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Create a link-sharing preview with Chrome, Chromium, or Edge",
    )
    parser.add_argument(
        "--no-notes",
        action="store_true",
        help="Remove speaker notes from the exported presentation",
    )
    parser.add_argument(
        "--trim-bibliography",
        action="store_true",
        help="Keep only cited bibliography entries and their dependencies",
    )
    args = parser.parse_args(arguments)
    destination = export_presentation(
        args.deck,
        args.output,
        assets=args.assets,
        preview=args.preview,
        include_notes=not args.no_notes,
        trim_bibliography=args.trim_bibliography,
    )
    print(f"Exported Quarkfoil presentation to {destination}")
    print(f"Open {destination / 'index.html'} directly or serve it from any static web server")
    return 0


def _pack(arguments: list[str]) -> int:
    from .exporter import pack_presentation

    parser = argparse.ArgumentParser(
        prog="quarkfoil pack",
        description="Copy a Quarkfoil presentation and its assets into an editable project folder",
    )
    parser.add_argument("deck", type=Path, help="Markdown presentation to pack")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Directory to create or update")
    parser.add_argument(
        "--no-notes",
        action="store_true",
        help="Remove speaker notes from the packed presentation",
    )
    parser.add_argument(
        "--trim-bibliography",
        action="store_true",
        help="Keep only cited bibliography entries and their dependencies",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace destination files that differ from the packed ones",
    )
    args = parser.parse_args(arguments)
    try:
        destination = pack_presentation(
            args.deck,
            args.output,
            include_notes=not args.no_notes,
            trim_bibliography=args.trim_bibliography,
            force=args.force,
        )
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"quarkfoil pack: {error}", file=sys.stderr)
        return 1
    print(f"Packed Quarkfoil presentation into {destination}")
    print(f"Keep editing it with: quarkfoil {destination / args.deck.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["export"]:
        return _export(arguments[1:])
    if arguments[:1] == ["pack"]:
        return _pack(arguments[1:])
    if arguments[:1] == ["deck"]:
        from .deck_cli import main as deck

        return deck(arguments[1:])
    from .server import main as serve

    return serve(arguments)

__all__ = ["main"]
