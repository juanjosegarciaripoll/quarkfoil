"""Machine-readable, revision-guarded presentation editing commands."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from .parser import Deck, parse_deck
from .storage import atomic_write, deck_file_lock


MAX_DECK_BYTES = 20 * 1024 * 1024
GUIDE = """Quarkfoil agent protocol v1

1. Read:
   quarkfoil deck inspect DECK [--no-notes]

2. Apply:
   quarkfoil deck apply DECK [TRANSACTION.json|-] [--no-notes]

Transaction:
{"revision":"sha256:...","operations":[...]}

Operations:
{"operation":"replace","slide":N,"source":"..."}
{"operation":"insert","after":N,"source":"..."}   # 0 = beginning
{"operation":"delete","slide":N}
{"operation":"move","slide":N,"after":N}           # 0 = beginning

Operations are sequential. Always use the revision returned by inspect.
Exit 3 means the deck changed: inspect again and rebuild the transaction.
--no-notes filters returned JSON only; it never deletes stored notes.
"""


class DeckCommandError(Exception):
    """An error suitable for reporting by the command-line interface."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


class RevisionConflict(DeckCommandError):
    def __init__(self, expected: str, current: str):
        super().__init__(f"presentation changed: expected {expected}, current revision is {current}", 3)
        self.expected = expected
        self.current = current


