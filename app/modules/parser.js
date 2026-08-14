import { SHAPES } from "./shapes.js";

const LAYOUTS = new Set(["1", "1-1", "1-2", "2-1", "0", "front", "free"]);
export const THEMES = ["scientific-light", "scientific-dark"];
const THEME_SET = new Set(THEMES);
const CELL_NAMES = new Set(["core", "left", "right", "top-left", "bottom-left", "top-right", "bottom-right"]);
const CELLS_BY_LAYOUT = {
  "1": ["core"],
  "1-1": ["left", "right"],
  "1-2": ["left", "top-right", "bottom-right"],
  "2-1": ["top-left", "bottom-left", "right"],
  "0": [],
  front: ["core"],
  free: [],
};

function largestLayoutCell(layout, columns, rows) {
  const [columnA, columnB] = columns;
  const [rowA, rowB] = rows;
  const areas = {
    left: columnA,
    right: columnB,
    "top-left": columnA * rowA / 100,
    "bottom-left": columnA * rowB / 100,
    "top-right": columnB * rowA / 100,
    "bottom-right": columnB * rowB / 100,
  };
  return (CELLS_BY_LAYOUT[layout] || []).reduce(
    (largest, cell) => largest === null || areas[cell] > areas[largest] ? cell : largest,
    null,
  );
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function parseAttributes(source = "") {
  const attrs = { classes: [], id: "", values: {} };
  const tokenPattern = /(?:[^\s"']+|"[^"]*"|'[^']*')+/g;
  for (const token of source.match(tokenPattern) || []) {
    if (token.startsWith(".")) attrs.classes.push(token.slice(1));
    else if (token.startsWith("#")) attrs.id = token.slice(1);
    else {
      const equals = token.indexOf("=");
      if (equals === -1) attrs.values[token] = "true";
      else {
        const key = token.slice(0, equals);
        let value = token.slice(equals + 1);
        if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
          value = value.slice(1, -1);
        }
        attrs.values[key] = value;
      }
    }
  }
  return attrs;
}

export function serializeAttributes(attrs) {
  const tokens = [];
  if (attrs.id) tokens.push(`#${attrs.id}`);
  for (const cls of attrs.classes || []) tokens.push(`.${cls}`);
  for (const [key, raw] of Object.entries(attrs.values || {})) {
    const value = String(raw);
    tokens.push(`${key}=${JSON.stringify(value)}`);
  }
  return tokens.join(" ");
}

function parseRatio(value, fallback = [50, 50]) {
  if (!value) return [...fallback];
  const numbers = value.trim().split(/[\s,/:]+/).map(Number);
  if (numbers.length !== 2 || numbers.some(number => !Number.isFinite(number) || number <= 0)) return [...fallback];
  const total = numbers[0] + numbers[1];
  return numbers.map(number => 100 * number / total);
}

function parseFontSize(value) {
  const match = /^([0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:em)?$/i.exec(String(value ?? "1").trim());
  return match ? Number(match[1]) : Number.NaN;
}

function splitFrontMatter(source, diagnostics) {
  if (!source.startsWith("---")) return { metadata: {}, bodyStart: 0, raw: "" };
  const match = /^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)/.exec(source);
  if (!match) {
    diagnostics.push({ level: "error", message: "Unclosed YAML front matter", line: 1 });
    return { metadata: {}, bodyStart: 0, raw: "" };
  }
  let metadata = {};
  try {
    metadata = window.jsyaml.load(match[1]) || {};
    if (typeof metadata !== "object" || Array.isArray(metadata)) throw new Error("Front matter must be a mapping");
  } catch (error) {
    diagnostics.push({ level: "error", message: `YAML: ${error.message}`, line: error.mark?.line + 2 || 1 });
  }
  return { metadata, bodyStart: match[0].length, raw: match[0] };
}

function splitSlides(source, start) {
  const body = source.slice(start);
  const separators = [];
  const pattern = /^\s*---\s*$/gm;
  let match;
  while ((match = pattern.exec(body))) separators.push({ start: start + match.index, end: start + pattern.lastIndex });
  const ranges = [];
  let cursor = start;
  for (const separator of separators) {
    const candidate = source.slice(cursor, separator.start);
    if (candidate.trim()) ranges.push({ start: cursor, end: separator.start });
    cursor = separator.end;
    if (source[cursor] === "\r") cursor += 1;
    if (source[cursor] === "\n") cursor += 1;
  }
  if (source.slice(cursor).trim()) ranges.push({ start: cursor, end: source.length });
  return ranges;
}

function parseSection(source, range, index, diagnostics) {
  const raw = source.slice(range.start, range.end);
  const heading = /^\s*(#{1,6})\s+([^\r\n]+)\r?\n?/.exec(raw);
  if (!heading) return null;
  let title = heading[2].trim();
  const attrMatch = /\s+\{([^}]*)\}\s*$/.exec(title);
  if (!attrMatch) return null;
  const attrs = parseAttributes(attrMatch[1]);
  if (!attrs.classes.includes("section")) return null;
  title = title.slice(0, attrMatch.index).trim() || "Untitled section";
  const id = attrs.id || `section-${index + 1}`;
  if (!attrs.id) diagnostics.push({ level: "warning", message: `Section '${title}' has no stable source ID` });
  if (raw.slice(heading[0].length).trim()) diagnostics.push({ level: "warning", message: `Content beneath section '${title}' is not presented` });
  return {
    kind: "section",
    index,
    id,
    title,
    attrs,
    raw,
    range,
    headingRange: { start: range.start + heading.index, end: range.start + heading.index + heading[0].replace(/\r?\n$/, "").length },
    hashes: heading[1],
  };
}

function lineNumber(source, offset) {
  return source.slice(0, offset).split(/\r?\n/).length;
}

function parseImage(markdown) {
  const trimmed = markdown.trim();
  const match = /^!\[([^\]]*)\]\(([^)\s]+)(?:\s+["']([^"']*)["'])?\)\s*(?:\{([^}]*)\})?\s*$/.exec(trimmed);
  if (!match) return null;
  return { alt: match[1], source: match[2], title: match[3] || "", attrs: parseAttributes(match[4] || "") };
}

