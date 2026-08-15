import { escapeHtml, THEMES } from "./parser.js";
import { makeShapeSvg, shapeLabelInsets } from "./shapes.js";
import { attributionKeys, renderCitation } from "./bibliography.js";

function preserveAdditionalBlankLines(source, spacers) {
  return source.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~)/g).map((part, index) => {
    if (index % 2) return part;
    return part.replace(/(?:\r?\n[ \t]*){2,}/g, run => {
      const extra = (run.match(/\r?\n/g) || []).length - 2;
      if (extra <= 0) return run;
      const tokens = Array.from({ length: extra }, () => {
        const token = `SCIBLANKLINEPLACEHOLDER${spacers.length}X`;
        spacers.push(token);
        return token;
      });
      return `\n\n${tokens.join("\n\n")}\n\n`;
    });
  }).join("");
}

function preserveMarkdownFragments(source, fragments) {
  return source.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g).map((part, index) => {
    if (index % 2) return part;
    return part.replace(/([ \t]*)\{fragment\s*=\s*(\d+)\}[ \t]*(?=\r?$)/gm, (whole, leading, value) => {
      const fragmentIndex = Number(value);
      if (!Number.isSafeInteger(fragmentIndex)) return whole;
      const token = `SCIFRAGMENTPLACEHOLDER${fragments.length}X`;
      fragments.push({ token, index: fragmentIndex });
      return `${leading}${token}`;
    });
  }).join("");
}

function applyMarkdownFragments(html, fragments) {
  if (!fragments.length) return html;
  const template = document.createElement("template");
  template.innerHTML = html;
  const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);
  for (const fragment of fragments) {
    const node = textNodes.find(candidate => candidate.data.includes(fragment.token));
    if (!node) continue;
    node.data = node.data.replace(fragment.token, "");
    const parent = node.parentElement;
    const block = parent?.closest("li") || parent?.closest("p, h1, h2, h3, h4, h5, h6");
    if (!block) continue;
    block.classList.add("fragment");
    block.dataset.fragmentIndex = String(fragment.index);
  }
  return template.innerHTML;
}

function markdown(source, bibliography = null, { breaks = false, preserveBlankLines = false } = {}) {
  try {
    const equations = [];
    let protectedSource = String(source || "").replace(
      /\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$|\\\(([\s\S]*?)\\\)|(?<!\\)\$([^\n$]+?)(?<!\\)\$/g,
      (whole, bracketDisplay, dollarDisplay, bracketInline, dollarInline) => {
        const display = bracketDisplay !== undefined || dollarDisplay !== undefined;
        const expression = bracketDisplay ?? dollarDisplay ?? bracketInline ?? dollarInline ?? "";
        const token = `SCIMATHPLACEHOLDER${equations.length}X`;
        equations.push({ token, expression, display });
        return token;
      },
    );
    const citations = [];
    protectedSource = protectedSource.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g).map((part, index) => {
      if (index % 2) return part;
      return part.replace(/(?<!\\)\[@([\w:./+-]+)(?:\s*;\s*@([\w:./+-]+))*\]/g, whole => {
        const token = `SCICITATIONPLACEHOLDER${citations.length}X`;
        citations.push({ token, keys: [...whole.matchAll(/@([\w:./+-]+)/g)].map(match => match[1]) });
        return token;
      });
    }).join("");
    const fragments = [];
    protectedSource = preserveMarkdownFragments(protectedSource, fragments);
    const spacers = [];
    if (preserveBlankLines) protectedSource = preserveAdditionalBlankLines(protectedSource, spacers);
    const renderer = new window.marked.Renderer();
    renderer.html = token => {
      const text = typeof token === "string" ? token : token?.text || token?.raw || "";
      return escapeHtml(text);
    };
    let html = window.marked.parse(protectedSource, { gfm: true, breaks, async: false, renderer });
    html = applyMarkdownFragments(html, fragments);
    for (const equation of equations) {
      const rendered = window.katex.renderToString(equation.expression, {
        displayMode: equation.display,
        throwOnError: false,
        trust: false,
        strict: "warn",
      });
      html = html.replaceAll(equation.token, rendered);
    }
    for (const citation of citations) html = html.replaceAll(citation.token, citation.keys.map(key => renderCitation(key, bibliography)).join(", "));
    for (const token of spacers) html = html.replace(new RegExp(`<p>\\s*${token}\\s*</p>`), '<div class="slide-content-spacer" aria-hidden="true"></div>');
    return html;
  } catch (error) {
    return `<pre class="render-error">${escapeHtml(error.message)}</pre>`;
  }
}

