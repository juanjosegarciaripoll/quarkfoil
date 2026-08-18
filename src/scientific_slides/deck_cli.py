"""Machine-readable, revision-guarded presentation editing commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from .parser import Deck, parse_deck
from .storage import atomic_write, deck_file_lock


MAX_DECK_BYTES = 20 * 1024 * 1024
PROTOCOL_VERSION = 1
CAPABILITIES = ("replace", "insert", "delete", "move", "notes_policy", "dry_run", "quiet", "compact", "inspect_projection")
GUIDE = """Quarkfoil agent protocol v1

1. Read:
   quarkfoil deck inspect DECK [--no-notes]

2. Apply:
   quarkfoil deck apply DECK [TRANSACTION.json|-] [--dry-run] [--quiet]

Transaction:
{"revision":"sha256:...","operations":[...]}

Operations:
{"operation":"replace","slide":N,"source":"...","notes":"preserve|replace|remove"}
{"operation":"insert","after":N,"source":"..."}   # 0 = beginning
{"operation":"delete","slide":N}
{"operation":"move","slide":N,"after":N}           # 0 = beginning

Operations are sequential. Always use the revision returned by inspect.
Exit 3 means the deck changed: inspect again and rebuild the transaction.
Errors are JSON on stderr. Run `quarkfoil deck protocol` for the full contract.
--no-notes hides returned notes; replacement notes default to preserve.
"""

PROTOCOL = {
    "name": "quarkfoil-deck",
    "protocol_version": PROTOCOL_VERSION,
    "capabilities": list(CAPABILITIES),
    "workflow": ["inspect the deck", "retain its revision", "apply a transaction using that revision"],
    "transaction": {
        "required": ["revision", "operations"],
        "operations_are_sequential": True,
        "unknown_fields": "rejected",
        "operations": {
            "replace": {"required": ["slide", "source"], "optional": {"notes": ["preserve", "replace", "remove"]}},
            "insert": {"required": ["after", "source"], "after_zero": "beginning"},
            "delete": {"required": ["slide"]},
            "move": {"required": ["slide", "after"], "after_zero": "beginning"},
        },
    },
    "responses": {
        "success": "JSON on stdout",
        "error": "JSON on stderr",
        "inspect": ["protocol_version", "revision", "metadata", "source", "slides", "diagnostics"],
        "apply": ["protocol_version", "revision", "metadata", "source", "slides", "diagnostics"],
        "quiet_apply": ["protocol_version", "capabilities", "revision", "diagnostics", "dry_run"],
    },
    "exit_codes": {"0": "success", "2": "invalid request", "3": "revision conflict"},
    "revision": "SHA-256 of the exact UTF-8 file bytes",
    "failure_guarantee": "A failed transaction leaves the presentation byte-for-byte unchanged.",
}


class DeckCommandError(Exception):
    """An error suitable for reporting by the command-line interface."""

    def __init__(self, message: str, exit_code: int = 2, *, code: str = "invalid_request", **details: Any):
        super().__init__(message)
        self.exit_code = exit_code
        self.code = code
        self.details = details

    def at_operation(self, index: int) -> DeckCommandError:
        if "operation" not in self.details:
            self.details["operation"] = index
            self.details["path"] = f"operations[{index}]"
        return self


class RevisionConflict(DeckCommandError):
    def __init__(self, expected: str, current: str):
        super().__init__(
            f"presentation changed: expected {expected}, current revision is {current}",
            3,
            code="revision_mismatch",
            expected_revision=expected,
            actual_revision=current,
        )
        self.expected = expected
        self.current = current


class DeckArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise DeckCommandError(message, code="usage_error")


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
    while True:
        deck = parse_deck(source)
        ranges = [slide.notes_range for slide in deck.slides if slide.notes_range]
        if not ranges:
            return source
        for source_range in sorted(ranges, key=lambda item: item.start, reverse=True):
            source = source[:source_range.start] + source[source_range.end:]


def _diagnostics(deck: Deck) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in {
            "level": item.level,
            "message": item.message,
            "line": item.line,
            "slide": item.slide,
        }.items() if value is not None}
        for item in deck.diagnostics
    ]


def _summary(
    source: str,
    current_revision: str,
    *,
    include_notes: bool,
    include_source: bool = True,
    selected_slides: set[int] | None = None,
) -> dict[str, Any]:
    deck = parse_deck(source)
    slides = []
    for slide in deck.slides:
        if selected_slides is not None and slide.index + 1 not in selected_slides:
            continue
        raw = slide.raw if include_notes else without_notes(slide.raw)
        slides.append({
            "number": slide.index + 1,
            "title": slide.title,
            "layout": slide.layout,
            "trashed": slide.trashed,
            "source": raw,
        })
    result = {
        "protocol_version": PROTOCOL_VERSION,
        "capabilities": list(CAPABILITIES),
        "revision": current_revision,
        "metadata": deck.metadata,
        "slides": slides,
        "diagnostics": _diagnostics(deck),
    }
    if include_source:
        result["source"] = source if include_notes else without_notes(source)
    return result


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


def _newline(source: str) -> str:
    return "\r\n" if "\r\n" in source else "\n"


def _separator_after(source: str) -> str:
    newline = _newline(source)
    leading = newline if source.endswith(("\n", "\r")) else newline * 2
    return f"{leading}---{newline}{newline}"


def _replace_slide(source: str, deck: Deck, number: int, replacement: str) -> str:
    slide = deck.slides[number - 1]
    raw = slide.raw
    leading_length = len(raw) - len(raw.lstrip())
    trailing_length = len(raw) - len(raw.rstrip())
    leading = raw[:leading_length]
    trailing = raw[len(raw) - trailing_length:] if trailing_length else ""
    patched = f"{leading}{replacement.strip()}{trailing}"
    return source[:slide.range.start] + patched + source[slide.range.end:]


def _insert_slide(source: str, deck: Deck, after: int, slide_source: str) -> str:
    if after == 0:
        insertion = deck.items[0].range.start if deck.items else deck.front_matter_range.end
        slide = slide_source.strip()
        return source[:insertion] + slide + _separator_after(slide) + source[insertion:]
    target = deck.slides[after - 1]
    insertion = target.range.end
    slide = slide_source.strip()
    suffix = _newline(source) if insertion == len(source) else ""
    return source[:insertion] + _separator_after(source[:insertion]) + slide + suffix + source[insertion:]


def _delete_slide(source: str, deck: Deck, number: int) -> str:
    position = _slide_position(deck, number)
    target = deck.items[position]
    if position + 1 < len(deck.items):
        start, end = target.range.start, deck.items[position + 1].range.start
    else:
        start, end = deck.items[position - 1].range.end, target.range.end
    return source[:start] + source[end:]


def _check_fields(operation: dict[str, Any], required: set[str], optional: set[str] | None = None) -> None:
    optional = optional or set()
    allowed = required | optional | {"operation", "op"}
    missing = required - operation.keys()
    unknown = operation.keys() - allowed
    if missing:
        raise DeckCommandError(f"missing operation field '{sorted(missing)[0]}'")
    if unknown:
        raise DeckCommandError(f"unknown operation field '{sorted(unknown)[0]}'")


def _apply_operation(source: str, operation: Any) -> str:
    if not isinstance(operation, dict):
        raise DeckCommandError("each operation must be a JSON object")
    name = operation.get("operation", operation.get("op"))
    if not isinstance(name, str):
        raise DeckCommandError("each operation requires an 'operation' field")
    deck = parse_deck(source)
    if name == "replace":
        _check_fields(operation, {"slide", "source"}, {"notes"})
        number = _integer(operation, "slide")
        _slide_position(deck, number)
        replacement = _slide_source(operation.get("source"))
        existing = deck.slides[number - 1]
        notes = operation.get("notes", "preserve")
        if notes not in ("preserve", "replace", "remove"):
            raise DeckCommandError("operation field 'notes' must be preserve, replace, or remove")
        if notes != "replace":
            replacement = without_notes(replacement).rstrip()
        if notes == "preserve" and existing.notes_range:
            note = deck.source[existing.notes_range.start:existing.notes_range.end].strip()
            newline = _newline(source)
            replacement = f"{replacement}{newline}{newline}{note}"
        return _replace_slide(source, deck, number, replacement)
    elif name == "insert":
        _check_fields(operation, {"after", "source"})
        after = _integer(operation, "after", minimum=0)
        if after > len(deck.slides):
            raise DeckCommandError(f"cannot insert after slide {after}; presentation has {len(deck.slides)} slides")
        return _insert_slide(source, deck, after, _slide_source(operation.get("source")))
    elif name == "delete":
        _check_fields(operation, {"slide"})
        if len(deck.slides) == 1:
            raise DeckCommandError("a presentation must contain at least one slide")
        number = _integer(operation, "slide")
        _slide_position(deck, number)
        return _delete_slide(source, deck, number)
    elif name == "move":
        _check_fields(operation, {"slide", "after"})
        number = _integer(operation, "slide")
        after = _integer(operation, "after", minimum=0)
        if after > len(deck.slides):
            raise DeckCommandError(f"cannot move after slide {after}; presentation has {len(deck.slides)} slides")
        if number == after:
            raise DeckCommandError("a slide cannot be moved after itself")
        _slide_position(deck, number)
        if after == number - 1:
            return source
        moved = deck.slides[number - 1].raw
        reduced = _delete_slide(source, deck, number)
        reduced_deck = parse_deck(reduced)
        adjusted_after = after - 1 if number < after else after
        return _insert_slide(reduced, reduced_deck, adjusted_after, moved)
    else:
        raise DeckCommandError(f"unknown operation '{name}'")


def apply_transaction(source: str, operations: Any) -> str:
    if not isinstance(operations, list) or not operations:
        raise DeckCommandError("transaction requires a nonempty 'operations' array")
    for index, operation in enumerate(operations):
        try:
            source = _apply_operation(source, operation)
        except DeckCommandError as error:
            raise error.at_operation(index) from error
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


def _selected_slides(value: str | None) -> set[int] | None:
    if value is None:
        return None
    try:
        selected = {int(item) for item in value.split(",")}
    except ValueError as error:
        raise DeckCommandError("--slides must be comma-separated positive integers", code="usage_error") from error
    if not selected or min(selected) < 1:
        raise DeckCommandError("--slides must be comma-separated positive integers", code="usage_error")
    return selected


def _print_json(payload: Any, *, compact: bool = False, stream: Any = None) -> None:
    separators = (",", ":") if compact else None
    print(json.dumps(payload, ensure_ascii=False, indent=None if compact else 2, separators=separators),
          file=sys.stdout if stream is None else stream, flush=True)


def _silence_broken_pipe() -> None:
    try:
        descriptor = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(descriptor, sys.stdout.fileno())
        finally:
            os.close(descriptor)
    except (OSError, ValueError):
        pass


def _inspect(arguments: list[str]) -> int:
    parser = DeckArgumentParser(prog="quarkfoil deck inspect", description="Return a presentation snapshot for an editing agent")
    parser.add_argument("deck", type=Path)
    parser.add_argument("--no-notes", action="store_true", help="Omit speaker notes from returned source")
    parser.add_argument("--no-source", action="store_true", help="Omit the whole-deck source field")
    parser.add_argument("--slides", help="Return only these comma-separated slide numbers")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    args = parser.parse_args(arguments)
    data, current = _read_deck(args.deck)
    summary = _summary(data.decode("utf-8"), current, include_notes=not args.no_notes,
                       include_source=not args.no_source, selected_slides=_selected_slides(args.slides))
    _print_json(summary, compact=args.compact)
    return 0


def _apply(arguments: list[str]) -> int:
    parser = DeckArgumentParser(prog="quarkfoil deck apply", description="Atomically apply a revision-guarded slide transaction")
    parser.add_argument("deck", type=Path)
    parser.add_argument("transaction", nargs="?", default="-", help="JSON transaction file, or - for stdin (default)")
    parser.add_argument("--if-revision", help="Expected SHA-256 revision; may instead be present in transaction JSON")
    parser.add_argument("--no-notes", action="store_true", help="Omit notes from returned JSON; does not change stored notes")
    parser.add_argument("--dry-run", "--check", action="store_true", help="Validate and return the result without writing")
    parser.add_argument("--quiet", action="store_true", help="Return only revision and diagnostics")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    args = parser.parse_args(arguments)
    transaction = _load_transaction(args.transaction)
    if isinstance(transaction, list):
        operations, embedded_revision = transaction, None
    elif isinstance(transaction, dict):
        unknown = transaction.keys() - {"revision", "operations"}
        if unknown:
            raise DeckCommandError(f"unknown transaction field '{sorted(unknown)[0]}'")
        operations, embedded_revision = transaction.get("operations"), transaction.get("revision")
    else:
        raise DeckCommandError("transaction must be an object or an operations array")
    if args.if_revision and embedded_revision and _expected_revision(args.if_revision) != _expected_revision(embedded_revision):
        raise DeckCommandError("--if-revision and transaction revision disagree", code="revision_disagreement")
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
        if not args.dry_run:
            atomic_write(path, encoded)
    updated_revision = revision(encoded)
    if args.quiet:
        payload = {"protocol_version": PROTOCOL_VERSION, "capabilities": list(CAPABILITIES), "revision": updated_revision,
                   "diagnostics": _diagnostics(parse_deck(updated)), "dry_run": args.dry_run}
    else:
        payload = _summary(updated, updated_revision, include_notes=not args.no_notes)
        payload["dry_run"] = args.dry_run
    _print_json(payload, compact=args.compact)
    return 0


def main(arguments: list[str]) -> int:
    try:
        if not arguments or arguments[0] not in ("guide", "protocol", "inspect", "apply"):
            parser = DeckArgumentParser(prog="quarkfoil deck", description="Inspect or atomically edit a presentation for an LLM agent")
            parser.add_argument("command", choices=("guide", "protocol", "inspect", "apply"))
            parser.parse_args(arguments)
        if arguments[0] == "guide":
            if len(arguments) != 1:
                raise DeckCommandError("guide takes no arguments", code="usage_error")
            print(GUIDE, end="", flush=True)
            return 0
        if arguments[0] == "protocol":
            if len(arguments) != 1:
                raise DeckCommandError("protocol takes no arguments", code="usage_error")
            _print_json(PROTOCOL)
            return 0
        return _inspect(arguments[1:]) if arguments[0] == "inspect" else _apply(arguments[1:])
    except DeckCommandError as error:
        _print_json({"error": error.code, "message": str(error), **error.details}, compact=True, stream=sys.stderr)
        return error.exit_code
    except BrokenPipeError:
        _silence_broken_pipe()
        return 0


__all__ = ["DeckCommandError", "GUIDE", "PROTOCOL", "RevisionConflict", "apply_transaction", "main", "revision", "without_notes"]