function parseVideo(attrs) {
  if (attrs.values.type !== "video") return null;
  return {
    source: attrs.values.src || "",
    poster: attrs.values.poster || "",
    fit: attrs.values.fit || "contain",
    controls: attrs.values.controls !== "false",
    autoplay: attrs.values.autoplay === "true",
    loop: attrs.values.loop === "true",
    muted: attrs.values.muted === "true",
  };
}

function parseDirectiveBlocks(raw, absoluteStart, diagnostics, source) {
  const lines = raw.split(/(?<=\n)/);
  const blocks = [];
  const occupied = [];
  let localOffset = 0;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const text = line.replace(/\r?\n$/, "");
    const open = /^:::\s*([a-z][a-z0-9-]*)?\s*(?:\{([^}]*)\})?\s*$/i.exec(text);
    if (!open || !open[1]) {
      localOffset += line.length;
      continue;
    }
    const headerStart = localOffset;
    const bodyStart = localOffset + line.length;
    let scanOffset = bodyStart;
    let closeIndex = -1;
    for (let cursor = index + 1; cursor < lines.length; cursor += 1) {
      if (/^:::\s*(?:\r?\n)?$/.test(lines[cursor])) {
        closeIndex = cursor;
        break;
      }
      scanOffset += lines[cursor].length;
    }
    if (closeIndex === -1) {
      diagnostics.push({
        level: "error",
        message: `Unclosed ::: ${open[1]} block`,
        line: lineNumber(source, absoluteStart + headerStart),
      });
      localOffset += line.length;
      continue;
    }
    const closeStart = scanOffset;
    const end = closeStart + lines[closeIndex].length;
    blocks.push({
      name: open[1].toLowerCase(),
      attrs: parseAttributes(open[2] || ""),
      body: raw.slice(bodyStart, closeStart).replace(/\r?\n$/, ""),
      range: {
        start: absoluteStart + headerStart,
        headerEnd: absoluteStart + bodyStart,
        bodyStart: absoluteStart + bodyStart,
        bodyEnd: absoluteStart + closeStart,
        end: absoluteStart + end,
      },
    });
    occupied.push([headerStart, end]);
    for (let cursor = index; cursor <= closeIndex; cursor += 1) localOffset += lines[cursor].length;
    index = closeIndex;
  }
  return { blocks, occupied };
}

function removeRanges(raw, ranges) {
  let result = raw;
  for (const [start, end] of [...ranges].sort((a, b) => b[0] - a[0])) {
    result = result.slice(0, start) + result.slice(end);
  }
  return result.trim();
}

function ordinarySourceRanges(raw, occupied, absoluteStart) {
  const ranges = [];
  let cursor = 0;
  for (const [start, end] of [...occupied, [raw.length, raw.length]].sort((left, right) => left[0] - right[0])) {
    const segment = raw.slice(cursor, start);
    const first = segment.search(/\S/);
    if (first >= 0) {
      const last = segment.search(/\s*$/);
      ranges.push({ start: absoluteStart + cursor + first, end: absoluteStart + cursor + last });
    }
    cursor = Math.max(cursor, end);
  }
  return ranges;
}

