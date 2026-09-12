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


def _print(arguments: list[str]) -> int:
    from .printer import BROWSER_TIMEOUT_SECONDS, SLIDE_HEIGHT_INCHES, SLIDE_WIDTH_INCHES, print_presentation

    parser = argparse.ArgumentParser(
        prog="quarkfoil print",
        description="Render a Quarkfoil presentation to PDF with a headless browser",
    )
    parser.add_argument("deck", type=Path, help="Markdown presentation to print")
    parser.add_argument(
        "--output", "-o", type=Path,
        help="PDF file to write (default: the presentation name with a .pdf suffix)",
    )
    parser.add_argument(
        "--browser",
        help="Browser to print with (default: the first Chrome, Chromium, Edge, or Firefox found)",
    )
    parser.add_argument(
        "--timeout", type=float, default=BROWSER_TIMEOUT_SECONDS,
        help=f"Seconds to wait for the browser (default: {BROWSER_TIMEOUT_SECONDS:.0f})",
    )
    args = parser.parse_args(arguments)
    try:
        destination, browser = print_presentation(
            args.deck, args.output, browser=args.browser, timeout=args.timeout
        )
    except (FileNotFoundError, IsADirectoryError, ValueError, RuntimeError) as error:
        print(f"quarkfoil print: {error}", file=sys.stderr)
        return 1
    print(f"Printed Quarkfoil presentation to {destination}")
    print(
        f"One slide per page, {SLIDE_WIDTH_INCHES:.2f} x {SLIDE_HEIGHT_INCHES:.2f} in, printed with {browser}"
    )
    return 0


def _publish(arguments: list[str]) -> int:
    from .publisher import PublishError, publish_index, publish_presentations

    parser = argparse.ArgumentParser(
        prog="quarkfoil publish",
        description="Publish a presentation into a collection that shares one runtime and asset pool",
    )
    parser.add_argument(
        "decks", nargs="*", type=Path, metavar="DECK",
        help="Markdown presentations to publish; several are staged and listed together",
    )
    parser.add_argument(
        "--site", required=True, metavar="TARGET",
        help="collection directory, or an rsync destination such as host:talks/",
    )
    parser.add_argument("--name", help="Folder name for the talk (default: the deck's file name)")
    notes = parser.add_mutually_exclusive_group()
    notes.add_argument(
        "--notes", dest="notes", action="store_true", default=False,
        help="Publish the speaker notes too; they are readable by anyone",
    )
    notes.add_argument(
        "--no-notes", dest="notes", action="store_false",
        help="Leave the speaker notes out of the published deck (default)",
    )
    parser.add_argument(
        "--trim-bibliography", action="store_true",
        help="Keep only cited bibliography entries and their dependencies",
    )
    parser.add_argument("--index-only", action="store_true", help="Rebuild the listing without publishing a deck")
    parser.add_argument("--no-index", action="store_true", help="Publish the deck without rebuilding the listing")
    parser.add_argument("--index-title", help="Heading of the listing; remembered by the collection (default: Talks)")
    parser.add_argument("--index-lede", help="Sentence under the listing heading; remembered by the collection")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be published, change nothing")
    parser.add_argument("--rsync", default="rsync", help="rsync program to use for a remote site")
    args = parser.parse_args(arguments)
    if args.index_only and args.decks:
        parser.error("--index-only takes no deck")
    if not args.index_only and not args.decks:
        parser.error("a deck is required unless --index-only is given")
    if args.name and len(args.decks) > 1:
        parser.error("--name applies to a single deck")
    try:
        if args.index_only:
            publish_index(
                args.site, title=args.index_title, lede=args.index_lede,
                dry_run=args.dry_run, rsync=args.rsync,
            )
        else:
            published = publish_presentations(
                args.decks,
                args.site,
                names=[args.name] if args.name else None,
                include_notes=args.notes,
                trim_bibliography=args.trim_bibliography,
                index=not args.no_index,
                index_title=args.index_title,
                index_lede=args.index_lede,
                dry_run=args.dry_run,
                rsync=args.rsync,
            )
            for meta in published:
                series = f" in {meta['series']}" if meta.get("series") else ""
                print(f"Published {meta['title']} as {meta['slug']}/ ({meta['date']}){series}")
    except PublishError as error:
        print(f"quarkfoil publish: {error}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as error:
        print(f"quarkfoil publish: {error}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["export"]:
        return _export(arguments[1:])
    if arguments[:1] == ["pack"]:
        return _pack(arguments[1:])
    if arguments[:1] == ["publish"]:
        return _publish(arguments[1:])
    if arguments[:1] == ["print"]:
        return _print(arguments[1:])
    if arguments[:1] == ["deck"]:
        from .deck_cli import main as deck

        return deck(arguments[1:])
    from .server import main as serve

    return serve(arguments)

__all__ = ["main"]
