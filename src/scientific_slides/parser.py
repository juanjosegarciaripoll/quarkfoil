"""Structural parser for Quarkfoil presentation Markdown.

``app/modules/parser.js`` remains the canonical browser implementation.  This
module mirrors its document model for Python-side, source-preserving tools; it
does not parse or render Markdown inside cells and overlays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Literal

import yaml


LAYOUTS = frozenset(("1", "1-1", "1-2", "2-1", "0", "front", "free"))
THEMES = ("scientific-light", "scientific-dark")
CELL_NAMES = frozenset(("core", "left", "right", "top-left", "bottom-left", "top-right", "bottom-right"))
SHAPES = frozenset(("rectangle", "rounded-rectangle", "ellipse", "circle", "diamond", "triangle", "hexagon", "cross", "x", "star", "cloud", "callout", "left-brace", "right-brace", "arc"))
_COLOR = re.compile(r"^#[0-9a-f]{6}(?:[0-9a-f]{2})?$", re.IGNORECASE)
_HEADING = re.compile(r"^\s*(#{1,6})\s+([^\r\n]+)\r?\n?")
_ATTRIBUTES = re.compile(r"\s+\{([^}]*)\}\s*$")
_ATTRIBUTE_TOKEN = re.compile(r'''(?:[^\s"']+|"[^"]*"|'[^']*')+''')
_IMAGE = re.compile(r'''^!\[([^]]*)\]\(([^)\s]+)(?:\s+["']([^"']*)["'])?\)\s*(?:\{([^}]*)\})?\s*$''')


@dataclass(slots=True)
class SourceRange:
    start: int
    end: int
    header_end: int | None = None
    body_start: int | None = None
    body_end: int | None = None


@dataclass(slots=True)
class Attributes:
    classes: list[str] = field(default_factory=list)
    id: str = ""
    values: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Diagnostic:
    level: Literal["warning", "error"]
    message: str
    line: int | None = None
    slide: int | None = None


@dataclass(slots=True)
class Image:
    alt: str
    source: str
    title: str
    attrs: Attributes


@dataclass(slots=True)
class Video:
    source: str
    poster: str
    fit: str
    controls: bool
    autoplay: bool
    loop: bool
    muted: bool


@dataclass(slots=True)
class Cell:
    id: str
    type: str
    source: str
    image: Image | None
    video: Video | None
    range: SourceRange | None
    attrs: Attributes
    font_size: float
    source_ranges: list[SourceRange] = field(default_factory=list)


@dataclass(slots=True)
class Overlay:
    id: str
    type: str
    source: str
    image: Image | None
    video: Video | None
    attrs: Attributes
    range: SourceRange
    geometry: dict[str, float]
    font_size: float
    rotation: float
    color: str | None
    alignment: str
    fragment: float | None
    locked: bool
    shape: str
    fill: str | None
    stroke: str | None
    stroke_width: float
    stroke_style: str
    shadow: bool
    shape_parameters: dict[str, Any] | None
    arrow: dict[str, Any] | None


@dataclass(slots=True)
class Section:
    kind: Literal["section"]
    index: int
    id: str
    title: str
    attrs: Attributes
    raw: str
    range: SourceRange
    heading_range: SourceRange
    hashes: str
    is_trash: bool
    slide_count: int = 0


@dataclass(slots=True)
class Slide:
    kind: Literal["slide"]
    index: int
    id: str
    title: str
    raw: str
    range: SourceRange
    heading_range: SourceRange | None
    title_range: SourceRange | None
    title_source: str
    heading_attrs: Attributes
    trashed: bool
    layout: str
    columns: tuple[float, float]
    rows: tuple[float, float]
    cells: list[Cell]
    overlays: list[Overlay]
    footer: tuple[str, SourceRange] | None
    notes: str
    notes_range: SourceRange | None


@dataclass(slots=True)
class Deck:
    source: str
    metadata: dict[str, Any]
    front_matter_range: SourceRange
    slides: list[Slide]
    sections: list[Section]
    items: list[Slide | Section]
    diagnostics: list[Diagnostic]


@dataclass(slots=True)
class _Block:
    name: str
    attrs: Attributes
    body: str
    range: SourceRange
    local_start: int
    local_end: int


def parse_attributes(source: str = "") -> Attributes:
    attrs = Attributes()
    for token in _ATTRIBUTE_TOKEN.findall(source):
        if token.startswith("."):
            attrs.classes.append(token[1:])
        elif token.startswith("#"):
            attrs.id = token[1:]
        else:
            key, separator, value = token.partition("=")
            if not separator:
                attrs.values[key] = "true"
            else:
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                attrs.values[key] = value
    return attrs


def _number(value: Any, default: float = math.nan) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _font_size(value: Any = "1") -> float:
    if value is None:
        value = "1"
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:em)?", str(value).strip(), re.IGNORECASE)
    return float(match.group(1)) if match else math.nan


def _ratio(value: str | None) -> tuple[float, float]:
    if not value:
        return (50.0, 50.0)
    try:
        numbers = tuple(float(item) for item in re.split(r"[\s,/:]+", value.strip()))
    except ValueError:
        return (50.0, 50.0)
    if len(numbers) != 2 or any(not math.isfinite(item) or item <= 0 for item in numbers):
        return (50.0, 50.0)
    total = sum(numbers)
    return (100 * numbers[0] / total, 100 * numbers[1] / total)


def _front_matter(source: str, diagnostics: list[Diagnostic]) -> tuple[dict[str, Any], int]:
    if not source.startswith("---"):
        return {}, 0
    match = re.match(r"^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)", source)
    if not match:
        diagnostics.append(Diagnostic("error", "Unclosed YAML front matter", line=1))
        return {}, 0
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
        if not isinstance(metadata, dict):
            raise ValueError("Front matter must be a mapping")
    except (yaml.YAMLError, ValueError) as error:
        mark = getattr(error, "problem_mark", None)
        diagnostics.append(Diagnostic("error", f"YAML: {error}", line=mark.line + 2 if mark else 1))
        metadata = {}
    return metadata, match.end()


def _item_ranges(source: str, start: int) -> list[SourceRange]:
    separators = list(re.finditer(r"^\s*---\s*$", source[start:], re.MULTILINE))
    ranges: list[SourceRange] = []
    cursor = start
    for separator in separators:
        separator_start, separator_end = start + separator.start(), start + separator.end()
        if source[cursor:separator_start].strip():
            ranges.append(SourceRange(cursor, separator_start))
        cursor = separator_end
        if cursor < len(source) and source[cursor] == "\r":
            cursor += 1
        if cursor < len(source) and source[cursor] == "\n":
            cursor += 1
    if source[cursor:].strip():
        ranges.append(SourceRange(cursor, len(source)))
    return ranges


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _blocks(raw: str, absolute_start: int, diagnostics: list[Diagnostic], source: str) -> list[_Block]:
    lines = raw.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    blocks: list[_Block] = []
    index = 0
    while index < len(lines):
        text = lines[index].rstrip("\r\n")
        opened = re.fullmatch(r":::\s*([a-z][a-z0-9-]*)?\s*(?:\{([^}]*)\})?\s*", text, re.IGNORECASE)
        if not opened or not opened.group(1):
            index += 1
            continue
        close = index + 1
        while close < len(lines) and not re.fullmatch(r":::\s*(?:\r?\n)?", lines[close]):
            close += 1
        if close == len(lines):
            diagnostics.append(Diagnostic("error", f"Unclosed ::: {opened.group(1)} block", line=_line_number(source, absolute_start + offsets[index])))
            index += 1
            continue
        header_start = offsets[index]
        body_start = header_start + len(lines[index])
        close_start = offsets[close]
        end = close_start + len(lines[close])
        blocks.append(_Block(
            opened.group(1).lower(), parse_attributes(opened.group(2) or ""),
            raw[body_start:close_start].removesuffix("\n").removesuffix("\r"),
            SourceRange(absolute_start + header_start, absolute_start + end, absolute_start + body_start, absolute_start + body_start, absolute_start + close_start),
            header_start, end,
        ))
        index = close + 1
    return blocks


def _image(markdown: str) -> Image | None:
    match = _IMAGE.fullmatch(markdown.strip())
    return Image(match.group(1), match.group(2), match.group(3) or "", parse_attributes(match.group(4) or "")) if match else None


def _video(attrs: Attributes) -> Video | None:
    if attrs.values.get("type") != "video":
        return None
    values = attrs.values
    return Video(values.get("src", ""), values.get("poster", ""), values.get("fit", "contain"), values.get("controls") != "false", values.get("autoplay") == "true", values.get("loop") == "true", values.get("muted") == "true")


def _section(source: str, source_range: SourceRange, index: int, diagnostics: list[Diagnostic]) -> Section | None:
    raw = source[source_range.start:source_range.end]
    heading = _HEADING.match(raw)
    if not heading:
        return None
    title = heading.group(2).strip()
    attribute_match = _ATTRIBUTES.search(title)
    if not attribute_match:
        return None
    attrs = parse_attributes(attribute_match.group(1))
    if "section" not in attrs.classes:
        return None
    title = title[:attribute_match.start()].strip() or "Untitled section"
    identifier = attrs.id or f"section-{index + 1}"
    if not attrs.id:
        diagnostics.append(Diagnostic("warning", f"Section '{title}' has no stable source ID"))
    if raw[heading.end():].strip():
        diagnostics.append(Diagnostic("warning", f"Content beneath section '{title}' is not presented"))
    heading_text = heading.group(0).rstrip("\r\n")
    return Section("section", index, identifier, title, attrs, raw, source_range, SourceRange(source_range.start + heading.start(), source_range.start + heading.start() + len(heading_text)), heading.group(1), "trash" in attrs.classes)


def _ordinary_ranges(raw: str, blocks: list[_Block], absolute_start: int) -> list[SourceRange]:
    result: list[SourceRange] = []
    cursor = 0
    for start, end in sorted([(block.local_start, block.local_end) for block in blocks] + [(len(raw), len(raw))]):
        segment = raw[cursor:start]
        if segment.strip():
            leading = len(segment) - len(segment.lstrip())
            trailing = len(segment.rstrip())
            result.append(SourceRange(absolute_start + cursor + leading, absolute_start + cursor + trailing))
        cursor = max(cursor, end)
    return result


def _slide(source: str, source_range: SourceRange, index: int, diagnostics: list[Diagnostic]) -> Slide:
    raw = source[source_range.start:source_range.end]
    heading = _HEADING.match(raw)
    title = title_source = ""
    title_range = heading_range = None
    attrs = Attributes()
    content_start = source_range.start
    if heading:
        heading_text = heading.group(2).strip()
        attribute_match = _ATTRIBUTES.search(heading_text)
        if attribute_match:
            attrs = parse_attributes(attribute_match.group(1))
            heading_text = heading_text[:attribute_match.start()].strip()
        title = heading_text
        clean_heading = heading.group(0).rstrip("\r\n")
        heading_range = SourceRange(source_range.start + heading.start(), source_range.start + heading.start() + len(clean_heading))
        title_lines = [f"{heading.group(1)} {heading_text}"]
        title_end = heading.end()
        scan = heading.end()
        pending = ""
        while scan < len(raw):
            line_match = re.match(r"[^\r\n]*(?:\r?\n|$)", raw[scan:])
            line = line_match.group(0) if line_match else ""
            if not line:
                break
            text = line.rstrip("\r\n")
            if not text.strip():
                pending += line
            elif re.match(r"^\s*#{1,6}\s+\S", text):
                if pending:
                    title_lines.extend([""] * max(1, pending.count("\n")))
                title_lines.append(text.strip())
                title_end = scan + len(line)
                pending = ""
            else:
                break
            scan += len(line)
        title_range = SourceRange(source_range.start + heading.start(), source_range.start + title_end)
        title_source = "\n".join(title_lines)
        content_start = source_range.start + title_end
    layout_class = next((name for name in attrs.classes if name.startswith("layout-")), None)
    layout = layout_class[7:] if layout_class else "1"
    if layout not in LAYOUTS:
        diagnostics.append(Diagnostic("warning", f"Unknown layout '{layout}', using 1", slide=index + 1))
        layout = "1"
    body = source[content_start:source_range.end]
    blocks = _blocks(body, content_start, diagnostics, source)
    cells: list[Cell] = []
    overlays: list[Overlay] = []
    footer = None
    notes = ""
    notes_range = None
    for block in blocks:
        image = _image(block.body)
        video = _video(block.attrs)
        if block.name in CELL_NAMES:
            cells.append(Cell(block.name, "video" if video else "image" if image else "markdown", block.body, image, video, block.range, block.attrs, _font_size(block.attrs.values.get("font-size", "0.72"))))
        elif block.name == "overlay":
            overlay_type = block.attrs.values.get("type", "image" if image else "markdown")
            identifier = block.attrs.id or f"overlay-{index + 1}-{len(overlays) + 1}"
            if not block.attrs.id:
                diagnostics.append(Diagnostic("warning", f"Overlay '{identifier}' has no stable source ID", slide=index + 1))
            values = block.attrs.values
            arrow = None
            if overlay_type == "arrow":
                arrow = {"x1": _number(values.get("x1"), 25), "y1": _number(values.get("y1"), 50), "x2": _number(values.get("x2"), 75), "y2": _number(values.get("y2"), 50), "heads": values.get("heads", "end")}
                if all(math.isfinite(arrow[name]) for name in ("x1", "y1", "x2", "y2")):
                    x, y = max(0, min(arrow["x1"], arrow["x2"]) - 1), max(0, min(arrow["y1"], arrow["y2"]) - 1)
                    width = min(100, max(arrow["x1"], arrow["x2"]) + 1) - x
                    height = min(100, max(arrow["y1"], arrow["y2"]) + 1) - y
                else:
                    x = y = width = height = math.nan
                geometry = {"x": x, "y": y, "w": width, "h": height, "z": _number(values.get("z"), len(overlays) + 10)}
            else:
                geometry = {name: _number(values.get(name), default) for name, default in (("x", 10), ("y", 20), ("w", 30), ("h", 15), ("z", len(overlays) + 10))}
            shape = values.get("shape", "rectangle")
            shape_parameters = {"startAngle": _number(values.get("start-angle"), 0), "endAngle": _number(values.get("end-angle"), 180), "heads": values.get("heads", "none")} if shape == "arc" else None
            overlays.append(Overlay(identifier, overlay_type, block.body, image, video, block.attrs, block.range, geometry, _font_size(values.get("font-size")), _number(values.get("rotation"), 0), values.get("color"), values.get("align", "center" if overlay_type in ("equation", "shape") else "left"), _number(values["fragment"]) if values.get("fragment") else None, values.get("locked") == "true", shape, values.get("fill"), values.get("stroke"), _number(values.get("stroke-width"), 2), values.get("stroke-style", "solid"), values.get("shadow") == "true", shape_parameters, arrow))
        elif block.name == "footer":
            footer = (block.body, block.range)
        elif block.name == "notes":
            notes, notes_range = block.body, block.range
        else:
            diagnostics.append(Diagnostic("warning", f"Unknown directive '{block.name}'", slide=index + 1))
    ordinary_parts = []
    cursor = 0
    for block in sorted(blocks, key=lambda item: item.local_start):
        ordinary_parts.append(body[cursor:block.local_start])
        cursor = block.local_end
    ordinary_parts.append(body[cursor:])
    ordinary = "".join(ordinary_parts).strip()
    if ordinary:
        ordinary_range = SourceRange(content_start, source_range.end, content_start, content_start, source_range.end) if not blocks else None
        cells.insert(0, Cell("core", "markdown", ordinary, None, None, ordinary_range, Attributes(), 0.72, [ordinary_range] if ordinary_range else _ordinary_ranges(body, blocks, content_start)))
    if not cells and layout not in ("0", "free"):
        cells.append(Cell("core", "markdown", "", None, None, None, Attributes(), 0.72))
    _validate_objects(cells, overlays, index, diagnostics)
    return Slide("slide", index, attrs.id or f"slide-{index + 1}", title, raw, source_range, heading_range, title_range, title_source, attrs, "trashed" in attrs.classes, layout, _ratio(attrs.values.get("columns")), _ratio(attrs.values.get("rows")), cells, overlays, footer, notes, notes_range)


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    return list(dict.fromkeys(value for value in values if value in seen or seen.add(value)))


def _validate_objects(cells: list[Cell], overlays: list[Overlay], index: int, diagnostics: list[Diagnostic]) -> None:
    for identifier in _duplicates([cell.id for cell in cells]):
        diagnostics.append(Diagnostic("error", f"Duplicate '{identifier}' cell", slide=index + 1))
    for cell in cells:
        if not math.isfinite(cell.font_size) or cell.font_size <= 0:
            diagnostics.append(Diagnostic("error", f"Cell '{cell.id}' has invalid font size", slide=index + 1))
    for identifier in _duplicates([overlay.id for overlay in overlays]):
        diagnostics.append(Diagnostic("error", f"Duplicate overlay ID '{identifier}'", slide=index + 1))
    for overlay in overlays:
        def error(message: str) -> None:
            diagnostics.append(Diagnostic("error", message, slide=index + 1))
        if any(not math.isfinite(value) for value in overlay.geometry.values()): error(f"Overlay '{overlay.id}' has invalid geometry")
        if not math.isfinite(overlay.font_size) or overlay.font_size <= 0: error(f"Overlay '{overlay.id}' has invalid font size")
        if not math.isfinite(overlay.rotation): error(f"Overlay '{overlay.id}' has invalid rotation")
        if overlay.alignment not in ("left", "center", "right"): error(f"Overlay '{overlay.id}' has invalid alignment")
        if overlay.type == "shape" and overlay.shape not in SHAPES: error(f"Overlay '{overlay.id}' has unknown shape '{overlay.shape}'")
        if overlay.shape == "arc" and (not overlay.shape_parameters or not math.isfinite(overlay.shape_parameters["startAngle"]) or not math.isfinite(overlay.shape_parameters["endAngle"])): error(f"Arc '{overlay.id}' has invalid angles")
        if overlay.shape == "arc" and overlay.shape_parameters and overlay.shape_parameters["heads"] not in ("none", "start", "end", "both"): error(f"Arc '{overlay.id}' has invalid arrowheads")
        if overlay.type in ("shape", "arrow") and (not math.isfinite(overlay.stroke_width) or overlay.stroke_width < 0): error(f"Overlay '{overlay.id}' has invalid stroke width")
        if overlay.type in ("shape", "arrow") and overlay.stroke_style not in ("solid", "dash", "dash-dot", "dotted"): error(f"Overlay '{overlay.id}' has invalid stroke style '{overlay.stroke_style}'")
        if overlay.type == "arrow" and (not overlay.arrow or any(not math.isfinite(overlay.arrow[name]) for name in ("x1", "y1", "x2", "y2"))): error(f"Arrow '{overlay.id}' has invalid endpoints")
        if overlay.type == "arrow" and overlay.arrow and overlay.arrow["heads"] not in ("none", "start", "end", "both"): error(f"Arrow '{overlay.id}' has invalid arrowheads")
        if overlay.type == "video" and (not overlay.video or not overlay.video.source): error(f"Video overlay '{overlay.id}' has no src")
        if overlay.color and not _COLOR.fullmatch(overlay.color): diagnostics.append(Diagnostic("warning", f"Overlay '{overlay.id}' has invalid text color '{overlay.color}'", slide=index + 1))


def parse_deck(source: str) -> Deck:
    """Parse presentation source without interpreting Markdown content."""
    diagnostics: list[Diagnostic] = []
    metadata, body_start = _front_matter(source, diagnostics)
    slides: list[Slide] = []
    sections: list[Section] = []
    items: list[Slide | Section] = []
    for source_range in _item_ranges(source, body_start):
        section = _section(source, source_range, len(sections), diagnostics)
        if section:
            sections.append(section)
            items.append(section)
        else:
            slide = _slide(source, source_range, len(slides), diagnostics)
            slides.append(slide)
            items.append(slide)
    active_section = None
    for item in items:
        if isinstance(item, Section):
            active_section = item
        elif active_section:
            active_section.slide_count += 1
    if metadata.get("theme") and str(metadata["theme"]) not in THEMES:
        diagnostics.append(Diagnostic("warning", f"Unknown deck theme '{metadata['theme']}', using scientific-light"))
    for slide in slides:
        theme = slide.heading_attrs.values.get("theme")
        if theme and theme not in THEMES:
            diagnostics.append(Diagnostic("warning", f"Unknown theme '{theme}', using the deck theme", slide=slide.index + 1))
        for name in ("background", "foreground"):
            color = slide.heading_attrs.values.get(name)
            if color and not _COLOR.fullmatch(color):
                diagnostics.append(Diagnostic("warning", f"Invalid {name} color '{color}', using the theme color", slide=slide.index + 1))
    if not slides:
        diagnostics.append(Diagnostic("error", "The deck contains no slides"))
    for identifier in _duplicates([slide.id for slide in slides]):
        diagnostics.append(Diagnostic("error", f"Duplicate slide ID '{identifier}'"))
    for identifier in _duplicates([section.id for section in sections]):
        diagnostics.append(Diagnostic("error", f"Duplicate section ID '{identifier}'"))
    return Deck(source, metadata, SourceRange(0, body_start), slides, sections, items, diagnostics)


__all__ = ["Attributes", "Cell", "Deck", "Diagnostic", "Image", "Overlay", "Section", "Slide", "SourceRange", "Video", "parse_attributes", "parse_deck"]