function safeAssetPath(source) {
  if (!source || /^(?:javascript|data:text\/html):/i.test(source)) return "";
  return source.replaceAll("\\", "/").split("/").map(part => encodeURIComponent(part)).join("/");
}

function titleMarkdown(source) {
  return String(source || "").split(/\r?\n/).map(line =>
    line.trim() ? markdown(line) : '<div class="slide-title-spacer" aria-hidden="true"></div>',
  ).join("");
}

function makeImage(image, assetResolver) {
  const resolved = assetResolver(image.source);
  const fit = image.attrs.values.fit || "contain";
  const parsedOpacity = Number(image.attrs.values.opacity ?? 1);
  const opacity = Number.isFinite(parsedOpacity) ? Math.min(1, Math.max(0, parsedOpacity)) : 1;
  const source = resolved || safeAssetPath(image.source);
  if (fit === "stretch") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("slide-image");
    svg.dataset.fit = fit;
    svg.dataset.source = image.source;
    svg.style.opacity = String(opacity);
    svg.setAttribute("viewBox", "0 0 1 1");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("role", "img");
    if (image.alt) svg.setAttribute("aria-label", image.alt);
    else svg.setAttribute("aria-hidden", "true");
    if (image.title) {
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = image.title;
      svg.append(title);
    }
    const resource = document.createElementNS("http://www.w3.org/2000/svg", "image");
    resource.setAttribute("href", source);
    resource.setAttribute("x", "0");
    resource.setAttribute("y", "0");
    resource.setAttribute("width", "1");
    resource.setAttribute("height", "1");
    resource.setAttribute("preserveAspectRatio", "none");
    svg.append(resource);
    return svg;
  }
  const img = document.createElement("img");
  img.className = "slide-image";
  img.dataset.source = image.source;
  img.style.opacity = String(opacity);
  img.alt = image.alt || "";
  img.src = source;
  if (image.title) img.title = image.title;
  img.dataset.fit = fit;
  const [focusX = "50", focusY = "50"] = (image.attrs.values.focus || "50 50").split(/[\s,]+/);
  const normalizedFocus = value => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? Math.min(100, Math.max(0, numeric)) : 50;
  };
  const x = normalizedFocus(focusX);
  const y = normalizedFocus(focusY);
  img.style.objectPosition = `${x}% ${y}%`;
  img.style.setProperty("--image-focus-x", `${x}%`);
  img.style.setProperty("--image-focus-y", `${y}%`);
  img.style.setProperty("--image-focus-x-offset", `${-x}%`);
  img.style.setProperty("--image-focus-y-offset", `${-y}%`);
  return img;
}

function makeVideo(video, assetResolver) {
  const element = document.createElement("video");
  element.className = "slide-video";
  element.src = assetResolver(video.source) || safeAssetPath(video.source);
  if (video.poster) element.poster = assetResolver(video.poster) || safeAssetPath(video.poster);
  element.controls = video.controls;
  element.dataset.autoplay = String(video.autoplay);
  element.loop = video.loop;
  element.muted = video.muted;
  element.playsInline = true;
  element.preload = "metadata";
  element.dataset.fit = video.fit;
  return element;
}

let arrowMarkerSequence = 0;

function strokePattern(style, width) {
  const scale = Number(width) || 2;
  const units = {
    dash: [4, 3],
    "dash-dot": [4, 2, 0, 2],
    dotted: [0, 2.5],
  }[style];
  return units ? units.map(value => String(value * scale)).join(" ") : null;
}

