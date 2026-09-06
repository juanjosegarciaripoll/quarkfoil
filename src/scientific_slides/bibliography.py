"""Source-preserving bibliography filtering for static export."""

from __future__ import annotations

import re

from .parser import parse_deck


def citation_keys(source: str) -> set[str]:
    """Collect inline citations and both numbered and brief attribution keys.

    Keep the inline syntax and code exclusion aligned with bibliography.js.
    Notes are included while they remain in the exported source.
    """
    keys: set[str] = set()
    for slide in parse_deck(source).slides:
        content = "\n".join([
            slide.title, *(cell.source for cell in slide.cells),
            *(overlay.source for overlay in slide.overlays), slide.notes,
            slide.footer[0] if slide.footer else "",
        ])
        prose = re.sub(r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`", "\n", content)
        for match in re.finditer(r"(?<!\\)\[@([\w:./+-]+)(?:\s*;\s*@([\w:./+-]+))*\]", prose, re.ASCII):
            keys.update(re.findall(r"@([\w:./+-]+)", match.group(), re.ASCII))
        for overlay in slide.overlays:
            if overlay.type == "citation":
                values = overlay.attrs.values
                keys.update(filter(None, re.split(r"[\s,;]+", values.get("keys") or values.get("key") or "")))
    return keys


def _scan(source: str, start: int, closer: str) -> int:
    """Find a top-level delimiter, respecting nested braces and quoted values."""
    depth = 0
    quoted = False
    index = start
    while index < len(source):
        character = source[index]
        if character == "\\":
            index += 2
            continue
        if character == closer and depth == 0 and not quoted:
            return index
        if character == '"' and depth == 0:
            quoted = not quoted
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("Cannot trim bibliography: unbalanced BibTeX braces")
        elif character == "%" and depth == 0 and not quoted:
            newline = source.find("\n", index)
            index = len(source) if newline < 0 else newline
            continue
        index += 1
    if closer == "," and depth == 0 and not quoted:
        return len(source)
    raise ValueError("Cannot trim bibliography: unterminated BibTeX entry or value")


def _dependencies(body: str) -> set[str]:
    dependencies: set[str] = set()
    position = 0
    while position < len(body):
        end = _scan(body, position, ",")
        field = re.sub(r"(?m)^\s*%[^\n]*", "", body[position:end]).strip()
        name, separator, value = field.partition("=")
        if separator and name.strip().lower() in {"crossref", "xref", "xdata"}:
            value = value.strip()
            if value.startswith(("{", '"')):
                value = value[1:-1]
            dependencies.update(filter(None, (key.strip() for key in value.split(","))))
        position = end + 1
    return dependencies


def trim_bibliography(source: str, keys: set[str]) -> str:
    """Remove uncited records, retaining directives and dependency records.

    Entries are sliced verbatim; no BibTeX fields or macros are normalized.
    Malformed record boundaries fail export rather than silently losing data.
    """
    records: list[tuple[int, int, str | None, set[str]]] = []
    position = 0
    header = re.compile(r"@([a-z]+)\s*([{(])", re.IGNORECASE)
    while position < len(source):
        if source[position] == "%":
            newline = source.find("\n", position)
            position = len(source) if newline < 0 else newline + 1
            continue
        if source[position] != "@":
            position += 1
            continue
        match = header.match(source, position)
        if not match:
            raise ValueError("Cannot trim bibliography: invalid BibTeX entry header")
        end = _scan(source, match.end(), "}" if match[2] == "{" else ")") + 1
        body = source[match.end():end - 1]
        key = None
        dependencies: set[str] = set()
        if match[1].lower() not in {"comment", "preamble", "string"}:
            key, separator, fields = body.partition(",")
            key = key.strip()
            if not separator or not key or re.search(r"\s", key):
                raise ValueError("Cannot trim bibliography: invalid BibTeX citation key")
            dependencies = _dependencies(fields)
        records.append((position, end, key, dependencies))
        position = end

    retained = set(keys)
    by_key = {key: dependencies for _, _, key, dependencies in records if key is not None}
    pending = list(retained)
    while pending:
        for dependency in by_key.get(pending.pop(), set()) - retained:
            retained.add(dependency)
            pending.append(dependency)
    pieces = []
    position = 0
    for start, end, key, _ in records:
        pieces.append(source[position:start])
        if key is None or key in retained:
            pieces.append(source[start:end])
        position = end
    pieces.append(source[position:])
    return "".join(pieces)