def revision(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _read_deck(path: Path) -> tuple[bytes, str]:
    try:
        if path.suffix.lower() not in (".md", ".markdown") or not path.is_file():
            raise DeckCommandError("presentation must be an existing .md or .markdown file")
        data = path.read_bytes()
    except OSError as error:
        raise DeckCommandError(str(error)) from error
    if len(data) > MAX_DECK_BYTES:
        raise DeckCommandError(f"presentation exceeds the {MAX_DECK_BYTES}-byte limit")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DeckCommandError("presentation is not valid UTF-8") from error
    return data, revision(data)


def without_notes(source: str) -> str:
    """Return *source* with parsed speaker-note directives removed."""
    deck = parse_deck(source)
    ranges = [slide.notes_range for slide in deck.slides if slide.notes_range]
    for source_range in sorted(ranges, key=lambda item: item.start, reverse=True):
        source = source[:source_range.start] + source[source_range.end:]
    return source


def _summary(source: str, current_revision: str, *, include_notes: bool) -> dict[str, Any]:
    deck = parse_deck(source)
    returned_source = source if include_notes else without_notes(source)
    slides = []
    for slide in deck.slides:
        raw = slide.raw if include_notes else without_notes(slide.raw)
        slides.append({
            "number": slide.index + 1,
            "title": slide.title,
            "layout": slide.layout,
            "trashed": slide.trashed,
            "source": raw,
        })
    return {
        "revision": current_revision,
        "source": returned_source,
        "slides": slides,
        "diagnostics": [
            {key: value for key, value in {
                "level": item.level,
                "message": item.message,
                "line": item.line,
                "slide": item.slide,
            }.items() if value is not None}
            for item in deck.diagnostics
        ],
    }


def _compose(deck: Deck, items: list[str]) -> str:
    front = deck.source[:deck.front_matter_range.end].rstrip()
    body = "\n\n---\n\n".join(item.strip() for item in items)
    separator = "\n\n" if front and body else ""
    return f"{front}{separator}{body}\n"


def _slide_source(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeckCommandError("slide source must be a nonempty string")
    imported = parse_deck(value)
    errors = [item.message for item in imported.diagnostics if item.level == "error"]
    if errors:
        raise DeckCommandError(f"invalid slide source: {errors[0]}")
    if imported.front_matter_range.end or len(imported.slides) != 1 or imported.sections or len(imported.items) != 1:
        raise DeckCommandError("slide source must contain exactly one slide and no sections")
    return imported.slides[0].raw.strip()


def _integer(operation: dict[str, Any], name: str, *, minimum: int = 1) -> int:
    value = operation.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise DeckCommandError(f"operation field '{name}' must be an integer of at least {minimum}")
    return value


def _slide_position(deck: Deck, number: int) -> int:
    if number > len(deck.slides):
        raise DeckCommandError(f"unknown slide {number}; presentation has {len(deck.slides)} slides")
    target = deck.slides[number - 1]
    return next(index for index, item in enumerate(deck.items) if item is target)


def _apply_operation(source: str, operation: Any) -> str:
    if not isinstance(operation, dict):
        raise DeckCommandError("each operation must be a JSON object")
    name = operation.get("operation", operation.get("op"))
    if not isinstance(name, str):
        raise DeckCommandError("each operation requires an 'operation' field")
    deck = parse_deck(source)
    items = [item.raw for item in deck.items]
    if name == "replace":
        position = _slide_position(deck, _integer(operation, "slide"))
        items[position] = _slide_source(operation.get("source"))
    elif name == "insert":
        after = _integer(operation, "after", minimum=0)
        if after > len(deck.slides):
            raise DeckCommandError(f"cannot insert after slide {after}; presentation has {len(deck.slides)} slides")
        position = 0 if after == 0 else _slide_position(deck, after) + 1
        items.insert(position, _slide_source(operation.get("source")))
    elif name == "delete":
        if len(deck.slides) == 1:
            raise DeckCommandError("a presentation must contain at least one slide")
        del items[_slide_position(deck, _integer(operation, "slide"))]
    elif name == "move":
        number = _integer(operation, "slide")
        after = _integer(operation, "after", minimum=0)
        if after > len(deck.slides):
            raise DeckCommandError(f"cannot move after slide {after}; presentation has {len(deck.slides)} slides")
        if number == after:
            raise DeckCommandError("a slide cannot be moved after itself")
        source_position = _slide_position(deck, number)
        moved = items.pop(source_position)
        if after == 0:
            destination = 0
        else:
            target_position = _slide_position(deck, after)
            destination = target_position + 1 - (1 if source_position < target_position else 0)
        items.insert(destination, moved)
    else:
        raise DeckCommandError(f"unknown operation '{name}'")
    return _compose(deck, items)


def apply_transaction(source: str, operations: Any) -> str:
    if not isinstance(operations, list) or not operations:
        raise DeckCommandError("transaction requires a nonempty 'operations' array")
    for operation in operations:
        source = _apply_operation(source, operation)
    deck = parse_deck(source)
    errors = [item.message for item in deck.diagnostics if item.level == "error"]
    if errors:
        raise DeckCommandError(f"transaction produced an invalid presentation: {errors[0]}")
    return source


def _load_transaction(path: str) -> Any:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        return json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeckCommandError(f"cannot read transaction: {error}") from error


def _expected_revision(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise DeckCommandError("a revision is required through --if-revision or transaction JSON")
    return value if value.startswith("sha256:") else f"sha256:{value}"


def _inspect(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="quarkfoil deck inspect", description="Return a presentation snapshot for an editing agent")
    parser.add_argument("deck", type=Path)
    parser.add_argument("--no-notes", action="store_true", help="Omit speaker notes from returned source")
    args = parser.parse_args(arguments)
    data, current = _read_deck(args.deck)
    print(json.dumps(_summary(data.decode("utf-8"), current, include_notes=not args.no_notes), ensure_ascii=False, indent=2))
    return 0


def _apply(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="quarkfoil deck apply", description="Atomically apply a revision-guarded slide transaction")
    parser.add_argument("deck", type=Path)
    parser.add_argument("transaction", nargs="?", default="-", help="JSON transaction file, or - for stdin (default)")
    parser.add_argument("--if-revision", help="Expected SHA-256 revision; may instead be present in transaction JSON")
    parser.add_argument("--no-notes", action="store_true", help="Omit speaker notes from returned source")
    args = parser.parse_args(arguments)
    transaction = _load_transaction(args.transaction)
    if isinstance(transaction, list):
        operations, embedded_revision = transaction, None
    elif isinstance(transaction, dict):
        operations, embedded_revision = transaction.get("operations"), transaction.get("revision")
    else:
        raise DeckCommandError("transaction must be an object or an operations array")
    expected = _expected_revision(args.if_revision or embedded_revision)
    path = args.deck.resolve()
    with deck_file_lock(path):
        data, current = _read_deck(path)
        if current != expected:
            raise RevisionConflict(expected, current)
        updated = apply_transaction(data.decode("utf-8"), operations)
        encoded = updated.encode("utf-8")
        if len(encoded) > MAX_DECK_BYTES:
            raise DeckCommandError(f"updated presentation exceeds the {MAX_DECK_BYTES}-byte limit")
        atomic_write(path, encoded)
    updated_revision = revision(encoded)
    print(json.dumps(_summary(updated, updated_revision, include_notes=not args.no_notes), ensure_ascii=False, indent=2))
    return 0


def main(arguments: list[str]) -> int:
    if not arguments or arguments[0] not in ("guide", "inspect", "apply"):
        parser = argparse.ArgumentParser(prog="quarkfoil deck", description="Inspect or atomically edit a presentation for an LLM agent")
        parser.add_argument("command", choices=("guide", "inspect", "apply"))
        parser.parse_args(arguments)
    if arguments[0] == "guide":
        if len(arguments) != 1:
            raise SystemExit("usage: quarkfoil deck guide")
        print(GUIDE, end="")
        return 0
    try:
        return _inspect(arguments[1:]) if arguments[0] == "inspect" else _apply(arguments[1:])
    except DeckCommandError as error:
        print(f"quarkfoil deck: {error}", file=sys.stderr)
        return error.exit_code


__all__ = ["DeckCommandError", "GUIDE", "RevisionConflict", "apply_transaction", "main", "revision", "without_notes"]