function makeArrow(overlay) {
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  svg.classList.add("arrow-svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.style.left = `${-100 * overlay.geometry.x / overlay.geometry.w}%`;
  svg.style.top = `${-100 * overlay.geometry.y / overlay.geometry.h}%`;
  svg.style.width = `${10000 / overlay.geometry.w}%`;
  svg.style.height = `${10000 / overlay.geometry.h}%`;
  const markerId = `quarkfoil-arrowhead-${++arrowMarkerSequence}`;
  const definitions = document.createElementNS(namespace, "defs");
  const marker = document.createElementNS(namespace, "marker");
  marker.classList.add("arrow-marker");
  for (const [name, value] of [["id", markerId], ["viewBox", "0 0 10 10"], ["refX", "8"], ["refY", "5"], ["markerWidth", "6"], ["markerHeight", "6"], ["orient", "auto-start-reverse"], ["markerUnits", "strokeWidth"]]) marker.setAttribute(name, value);
  const head = document.createElementNS(namespace, "path");
  head.classList.add("arrow-head");
  head.setAttribute("d", "M0 0 L10 5 L0 10 Z");
  head.setAttribute("fill", overlay.stroke || "var(--shape-default-stroke)");
  head.setAttribute("stroke", "none");
  marker.append(head);
  definitions.append(marker);
  const line = document.createElementNS(namespace, "line");
  line.classList.add("arrow-line");
  const { arrow } = overlay;
  const coordinates = {
    x1: arrow.x1,
    y1: arrow.y1,
    x2: arrow.x2,
    y2: arrow.y2,
  };
  for (const [name, value] of Object.entries(coordinates)) line.setAttribute(name, String(value));
  line.setAttribute("stroke", overlay.stroke || "var(--shape-default-stroke)");
  line.setAttribute("stroke-width", String(overlay.strokeWidth));
  const dashArray = strokePattern(overlay.strokeStyle, overlay.strokeWidth);
  if (dashArray) line.setAttribute("stroke-dasharray", dashArray);
  line.setAttribute("stroke-linecap", ["dash-dot", "dotted"].includes(overlay.strokeStyle) ? "round" : "butt");
  line.setAttribute("paint-order", "stroke markers");
  line.setAttribute("vector-effect", "non-scaling-stroke");
  if (["start", "both"].includes(arrow.heads)) line.setAttribute("marker-start", `url(#${markerId})`);
  if (["end", "both"].includes(arrow.heads)) line.setAttribute("marker-end", `url(#${markerId})`);
  const hitTarget = line.cloneNode(false);
  hitTarget.classList.remove("arrow-line");
  hitTarget.classList.add("arrow-hit");
  hitTarget.removeAttribute("marker-start");
  hitTarget.removeAttribute("marker-end");
  hitTarget.removeAttribute("stroke-dasharray");
  hitTarget.setAttribute("stroke-linecap", "round");
  hitTarget.setAttribute("stroke", "transparent");
  hitTarget.setAttribute("stroke-width", "12");
  hitTarget.setAttribute("pointer-events", "stroke");
  svg.append(definitions, hitTarget, line);
  return svg;
}

function fillContent(container, item, assetResolver, bibliography, preserveLines = false, preserveBlankLines = false) {
  if (item.type === "image" && item.image) container.append(makeImage(item.image, assetResolver));
  else if (item.type === "video" && item.video) container.append(makeVideo(item.video, assetResolver));
  else if (item.type === "arrow" && item.arrow) container.append(makeArrow(item));
  else if (item.type === "shape") {
    container.dataset.shape = item.shape;
    container.dataset.shadow = String(item.shadow);
    if (item.fill) container.style.setProperty("--shape-fill", item.fill);
    if (item.stroke) container.style.setProperty("--shape-stroke", item.stroke);
    container.style.setProperty("--shape-stroke-width", String(item.strokeWidth));
    container.style.setProperty("--shape-stroke-dasharray", strokePattern(item.strokeStyle, item.strokeWidth) || "none");
    container.style.setProperty("--shape-stroke-linecap", ["dash-dot", "dotted"].includes(item.strokeStyle) ? "round" : "butt");
    const [top, right, bottom, left] = shapeLabelInsets(item.shape);
    container.style.setProperty("--shape-label-top", `${top}%`);
    container.style.setProperty("--shape-label-right", `${right}%`);
    container.style.setProperty("--shape-label-bottom", `${bottom}%`);
    container.style.setProperty("--shape-label-left", `${left}%`);
    const label = document.createElement("div");
    label.className = "shape-label";
    label.innerHTML = markdown(item.source, bibliography, { breaks: preserveLines, preserveBlankLines });
    container.append(makeShapeSvg(item.shape, item.shapeParameters), label);
  }
  else if (item.type === "citation") {
    const brief = item.attrs.values.display !== "number";
    container.innerHTML = attributionKeys(item).map(key => renderCitation(key, bibliography, { brief })).join("; ");
  }
  else container.innerHTML = markdown(item.source, bibliography, { breaks: preserveLines && item.type === "markdown", preserveBlankLines });
}

function cellMap(layout) {
  if (layout === "0") return [];
  if (layout === "1-1") return ["left", "right"];
  if (layout === "1-2") return ["left", "top-right", "bottom-right"];
  if (layout === "2-1") return ["top-left", "bottom-left", "right"];
  if (layout === "free") return [];
  return ["core"];
}

function findCell(slide, name) {
  return slide.cells.find(cell => cell.id === name) || (name === "core" ? slide.cells[0] : null);
}

function renderSlide(slide, metadata, assetResolver, bibliography) {
  const section = document.createElement("section");
  const deckTheme = THEMES.includes(String(metadata?.theme)) ? String(metadata.theme) : "scientific-light";
  const requestedTheme = slide.headingAttrs.values.theme;
  const theme = THEMES.includes(requestedTheme) ? requestedTheme : deckTheme;
  section.className = `scientific-slide layout-${slide.layout} theme-${theme}`;
  section.dataset.slideIndex = String(slide.index);
  section.dataset.slideId = slide.id;
  section.style.setProperty("--column-a", `${slide.columns[0]}fr`);
  section.style.setProperty("--column-b", `${slide.columns[1]}fr`);
  section.style.setProperty("--row-a", `${slide.rows[0]}fr`);
  section.style.setProperty("--row-b", `${slide.rows[1]}fr`);
  for (const [attribute, variable] of [["background", "--slide-background"], ["foreground", "--slide-foreground"]]) {
    const color = slide.headingAttrs.values[attribute];
    if (/^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i.test(color || "")) section.style.setProperty(variable, color);
  }

  const frame = document.createElement("div");
  frame.className = "slide-frame";

  if (slide.titleSource) {
    const title = document.createElement("div");
    title.className = "slide-title";
    title.innerHTML = titleMarkdown(slide.titleSource);
    frame.append(title);
  } else section.classList.add("no-title");

  const core = document.createElement("div");
  core.className = "slide-core";
  const grid = document.createElement("div");
  grid.className = "slide-grid";
  for (const name of cellMap(slide.layout)) {
    const cell = document.createElement("div");
    cell.className = `slide-cell cell-${name}`;
    cell.dataset.cellId = name;
    const item = findCell(slide, name);
    if (item) {
      cell.dataset.contentType = item.type;
      fillContent(cell, item, assetResolver, bibliography, false, true);
    } else {
      cell.dataset.empty = "true";
      cell.innerHTML = `<span class="empty-cell-label">${escapeHtml(name)}</span>`;
    }
    grid.append(cell);
  }
  core.append(grid);

  const overlayLayer = document.createElement("div");
  overlayLayer.className = "overlay-layer";
  for (const overlay of slide.overlays) {
    const element = document.createElement("div");
    element.className = `slide-overlay overlay-${overlay.type}`;
    if (overlay.fragment !== null && Number.isFinite(overlay.fragment)) {
      element.classList.add("fragment");
      element.dataset.fragmentIndex = String(overlay.fragment);
    }
    element.dataset.objectId = overlay.id;
    element.dataset.objectType = overlay.type;
    if (overlay.type === "citation") element.dataset.citationDisplay = overlay.attrs.values.display || "number";
    element.dataset.locked = String(overlay.locked);
    element.style.left = `${overlay.geometry.x}%`;
    element.style.top = `${overlay.geometry.y}%`;
    element.style.width = `${overlay.geometry.w}%`;
    element.style.height = `${overlay.geometry.h}%`;
    element.style.zIndex = String(overlay.geometry.z);
    if (/^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i.test(overlay.color || "")) element.style.color = overlay.color;
    if (!["image", "video", "arrow"].includes(overlay.type)) {
      element.style.fontSize = `${overlay.fontSize}em`;
      element.style.textAlign = overlay.alignment;
      element.dataset.align = overlay.alignment;
    }
    fillContent(element, overlay, assetResolver, bibliography, true, true);
    overlayLayer.append(element);
  }
  frame.append(core);
  section.append(frame, overlayLayer);

  const footerSource = slide.footer?.source ?? metadata?.defaults?.footer ?? "";
  if (footerSource && slide.headingAttrs.values.footer !== "none") {
    const footer = document.createElement("footer");
    footer.className = "slide-footer";
    footer.innerHTML = markdown(String(footerSource), bibliography);
    frame.append(footer);
  } else section.classList.add("no-footer");

  if (slide.notes) {
    const notes = document.createElement("aside");
    notes.className = "notes";
    notes.innerHTML = markdown(slide.notes);
    section.append(notes);
  }
  return section;
}

export function renderDeck(deck, target, assetResolver = source => `/project/${safeAssetPath(source)}`, bibliography = null) {
  const fragment = document.createDocumentFragment();
  for (const slide of deck.slides) fragment.append(renderSlide(slide, deck.metadata, assetResolver, bibliography));
  target.replaceChildren(fragment);
}

export function renderMarkdownPreview(source, target, options = {}) {
  target.innerHTML = markdown(source, null, options);
}

export function syncVideoPlayback(activeSlide, { autoplay = true, pauseActive = false } = {}) {
  document.querySelectorAll(".scientific-slide .slide-video").forEach(video => {
    if (!activeSlide?.contains(video) || pauseActive) video.pause();
    else if (autoplay && video.dataset.autoplay === "true") video.play().catch(() => {});
  });
}
