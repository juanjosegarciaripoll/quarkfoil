"""Machine-readable, revision-guarded presentation editing commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

import yaml

from .parser import Deck, parse_deck
from .storage import atomic_write, deck_file_lock


MAX_DECK_BYTES = 20 * 1024 * 1024
UNRELIABLE_BOUNDARY_CODES = frozenset(("unreliable_slide_boundaries", "unterminated_fence"))
PROTOCOL_VERSION = 1
CAPABILITIES = ("replace", "insert", "delete", "move", "notes_policy", "dry_run", "quiet", "compact",
                "inspect_projection", "slide_fingerprints", "apply_results", "source_file", "substitute",
                "edit_documents", "yaml_results", "markdown_projection")
GUIDE = """Quarkfoil agent protocol v1

Read and edit literal Markdown:
  quarkfoil deck inspect DECK --slides N --format edit [--no-notes] > slide.md
  quarkfoil deck apply DECK --edit slide.md

The edit document carries the guarded deck and slide revisions in a YAML
header. Keep the header. Repeat --edit for one ordered atomic transaction.
Use --format markdown for readable output without an edit receipt.

JSON remains available:
  quarkfoil deck inspect DECK --no-source --slides N --compact [--no-notes]
  quarkfoil deck apply DECK [TRANSACTION.json|-] --quiet --compact

Transaction:
{"revision":"sha256:...","operations":[...]}
{"operation":"replace","slide":N,"source":"...","notes":"preserve|replace|remove"}

