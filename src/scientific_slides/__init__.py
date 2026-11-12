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


def _download(arguments: list[str]) -> int:
    from .downloader import DownloadError, download_talk

    parser = argparse.ArgumentParser(
        prog="quarkfoil download",
        description=(
            "Download a published talk as an editable Quarkfoil project, a ZIP archive of it, "
            "a PDF, or any combination"
        ),
    )
    parser.add_argument("url", metavar="URL", help="Public URL of the published talk")
    parser.add_argument("--output", "-o", type=Path, help="Directory to create or update with the editable project")
    parser.add_argument("--zip", type=Path, metavar="FILE.zip", help="Write the editable project as a ZIP archive")
    parser.add_argument("--pdf", type=Path, metavar="FILE.pdf", help="Print the talk to PDF, one slide per page, with an installed browser")
    parser.add_argument(
        "--sha256", action="store_true",
        help="Write FILE.sha256 beside the ZIP archive and the PDF, for checking later with sha256sum -c",
    )
    parser.add_argument("--name", help="Recovered Markdown file name (default: original name or talk slug)")
    parser.add_argument(
        "--force", action="store_true",
        help="Replace destination files, a ZIP archive, a PDF, or checksum files that differ from the download",
    )
    parser.add_argument(
        "--timeout", type=float, default=30,
        help="Seconds allowed for each download (default: 30)",
    )
    parser.add_argument(
        "--browser",
        help="Browser to print the PDF with (default: the first Chrome, Chromium, Edge, or Firefox that starts)",
    )
    args = parser.parse_args(arguments)
    if args.output is None and args.zip is None and args.pdf is None:
        parser.error("choose at least one of --output, --zip, or --pdf")
    try:
        result = download_talk(
            args.url, output=args.output, archive=args.zip, pdf=args.pdf,
            name=args.name, force=args.force, timeout=args.timeout, browser=args.browser,
            checksums=args.sha256,
        )
    except (DownloadError, FileExistsError, FileNotFoundError, IsADirectoryError, RuntimeError, ValueError) as error:
        print(f"quarkfoil download: {error}", file=sys.stderr)
        return 1
    if result.project is not None:
        print(f"Downloaded editable Quarkfoil project to {result.project}")
        print(f"Keep editing it with: quarkfoil {result.deck}")
    if result.archive is not None:
        state = "is already up to date" if result.archive_unchanged else "written"
        print(f"ZIP archive of the editable project {state}: {result.archive}")
    if result.pdf is not None:
        print(f"Printed the talk to {result.pdf} (one slide per page, printed with {result.browser})")
    for checksum in result.checksums:
        print(f"SHA-256 written: {checksum}")
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
    parser.add_argument(
        "--site-url", metavar="URL",
        help="Public collection URL; remembered and used for canonical links and social cards",
    )
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
                args.site, title=args.index_title, lede=args.index_lede, site_url=args.site_url,
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
                site_url=args.site_url,
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


COMMANDS = {
    "export": (_export, "Export a presentation as a static website"),
    "pack": (_pack, "Copy a presentation and its assets into an editable project folder"),
    "print": (_print, "Render a presentation to PDF with a headless browser"),
    "publish": (_publish, "Publish presentations into a shared collection of talks"),
    "download": (_download, "Recover a published talk as a project, ZIP archive, or PDF"),
    "deck": (None, "Create, inspect, edit, or render a deck for an LLM agent"),
}


def _commands_help() -> str:
    width = max(len(name) for name in COMMANDS)
    lines = [f"  {name:<{width}}  {summary}" for name, (_, summary) in COMMANDS.items()]
    return "\n".join(
        [
            "commands:",
            *lines,
            "",
            "Run 'quarkfoil COMMAND --help' for the options of each command.",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    command = arguments[0] if arguments else None
    if command == "deck":
        from .deck_cli import main as deck

        return deck(arguments[1:])
    if command in COMMANDS:
        handler, _ = COMMANDS[command]
        return handler(arguments[1:])
    from .server import main as serve

    return serve(arguments, epilog=_commands_help())

__all__ = ["main"]
