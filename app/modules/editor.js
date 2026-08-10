import {
  deleteOverlay,
  duplicateOverlay,
  insertOverlay,
  setCellContent,
  updateBlockContent,
  updateHeadingLayout,
  updateOverlay,
  updateSlideTitle,
  updateSlideProperties,
} from "./parser.js";
import { renderMarkdownPreview } from "./render.js";

const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));
const round = value => Math.round(value * 10) / 10;
export const videoFile = file => file?.type?.startsWith("video/") || /\.(?:avi|mkv|mp4|webm)$/i.test(file?.name || "");
export const projectAssetPage = (assets, query, page, pageSize = 24) => {
  const needle = query.trim().toLocaleLowerCase();
  const filtered = needle ? assets.filter(asset => asset.path.toLocaleLowerCase().includes(needle)) : assets;
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(Math.max(0, page), pages - 1);
  return { assets: filtered.slice(current * pageSize, (current + 1) * pageSize), count: filtered.length, page: current, pages };
};

export function pageSlideIndex(current, count, key) {
  const direction = key === "PageUp" ? -1 : key === "PageDown" ? 1 : 0;
  return direction ? clamp(current + direction, 0, Math.max(0, count - 1)) : current;
}

function colorInputValue(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (/^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/.test(normalized)) return normalized;
  if (/^#[0-9a-f]{3}$/.test(normalized)) return `#${[...normalized.slice(1)].map(character => character.repeat(2)).join("")}`;
  if (!normalized.startsWith("rgb")) return null;
  const components = normalized.match(/[\d.]+%?/g);
  if (!components || components.length < 3) return null;
  const hexadecimal = components.slice(0, 3)
    .map(component => {
      const value = Number.parseFloat(component) * (component.endsWith("%") ? 2.55 : 1);
      return Math.round(clamp(value, 0, 255)).toString(16).padStart(2, "0");
    })
    .join("");
  if (components.length < 4) return `#${hexadecimal}`;
  const alpha = components[3].endsWith("%") ? Number.parseFloat(components[3]) / 100 : Number.parseFloat(components[3]);
  return `#${hexadecimal}${Math.round(clamp(alpha, 0, 1) * 255).toString(16).padStart(2, "0")}`;
}

function setColorControl(id, value, fallback) {
  const normalized = colorInputValue(value) || fallback;
  document.querySelector(`#${id}`).value = normalized.slice(0, 7);
  const alpha = normalized.length === 9 ? Number.parseInt(normalized.slice(7), 16) / 255 : 1;
  document.querySelector(`#${id}-alpha`).value = String(Math.round(alpha * 100));
}

function colorControlValue(id) {
  const color = document.querySelector(`#${id}`).value;
  const alphaInput = document.querySelector(`#${id}-alpha`);
  const requestedOpacity = alphaInput.value.trim() === "" ? 100 : Number(alphaInput.value);
  const opacity = clamp(Number.isFinite(requestedOpacity) ? requestedOpacity : 100, 0, 100);
  alphaInput.value = String(opacity);
  const alpha = Math.round(opacity * 255 / 100);
  return alpha === 255 ? color : `${color}${alpha.toString(16).padStart(2, "0")}`;
}

export function setRangeControl(id, requestedValue) {
  const range = document.querySelector(`#${id}`);
  const minimum = Number(range.min);
  const maximum = Number(range.max);
  const step = Number(range.step) || 1;
  const numeric = String(requestedValue).trim() === "" ? Number.NaN : Number(requestedValue);
  const bounded = clamp(Number.isFinite(numeric) ? numeric : Number(range.value), minimum, maximum);
  const value = Number((minimum + Math.round((bounded - minimum) / step) * step).toFixed(10));
  range.value = String(value);
  document.querySelector(`#${id}-value`).value = String(value);
  return value;
}

export function bindRangeControl(id) {
  const range = document.querySelector(`#${id}`);
  const number = document.querySelector(`#${id}-value`);
  range.addEventListener("input", () => setRangeControl(id, range.value));
  number.addEventListener("change", () => {
    setRangeControl(id, number.value);
    range.dispatchEvent(new Event("input"));
    range.dispatchEvent(new Event("change"));
  });
}

function resolvedThemeColor(container, variable) {
  const probe = document.createElement("span");
  probe.style.color = `var(${variable})`;
  container.append(probe);
  const color = colorInputValue(getComputedStyle(probe).color);
  probe.remove();
  return color;
}

const IMAGE_EXTENSIONS = {
  "image/gif": "gif",
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/svg+xml": "svg",
  "image/webp": "webp",
};

export function clipboardImageFile(clipboardData, timestamp = Date.now()) {
  const candidates = [...(clipboardData?.files || [])]
    .filter(candidate => candidate.type.startsWith("image/"));
  for (const item of clipboardData?.items || []) {
    if (item.kind !== "file" || !item.type.startsWith("image/")) continue;
    const file = item.getAsFile();
    if (file && !candidates.includes(file)) candidates.push(file);
  }
  candidates.sort((left, right) => {
    const score = file => (file.type === "image/png" ? 0 : 4) + (file.name?.includes(".") ? 2 : 0);
    return score(right) - score(left);
  });
  const file = candidates[0];
  if (!file) return null;
  const extension = IMAGE_EXTENSIONS[file.type];
  if (!extension || file.name?.includes(".")) return file;
  return new File([file], `pasted-image-${timestamp}.${extension}`, {
    type: file.type,
    lastModified: file.lastModified,
  });
}

export function renameClipboardImage(file, requestedName) {
  const name = requestedName?.trim().replace(/[\\/]/g, "-");
  if (!name) return null;
  const extension = IMAGE_EXTENSIONS[file.type];
  const completeName = extension && !/\.[a-z0-9]+$/i.test(name) ? `${name}.${extension}` : name;
  if (completeName === file.name) return file;
  return new File([file], completeName, { type: file.type, lastModified: file.lastModified });
}

export function initialImageGeometry(imageAspect, slideAspect, position = null) {
  const maximum = 35;
  const percentageAspect = imageAspect / slideAspect;
  const w = round(percentageAspect >= 1 ? maximum : maximum * percentageAspect);
  const h = round(percentageAspect >= 1 ? maximum / percentageAspect : maximum);
  return {
    x: position ? clamp(round(position.x), 0, 100 - w) : round((100 - w) / 2),
    y: position ? clamp(round(position.y), 0, 100 - h) : round((100 - h) / 2),
    w,
    h,
  };
}

function imageAspectRatio(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image.naturalWidth / image.naturalHeight);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Unable to read image dimensions"));
    };
    image.src = url;
  });
}