Operations are sequential and guarded by the inspected revision.
Exit 3 means the deck changed: inspect again and rebuild the transaction.
--no-notes hides returned notes. Default notes policy preserves existing notes
in replacements. Run `quarkfoil deck protocol` for the full JSON contract.
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
            "replace": {"required": ["slide", "exactly one of source or source_file"],
                        "optional": {"notes": ["preserve", "replace", "remove"], "source_revision": "sha256:..."}},
            "insert": {"required": ["after", "exactly one of source or source_file"],
                       "optional": {"source_revision": "sha256:..."}, "after_zero": "beginning"},
            "delete": {"required": ["slide"]},
            "move": {"required": ["slide", "after"], "after_zero": "beginning"},
            "substitute": {"required": ["slide", "expect", "replacement"], "optional": {"count": 1}},
        },
    },
    "edit_documents": {
        "marker": {"quarkfoil_edit": 1},
        "apply": "repeat --edit FILE for ordered atomic application",
        "operations": {
            "replace": {"header": ["deck_revision", "slide", "slide_revision", "notes"],
                        "body": "exactly one Markdown slide"},
            "insert": {"header": ["deck_revision", "slide"],
                       "slide": "resulting insertion position", "body": "exactly one Markdown slide"},
            "delete": {"header": ["deck_revision", "slide", "slide_revision"]},
            "move": {"header": ["deck_revision", "slide", "slide_revision", "after"]},
            "substitute": {"header": ["deck_revision", "slide", "slide_revision", "expect", "replacement"],
                           "optional": {"count": 1}},
        },
        "operations_are_sequential": True,
        "io": {"success": "YAML receipt on stdout", "error": "YAML on stderr"},
        "exit_code_4": "operation precondition mismatch",
    },
    "io": {"success": "JSON on stdout", "error": "JSON on stderr"},
    "response_shapes": {
        "slide": {
            "type": "object",
            "required": ["number", "slide_revision", "title", "layout", "trashed", "section", "source"],
            "properties": {
                "number": {"type": "integer", "minimum": 1},
                "slide_revision": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                "title": {"type": "string"}, "layout": {"type": "string"},
                "trashed": {"type": "boolean"}, "source": {"type": "string"},
                "section": {"type": ["object", "null"]},
            },
            "additionalProperties": False,
        },
        "changed_slide": {
            "type": "object",
            "required": ["number", "slide_revision", "title", "layout", "trashed", "section"],
            "properties": {
                "number": {"type": "integer", "minimum": 1},
                "slide_revision": {"type": "string"}, "title": {"type": "string"},
                "layout": {"type": "string"}, "trashed": {"type": "boolean"},
                "section": {"type": ["object", "null"]},
                "source": {"type": "string", "notes": "omitted by --quiet"},
            },
            "additionalProperties": False,
        },
        "inspect": {
            "type": "object",
            "required": ["protocol_version", "capabilities", "revision", "metadata", "slides", "diagnostics",
                         "slides_reliable"],
            "properties": {
                "protocol_version": {"const": PROTOCOL_VERSION}, "capabilities": {"type": "array"},
                "revision": {"type": "string"}, "metadata": {"type": "object"},
                "slides": {"type": "array", "items": "slide"},
                "diagnostics": {"type": "array"}, "source": {"type": "string"},
                "slides_reliable": {"type": "boolean"},
            },
            "additionalProperties": False,
            "notes": "source is omitted with --no-source; projected slides are returned in deck order",
        },
        "apply": {
            "type": "object",
            "required": ["protocol_version", "capabilities", "revision", "diagnostics", "dry_run",
                         "changed_slides", "operation_results"],
            "properties": {
                "protocol_version": {"const": PROTOCOL_VERSION}, "capabilities": {"type": "array"},
                "revision": {"type": "string"}, "diagnostics": {"type": "array"},
                "dry_run": {"type": "boolean"},
                "changed_slides": {"type": "array", "items": "changed_slide"},
                "operation_results": {"type": "array", "items": "operation_result"},
                "metadata": {"type": "object"},
                "slides": {"type": "array", "items": "slide"},
                "source": {"type": "string"}, "slides_reliable": {"type": "boolean"},
            },
            "additionalProperties": False,
            "notes": "--quiet omits metadata, slides, source, and source within changed_slides",
        },
        "operation_result": {
            "type": "object", "required": ["operation", "type", "result_slide"],
            "properties": {
                "operation": {"type": "integer", "minimum": 0},
                "type": {"enum": ["replace", "insert", "delete", "move", "substitute"]},
                "result_slide": {"type": ["integer", "null"], "minimum": 1},
                "deleted_slide": {"type": "integer", "minimum": 1},
                "from_slide": {"type": "integer", "minimum": 1},
                "after": {"type": "integer", "minimum": 0}, "no_op": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "error": {
            "type": "object",
            "required": ["error", "message"],
            "properties": {
                "error": {"type": "string"}, "message": {"type": "string"},
                "operation": {"type": "integer", "minimum": 0}, "path": {"type": "string"},
                "expected_revision": {"type": "string"}, "actual_revision": {"type": "string"},
            },
            "notes": "revision_mismatch includes expected_revision and actual_revision",
        },
    },
    "exit_codes": {"0": "success", "2": "invalid request", "3": "revision conflict", "4": "expectation mismatch"},
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


class ExpectationMismatch(DeckCommandError):
    def __init__(self, slide: int, expected_count: int, actual_count: int):
        super().__init__(
            f"slide {slide} contains the expected text {actual_count} times, not {expected_count}",
            4,
            code="expectation_mismatch",
            slide=slide,
            expected_count=expected_count,
            actual_count=actual_count,
        )


class SlideRevisionMismatch(DeckCommandError):
    def __init__(self, slide: int, expected: str, actual: str):
        super().__init__(
            f"slide {slide} no longer identifies the inspected slide",
            4,
            code="slide_revision_mismatch",
            slide=slide,
            expected_slide_revision=expected,
            actual_slide_revision=actual,
        )


class DeckArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise DeckCommandError(message, code="usage_error")


def revision(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _strict_revision(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:") \
            or any(character not in "0123456789abcdef" for character in value[7:]):
        raise DeckCommandError(f"edit field '{field}' must be sha256 followed by 64 lowercase hexadecimal digits")
    return value


class _StrictYamlLoader(yaml.SafeLoader):
    """Safe YAML loader which also rejects duplicate mapping keys."""


def _strict_mapping(loader: _StrictYamlLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, "mapping keys must be scalar", key_node.start_mark,
            ) from error
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, f"duplicate key {key!r}", key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_StrictYamlLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _strict_mapping)


def _load_strict_yaml(source: str) -> Any:
    try:
        for token in yaml.scan(source):
            if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)):
                raise DeckCommandError("YAML aliases and anchors are not allowed")
        return yaml.load(source, Loader=_StrictYamlLoader)
    except DeckCommandError:
        raise
    except yaml.YAMLError as error:
        raise DeckCommandError(f"invalid YAML edit header: {error}") from error


def _print_yaml(payload: Any, *, stream: Any = None) -> None:
    output = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(output, end="", file=sys.stdout if stream is None else stream, flush=True)


def _edit_text(header: dict[str, Any], body: str = "") -> str:
    encoded = yaml.safe_dump(header, allow_unicode=True, sort_keys=False, default_flow_style=False).rstrip()
    return f"---\n{encoded}\n---\n" + (f"\n{body.lstrip()}" if body else "")


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
            "code": item.code,
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
    slides_reliable = not any(item.code in UNRELIABLE_BOUNDARY_CODES for item in deck.diagnostics)
    if selected_slides is not None and not slides_reliable:
        raise DeckCommandError(
            "numbered slide projection is unsafe because slide boundaries are unreliable",
            code="unreliable_slide_boundaries",
        )
    if selected_slides is not None:
        missing = sorted(selected_slides - set(range(1, len(deck.slides) + 1)))
        if missing:
            raise DeckCommandError(
                f"unknown slide {missing[0]}; presentation has {len(deck.slides)} slides",
                code="unknown_slide", slide=missing[0], slide_count=len(deck.slides),
            )
    slides = []
    for slide in deck.slides:
        if selected_slides is not None and slide.index + 1 not in selected_slides:
            continue
        raw = slide.raw if include_notes else without_notes(slide.raw)
        slides.append({
            "number": slide.index + 1,
            "slide_revision": revision(slide.raw.encode("utf-8")),
            "title": slide.title,
            "layout": slide.layout,
            "trashed": slide.trashed,
            "section": None if slide.section is None else {"id": slide.section.id, "title": slide.section.title},
            "source": raw,
        })
    result = {
        "protocol_version": PROTOCOL_VERSION,
        "capabilities": list(CAPABILITIES),
        "revision": current_revision,
        "metadata": deck.metadata,
        "slides": slides,
        "diagnostics": _diagnostics(deck),
        "slides_reliable": slides_reliable,
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
    suffix = _newline(source)
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
    if "slide_revision" in operation:
        number = _integer(operation, "slide")
        _slide_position(deck, number)
        expected_slide_revision = _strict_revision(operation["slide_revision"], "slide_revision")
        actual_slide_revision = revision(deck.slides[number - 1].raw.encode("utf-8"))
        if expected_slide_revision != actual_slide_revision:
            raise SlideRevisionMismatch(number, expected_slide_revision, actual_slide_revision)
    if name == "replace":
        _check_fields(operation, {"slide", "source"}, {"notes", "slide_revision"})
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
        _check_fields(operation, {"slide"}, {"slide_revision"})
        if len(deck.slides) == 1:
            raise DeckCommandError("a presentation must contain at least one slide")
        number = _integer(operation, "slide")
        _slide_position(deck, number)
        return _delete_slide(source, deck, number)
    elif name == "move":
        _check_fields(operation, {"slide", "after"}, {"slide_revision"})
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
    elif name == "substitute":
        _check_fields(operation, {"slide", "expect", "replacement"}, {"count", "slide_revision"})
        number = _integer(operation, "slide")
        _slide_position(deck, number)
        expected = operation.get("expect")
        replacement = operation.get("replacement")
        if not isinstance(expected, str) or not expected:
            raise DeckCommandError("operation field 'expect' must be a nonempty string")
        if not isinstance(replacement, str):
            raise DeckCommandError("operation field 'replacement' must be a string")
        expected_count = operation.get("count", 1)
        if isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 1:
            raise DeckCommandError("operation field 'count' must be a positive integer")
        slide = deck.slides[number - 1]
        actual_count = slide.raw.count(expected)
        if actual_count != expected_count:
            raise ExpectationMismatch(number, expected_count, actual_count)
        replaced = slide.raw.replace(expected, replacement)
        return source[:slide.range.start] + replaced + source[slide.range.end:]
    else:
        raise DeckCommandError(f"unknown operation '{name}'")


def _apply_transaction_details(source: str, operations: Any) -> tuple[str, list[dict[str, Any]], set[str], list[str]]:
    if not isinstance(operations, list) or not operations:
        raise DeckCommandError("transaction requires a nonempty 'operations' array")
    tokens = [f"original:{index}" for index in range(len(parse_deck(source).slides))]
    touched: set[str] = set()
    results: list[dict[str, Any]] = []
    for index, operation in enumerate(operations):
        try:
            updated = _apply_operation(source, operation)
        except DeckCommandError as error:
            raise error.at_operation(index) from error
        name = operation.get("operation", operation.get("op"))
        result: dict[str, Any] = {"operation": index, "type": name}
        if name in ("replace", "substitute"):
            token = tokens[operation["slide"] - 1]
            touched.add(token)
            result["_token"] = token
        elif name == "insert":
            token = f"inserted:{index}"
            tokens.insert(operation["after"], token)
            touched.add(token)
            result["_token"] = token
        elif name == "delete":
            token = tokens.pop(operation["slide"] - 1)
            touched.discard(token)
            result.update({"deleted_slide": operation["slide"], "result_slide": None})
        elif name == "move":
            number, after = operation["slide"], operation["after"]
            token = tokens[number - 1]
            no_op = after == number - 1
            if not no_op:
                tokens.pop(number - 1)
                tokens.insert(after - 1 if number < after else after, token)
                touched.add(token)
            result.update({"from_slide": number, "after": after, "no_op": no_op, "_token": token})
        results.append(result)
        source = updated
    deck = parse_deck(source)
    errors = [item.message for item in deck.diagnostics if item.level == "error"]
    if errors:
        raise DeckCommandError(f"transaction produced an invalid presentation: {errors[0]}")
    positions = {token: index + 1 for index, token in enumerate(tokens)}
    for result in results:
        token = result.pop("_token", None)
        if token is not None:
            result["result_slide"] = positions.get(token)
    return source, results, touched, tokens


def apply_transaction(source: str, operations: Any) -> str:
    return _apply_transaction_details(source, operations)[0]


def _changed_slides(
    source: str, touched: set[str], tokens: list[str], *, include_notes: bool, include_source: bool,
) -> list[dict[str, Any]]:
    deck = parse_deck(source)
    payload = []
    for index, (slide, token) in enumerate(zip(deck.slides, tokens), start=1):
        if token not in touched:
            continue
        item = {
            "number": index,
            "slide_revision": revision(slide.raw.encode("utf-8")),
            "title": slide.title,
            "layout": slide.layout,
            "trashed": slide.trashed,
            "section": None if slide.section is None else {"id": slide.section.id, "title": slide.section.title},
        }
        if include_source:
            item["source"] = slide.raw if include_notes else without_notes(slide.raw)
        payload.append(item)
    return payload


def _load_transaction(path: str) -> tuple[Any, Path]:
    try:
        if path == "-":
            text, base = sys.stdin.read(), Path.cwd()
        else:
            transaction_path = Path(path).resolve()
            text, base = transaction_path.read_text(encoding="utf-8"), transaction_path.parent
        return json.loads(text), base
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeckCommandError(f"cannot read transaction: {error}") from error


_EDIT_COMMON_FIELDS = {"quarkfoil_edit", "operation", "deck_revision"}
_EDIT_INFO_FIELDS = {"title", "layout", "section", "trashed"}
_EDIT_OPERATION_FIELDS = {
    "replace": {"slide", "slide_revision", "notes"},
    "insert": {"slide"},
    "delete": {"slide", "slide_revision"},
    "move": {"slide", "slide_revision", "after"},
    "substitute": {"slide", "slide_revision", "expect", "replacement", "count"},
}


def _split_edit_document(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise DeckCommandError("edit document must begin with a YAML '---' header")
    closing = next((index for index, line in enumerate(lines[1:], start=1) if line.rstrip("\r\n") == "---"), None)
    if closing is None:
        raise DeckCommandError("edit document has no closing YAML '---' delimiter")
    header = _load_strict_yaml("".join(lines[1:closing]))
    if not isinstance(header, dict):
        raise DeckCommandError("edit document header must be a YAML mapping")
    return header, "".join(lines[closing + 1:]).lstrip("\r\n")


def _parse_edit_document(text: str, label: str) -> tuple[str, dict[str, Any]]:
    if len(text.encode("utf-8")) > MAX_DECK_BYTES:
        raise DeckCommandError(f"edit document exceeds the {MAX_DECK_BYTES}-byte limit", input=label)
    try:
        header, body = _split_edit_document(text)
        if header.get("quarkfoil_edit") != 1 or isinstance(header.get("quarkfoil_edit"), bool):
            raise DeckCommandError("edit document requires 'quarkfoil_edit: 1'")
        name = header.get("operation")
        if name not in _EDIT_OPERATION_FIELDS:
            raise DeckCommandError(f"unknown edit operation {name!r}")
        allowed = _EDIT_COMMON_FIELDS | _EDIT_INFO_FIELDS | _EDIT_OPERATION_FIELDS[name]
        unknown = header.keys() - allowed
        if unknown:
            raise DeckCommandError(f"unknown edit field {sorted(unknown, key=str)[0]!r}")
        required = _EDIT_COMMON_FIELDS | _EDIT_OPERATION_FIELDS[name]
        if name == "substitute":
            required -= {"count"}
        missing = required - header.keys()
        if missing:
            raise DeckCommandError(f"missing edit field '{sorted(missing)[0]}'")
        deck_revision = _strict_revision(header["deck_revision"], "deck_revision")
        if "slide_revision" in header:
            _strict_revision(header["slide_revision"], "slide_revision")
        operation = {key: header[key] for key in _EDIT_OPERATION_FIELDS[name] if key in header}
        operation["operation"] = name
        if name == "insert":
            position = operation.pop("slide")
            if isinstance(position, bool) or not isinstance(position, int) or position < 1:
                raise DeckCommandError("edit field 'slide' must be a positive integer")
            operation["after"] = position - 1
        if name in ("replace", "insert"):
            operation["source"] = _slide_source(body)
            if name == "replace" and header["notes"] not in ("preserve", "replace", "remove"):
                raise DeckCommandError("edit field 'notes' must be preserve, replace, or remove")
        elif body.strip():
            raise DeckCommandError(f"{name} edit document must not contain a Markdown body")
        return deck_revision, operation
    except DeckCommandError as error:
        error.details.setdefault("input", label)
        raise


def _load_edit_documents(paths: list[str]) -> tuple[str, list[dict[str, Any]], list[str]]:
    if paths.count("-") > 1:
        raise DeckCommandError("standard input may be used for at most one edit document")
    revisions: list[str] = []
    operations: list[dict[str, Any]] = []
    labels: list[str] = []
    for path in paths:
        label = "-" if path == "-" else str(Path(path))
        try:
            text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise DeckCommandError(f"cannot read edit document: {error}", input=label) from error
        expected, operation = _parse_edit_document(text, label)
        revisions.append(expected)
        operations.append(operation)
        labels.append(label)
    if not revisions:
        raise DeckCommandError("at least one --edit document is required")
    if any(value != revisions[0] for value in revisions[1:]):
        raise DeckCommandError("edit documents have different deck revisions", code="revision_disagreement")
    return revisions[0], operations, labels


def _materialize_sources(operations: Any, base: Path) -> Any:
    """Read each external slide fragment once and replace it with inline source."""
    if not isinstance(operations, list):
        return operations
    materialized = []
    for index, value in enumerate(operations):
        if not isinstance(value, dict) or value.get("operation", value.get("op")) not in ("replace", "insert"):
            materialized.append(value)
            continue
        operation = dict(value)
        has_source = "source" in operation
        has_file = "source_file" in operation
        if has_source == has_file:
            raise DeckCommandError(
                "operation requires exactly one of 'source' or 'source_file'",
                operation=index, path=f"operations[{index}]",
            )
        if not has_file:
            if "source_revision" in operation:
                raise DeckCommandError(
                    "'source_revision' requires 'source_file'",
                    operation=index, path=f"operations[{index}].source_revision",
                )
            materialized.append(operation)
            continue
        source_value = operation["source_file"]
        if not isinstance(source_value, str) or not source_value:
            raise DeckCommandError(
                "operation field 'source_file' must be a nonempty path",
                operation=index, path=f"operations[{index}].source_file",
            )
        source_path = Path(source_value)
        resolved = (base / source_path).resolve() if not source_path.is_absolute() else source_path.resolve()
        details = {"operation": index, "path": f"operations[{index}].source_file", "resolved_source_path": str(resolved)}
        try:
            data = resolved.read_bytes()
        except OSError as error:
            raise DeckCommandError(f"cannot read slide source: {error}", **details) from error
        if len(data) > MAX_DECK_BYTES:
            raise DeckCommandError(f"slide source exceeds the {MAX_DECK_BYTES}-byte limit", **details)
        expected = operation.get("source_revision")
        actual = revision(data)
        if expected is not None:
            if not isinstance(expected, str) or not expected.startswith("sha256:") or len(expected) != 71 \
                    or any(character not in "0123456789abcdef" for character in expected[7:]):
                raise DeckCommandError("source_revision must be sha256 followed by 64 lowercase hexadecimal digits", **details)
            if expected != actual:
                raise DeckCommandError(
                    "slide source revision does not match",
                    code="source_revision_mismatch", expected_source_revision=expected,
                    actual_source_revision=actual, **details,
                )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DeckCommandError("slide source is not valid UTF-8", **details) from error
        try:
            _slide_source(text)
        except DeckCommandError as error:
            error.details.update(details)
            raise
        operation["source"] = text
        del operation["source_file"]
        operation.pop("source_revision", None)
        materialized.append(operation)
    return materialized


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


def _slide_edit_document(slide: dict[str, Any], deck_revision: str, *, include_notes: bool) -> str:
    header = {
        "quarkfoil_edit": 1,
        "operation": "replace",
        "deck_revision": deck_revision,
        "slide": slide["number"],
        "slide_revision": slide["slide_revision"],
        "title": slide["title"],
        "layout": slide["layout"],
        "section": slide["section"],
        "trashed": slide["trashed"],
        "notes": "replace" if include_notes else "preserve",
    }
    return _edit_text(header, slide["source"])


def _write_edit_directory(destination: Path, summary: dict[str, Any], *, include_notes: bool) -> None:
    destination = destination.resolve()
    if destination.exists():
        raise DeckCommandError("edit output destination already exists", path=str(destination))
    if not destination.parent.is_dir():
        raise DeckCommandError("edit output parent directory does not exist", path=str(destination.parent))
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        entries = []
        for slide in summary["slides"]:
            filename = f"slide-{slide['number']:04d}.md"
            (temporary / filename).write_text(
                _slide_edit_document(slide, summary["revision"], include_notes=include_notes), encoding="utf-8",
            )
            entries.append({
                "slide": slide["number"], "slide_revision": slide["slide_revision"], "file": filename,
            })
        manifest = {
            "quarkfoil_edit_manifest": 1,
            "deck_revision": summary["revision"],
            "slides": entries,
            "diagnostics": summary["diagnostics"],
        }
        (temporary / "manifest.yml").write_text(
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8",
        )
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _inspect(arguments: list[str]) -> int:
    parser = DeckArgumentParser(prog="quarkfoil deck inspect", description="Return a presentation snapshot for an editing agent")
    parser.add_argument("deck", type=Path)
    parser.add_argument("--no-notes", action="store_true", help="Omit speaker notes from returned content")
    parser.add_argument("--no-source", action="store_true", help="Omit the whole-deck source from JSON or YAML")
    parser.add_argument("--slides", help="Return only these comma-separated slide numbers")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    parser.add_argument("--format", choices=("json", "yaml", "edit", "markdown"), default="json",
                        help="Output format; edit is guarded YAML followed by literal Markdown")
    parser.add_argument("--output", type=Path, help="New directory for one or more editable slide documents")
    args = parser.parse_args(arguments)
    selected = _selected_slides(args.slides)
    if args.format in ("edit", "markdown") and selected is None:
        raise DeckCommandError(f"--format {args.format} requires --slides", code="usage_error")
    if args.output is not None and args.format != "edit":
        raise DeckCommandError("--output requires --format edit", code="usage_error")
    if args.compact and args.format != "json":
        raise DeckCommandError("--compact is only available with --format json", code="usage_error")
    data, current = _read_deck(args.deck)
    summary = _summary(data.decode("utf-8"), current, include_notes=not args.no_notes,
                       include_source=args.format in ("edit", "markdown") or not args.no_source,
                       selected_slides=selected)
    if args.format == "json":
        _print_json(summary, compact=args.compact)
    elif args.format == "yaml":
        _print_yaml(summary)
    elif args.format == "edit":
        if args.output is not None:
            _write_edit_directory(args.output, summary, include_notes=not args.no_notes)
            _print_yaml({"quarkfoil_result": 1, "revision": current, "output": str(args.output),
                         "slides": len(summary["slides"])})
        elif len(summary["slides"]) != 1:
            raise DeckCommandError("stdout edit format requires exactly one selected slide; use --output",
                                   code="usage_error")
        else:
            print(_slide_edit_document(summary["slides"][0], current, include_notes=not args.no_notes),
                  end="", flush=True)
    else:
        multiple = len(summary["slides"]) > 1
        chunks = []
        for slide in summary["slides"]:
            prefix = f"<!-- quarkfoil slide {slide['number']} -->\n\n" if multiple else ""
            chunks.append(prefix + slide["source"].strip())
        print("\n\n".join(chunks) + "\n", end="", flush=True)
    return 0


def _apply(arguments: list[str]) -> int:
    parser = DeckArgumentParser(prog="quarkfoil deck apply", description="Atomically apply a revision-guarded slide transaction")
    parser.add_argument("deck", type=Path)
    parser.add_argument("transaction", nargs="?", default="-", help="JSON transaction file, or - for stdin (default)")
    parser.add_argument("--edit", action="append", default=[], metavar="FILE",
                        help="YAML edit document; repeat to apply several in order")
    parser.add_argument("--if-revision", help="Expected SHA-256 revision; may instead be present in transaction JSON")
    parser.add_argument("--no-notes", action="store_true", help="Omit notes from returned JSON; does not change stored notes")
    parser.add_argument("--dry-run", "--check", action="store_true",
                        help="Preview without writing; normal apply already validates atomically")
    parser.add_argument(
        "--quiet", action="store_true",
        help="Omit Markdown source; return revision, changed-slide summaries, operation results, and diagnostics",
    )
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    args = parser.parse_args(arguments)
    edit_mode = bool(args.edit)
    if edit_mode:
        if args.transaction != "-":
            raise DeckCommandError("a JSON transaction cannot be combined with --edit", code="usage_error")
        if args.if_revision:
            raise DeckCommandError("--if-revision cannot be combined with guarded edit documents", code="usage_error")
        expected, operations, edit_labels = _load_edit_documents(args.edit)
    else:
        transaction, transaction_base = _load_transaction(args.transaction)
        if isinstance(transaction, list):
            operations, embedded_revision = transaction, None
        elif isinstance(transaction, dict):
            unknown = transaction.keys() - {"revision", "operations"}
            if unknown:
                raise DeckCommandError(f"unknown transaction field '{sorted(unknown)[0]}'")
            operations, embedded_revision = transaction.get("operations"), transaction.get("revision")
        else:
            raise DeckCommandError("transaction must be an object or an operations array")
        operations = _materialize_sources(operations, transaction_base)
        if args.if_revision and embedded_revision and _expected_revision(args.if_revision) != _expected_revision(embedded_revision):
            raise DeckCommandError("--if-revision and transaction revision disagree", code="revision_disagreement")
        expected = _expected_revision(args.if_revision or embedded_revision)
        edit_labels = []
    path = args.deck.resolve()
    with deck_file_lock(path):
        data, current = _read_deck(path)
        if current != expected:
            raise RevisionConflict(expected, current)
        try:
            updated, operation_results, touched, tokens = _apply_transaction_details(data.decode("utf-8"), operations)
        except DeckCommandError as error:
            operation_index = error.details.get("operation")
            if edit_mode and isinstance(operation_index, int) and operation_index < len(edit_labels):
                error.details.setdefault("input", edit_labels[operation_index])
            raise
        encoded = updated.encode("utf-8")
        if len(encoded) > MAX_DECK_BYTES:
            raise DeckCommandError(f"updated presentation exceeds the {MAX_DECK_BYTES}-byte limit")
        if not args.dry_run:
            atomic_write(path, encoded)
    updated_revision = revision(encoded)
    common = {
        "protocol_version": PROTOCOL_VERSION,
        "capabilities": list(CAPABILITIES),
        "revision": updated_revision,
        "diagnostics": _diagnostics(parse_deck(updated)),
        "dry_run": args.dry_run,
        "changed_slides": _changed_slides(
            updated, touched, tokens, include_notes=not args.no_notes, include_source=not args.quiet,
        ),
        "operation_results": operation_results,
    }
    if edit_mode:
        yaml_operations = []
        for index, result in enumerate(operation_results):
            item = {"operation": result["type"], "input": edit_labels[index]}
            item.update({key: value for key, value in result.items() if key not in ("operation", "type")})
            result_slide = item.get("result_slide")
            if result_slide is not None:
                final_slide = parse_deck(updated).slides[result_slide - 1]
                item["slide_revision"] = revision(final_slide.raw.encode("utf-8"))
            yaml_operations.append(item)
        _print_yaml({"quarkfoil_result": 1, "revision": updated_revision, "dry_run": args.dry_run,
                     "operations": yaml_operations, "diagnostics": common["diagnostics"]})
        return 0
    if args.quiet:
        payload = common
    else:
        payload = _summary(updated, updated_revision, include_notes=not args.no_notes)
        payload.update(common)
    _print_json(payload, compact=args.compact)
    return 0


def main(arguments: list[str]) -> int:
    yaml_errors = (
        bool(arguments) and arguments[0] == "apply" and "--edit" in arguments
    ) or (
        bool(arguments) and arguments[0] == "inspect"
        and any(value in arguments for value in ("yaml", "edit", "markdown"))
        and "--format" in arguments
    )
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
        payload = {"error": error.code, "message": str(error), **error.details}
        if yaml_errors:
            _print_yaml({"quarkfoil_error": 1, **payload}, stream=sys.stderr)
        else:
            _print_json(payload, compact=True, stream=sys.stderr)
        return error.exit_code
    except BrokenPipeError:
        _silence_broken_pipe()
        return 0


__all__ = ["DeckCommandError", "GUIDE", "PROTOCOL", "RevisionConflict", "apply_transaction", "main", "revision", "without_notes"]