function parseSlide(source, range, index, diagnostics) {
  const raw = source.slice(range.start, range.end);
  let contentStart = range.start;
  let title = "";
  let headingRange = null;
  let headingAttrs = parseAttributes("");
  const heading = /^\s*(#{1,6})\s+([^\r\n]+)\r?\n?/.exec(raw);
  let titleRange = null;
  let titleSource = "";
  if (heading) {
    let headingText = heading[2].trim();
    const attrMatch = /\s+\{([^}]*)\}\s*$/.exec(headingText);
    if (attrMatch) {
      headingAttrs = parseAttributes(attrMatch[1]);
      headingText = headingText.slice(0, attrMatch.index).trim();
    }
    title = headingText;
    headingRange = { start: range.start + heading.index, end: range.start + heading.index + heading[0].replace(/\r?\n$/, "").length };
    const titleLines = [`${heading[1]} ${headingText}`];
    let titleEnd = heading[0].length;
    let scan = heading[0].length;
    let pendingWhitespace = "";
    while (scan < raw.length) {
      const line = /^[^\r\n]*(?:\r?\n|$)/.exec(raw.slice(scan))?.[0] || "";
      if (!line) break;
      const text = line.replace(/\r?\n$/, "");
      if (!text.trim()) pendingWhitespace += line;
      else if (/^\s*#{1,6}\s+\S/.test(text)) {
        if (pendingWhitespace) titleLines.push(...Array(pendingWhitespace.match(/\r?\n/g)?.length || 1).fill(""));
        titleLines.push(text.trim());
        titleEnd = scan + line.length;
        pendingWhitespace = "";
      } else break;
      scan += line.length;
    }
    titleRange = { start: range.start + heading.index, end: range.start + titleEnd };
    titleSource = titleLines.join("\n");
    contentStart = range.start + titleEnd;
  }
  const layoutClass = headingAttrs.classes.find(cls => cls.startsWith("layout-"));
  let layout = layoutClass ? layoutClass.slice(7) : "1";
  if (!LAYOUTS.has(layout)) {
    diagnostics.push({ level: "warning", slide: index + 1, message: `Unknown layout '${layout}', using 1` });
    layout = "1";
  }
  const bodyRaw = source.slice(contentStart, range.end);
  const parsed = parseDirectiveBlocks(bodyRaw, contentStart, diagnostics, source);
  const cells = [];
  const overlays = [];
  let footer = null;
  let notes = "";
  let notesRange = null;
  for (const block of parsed.blocks) {
    if (CELL_NAMES.has(block.name)) {
      const image = parseImage(block.body);
      const video = parseVideo(block.attrs);
      cells.push({ id: block.name, type: video ? "video" : image ? "image" : "markdown", source: block.body, image, video, range: block.range, attrs: block.attrs });
    } else if (block.name === "overlay") {
      const image = parseImage(block.body);
      const type = block.attrs.values.type || (image ? "image" : "markdown");
      const video = parseVideo(block.attrs);
      const id = block.attrs.id || `overlay-${index + 1}-${overlays.length + 1}`;
      if (!block.attrs.id) diagnostics.push({ level: "warning", slide: index + 1, message: `Overlay '${id}' has no stable source ID` });
      const alignment = block.attrs.values.align || (["equation", "shape"].includes(type) ? "center" : "left");
      const shape = block.attrs.values.shape || "rectangle";
      const arrow = type === "arrow" ? {
        x1: Number(block.attrs.values.x1 ?? 25),
        y1: Number(block.attrs.values.y1 ?? 50),
        x2: Number(block.attrs.values.x2 ?? 75),
        y2: Number(block.attrs.values.y2 ?? 50),
        heads: block.attrs.values.heads || "end",
      } : null;
      const arrowGeometry = arrow ? {
        x: Math.max(0, Math.min(arrow.x1, arrow.x2) - 1),
        y: Math.max(0, Math.min(arrow.y1, arrow.y2) - 1),
        w: Math.min(100, Math.max(arrow.x1, arrow.x2) + 1) - Math.max(0, Math.min(arrow.x1, arrow.x2) - 1),
        h: Math.min(100, Math.max(arrow.y1, arrow.y2) + 1) - Math.max(0, Math.min(arrow.y1, arrow.y2) - 1),
        z: Number(block.attrs.values.z ?? overlays.length + 10),
      } : null;
      overlays.push({
        id,
        type,
        source: block.body,
        image,
        video,
        attrs: block.attrs,
        range: block.range,
        geometry: arrowGeometry || {
          x: Number(block.attrs.values.x ?? 10),
          y: Number(block.attrs.values.y ?? 20),
          w: Number(block.attrs.values.w ?? 30),
          h: Number(block.attrs.values.h ?? 15),
          z: Number(block.attrs.values.z ?? overlays.length + 10),
        },
        fontSize: parseFontSize(block.attrs.values["font-size"]),
        color: block.attrs.values.color || null,
        alignment,
        fragment: block.attrs.values.fragment ? Number(block.attrs.values.fragment) : null,
        locked: block.attrs.values.locked === "true",
        shape,
        fill: block.attrs.values.fill || null,
        stroke: block.attrs.values.stroke || null,
        strokeWidth: Number(block.attrs.values["stroke-width"] ?? 2),
        shadow: block.attrs.values.shadow === "true",
        arrow,
      });
    } else if (block.name === "footer") footer = { source: block.body, range: block.range };
    else if (block.name === "notes") {
      notes = block.body;
      notesRange = block.range;
    }
    else diagnostics.push({ level: "warning", slide: index + 1, message: `Unknown directive '${block.name}'` });
  }
  const ordinary = removeRanges(bodyRaw, parsed.occupied);
  if (ordinary) {
    const ordinaryRange = parsed.occupied.length === 0
      ? { start: contentStart, headerEnd: contentStart, bodyStart: contentStart, bodyEnd: range.end, end: range.end }
      : null;
    const sourceRanges = ordinaryRange ? [ordinaryRange] : ordinarySourceRanges(bodyRaw, parsed.occupied, contentStart);
    cells.unshift({ id: "core", type: "markdown", source: ordinary, image: null, video: null, range: ordinaryRange, sourceRanges, attrs: parseAttributes("") });
  }
  if (!cells.length && !["0", "free"].includes(layout)) cells.push({ id: "core", type: "markdown", source: "", image: null, video: null, range: null, attrs: parseAttributes("") });
  const duplicateCells = cells.map(cell => cell.id).filter((id, position, all) => all.indexOf(id) !== position);
  for (const id of new Set(duplicateCells)) diagnostics.push({ level: "error", slide: index + 1, message: `Duplicate '${id}' cell` });
  const duplicateOverlays = overlays.map(overlay => overlay.id).filter((id, position, all) => all.indexOf(id) !== position);
  for (const id of new Set(duplicateOverlays)) diagnostics.push({ level: "error", slide: index + 1, message: `Duplicate overlay ID '${id}'` });
  for (const overlay of overlays) {
    const values = Object.values(overlay.geometry);
    if (values.some(value => !Number.isFinite(value))) diagnostics.push({ level: "error", slide: index + 1, message: `Overlay '${overlay.id}' has invalid geometry` });
    if (!Number.isFinite(overlay.fontSize) || overlay.fontSize <= 0) diagnostics.push({ level: "error", slide: index + 1, message: `Overlay '${overlay.id}' has invalid font size` });
    if (!["left", "center", "right"].includes(overlay.alignment)) diagnostics.push({ level: "error", slide: index + 1, message: `Overlay '${overlay.id}' has invalid alignment` });
    if (overlay.type === "shape" && !Object.hasOwn(SHAPES, overlay.shape)) diagnostics.push({ level: "error", slide: index + 1, message: `Overlay '${overlay.id}' has unknown shape '${overlay.shape}'` });
    if (["shape", "arrow"].includes(overlay.type) && (!Number.isFinite(overlay.strokeWidth) || overlay.strokeWidth < 0)) diagnostics.push({ level: "error", slide: index + 1, message: `Overlay '${overlay.id}' has invalid stroke width` });
    if (overlay.type === "arrow" && (!overlay.arrow || [overlay.arrow.x1, overlay.arrow.y1, overlay.arrow.x2, overlay.arrow.y2].some(value => !Number.isFinite(value)))) diagnostics.push({ level: "error", slide: index + 1, message: `Arrow '${overlay.id}' has invalid endpoints` });
    if (overlay.type === "arrow" && !["none", "start", "end", "both"].includes(overlay.arrow?.heads)) diagnostics.push({ level: "error", slide: index + 1, message: `Arrow '${overlay.id}' has invalid arrowheads` });
    if (overlay.type === "video" && !overlay.video?.source) diagnostics.push({ level: "error", slide: index + 1, message: `Video overlay '${overlay.id}' has no src` });
    if (overlay.color && !/^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i.test(overlay.color)) diagnostics.push({ level: "warning", slide: index + 1, message: `Overlay '${overlay.id}' has invalid text color '${overlay.color}'` });
  }
  return {
    kind: "slide",
    index,
    id: headingAttrs.id || `slide-${index + 1}`,
    title,
    raw,
    range,
    headingRange,
    titleRange,
    titleSource,
    headingAttrs,
    layout,
    columns: parseRatio(headingAttrs.values.columns),
    rows: parseRatio(headingAttrs.values.rows),
    cells,
    overlays,
    footer,
    notes,
    notesRange,
  };
}

