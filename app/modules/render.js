import { escapeHtml, THEMES } from "./parser.js";
import { makeShapeSvg } from "./shapes.js";
import { renderCitation } from "./bibliography.js";

function markdown(source, bibliography = null, { breaks = false } = {}) {
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
    const renderer = new window.marked.Renderer();
    renderer.html = token => {
      const text = typeof token === "string" ? token : token?.text || token?.raw || "";
      return escapeHtml(text);
    };
    let html = window.marked.parse(protectedSource, { gfm: true, breaks, async: false, renderer });
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
  const img = document.createElement("img");
  img.className = "slide-image";
  img.alt = image.alt || "";
  const resolved = assetResolver(image.source);
  img.src = resolved || safeAssetPath(image.source);
  if (image.title) img.title = image.title;
  const fit = image.attrs.values.fit || "contain";
  img.dataset.fit = fit;
  const [focusX = "50", focusY = "50"] = (image.attrs.values.focus || "50 50").split(/[\s,]+/);
  img.style.objectPosition = `${Number(focusX) || 50}% ${Number(focusY) || 50}%`;
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

function fillContent(container, item, assetResolver, bibliography, preserveLines = false) {
  if (item.type === "image" && item.image) container.append(makeImage(item.image, assetResolver));
  else if (item.type === "video" && item.video) container.append(makeVideo(item.video, assetResolver));
  else if (item.type === "shape") {
    container.dataset.shape = item.shape;
    container.dataset.shadow = String(item.shadow);
    if (item.fill) container.style.setProperty("--shape-fill", item.fill);
    if (item.stroke) container.style.setProperty("--shape-stroke", item.stroke);
    container.style.setProperty("--shape-stroke-width", String(item.strokeWidth));
    const label = document.createElement("div");
    label.className = "shape-label";
    label.innerHTML = markdown(item.source, bibliography, { breaks: preserveLines });
    container.append(makeShapeSvg(item.shape), label);
  }
  else if (item.type === "citation") container.innerHTML = renderCitation(item.attrs.values.key || "", bibliography, { brief: item.attrs.values.display !== "number" });
  else container.innerHTML = markdown(item.source, bibliography, { breaks: preserveLines && item.type === "markdown" });
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
    if (/^#[0-9a-f]{6}$/i.test(color || "")) section.style.setProperty(variable, color);
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
      fillContent(cell, item, assetResolver, bibliography);
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
    element.dataset.locked = String(overlay.locked);
    element.style.left = `${overlay.geometry.x}%`;
    element.style.top = `${overlay.geometry.y}%`;
    element.style.width = `${overlay.geometry.w}%`;
    element.style.height = `${overlay.geometry.h}%`;
    element.style.zIndex = String(overlay.geometry.z);
    if (/^#[0-9a-f]{6}$/i.test(overlay.color || "")) element.style.color = overlay.color;
    if (!["image", "video"].includes(overlay.type)) {
      element.style.fontSize = `${overlay.fontSize}em`;
      element.style.textAlign = overlay.alignment;
      element.dataset.align = overlay.alignment;
    }
    fillContent(element, overlay, assetResolver, bibliography, true);
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

export function syncVideoPlayback(activeSlide) {
  document.querySelectorAll(".scientific-slide .slide-video").forEach(video => {
    if (!activeSlide?.contains(video)) video.pause();
    else if (video.dataset.autoplay === "true") video.play().catch(() => {});
  });
}
