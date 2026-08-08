import { escapeHtml } from "./parser.js";

function markdown(source) {
  try {
    const equations = [];
    const protectedSource = String(source || "").replace(
      /\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$|\\\(([\s\S]*?)\\\)|(?<!\\)\$([^\n$]+?)(?<!\\)\$/g,
      (whole, bracketDisplay, dollarDisplay, bracketInline, dollarInline) => {
        const display = bracketDisplay !== undefined || dollarDisplay !== undefined;
        const expression = bracketDisplay ?? dollarDisplay ?? bracketInline ?? dollarInline ?? "";
        const token = `SCIMATHPLACEHOLDER${equations.length}X`;
        equations.push({ token, expression, display });
        return token;
      },
    );
    const renderer = new window.marked.Renderer();
    renderer.html = token => {
      const text = typeof token === "string" ? token : token?.text || token?.raw || "";
      return escapeHtml(text);
    };
    let html = window.marked.parse(protectedSource, { gfm: true, breaks: false, async: false, renderer });
    for (const equation of equations) {
      const rendered = window.katex.renderToString(equation.expression, {
        displayMode: equation.display,
        throwOnError: false,
        trust: false,
        strict: "warn",
      });
      html = html.replaceAll(equation.token, rendered);
    }
    return html;
  } catch (error) {
    return `<pre class="render-error">${escapeHtml(error.message)}</pre>`;
  }
}

function safeAssetPath(source) {
  if (!source || /^(?:javascript|data:text\/html):/i.test(source)) return "";
  return source.replaceAll("\\", "/").split("/").map(part => encodeURIComponent(part)).join("/");
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

function fillContent(container, item, assetResolver) {
  if (item.type === "image" && item.image) container.append(makeImage(item.image, assetResolver));
  else container.innerHTML = markdown(item.source);
}

function cellMap(layout) {
  if (layout === "1-1") return ["left", "right"];
  if (layout === "1-2") return ["left", "top-right", "bottom-right"];
  if (layout === "2-1") return ["top-left", "bottom-left", "right"];
  if (layout === "free") return [];
  return ["core"];
}

function findCell(slide, name) {
  return slide.cells.find(cell => cell.id === name) || (name === "core" ? slide.cells[0] : null);
}

function renderSlide(slide, metadata, assetResolver) {
  const section = document.createElement("section");
  section.className = `scientific-slide layout-${slide.layout}`;
  section.dataset.slideIndex = String(slide.index);
  section.dataset.slideId = slide.id;
  section.style.setProperty("--columns", `${slide.columns[0]}fr ${slide.columns[1]}fr`);
  section.style.setProperty("--rows", `${slide.rows[0]}fr ${slide.rows[1]}fr`);
  section.style.setProperty("--column-a-pct", `${slide.columns[0]}%`);
  section.style.setProperty("--column-b-pct", `${slide.columns[1]}%`);
  section.style.setProperty("--row-a-pct", `${slide.rows[0]}%`);
  section.style.setProperty("--row-b-pct", `${slide.rows[1]}%`);

  if (slide.title) {
    const title = document.createElement(slide.headingAttrs.classes.includes("title-slide") ? "h1" : "h2");
    title.className = "slide-title";
    title.innerHTML = markdown(slide.title).replace(/^<p>|<\/p>\s*$/g, "");
    section.append(title);
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
      fillContent(cell, item, assetResolver);
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
    fillContent(element, overlay, assetResolver);
    overlayLayer.append(element);
  }
  section.append(core, overlayLayer);

  const footerSource = slide.footer?.source ?? metadata?.defaults?.footer ?? "";
  if (footerSource && slide.headingAttrs.values.footer !== "none") {
    const footer = document.createElement("footer");
    footer.className = "slide-footer";
    footer.innerHTML = markdown(String(footerSource));
    section.append(footer);
  } else section.classList.add("no-footer");

  if (slide.notes) {
    const notes = document.createElement("aside");
    notes.className = "notes";
    notes.innerHTML = markdown(slide.notes);
    section.append(notes);
  }
  return section;
}

export function renderDeck(deck, target, assetResolver = source => `/project/${safeAssetPath(source)}`) {
  const fragment = document.createDocumentFragment();
  for (const slide of deck.slides) fragment.append(renderSlide(slide, deck.metadata, assetResolver));
  target.replaceChildren(fragment);
}

export function renderMarkdownPreview(source, target) {
  target.innerHTML = markdown(source);
}