export function parseDeck(source) {
  const diagnostics = [];
  const front = splitFrontMatter(source, diagnostics);
  const ranges = splitSlides(source, front.bodyStart);
  const slides = [];
  const sections = [];
  const items = ranges.map(range => {
    const section = parseSection(source, range, sections.length, diagnostics);
    if (section) {
      sections.push(section);
      return section;
    }
    const slide = parseSlide(source, range, slides.length, diagnostics);
    slides.push(slide);
    return slide;
  });
  let activeSection = null;
  for (const item of items) {
    if (item.kind === "section") {
      activeSection = item;
      activeSection.slideCount = 0;
    } else if (activeSection) activeSection.slideCount += 1;
  }
  if (front.metadata.theme && !THEME_SET.has(String(front.metadata.theme))) diagnostics.push({ level: "warning", message: `Unknown deck theme '${front.metadata.theme}', using scientific-light` });
  for (const slide of slides) {
    const theme = slide.headingAttrs.values.theme;
    if (theme && !THEME_SET.has(theme)) diagnostics.push({ level: "warning", slide: slide.index + 1, message: `Unknown theme '${theme}', using the deck theme` });
    for (const name of ["background", "foreground"]) {
      const color = slide.headingAttrs.values[name];
      if (color && !/^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i.test(color)) diagnostics.push({ level: "warning", slide: slide.index + 1, message: `Invalid ${name} color '${color}', using the theme color` });
    }
  }
  if (!slides.length) diagnostics.push({ level: "error", message: "The deck contains no slides" });
  const slideIds = slides.map(slide => slide.id);
  for (const id of new Set(slideIds.filter((value, index) => slideIds.indexOf(value) !== index))) {
    diagnostics.push({ level: "error", message: `Duplicate slide ID '${id}'` });
  }
  const sectionIds = sections.map(section => section.id);
  for (const id of new Set(sectionIds.filter((value, index) => sectionIds.indexOf(value) !== index))) {
    diagnostics.push({ level: "error", message: `Duplicate section ID '${id}'` });
  }
  return { source, metadata: front.metadata, frontMatterRange: { start: 0, end: front.bodyStart }, slides, sections, items, diagnostics };
}

export function patchRange(source, start, end, replacement) {
  return source.slice(0, start) + replacement + source.slice(end);
}

function normalizeSlideSpacing(source) {
  let normalized = source.trimEnd();
  if (!normalized) return "";
  const slide = parseSlide(normalized, { start: 0, end: normalized.length }, 0, []);
  const contentStart = slide.titleRange?.end || 0;
  const blocks = parseDirectiveBlocks(normalized.slice(contentStart), contentStart, [], normalized).blocks;
  const edits = [];
  if (blocks.length && slide.titleRange) {
    const gap = normalized.slice(slide.titleRange.end, blocks[0].range.start);
    if (!gap.trim()) edits.push({ start: slide.titleRange.end, end: blocks[0].range.start, replacement: "\n" });
  }
  for (let index = 1; index < blocks.length; index += 1) {
    const previous = blocks[index - 1];
    const current = blocks[index];
    const gap = normalized.slice(previous.range.end, current.range.start);
    if (!gap.trim()) edits.push({ start: previous.range.end, end: current.range.start, replacement: "\n" });
  }
  for (const edit of edits.sort((left, right) => right.start - left.start)) {
    normalized = patchRange(normalized, edit.start, edit.end, edit.replacement);
  }
  return `${normalized.trimEnd()}\n`;
}

function sourceNewline(source) {
  return source.includes("\r\n") ? "\r\n" : "\n";
}