export class DesignEditor {
  constructor(options) {
    this.options = options;
    this.selected = null;
    this.selectedCell = null;
    this.drag = null;
    this.dialogTarget = null;
    this.stage = document.querySelector("#stage");
    this.properties = document.querySelector("#object-properties");
    this.slideProperties = document.querySelector("#slide-properties");
    this.imageProperties = document.querySelector("#image-properties");
    this.videoProperties = document.querySelector("#video-properties");
    this.shapeProperties = document.querySelector("#shape-properties");
    this.fontProperties = document.querySelector("#font-properties");
    this.noSelection = document.querySelector("#no-selection");
    this.dialog = document.querySelector("#content-dialog");
    this.contentEditor = document.querySelector("#content-editor");
    this.preview = document.querySelector("#content-preview");
    this.imageInputPurpose = "add";
    this.videoInputPurpose = "add";
    this.bind();
  }

  bind() {
    this.stage.addEventListener("click", event => this.onClick(event));
    this.stage.addEventListener("dblclick", event => this.onDoubleClick(event));
    this.stage.addEventListener("pointerdown", event => this.onPointerDown(event));
    document.addEventListener("keydown", event => this.onKeyDown(event));
    document.addEventListener("paste", event => this.onPaste(event));
    for (const id of ["prop-focus-x", "prop-focus-y", "prop-font-size"]) bindRangeControl(id);
    document.querySelector("#layout-select").addEventListener("change", event => this.changeLayout(event.target.value));
    document.querySelector("#prop-slide-theme").addEventListener("change", event => this.applySlideProperties({ theme: event.target.value || null }));
    for (const name of ["background", "foreground"]) {
      for (const suffix of ["", "-alpha"]) {
        document.querySelector(`#prop-slide-${name}${suffix}`).addEventListener("change", () => this.applySlideProperties({ [name]: colorControlValue(`prop-slide-${name}`) }));
      }
    }
    document.querySelector("#reset-slide-background").addEventListener("click", () => this.applySlideProperties({ background: null }));
    document.querySelector("#reset-slide-foreground").addEventListener("click", () => this.applySlideProperties({ foreground: null }));
    document.querySelector("#add-text").addEventListener("click", () => this.addObject("markdown"));
    document.querySelector("#add-equation").addEventListener("click", () => this.addObject("equation"));
    document.querySelector("#add-image").addEventListener("click", () => {
      this.imageInputPurpose = "add";
      document.querySelector("#image-input").click();
    });
    document.querySelector("#add-video").addEventListener("click", () => {
      this.videoInputPurpose = "add";
      document.querySelector("#video-input").click();
    });
    document.querySelector("#add-shape").addEventListener("click", () => this.addShape(document.querySelector("#shape-select").value));
    document.querySelector("#image-input").addEventListener("change", event => {
      const file = event.target.files?.[0];
      if (this.imageInputPurpose === "replace") this.replaceImage(file);
      else this.addImage(file, null, this.selectedCell?.dataset.cellId || null);
      this.imageInputPurpose = "add";
      event.target.value = "";
    });
    document.querySelector("#video-input").addEventListener("change", event => {
      const file = event.target.files?.[0];
      if (this.videoInputPurpose === "replace") this.replaceVideo(file);
      else this.addVideo(file);
      this.videoInputPurpose = "add";
      event.target.value = "";
    });
    document.querySelector("#duplicate-object").addEventListener("click", () => this.duplicate());
    document.querySelector("#delete-object").addEventListener("click", () => this.remove());
    document.querySelector("#edit-content").addEventListener("click", () => this.openContentDialog());
    document.querySelector("#replace-image").addEventListener("click", () => {
      this.imageInputPurpose = "replace";
      document.querySelector("#image-input").click();
    });
    document.querySelector("#choose-project-image").addEventListener("click", () => this.openProjectImageDialog());
    document.querySelector("#replace-video").addEventListener("click", () => {
      this.videoInputPurpose = "replace";
      document.querySelector("#video-input").click();
    });
    document.querySelector("#choose-project-video").addEventListener("click", () => this.openProjectVideoDialog());
    this.contentEditor.addEventListener("input", () => this.updateContentPreview());
    this.dialog.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.preventDefault();
        this.dialogTarget = null;
        this.dialog.close("cancel");
        return;
      }
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        this.applyContentDialog();
      }
    });
    this.dialog.addEventListener("cancel", () => { this.dialogTarget = null; });
    this.dialog.addEventListener("close", () => {
      if (this.dialog.returnValue === "cancel") this.dialogTarget = null;
    });
    document.querySelector("#content-apply").addEventListener("click", event => {
      event.preventDefault();
      this.applyContentDialog();
    });
    for (const id of ["x", "y", "w", "h", "fragment", "z"]) {
      document.querySelector(`#prop-${id}`).addEventListener("change", () => this.applyProperties());
    }
    document.querySelector("#prop-locked").addEventListener("change", () => this.applyProperties());
    document.querySelector("#prop-fit").addEventListener("change", () => this.applyImageProperties());
    document.querySelector("#prop-focus-x").addEventListener("change", () => this.applyImageProperties());
    document.querySelector("#prop-focus-y").addEventListener("change", () => this.applyImageProperties());
    for (const id of ["video-fit", "video-controls", "video-autoplay", "video-loop", "video-muted", "video-poster"]) {
      document.querySelector(`#prop-${id}`).addEventListener("change", () => this.applyVideoProperties());
    }
    for (const id of ["shape", "shape-fill", "shape-fill-alpha", "shape-stroke", "shape-stroke-alpha", "shape-stroke-width", "shape-shadow"]) {
      document.querySelector(`#prop-${id}`).addEventListener("change", () => this.applyShapeProperties());
    }
    document.querySelector("#prop-font-size").addEventListener("input", event => this.previewFontSize(event.target.value));
    document.querySelector("#prop-font-size").addEventListener("change", () => this.applyFontSize());
    for (const id of ["prop-text-color", "prop-text-color-alpha"]) {
      document.querySelector(`#${id}`).addEventListener("change", () => this.applyTextColor(colorControlValue("prop-text-color")));
    }
    document.querySelector("#reset-text-color").addEventListener("click", () => this.applyTextColor(null));
    document.querySelectorAll(".alignment-buttons [data-align]").forEach(button => {
      button.addEventListener("click", () => this.applyAlignment(button.dataset.align));
    });
    this.stage.addEventListener("dragover", event => event.preventDefault());
    this.stage.addEventListener("drop", event => this.onDrop(event));
  }

  active() { return this.options.getMode() === "design"; }
  slideIndex() { return this.options.getSlideIndex(); }
  slide() { return this.options.getDeck().slides[this.slideIndex()]; }
  section() { return document.querySelector(`.scientific-slide[data-slide-index="${this.slideIndex()}"]`); }

  updateContentPreview() {
    const source = this.dialogTarget?.kind === "title"
      ? this.contentEditor.value.replace(/\r?\n/g, "  \n")
      : this.contentEditor.value;
    renderMarkdownPreview(source, this.preview, { breaks: this.dialogTarget?.kind === "overlay" });
  }

  refresh() {
    this.clearSelection();
    const slide = this.slide();
    if (!slide) return;
    document.querySelector("#layout-select").value = slide.layout;
  }

  onClick(event) {
    if (!this.active() || this.drag) return;
    const overlay = event.target.closest(".slide-overlay");
    if (overlay) { this.selectOverlay(overlay); return; }
    const cell = event.target.closest(".slide-cell");
    if (cell) { this.selectCell(cell); return; }
    this.clearSelection();
  }

  onDoubleClick(event) {
    if (!this.active()) return;
    const overlay = event.target.closest(".slide-overlay");
    const cell = event.target.closest(".slide-cell");
    const title = event.target.closest(".slide-title");
    if (!overlay && !cell && !title) return;
    event.preventDefault();
    event.stopPropagation();
    window.getSelection()?.removeAllRanges();
    if (overlay) { this.selectOverlay(overlay); this.openContentDialog(); }
    else if (cell) { this.selectCell(cell); this.openCellDialog(); }
    else this.openTitleDialog();
  }

  selectOverlay(element) {
    this.clearSelection();
    this.slideProperties.hidden = true;
    this.selected = element;
    element.classList.add("selected-object");
    for (const corner of ["nw", "ne", "se", "sw"]) {
      const handle = document.createElement("span");
      handle.className = `resize-handle ${corner}`;
      handle.dataset.corner = corner;
      element.append(handle);
    }
    this.noSelection.hidden = true;
    this.properties.hidden = false;
    const object = this.slide().overlays.find(item => item.id === element.dataset.objectId);
    this.fillProperties(object, element);
    document.querySelector("#duplicate-object").disabled = false;
    document.querySelector("#delete-object").disabled = false;
  }

  selectCell(element) {
    this.clearSelection();
    this.slideProperties.hidden = true;
    this.selectedCell = element;
    element.classList.add("selected-cell");
    const cell = this.slide().cells.find(item => item.id === element.dataset.cellId);
    this.noSelection.textContent = `Cell: ${element.dataset.cellId}. Double-click to edit.`;
    if (cell?.type === "image" && cell.image) {
      this.imageProperties.hidden = false;
      document.querySelector("#prop-fit").value = cell.image.attrs.values.fit || "contain";
      const focus = (cell.image.attrs.values.focus || "50 50").split(/[\s,]+/);
      setRangeControl("prop-focus-x", focus[0] || 50);
      setRangeControl("prop-focus-y", focus[1] || 50);
    } else if (cell?.type === "video") {
      this.noSelection.textContent = "Video cell properties must currently be edited in Source mode.";
    }
  }

  clearSelection() {
    document.querySelectorAll(".selected-object,.selected-cell").forEach(item => item.classList.remove("selected-object", "selected-cell"));
    document.querySelectorAll(".resize-handle").forEach(item => item.remove());
    this.selected = null;
    this.selectedCell = null;
    this.properties.hidden = true;
    this.imageProperties.hidden = true;
    this.videoProperties.hidden = true;
    this.shapeProperties.hidden = true;
    this.fontProperties.hidden = true;
    this.noSelection.hidden = true;
    this.slideProperties.hidden = false;
    document.querySelector("#edit-content").hidden = false;
    document.querySelector("#duplicate-object").disabled = true;
    document.querySelector("#delete-object").disabled = true;
    this.fillSlideProperties();
  }

  fillSlideProperties() {
    const slide = this.slide();
    const section = this.section();
    if (!slide || !section) return;
    const style = getComputedStyle(section);
    document.querySelector("#prop-slide-theme").value = slide.headingAttrs.values.theme || "";
    setColorControl("prop-slide-background", style.getPropertyValue("--slide-background"), "#fbfcfd");
    setColorControl("prop-slide-foreground", style.getPropertyValue("--slide-foreground"), "#17202a");
    const overrides = ["background", "foreground"].filter(name => slide.headingAttrs.values[name]);
    document.querySelector("#slide-color-state").textContent = overrides.length
      ? `Explicit ${overrides.join(" and ")} override${overrides.length === 1 ? "" : "s"}`
      : "Colors inherited from theme";
  }

  applySlideProperties(changes) {
    this.commit(updateSlideProperties(this.options.getDeck(), this.slideIndex(), changes));
  }

  fillProperties(object, element) {
    if (!object) return;
    document.querySelector("#prop-id").value = object.id;
    for (const key of ["x", "y", "w", "h", "z"]) document.querySelector(`#prop-${key}`).value = object.geometry[key];
    document.querySelector("#prop-fragment").value = object.fragment ?? "";
    document.querySelector("#prop-locked").checked = object.locked;
    document.querySelector("#edit-content").hidden = ["image", "video"].includes(object.type);
    if (object.type === "image" && object.image) {
      this.imageProperties.hidden = false;
      document.querySelector("#prop-fit").value = object.image.attrs.values.fit || "contain";
      const focus = (object.image.attrs.values.focus || "50 50").split(/[\s,]+/);
      setRangeControl("prop-focus-x", focus[0] || 50);
      setRangeControl("prop-focus-y", focus[1] || 50);
    } else if (object.type === "video" && object.video) {
      this.fillVideoProperties(object.video);
    } else {
      if (object.type === "shape") {
        this.shapeProperties.hidden = false;
        document.querySelector("#prop-shape").value = object.shape;
        const surfaceStyle = getComputedStyle(element.querySelector(".shape-surface"));
        setColorControl("prop-shape-fill", surfaceStyle.fill, "#dbeff2");
        setColorControl("prop-shape-stroke", surfaceStyle.stroke, "#146c7e");
        document.querySelector("#prop-shape-stroke-width").value = object.strokeWidth;
        document.querySelector("#prop-shape-shadow").checked = object.shadow;
      }
      this.fontProperties.hidden = false;
      setColorControl("prop-text-color", getComputedStyle(element).color, "#17202a");
      document.querySelector("#prop-font-size").value = object.fontSize;
      this.updateFontSizeOutput(object.fontSize);
      this.updateAlignmentButtons(object.alignment);
    }
  }

  updateFontSizeOutput(value) {
    setRangeControl("prop-font-size", value);
  }

  previewFontSize(value) {
    if (!this.selected) return;
    this.selected.style.fontSize = `${value}em`;
    this.updateFontSizeOutput(value);
  }

  applyFontSize() {
    if (!this.selected) return;
    const value = Number(document.querySelector("#prop-font-size").value);
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, {
      "font-size": `${Math.round(value * 100) / 100}em`,
    }));
  }

  applyTextColor(color) {
    if (!this.selected || ["image", "video"].includes(this.selected.dataset.objectType)) return;
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, { color }));
  }

  updateAlignmentButtons(alignment) {
    document.querySelectorAll(".alignment-buttons [data-align]").forEach(button => {
      button.classList.toggle("active", button.dataset.align === alignment);
      button.setAttribute("aria-pressed", String(button.dataset.align === alignment));
    });
  }

  applyAlignment(alignment) {
    if (!this.selected || !["left", "center", "right"].includes(alignment)) return;
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, { align: alignment }));
  }

  onPointerDown(event) {
    if (!this.active() || event.button !== 0) return;
    const handle = event.target.closest(".resize-handle");
    const overlay = event.target.closest(".slide-overlay");
    if (!overlay) return;
    const object = this.slide().overlays.find(item => item.id === overlay.dataset.objectId);
    if (!object || object.locked) return;
    event.preventDefault();
    event.stopPropagation();
    this.selectOverlay(overlay);
    const rect = this.section().getBoundingClientRect();
    this.drag = {
      kind: handle ? "resize" : "move",
      corner: handle?.dataset.corner,
      element: overlay,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      rect,
      original: { ...object.geometry },
    };
    overlay.setPointerCapture(event.pointerId);
    overlay.addEventListener("pointermove", this.boundMove = moveEvent => this.moveOverlay(moveEvent));
    overlay.addEventListener("pointerup", this.boundUp = upEvent => this.finishOverlay(upEvent));
  }

  moveOverlay(event) {
    if (!this.drag) return;
    const dx = 100 * (event.clientX - this.drag.startX) / this.drag.rect.width;
    const dy = 100 * (event.clientY - this.drag.startY) / this.drag.rect.height;
    const original = this.drag.original;
    let next = { ...original };
    if (this.drag.kind === "move") {
      next.x = clamp(round(original.x + dx), 0, 100 - original.w);
      next.y = clamp(round(original.y + dy), 0, 100 - original.h);
    } else {
      const corner = this.drag.corner;
      if (corner.includes("e")) next.w = clamp(round(original.w + dx), 1, 100 - original.x);
      if (corner.includes("s")) next.h = clamp(round(original.h + dy), 1, 100 - original.y);
      if (corner.includes("w")) {
        next.x = clamp(round(original.x + dx), 0, original.x + original.w - 1);
        next.w = round(original.w + original.x - next.x);
      }
      if (corner.includes("n")) {
        next.y = clamp(round(original.y + dy), 0, original.y + original.h - 1);
        next.h = round(original.h + original.y - next.y);
      }
    }
    this.applyGeometryToElement(this.drag.element, next);
    for (const key of ["x", "y", "w", "h"]) document.querySelector(`#prop-${key}`).value = next[key];
  }

  finishOverlay(event) {
    const drag = this.drag;
    if (!drag) return;
    drag.element.releasePointerCapture(event.pointerId);
    drag.element.removeEventListener("pointermove", this.boundMove);
    drag.element.removeEventListener("pointerup", this.boundUp);
    const changes = {
      x: Number(document.querySelector("#prop-x").value),
      y: Number(document.querySelector("#prop-y").value),
      w: Number(document.querySelector("#prop-w").value),
      h: Number(document.querySelector("#prop-h").value),
    };
    this.drag = null;
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), drag.element.dataset.objectId, changes));
  }

  applyGeometryToElement(element, geometry) {
    element.style.left = `${geometry.x}%`;
    element.style.top = `${geometry.y}%`;
    element.style.width = `${geometry.w}%`;
    element.style.height = `${geometry.h}%`;
  }

  changeLayout(layout) {
    const slide = this.slide();
    if (!slide) return;
    this.commit(updateHeadingLayout(this.options.getDeck(), this.slideIndex(), layout, slide.columns, slide.rows));
  }

  applyProperties() {
    if (!this.selected) return;
    const changes = {};
    for (const key of ["x", "y", "w", "h", "z"]) changes[key] = Number(document.querySelector(`#prop-${key}`).value);
    const fragment = document.querySelector("#prop-fragment").value;
    changes.fragment = fragment === "" ? null : Number(fragment);
    changes.locked = document.querySelector("#prop-locked").checked ? "true" : null;
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, changes));
  }

  applyImageProperties() {
    const object = this.selected
      ? this.slide().overlays.find(item => item.id === this.selected.dataset.objectId)
      : this.selectedCell
        ? this.slide().cells.find(item => item.id === this.selectedCell.dataset.cellId)
        : null;
    if (!object?.image) return;
    const fit = document.querySelector("#prop-fit").value;
    const focus = `${document.querySelector("#prop-focus-x").value} ${document.querySelector("#prop-focus-y").value}`;
    const body = `![${object.image.alt}](${object.image.source}){fit=${JSON.stringify(fit)} focus=${JSON.stringify(focus)}}`;
    if (this.selected) this.commit(updateBlockContent(this.options.getDeck(), this.slideIndex(), object.id, body));
    else this.commit(setCellContent(this.options.getDeck(), this.slideIndex(), object.id, body));
  }

  fillVideoProperties(video) {
    this.videoProperties.hidden = false;
    document.querySelector("#prop-video-fit").value = video.fit;
    document.querySelector("#prop-video-controls").checked = video.controls;
    document.querySelector("#prop-video-autoplay").checked = video.autoplay;
    document.querySelector("#prop-video-loop").checked = video.loop;
    document.querySelector("#prop-video-muted").checked = video.muted;
    document.querySelector("#prop-video-poster").value = video.poster;
  }

  applyVideoProperties() {
    if (!this.selected || this.selected.dataset.objectType !== "video") return;
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, {
      fit: document.querySelector("#prop-video-fit").value === "contain" ? null : "cover",
      controls: document.querySelector("#prop-video-controls").checked ? null : "false",
      autoplay: document.querySelector("#prop-video-autoplay").checked ? "true" : null,
      loop: document.querySelector("#prop-video-loop").checked ? "true" : null,
      muted: document.querySelector("#prop-video-muted").checked ? "true" : null,
      poster: document.querySelector("#prop-video-poster").value.trim() || null,
    }));
  }

  applyShapeProperties() {
    if (!this.selected || this.selected.dataset.objectType !== "shape") return;
    const shape = document.querySelector("#prop-shape").value;
    const fill = colorControlValue("prop-shape-fill");
    const stroke = colorControlValue("prop-shape-stroke");
    const strokeWidth = Number(document.querySelector("#prop-shape-stroke-width").value);
    const defaultFill = resolvedThemeColor(this.section(), "--shape-default-fill");
    const defaultStroke = resolvedThemeColor(this.section(), "--shape-default-stroke");
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, {
      shape: shape === "rectangle" ? null : shape,
      fill: fill === defaultFill ? null : fill,
      stroke: stroke === defaultStroke ? null : stroke,
      "stroke-width": strokeWidth === 2 ? null : strokeWidth,
      shadow: document.querySelector("#prop-shape-shadow").checked ? "true" : null,
    }));
  }

  openContentDialog() {
    if (!this.selected) return;
    const object = this.slide().overlays.find(item => item.id === this.selected.dataset.objectId);
    if (!object || ["image", "video"].includes(object.type)) return;
    this.dialogTarget = { kind: "overlay", id: object.id };
    document.querySelector("#content-dialog-title").textContent = object.type === "equation" ? "Edit LaTeX" : object.type === "shape" ? "Edit shape label" : "Edit Markdown";
    this.contentEditor.value = object.source;
    renderMarkdownPreview(object.source, this.preview, { breaks: true });
    this.dialog.showModal();
  }

  openCellDialog() {
    if (!this.selectedCell) return;
    const id = this.selectedCell.dataset.cellId;
    const cell = this.slide().cells.find(item => item.id === id);
    if (["image", "video"].includes(cell?.type)) {
      this.noSelection.textContent = `${cell.type === "image" ? "Image" : "Video"} cell: use its properties or Source mode.`;
      return;
    }
    if (cell && !cell.range && cell.source.trim()) {
      this.noSelection.textContent = `This mixed core content must be edited in Source mode.`;
      return;
    }
    this.dialogTarget = { kind: "cell", id };
    document.querySelector("#content-dialog-title").textContent = `Edit ${id} Markdown`;
    this.contentEditor.value = cell?.source || "";
    renderMarkdownPreview(cell?.source || "", this.preview);
    this.dialog.showModal();
  }

  openTitleDialog() {
    const slide = this.slide();
    if (!slide?.headingRange) return;
    this.clearSelection();
    this.dialogTarget = { kind: "title", id: slide.id };
    document.querySelector("#content-dialog-title").textContent = "Edit slide title";
    this.contentEditor.value = slide.titleSource;
    this.updateContentPreview();
    this.dialog.showModal();
  }

  applyContentDialog() {
    if (!this.dialogTarget) return;
    const next = this.dialogTarget.kind === "title"
      ? updateSlideTitle(this.options.getDeck(), this.slideIndex(), this.contentEditor.value)
      : this.dialogTarget.kind === "cell"
        ? setCellContent(this.options.getDeck(), this.slideIndex(), this.dialogTarget.id, this.contentEditor.value)
      : updateBlockContent(this.options.getDeck(), this.slideIndex(), this.dialogTarget.id, this.contentEditor.value);
    this.dialog.close();
    this.dialogTarget = null;
    this.commit(next);
  }

  addObject(type) {
    const deck = this.options.getDeck();
    const base = type === "equation" ? "equation" : "text";
    const id = this.uniqueId(`${base}-${this.slideIndex() + 1}`);
    const content = type === "equation" ? "\\[\nE = \\hbar \\omega\n\\]" : "Editable **Markdown**";
    this.commit(insertOverlay(deck, this.slideIndex(), { type, content, id }));
  }

  addShape(shape) {
    const id = this.uniqueId(`${shape}-${this.slideIndex() + 1}`);
    const content = ["sine", "cosine"].includes(shape) ? "" : "Editable **label**";
    this.commit(insertOverlay(this.options.getDeck(), this.slideIndex(), {
      type: "shape",
      content,
      id,
      x: 35,
      y: 35,
      w: 30,
      h: 20,
      attributes: shape === "rectangle" ? {} : { shape },
    }));
  }

  async addImage(file, position = null, cellId = null) {
    if (!file) return;
    const aspect = cellId ? null : await imageAspectRatio(file);
    const path = await this.options.importAsset(file);
    if (!path) return;
    const content = `![](${path}){fit=contain focus="50 50"}`;
    if (cellId) {
      this.commit(setCellContent(this.options.getDeck(), this.slideIndex(), cellId, content));
      return;
    }
    const id = this.uniqueId(`image-${this.slideIndex() + 1}`);
    const rect = this.section().getBoundingClientRect();
    const geometry = initialImageGeometry(aspect, rect.width / rect.height, position);
    this.commit(insertOverlay(this.options.getDeck(), this.slideIndex(), { type: "image", content, id, ...geometry }));
  }

  async addVideo(file, position = null) {
    if (!file) return;
    const slideId = this.slide().id;
    const imported = await this.options.importAsset(file);
    if (!imported) return;
    const path = typeof imported === "string" ? imported : imported.path;
    const id = this.uniqueId(`video-${this.slideIndex() + 1}`);
    const w = 40;
    const h = 22.5;
    this.commit(insertOverlay(this.options.getDeck(), this.slideIndex(), {
      type: "video",
      content: "",
      id,
      x: position ? clamp(round(position.x), 0, 100 - w) : 30,
      y: position ? clamp(round(position.y), 0, 100 - h) : 30,
      w,
      h,
      attributes: { src: path, poster: typeof imported === "string" ? null : imported.poster },
    }));
    if (typeof imported !== "string" && imported.completion) {
      imported.completion.then(() => {
        const video = this.section()?.querySelector(`[data-object-id="${CSS.escape(id)}"] video`);
        if (video) video.load();
      }).catch(() => {
        const deck = this.options.getDeck();
        const slideIndex = deck.slides.findIndex(slide => slide.id === slideId && slide.overlays.some(item => item.id === id && item.video?.source === path));
        if (slideIndex >= 0) this.commit(deleteOverlay(deck, slideIndex, id));
      });
    }
  }

  async replaceVideo(file) {
    if (!file || this.selected?.dataset.objectType !== "video") return;
    const objectId = this.selected.dataset.objectId;
    const original = this.slide().overlays.find(item => item.id === objectId)?.video;
    const slideId = this.slide().id;
    const imported = await this.options.importAsset(file);
    if (!imported) return;
    const path = typeof imported === "string" ? imported : imported.path;
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), objectId, {
      src: path,
      poster: typeof imported === "string" ? null : imported.poster,
    }));
    if (typeof imported !== "string" && imported.completion) {
      imported.completion.then(() => {
        const video = this.section()?.querySelector(`[data-object-id="${CSS.escape(objectId)}"] video`);
        if (video) video.load();
      }).catch(() => {
        const deck = this.options.getDeck();
        const slideIndex = deck.slides.findIndex(slide => slide.id === slideId && slide.overlays.some(item => item.id === objectId && item.video?.source === path));
        if (slideIndex >= 0 && original) {
          this.commit(updateOverlay(deck, slideIndex, objectId, { src: original.source, poster: original.poster || null }));
        }
      });
    }
  }

  replaceVideoPath(path) {
    if (!path || this.selected?.dataset.objectType !== "video") return;
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, { src: path }));
  }

  async replaceImage(file) {
    if (!file) return;
    const object = this.selected
      ? this.slide().overlays.find(item => item.id === this.selected.dataset.objectId)
      : this.selectedCell
        ? this.slide().cells.find(item => item.id === this.selectedCell.dataset.cellId)
        : null;
    if (!object?.image) return;
    const path = await this.options.importAsset(file);
    if (!path) return;
    this.replaceImagePath(path, object);
  }

  replaceImagePath(path, object = null) {
    object ||= this.selected
      ? this.slide().overlays.find(item => item.id === this.selected.dataset.objectId)
      : this.selectedCell
        ? this.slide().cells.find(item => item.id === this.selectedCell.dataset.cellId)
        : null;
    if (!object?.image || !path) return;
    const fit = object.image.attrs.values.fit || "contain";
    const focus = object.image.attrs.values.focus || "50 50";
    const title = object.image.title ? ` ${JSON.stringify(object.image.title)}` : "";
    const body = `![${object.image.alt}](${path}${title}){fit=${JSON.stringify(fit)} focus=${JSON.stringify(focus)}}`;
    if (this.selected) this.commit(updateBlockContent(this.options.getDeck(), this.slideIndex(), object.id, body));
    else this.commit(setCellContent(this.options.getDeck(), this.slideIndex(), object.id, body));
  }

  async openProjectImageDialog() {
    const dialog = document.querySelector("#project-image-dialog");
    const gallery = document.querySelector("#project-image-gallery");
    const status = document.querySelector("#project-image-status");
    const search = document.querySelector("#project-image-search");
    const previous = document.querySelector("#project-image-previous");
    const next = document.querySelector("#project-image-next");
    gallery.replaceChildren();
    search.value = "";
    status.textContent = "Loading images…";
    dialog.showModal();
    try {
      const assets = await this.options.listProjectImages();
      let page = 0;
      const render = () => {
        const result = projectAssetPage(assets, search.value, page);
        page = result.page;
        gallery.replaceChildren(...result.assets.map(asset => this.projectAssetChoice(asset, "image", () => this.replaceImagePath(asset.path))));
        previous.disabled = page === 0;
        next.disabled = page + 1 >= result.pages;
        status.textContent = result.count ? `${result.count} image${result.count === 1 ? "" : "s"} · Page ${page + 1} of ${result.pages}` : search.value ? "No images match your search" : "No images found in the presentation figures folder";
      };
      search.oninput = () => { page = 0; render(); };
      search.onkeydown = event => { if (event.key === "Enter") event.preventDefault(); };
      previous.onclick = () => { page -= 1; render(); };
      next.onclick = () => { page += 1; render(); };
      render();
      search.focus();
    } catch (error) {
      status.textContent = error.message;
    }
  }

  async openProjectVideoDialog() {
    const dialog = document.querySelector("#project-video-dialog");
    const gallery = document.querySelector("#project-video-gallery");
    const status = document.querySelector("#project-video-status");
    const search = document.querySelector("#project-video-search");
    const previous = document.querySelector("#project-video-previous");
    const next = document.querySelector("#project-video-next");
    gallery.replaceChildren();
    search.value = "";
    status.textContent = "Loading videos…";
    dialog.showModal();
    try {
      const assets = await this.options.listProjectVideos();
      let page = 0;
      const render = () => {
        const result = projectAssetPage(assets, search.value, page);
        page = result.page;
        gallery.replaceChildren(...result.assets.map(asset => this.projectAssetChoice(asset, "video", () => this.replaceVideoPath(asset.path))));
        previous.disabled = page === 0;
        next.disabled = page + 1 >= result.pages;
        status.textContent = result.count ? `${result.count} video${result.count === 1 ? "" : "s"} · Page ${page + 1} of ${result.pages}` : search.value ? "No videos match your search" : "No videos found in the presentation figures folder";
      };
      search.oninput = () => { page = 0; render(); };
      search.onkeydown = event => { if (event.key === "Enter") event.preventDefault(); };
      previous.onclick = () => { page -= 1; render(); };
      next.onclick = () => { page += 1; render(); };
      render();
      search.focus();
    } catch (error) {
      status.textContent = error.message;
    }
  }

  projectAssetChoice(asset, kind, select) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "project-image-choice";
    button.title = asset.path;
    const preview = document.createElement(kind === "video" ? "video" : "img");
    preview.src = this.options.resolveAsset(asset.path);
    if (kind === "video") {
      preview.muted = true;
      preview.preload = "metadata";
    } else preview.alt = "";
    const label = document.createElement("span");
    label.textContent = asset.path;
    button.append(preview, label);
    button.addEventListener("click", () => {
      button.closest("dialog").close();
      select();
    });
    return button;
  }

  onDrop(event) {
    if (!this.active()) return;
    event.preventDefault();
    const file = [...event.dataTransfer.files].find(item => item.type.startsWith("image/") || videoFile(item));
    if (!file) return;
    if (videoFile(file)) {
      const rect = this.section().getBoundingClientRect();
      this.addVideo(file, {
        x: 100 * (event.clientX - rect.left) / rect.width,
        y: 100 * (event.clientY - rect.top) / rect.height,
      });
      return;
    }
    const cell = event.target.closest(".slide-cell");
    if (cell) {
      this.addImage(file, null, cell.dataset.cellId);
      return;
    }
    const rect = this.section().getBoundingClientRect();
    this.addImage(file, {
      x: 100 * (event.clientX - rect.left) / rect.width,
      y: 100 * (event.clientY - rect.top) / rect.height,
    });
  }

  onPaste(event) {
    if (!this.active() || this.dialog.open
      || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)
      || document.activeElement?.isContentEditable) return;
    const file = clipboardImageFile(event.clipboardData);
    if (!file) return;
    event.preventDefault();
    const requestedName = window.prompt("Filename for pasted image:", file.name);
    const namedFile = renameClipboardImage(file, requestedName);
    if (!namedFile) return;
    const selectedObject = this.selected
      ? this.slide().overlays.find(item => item.id === this.selected.dataset.objectId)
      : this.selectedCell
        ? this.slide().cells.find(item => item.id === this.selectedCell.dataset.cellId)
        : null;
    if (selectedObject?.image) this.replaceImage(namedFile);
    else this.addImage(namedFile, null, this.selectedCell?.dataset.cellId || null);
  }

  duplicate() {
    if (!this.selected) return;
    const id = this.selected.dataset.objectId;
    this.commit(duplicateOverlay(this.options.getDeck(), this.slideIndex(), id, this.uniqueId(`${id}-copy`)));
  }

  remove() {
    if (!this.selected) return;
    this.commit(deleteOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId));
  }

  onKeyDown(event) {
    if (!this.active() || !this.selected || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    if (event.key === "Delete") { event.preventDefault(); this.remove(); return; }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d") { event.preventDefault(); this.duplicate(); return; }
    const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (!directions[event.key]) return;
    event.preventDefault();
    const object = this.slide().overlays.find(item => item.id === this.selected.dataset.objectId);
    if (!object || object.locked) return;
    const step = event.shiftKey ? 1 : 0.1;
    const [dx, dy] = directions[event.key];
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), object.id, {
      x: clamp(round(object.geometry.x + dx * step), 0, 100 - object.geometry.w),
      y: clamp(round(object.geometry.y + dy * step), 0, 100 - object.geometry.h),
    }));
  }

  uniqueId(prefix) {
    const ids = new Set(this.options.getDeck().slides.flatMap(slide => [slide.id, ...slide.overlays.map(item => item.id)]));
    let candidate = prefix;
    let counter = 2;
    while (ids.has(candidate)) candidate = `${prefix}-${counter++}`;
    return candidate;
  }

  commit(source) {
    const overlayId = this.selected?.dataset.objectId || null;
    const cellId = this.selectedCell?.dataset.cellId || null;
    this.options.commitSource(source);
    if (overlayId) {
      const overlay = [...(this.section()?.querySelectorAll(".slide-overlay") || [])]
        .find(item => item.dataset.objectId === overlayId);
      if (overlay) this.selectOverlay(overlay);
    } else if (cellId) {
      const cell = [...(this.section()?.querySelectorAll(".slide-cell") || [])]
        .find(item => item.dataset.cellId === cellId);
      if (cell) this.selectCell(cell);
    }
  }
}