function normalizeMarkdownSpacing(source, newline) {
  const output = [];
  let pendingBlank = false;
  let fence = null;
  for (const line of String(source).split(/\r?\n/)) {
    if (fence) {
      output.push(line);
      const close = /^ {0,3}(`{3,}|~{3,})[ \t]*$/.exec(line);
      if (close && close[1][0] === fence.character && close[1].length >= fence.length) fence = null;
      continue;
    }
    if (!line.trim()) {
      pendingBlank = output.length > 0;
      continue;
    }
    if (pendingBlank) output.push("");
    pendingBlank = false;
    output.push(line);
    const open = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (open) fence = { character: open[1][0], length: open[1].length };
  }
  return output.join(newline);
}

function normalizeSlide(slide, newline) {
  const raw = slide.raw;
  const local = offset => offset - slide.range.start;
  const title = slide.titleRange
    ? raw.slice(local(slide.titleRange.start), local(slide.titleRange.end)).replace(/(?:\r?\n)+$/, "").replace(/^(?:[ \t]*\r?\n)+/, "")
    : "";
  const bodyStart = slide.titleRange ? local(slide.titleRange.end) : 0;
  const body = raw.slice(bodyStart);
  const blocks = parseDirectiveBlocks(body, bodyStart, [], raw).blocks;
  const allowedCells = new Set(CELLS_BY_LAYOUT[slide.layout] || ["core"]);
  const keepOrdinary = allowedCells.has("core");
  const objects = [];
  let cursor = 0;
  for (const block of blocks) {
    const start = block.range.start - bodyStart;
    const end = block.range.end - bodyStart;
    const ordinary = normalizeMarkdownSpacing(body.slice(cursor, start), newline);
    if (keepOrdinary && ordinary) objects.push(ordinary);
    if (!CELL_NAMES.has(block.name) || allowedCells.has(block.name)) {
      objects.push(body.slice(start, end).replace(/\r?\n$/, ""));
    }
    cursor = end;
  }
  const ordinary = normalizeMarkdownSpacing(body.slice(cursor), newline);
  if (keepOrdinary && ordinary) objects.push(ordinary);
  return [title, ...objects].filter(Boolean).join(`${newline}${newline}`);
}

export function normalizeDeck(value) {
  const deck = typeof value === "string" ? parseDeck(value) : value;
  if (!deck?.source) throw new Error("Cannot normalize an empty presentation");
  const fatal = deck.diagnostics.find(item => item.level === "error");
  if (fatal) throw new Error(fatal.message);
  const newline = sourceNewline(deck.source);
  const frontMatter = deck.source.slice(0, deck.frontMatterRange.end).trim();
  const items = deck.items.map(item => item.kind === "slide"
    ? normalizeSlide(item, newline)
    : normalizeMarkdownSpacing(item.raw, newline));
  const separator = `${newline}${newline}---${newline}${newline}`;
  const body = items.filter(Boolean).join(separator);
  return `${frontMatter}${frontMatter && body ? `${newline}${newline}` : ""}${body}${newline}`;
}

function composeItems(deck, itemSources) {
  const frontMatter = deck.source.slice(0, deck.frontMatterRange.end).trimEnd();
  const body = itemSources.map(source => source.trim()).join("\n\n---\n\n");
  return `${frontMatter}${frontMatter ? "\n\n" : ""}${body}\n`;
}

const itemSources = deck => deck.items.map(item => item.raw);
const slideItemPosition = (deck, slideIndex) => deck.items.findIndex(item => item.kind === "slide" && item.index === slideIndex);
const sectionItemPosition = (deck, sectionId) => deck.items.findIndex(item => item.kind === "section" && item.id === sectionId);

function duplicateSlideSource(deck, slide) {
  if (!slide.headingAttrs.id || !slide.headingRange) return slide.raw;
  const usedIds = new Set(deck.slides.map(item => item.id));
  const base = `${slide.headingAttrs.id}-copy`;
  let id = base;
  let counter = 2;
  while (usedIds.has(id)) id = `${base}-${counter++}`;
  const attrs = structuredClone(slide.headingAttrs);
  attrs.id = id;
  const hashes = slide.raw.match(/^\s*(#{1,6})/)?.[1] || "##";
  const heading = `${hashes} ${slide.title} {${serializeAttributes(attrs)}}`;
  return patchRange(
    slide.raw,
    slide.headingRange.start - slide.range.start,
    slide.headingRange.end - slide.range.start,
    heading,
  );
}

function blankSlideSource(slide) {
  const attrs = structuredClone(slide.headingAttrs);
  attrs.id = "";
  const hashes = slide.raw.match(/^\s*(#{1,6})/)?.[1] || "##";
  const attributes = serializeAttributes(attrs);
  const cells = (CELLS_BY_LAYOUT[slide.layout] || ["core"])
    .map(name => `::: ${name}\n:::`)
    .join("\n\n");
  return `${hashes} New slide${attributes ? ` {${attributes}}` : ""}${cells ? `\n\n${cells}` : ""}`;
}

export function insertSlide(deck, slideIndex) {
  const slide = deck.slides[slideIndex];
  if (!slide) throw new Error("Unknown slide format to copy");
  const sources = itemSources(deck);
  sources.splice(slideItemPosition(deck, slideIndex) + 1, 0, blankSlideSource(slide));
  return composeItems(deck, sources);
}

export function moveSlide(deck, slideIndex, direction) {
  if (!deck.slides[slideIndex]) throw new Error("Unknown slide to move");
  const position = slideItemPosition(deck, slideIndex);
  const destination = position + Math.sign(direction);
  if (destination < 0 || destination >= deck.items.length) return deck.source;
  const sources = itemSources(deck);
  [sources[position], sources[destination]] = [sources[destination], sources[position]];
  return composeItems(deck, sources);
}

export function duplicateSlide(deck, slideIndex) {
  const slide = deck.slides[slideIndex];
  if (!slide) throw new Error("Unknown slide to duplicate");
  const sources = itemSources(deck);
  sources.splice(slideItemPosition(deck, slideIndex) + 1, 0, duplicateSlideSource(deck, slide));
  return composeItems(deck, sources);
}

export function importSlide(deck, slideIndex, importedSlide) {
  if (!importedSlide?.raw) throw new Error("Unknown slide to import");
  let source = importedSlide.raw;
  if (importedSlide.headingAttrs?.id && deck.slides.some(slide => slide.id === importedSlide.id)) {
    source = duplicateSlideSource(deck, importedSlide);
  }
  const sources = itemSources(deck);
  sources.splice(slideItemPosition(deck, slideIndex) + 1, 0, source);
  return composeItems(deck, sources);
}

export function deleteSlide(deck, slideIndex) {
  if (!deck.slides[slideIndex]) throw new Error("Unknown slide to delete");
  if (deck.slides.length === 1) throw new Error("A presentation must contain at least one slide");
  return composeItems(deck, deck.items.filter(item => item.kind !== "slide" || item.index !== slideIndex).map(item => item.raw));
}

export function insertSection(deck, slideIndex, title = "New section") {
  const position = slideItemPosition(deck, slideIndex);
  if (position < 0) throw new Error("Unknown slide for section insertion");
  const normalized = String(title).trim();
  if (!normalized || /[\r\n{}]/.test(normalized)) throw new Error("Section names must be a single nonempty line without braces");
  const base = normalized.toLocaleLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "section";
  const usedIds = new Set([...deck.slides.map(slide => slide.id), ...deck.sections.map(section => section.id)]);
  let id = base;
  let counter = 2;
  while (usedIds.has(id)) id = `${base}-${counter++}`;
  const sources = itemSources(deck);
  sources.splice(position, 0, `# ${normalized} {#${id} .section}`);
  return composeItems(deck, sources);
}

export function updateSectionTitle(deck, sectionId, title) {
  const section = deck.sections.find(item => item.id === sectionId);
  const normalized = String(title).trim();
  if (!section || !normalized || /[\r\n{}]/.test(normalized)) throw new Error("Section names must be a single nonempty line without braces");
  const replacement = `${section.hashes} ${normalized} {${serializeAttributes(section.attrs)}}`;
  return patchRange(deck.source, section.headingRange.start, section.headingRange.end, replacement);
}

export function moveSection(deck, sectionId, direction) {
  const position = sectionItemPosition(deck, sectionId);
  const destination = position + Math.sign(direction);
  if (position < 0) throw new Error(`Unknown section '${sectionId}'`);
  if (destination < 0 || destination >= deck.items.length) return deck.source;
  const sources = itemSources(deck);
  [sources[position], sources[destination]] = [sources[destination], sources[position]];
  return composeItems(deck, sources);
}

export function deleteSection(deck, sectionId) {
  const position = sectionItemPosition(deck, sectionId);
  if (position < 0) throw new Error(`Unknown section '${sectionId}'`);
  return composeItems(deck, deck.items.filter((_, index) => index !== position).map(item => item.raw));
}

export function updateHeadingLayout(deck, slideIndex, layout, columns, rows) {
  const slide = deck.slides[slideIndex];
  if (!slide?.headingRange) throw new Error("A layout requires a slide heading");
  const attrs = structuredClone(slide.headingAttrs);
  attrs.classes = attrs.classes.filter(cls => !cls.startsWith("layout-"));
  attrs.classes.push(`layout-${layout}`);
  if (["1-1", "1-2", "2-1"].includes(layout)) attrs.values.columns = columns.map(value => Math.round(value * 10) / 10).join(" ");
  else delete attrs.values.columns;
  if (["1-2", "2-1"].includes(layout)) attrs.values.rows = rows.map(value => Math.round(value * 10) / 10).join(" ");
  else delete attrs.values.rows;
  const hashes = slide.raw.match(/^\s*(#{1,6})/)?.[1] || "##";
  const heading = `${hashes} ${slide.title} {${serializeAttributes(attrs)}}`;
  const allowedCells = new Set(CELLS_BY_LAYOUT[layout] || ["core"]);
  const core = slide.layout === "1" && ["1-1", "1-2", "2-1"].includes(layout)
    ? slide.cells.find(cell => cell.id === "core")
    : null;
  const coreDestination = core ? largestLayoutCell(layout, columns, rows) : null;
  const coreRanges = new Set(core ? (core.range ? [core.range] : core.sourceRanges || []) : []);
  const removals = slide.cells
    .filter(cell => !allowedCells.has(cell.id))
    .flatMap(cell => cell.range ? [cell.range] : (cell.sourceRanges || []))
    .filter(range => !coreRanges.has(range));
  const coreEdits = [];
  if (coreDestination && core.range) {
    const header = deck.source.slice(core.range.start, core.range.headerEnd)
      .replace(/^(\s*:::\s*)core\b/i, `$1${coreDestination}`);
    coreEdits.push({ start: core.range.start, end: core.range.headerEnd, replacement: header });
  } else if (coreDestination && core.sourceRanges?.length) {
    const [first, ...rest] = core.sourceRanges;
    coreEdits.push({ start: first.start, end: first.end, replacement: directiveBlock(coreDestination, core.source) });
    coreEdits.push(...rest.map(range => ({ start: range.start, end: range.end, replacement: "" })));
  }
  const edits = [
    { start: slide.headingRange.start, end: slide.headingRange.end, replacement: heading },
    ...coreEdits,
    ...removals.map(range => ({ start: range.start, end: range.end, replacement: "" })),
  ].sort((left, right) => right.start - left.start);
  let source = slide.raw;
  for (const edit of edits) {
    source = patchRange(source, edit.start - slide.range.start, edit.end - slide.range.start, edit.replacement);
  }
  return patchRange(deck.source, slide.range.start, slide.range.end, normalizeSlideSpacing(source));
}

export function updateSlideProperties(deck, slideIndex, changes) {
  const slide = deck.slides[slideIndex];
  if (!slide?.headingRange) throw new Error("Slide properties require a heading");
  const attrs = structuredClone(slide.headingAttrs);
  for (const [key, value] of Object.entries(changes)) {
    if (value === null || value === "") delete attrs.values[key];
    else attrs.values[key] = String(value);
  }
  const hashes = slide.raw.match(/^\s*(#{1,6})/)?.[1] || "##";
  const attributes = serializeAttributes(attrs);
  const replacement = `${hashes} ${slide.title}${attributes ? ` {${attributes}}` : ""}`;
  return patchRange(deck.source, slide.headingRange.start, slide.headingRange.end, replacement);
}

export function updateSlideTitle(deck, slideIndex, title) {
  const slide = deck.slides[slideIndex];
  if (!slide?.headingRange) throw new Error("This slide has no title heading; add one in Source mode first");
  const attributes = serializeAttributes(slide.headingAttrs);
  const lines = String(title).trim().split(/\r?\n/).map(line => line.trim());
  if (!lines.some(Boolean)) lines.splice(0, lines.length, "## ---");
  if (lines.some(line => line && !/^#{1,6}\s+\S/.test(line))) throw new Error("Each non-empty title line must be a Markdown heading beginning with #");
  lines[0] = lines[0].replace(/\s+\{[^}]*\}\s*$/, "");
  if (attributes) lines[0] += ` {${attributes}}`;
  const trailing = /^[ \t]*(?:\r?\n[ \t]*)*/.exec(deck.source.slice(slide.titleRange.end, slide.range.end))?.[0] || "";
  const hasFollowingContent = slide.titleRange.end + trailing.length < slide.range.end;
  const replacement = `${lines.join("\n")}\n${hasFollowingContent ? "\n" : ""}`;
  return patchRange(deck.source, slide.titleRange.start, slide.titleRange.end + trailing.length, replacement);
}

export function updateOverlay(deck, slideIndex, objectId, changes) {
  const overlay = deck.slides[slideIndex]?.overlays.find(item => item.id === objectId);
  if (!overlay) throw new Error(`Unknown overlay '${objectId}'`);
  const attrs = structuredClone(overlay.attrs);
  attrs.id = objectId;
  for (const [key, value] of Object.entries(changes)) {
    if (value === null || value === "" || value === false) delete attrs.values[key];
    else attrs.values[key] = typeof value === "number" ? String(Math.round(value * 10) / 10) : String(value);
  }
  const replacement = `::: overlay {${serializeAttributes(attrs)}}\n`;
  return patchRange(deck.source, overlay.range.start, overlay.range.headerEnd, replacement);
}

export function updateBlockContent(deck, slideIndex, objectId, content) {
  const slide = deck.slides[slideIndex];
  const overlay = slide?.overlays.find(item => item.id === objectId);
  const cell = slide?.cells.find(item => item.id === objectId && item.range);
  const target = overlay || cell;
  if (!target?.range) throw new Error(`Cannot edit '${objectId}'`);
  const trimmed = String(content).trim();
  const normalized = trimmed ? `${trimmed}\n` : "";
  return patchRange(deck.source, target.range.bodyStart, target.range.bodyEnd, normalized);
}

function appendBlock(deck, slide, block) {
  const trailingStart = slide.range.start + slide.raw.trimEnd().length;
  const separator = slide.raw.trim() ? "\n\n" : "";
  return patchRange(deck.source, trailingStart, slide.range.end, `${separator}${block}\n`);
}

function directiveBlock(name, content, attributes = "") {
  const body = String(content).trim();
  return `::: ${name}${attributes}\n${body}${body ? "\n" : ""}:::`;
}

export function setCellContent(deck, slideIndex, cellId, content) {
  const slide = deck.slides[slideIndex];
  const cell = slide?.cells.find(item => item.id === cellId);
  if (cell?.range) return updateBlockContent(deck, slideIndex, cellId, content);
  if (cell?.sourceRanges?.length) {
    if (String(content).trim()) throw new Error(`Cannot edit mixed '${cellId}' content outside Source mode`);
    let source = deck.source;
    for (const range of [...cell.sourceRanges].sort((left, right) => right.start - left.start)) {
      source = patchRange(source, range.start, range.end, "");
    }
    return source;
  }
  return appendBlock(deck, slide, directiveBlock(cellId, content));
}

export function updateSlideNotes(deck, slideIndex, content) {
  const slide = deck.slides[slideIndex];
  if (!slide) throw new Error("Unknown slide");
  const notes = String(content).trim();
  if (!slide.notesRange) return notes ? appendBlock(deck, slide, directiveBlock("notes", notes)) : deck.source;
  if (!notes) {
    const source = patchRange(slide.raw, slide.notesRange.start - slide.range.start, slide.notesRange.end - slide.range.start, "");
    return patchRange(deck.source, slide.range.start, slide.range.end, normalizeSlideSpacing(source));
  }
  return patchRange(deck.source, slide.notesRange.bodyStart, slide.notesRange.bodyEnd, `${notes}\n`);
}

export function insertOverlay(deck, slideIndex, { type, content, id, x = 35, y = 30, w = 30, h = 15, attributes = {} }) {
  const slide = deck.slides[slideIndex];
  const safeId = id.replace(/[^a-zA-Z0-9_-]/g, "-");
  const extra = Object.entries(attributes).map(([key, value]) => ` ${key}=${JSON.stringify(value)}`).join("");
  const attrs = ` {#${safeId} type=${JSON.stringify(type)} x="${x}" y="${y}" w="${w}" h="${h}"${extra}}`;
  return appendBlock(deck, slide, directiveBlock("overlay", content, attrs));
}

export function insertArrow(deck, slideIndex, { id, x1 = 25, y1 = 50, x2 = 75, y2 = 50, attributes = {} }) {
  const slide = deck.slides[slideIndex];
  const safeId = id.replace(/[^a-zA-Z0-9_-]/g, "-");
  const extra = Object.entries(attributes).map(([key, value]) => ` ${key}=${JSON.stringify(value)}`).join("");
  const attrs = ` {#${safeId} type="arrow" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"${extra}}`;
  return appendBlock(deck, slide, directiveBlock("overlay", "", attrs));
}

export function deleteOverlay(deck, slideIndex, objectId) {
  return deleteOverlays(deck, slideIndex, [objectId]);
}

export function deleteOverlays(deck, slideIndex, objectIds) {
  const requested = [...new Set(objectIds)];
  if (!requested.length) return deck.source;
  const slide = deck.slides[slideIndex];
  const available = new Map((slide?.overlays || []).map(overlay => [overlay.id, overlay]));
  const unknown = requested.find(id => !available.has(id));
  if (unknown) throw new Error(`Unknown overlay '${unknown}'`);
  const overlays = requested.map(id => available.get(id)).sort((left, right) => right.range.start - left.range.start);
  let source = slide.raw;
  for (const overlay of overlays) {
    source = patchRange(source, overlay.range.start - slide.range.start, overlay.range.end - slide.range.start, "");
  }
  return patchRange(deck.source, slide.range.start, slide.range.end, normalizeSlideSpacing(source));
}

export function duplicateOverlay(deck, slideIndex, objectId, newId) {
  const overlay = deck.slides[slideIndex]?.overlays.find(item => item.id === objectId);
  if (!overlay) throw new Error(`Unknown overlay '${objectId}'`);
  const attrs = structuredClone(overlay.attrs);
  attrs.id = newId;
  if (overlay.arrow) {
    for (const key of ["x1", "y1", "x2", "y2"]) attrs.values[key] = String(overlay.arrow[key] + 2);
  } else {
    attrs.values.x = String(overlay.geometry.x + 2);
    attrs.values.y = String(overlay.geometry.y + 2);
  }
  const block = `\n::: overlay {${serializeAttributes(attrs)}}\n${overlay.source.trim()}\n:::\n`;
  return patchRange(deck.source, overlay.range.end, overlay.range.end, block);
}

export function serializeOverlays(deck, slideIndex, objectIds) {
  const slide = deck.slides[slideIndex];
  const requested = new Set(objectIds);
  const overlays = (slide?.overlays || []).filter(overlay => requested.has(overlay.id));
  if (overlays.length !== requested.size) throw new Error("Cannot copy an unknown overlay");
  return overlays.map(overlay => `::: overlay {${serializeAttributes(overlay.attrs)}}\n${overlay.source.trim()}${overlay.source.trim() ? "\n" : ""}:::`).join("\n\n");
}

export function pasteOverlays(deck, slideIndex, clipboardSource, offset = 2) {
  const slide = deck.slides[slideIndex];
  if (!slide) throw new Error("Unknown slide");
  const parsed = parseDeck(`## Clipboard {.layout-free}\n\n${String(clipboardSource).trim()}\n`);
  if (parsed.diagnostics.length || !parsed.slides[0]?.overlays.length) return null;
  const clipboardSlide = parsed.slides[0];
  const ordinary = clipboardSlide.cells.find(cell => cell.id === "core")?.source.trim();
  if (ordinary || clipboardSlide.cells.some(cell => cell.range) || clipboardSlide.footer || clipboardSlide.notes) return null;
  const minimumX = Math.min(...clipboardSlide.overlays.map(overlay => overlay.geometry.x));
  const minimumY = Math.min(...clipboardSlide.overlays.map(overlay => overlay.geometry.y));
  const maximumX = Math.max(...clipboardSlide.overlays.map(overlay => overlay.geometry.x + overlay.geometry.w));
  const maximumY = Math.max(...clipboardSlide.overlays.map(overlay => overlay.geometry.y + overlay.geometry.h));
  const dx = Math.max(-minimumX, Math.min(100 - maximumX, offset));
  const dy = Math.max(-minimumY, Math.min(100 - maximumY, offset));
  const used = new Set(slide.overlays.map(overlay => overlay.id));
  const ids = [];
  const blocks = clipboardSlide.overlays.map(overlay => {
    const attrs = structuredClone(overlay.attrs);
    const base = (attrs.id || "overlay").replace(/[^a-zA-Z0-9_-]/g, "-") || "overlay";
    let id = base;
    let counter = 1;
    while (used.has(id)) id = `${base}-copy${counter++ === 1 ? "" : `-${counter - 1}`}`;
    used.add(id);
    ids.push(id);
    attrs.id = id;
    if (overlay.arrow) {
      for (const key of ["x1", "x2"]) attrs.values[key] = String(overlay.arrow[key] + dx);
      for (const key of ["y1", "y2"]) attrs.values[key] = String(overlay.arrow[key] + dy);
    } else {
      attrs.values.x = String(overlay.geometry.x + dx);
      attrs.values.y = String(overlay.geometry.y + dy);
    }
    const body = overlay.source.trim();
    return `::: overlay {${serializeAttributes(attrs)}}\n${body}${body ? "\n" : ""}:::`;
  });
  let source = deck.source;
  for (const block of blocks) {
    const currentDeck = parseDeck(source);
    source = appendBlock(currentDeck, currentDeck.slides[slideIndex], block);
  }
  return { source, ids };
}
