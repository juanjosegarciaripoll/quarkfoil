import {
  deleteOverlay,
  deleteOverlays,
  duplicateOverlay,
  insertArrow,
  insertOverlay,
  pasteOverlays,
  parseDeck,
  serializeOverlays,
  setCellContent,
  updateCellProperties,
  updateBlockContent,
  updateHeadingLayout,
  updateOverlay,
  updateSlideTitle,
  updateSlideProperties,
} from "./parser.js";
import { renderMarkdownPreview } from "./render.js";
import { createPlotSvg } from "./plot.js";
import { initialShapeGeometry, makeShapeSvg, SHAPES } from "./shapes.js";

const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));
const round = value => Math.round(value * 10) / 10;
const OVERLAY_CLIPBOARD_TYPE = "application/x-quarkfoil-overlays";
const OVERLAY_CLIPBOARD_STORAGE_KEY = "quarkfoil-overlay-clipboard";
export const overlayPasteOffset = (sourceSlideId, targetSlideId) => sourceSlideId && sourceSlideId !== targetSlideId ? 0 : 2;
export function storeOverlayClipboard(payload, storage = window.localStorage) {
  try { storage.setItem(OVERLAY_CLIPBOARD_STORAGE_KEY, JSON.stringify(payload)); return true; }
  catch { return false; }
}
export function storedOverlayClipboard(source = "", storage = window.localStorage) {
  try {
    const payload = JSON.parse(storage.getItem(OVERLAY_CLIPBOARD_STORAGE_KEY) || "null");
    if (payload?.version !== 1 || typeof payload.source !== "string") return null;
    return !source || payload.source === source ? payload : null;
  } catch { return null; }
}
export const videoFile = file => file?.type?.startsWith("video/") || /\.(?:avi|mkv|mp4|webm)$/i.test(file?.name || "");
export const repeatedActivation = (previous, key, time, interval = 450) => Boolean(
  previous && previous.key === key && time - previous.time >= 0 && time - previous.time <= interval,
);
export const deleteKey = key => key === "Delete" || key === "Del" || key === "Backspace";
export function applyMarkdownStyle(textarea, marker) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const selected = textarea.value.slice(start, end);
  const wrappedOutside = textarea.value.slice(start - marker.length, start) === marker
    && textarea.value.slice(end, end + marker.length) === marker;
  const wrappedInside = selected.startsWith(marker) && selected.endsWith(marker) && selected.length >= marker.length * 2;
  if (wrappedOutside) {
    textarea.setRangeText(selected, start - marker.length, end + marker.length, "select");
    textarea.setSelectionRange(start - marker.length, end - marker.length);
  } else if (wrappedInside) {
    const content = selected.slice(marker.length, -marker.length);
    textarea.setRangeText(content, start, end, "select");
  } else {
    textarea.setRangeText(`${marker}${selected}${marker}`, start, end, "select");
    if (start === end) textarea.setSelectionRange(start + marker.length, start + marker.length);
    else textarea.setSelectionRange(start + marker.length, end + marker.length);
  }
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

export function handleMarkdownShortcut(event) {
  if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey || !(event.currentTarget instanceof HTMLTextAreaElement)) return false;
  const marker = event.key.toLowerCase() === "b" ? "**" : event.key.toLowerCase() === "i" ? "*" : null;
  if (!marker) return false;
  event.preventDefault();
  applyMarkdownStyle(event.currentTarget, marker);
  return true;
}
export const canvasStartsMarquee = ({ overlay, cell, title }) => !overlay && !cell && !title;
export const canvasLinkTarget = target => target?.closest?.("a[href]") || null;
export function buildShapePalette(target, choose) {
  const buttons = Object.entries(SHAPES).map(([shape, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "shape-option";
    button.dataset.shape = shape;
    button.title = label;
    button.setAttribute("aria-label", `Add ${label}`);
    button.setAttribute("role", "menuitem");
    button.append(makeShapeSvg(shape));
    button.addEventListener("click", () => choose(shape));
    return button;
  });
  target.replaceChildren(...buttons);
  return buttons;
}
export function buildShapeSelect(target) {
  const options = Object.entries(SHAPES).map(([shape, label]) => {
    const option = document.createElement("option");
    option.value = shape;
    option.textContent = label;
    return option;
  });
  target.replaceChildren(...options);
  return options;
}
export async function resolveImportDestination(exists, proposed, choose) {
  return await exists ? await choose() : proposed;
}
export async function videoConflictDestination(error, destination, choose) {
  if (error?.status !== 409 || destination.overwrite) throw error;
  return await choose();
}
export const projectAssetPage = (assets, query, page, pageSize = 24) => {
  const needle = query.trim().toLocaleLowerCase();
  const filtered = needle ? assets.filter(asset => asset.path.toLocaleLowerCase().includes(needle)) : assets;
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(Math.max(0, page), pages - 1);
  return { assets: filtered.slice(current * pageSize, (current + 1) * pageSize), count: filtered.length, page: current, pages };
};

export function pageSlideIndex(current, count, key) {
  if (key === "Home") return 0;
  if (key === "End") return Math.max(0, count - 1);
  const direction = key === "PageUp" ? -1 : key === "PageDown" ? 1 : 0;
  return direction ? clamp(current + direction, 0, Math.max(0, count - 1)) : current;
}

export function boundarySlideShortcut(event, editingPane) {
  return (event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey
    && ["Home", "End"].includes(event.key) && editingPane.contains(event.target);
}

export function moveGeometryGroup(geometries, dx, dy) {
  if (!geometries.length) return [];
  const minimumX = Math.min(...geometries.map(item => item.x));
  const minimumY = Math.min(...geometries.map(item => item.y));
  const maximumX = Math.max(...geometries.map(item => item.x + item.w));
  const maximumY = Math.max(...geometries.map(item => item.y + item.h));
  const boundedX = clamp(round(dx), -minimumX, 100 - maximumX);
  const boundedY = clamp(round(dy), -minimumY, 100 - maximumY);
  return geometries.map(item => ({ ...item, x: round(item.x + boundedX), y: round(item.y + boundedY) }));
}

export function dialogDragPosition(rect, dx, dy, viewportWidth, viewportHeight) {
  return {
    left: Math.round(clamp(rect.left + dx, 0, Math.max(0, viewportWidth - rect.width))),
    top: Math.round(clamp(rect.top + dy, 0, Math.max(0, viewportHeight - rect.height))),
  };
}

export function arrowGeometry(arrow) {
  const x = Math.max(0, Math.min(arrow.x1, arrow.x2) - 1);
  const y = Math.max(0, Math.min(arrow.y1, arrow.y2) - 1);
  return {
    x: round(x),
    y: round(y),
    w: round(Math.min(100, Math.max(arrow.x1, arrow.x2) + 1) - x),
    h: round(Math.min(100, Math.max(arrow.y1, arrow.y2) + 1) - y),
  };
}

export function rectanglesIntersect(left, right) {
  return left.left <= right.right && left.right >= right.left && left.top <= right.bottom && left.bottom >= right.top;
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

function ensurePlotArea(root, background, curve) {
  const existing = root.querySelector(".area");
  if (existing) return existing;
  const encodedBaseline = root.getAttribute("data-area-baseline");
  let baseline = encodedBaseline === null ? Number.NaN : Number(encodedBaseline);
  if (!Number.isFinite(baseline)) {
    const horizontalAxis = root.querySelector(".axes path")?.getAttribute("d")?.match(/^M[-+.\d]+\s+([-+.\d]+)H/);
    baseline = horizontalAxis ? Number(horizontalAxis[1]) : Number(background.getAttribute("y")) + Number(background.getAttribute("height"));
  }
  if (!Number.isFinite(baseline)) return null;
  const area = document.createElementNS("http://www.w3.org/2000/svg", "g");
  area.setAttribute("class", "area");
  area.setAttribute("fill", "none");
  area.setAttribute("stroke", "none");
  for (const curvePath of curve.querySelectorAll("path")) {
    const d = curvePath.getAttribute("d") || "";
    const numbers = [...d.matchAll(/[-+]?(?:\d+(?:\.\d*)?|\.\d+)/g)].map(match => Number(match[0]));
    if (numbers.length < 4 || numbers.some(value => !Number.isFinite(value))) continue;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", `${d} L${numbers.at(-2)} ${baseline} L${numbers[0]} ${baseline} Z`);
    area.append(path);
  }
  if (!area.childElementCount) return null;
  root.setAttribute("data-area-baseline", String(baseline));
  root.insertBefore(area, curve);
  return area;
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
    this.cellProperties = document.querySelector("#cell-properties");
    this.imageProperties = document.querySelector("#image-properties");
    this.videoProperties = document.querySelector("#video-properties");
    this.plotProperties = document.querySelector("#plot-properties");
    this.arrowProperties = document.querySelector("#arrow-properties");
    this.shapeProperties = document.querySelector("#shape-properties");
    this.attributionProperties = document.querySelector("#attribution-properties");
    this.fontProperties = document.querySelector("#font-properties");
    this.noSelection = document.querySelector("#no-selection");
    this.dialog = document.querySelector("#content-dialog");
    this.colorDialog = document.querySelector("#color-dialog");
    this.colorDialogTarget = null;
    this.contentEditor = document.querySelector("#content-editor");
    this.preview = document.querySelector("#content-preview");
    this.plotDialog = document.querySelector("#plot-dialog");
    this.shapePicker = document.querySelector("#shape-picker");
    this.shapePaletteButton = document.querySelector("#shape-palette-button");
    this.shapePalette = document.querySelector("#shape-palette");
    buildShapeSelect(document.querySelector("#prop-shape"));
    this.imageInputPurpose = "add";
    this.videoInputPurpose = "add";
    this.lastCanvasActivation = null;
    this.bind();
  }

  bind() {
    document.querySelectorAll("#properties form").forEach(form => {
      form.addEventListener("submit", event => event.preventDefault());
      form.addEventListener("keydown", event => {
        if (event.key !== "Enter" || !event.target.matches("input")) return;
        event.preventDefault();
        if (event.target.type === "color") return;
        event.target.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });
    const bindColorControl = (id, apply) => {
      for (const suffix of ["", "-alpha"]) document.querySelector(`#${id}${suffix}`).addEventListener("change", apply);
    };
    this.stage.addEventListener("click", event => this.onClick(event));
    this.stage.addEventListener("dblclick", event => this.onDoubleClick(event));
    this.stage.addEventListener("pointerdown", event => this.onPointerDown(event));
    document.addEventListener("keydown", event => this.onKeyDown(event));
    document.addEventListener("copy", event => this.onCopy(event));
    document.addEventListener("cut", event => this.onCopy(event, { cut: true }));
    document.addEventListener("paste", event => this.onPaste(event));
    for (const id of ["prop-focus-x", "prop-focus-y", "prop-image-opacity", "prop-font-size", "prop-cell-font-size", "prop-rotation"]) bindRangeControl(id);
    document.querySelector("#layout-select").addEventListener("change", event => this.changeLayout(event.target.value));
    document.querySelector("#prop-slide-theme").addEventListener("change", event => this.applySlideProperties({ theme: event.target.value || null }));
    document.querySelector("#prop-slide-footer").addEventListener("change", event => this.applySlideProperties({ footer: event.target.checked ? null : "none" }));
    for (const name of ["background", "foreground"]) {
      bindColorControl(`prop-slide-${name}`, () => this.applySlideProperties({ [name]: colorControlValue(`prop-slide-${name}`) }));
    }
    document.querySelector("#reset-slide-background").addEventListener("click", () => this.applySlideProperties({ background: null }));
    document.querySelector("#reset-slide-foreground").addEventListener("click", () => this.applySlideProperties({ foreground: null }));
    document.querySelector("#add-text").addEventListener("click", () => this.addObject("markdown"));
    document.querySelector("#add-equation").addEventListener("click", () => this.addObject("equation"));
    document.querySelector("#add-image").addEventListener("click", () => this.openProjectImageDialog("add"));
    document.querySelector("#add-video").addEventListener("click", () => this.openProjectVideoDialog("add"));
    document.querySelector("#add-plot").addEventListener("click", () => this.openPlotDialog());
    const shapeButtons = buildShapePalette(this.shapePalette, shape => {
      this.addShape(shape);
      this.closeShapePalette({ restoreFocus: true });
    });
    this.shapePicker.addEventListener("pointerenter", () => this.openShapePalette());
    this.shapePicker.addEventListener("pointerleave", () => {
      if (!this.shapePicker.matches(":focus-within")) this.closeShapePalette();
    });
    this.shapePicker.addEventListener("focusin", () => this.openShapePalette());
    this.shapePicker.addEventListener("focusout", () => queueMicrotask(() => {
      if (!this.shapePicker.matches(":focus-within")) this.closeShapePalette();
    }));
    this.shapePaletteButton.addEventListener("click", () => this.openShapePalette());
    this.shapePaletteButton.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.preventDefault();
        this.closeShapePalette({ restoreFocus: true });
        return;
      }
      if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
      event.preventDefault();
      this.openShapePalette();
      shapeButtons[event.key === "ArrowDown" ? 0 : shapeButtons.length - 1].focus();
    });
    this.shapePalette.addEventListener("keydown", event => this.onShapePaletteKeyDown(event, shapeButtons));
    document.addEventListener("pointerdown", event => {
      if (!this.shapePicker.contains(event.target)) this.closeShapePalette();
    });
    document.querySelector("#add-arrow").addEventListener("click", () => this.addShape("arrow"));
    for (const id of ["plot-expression", "plot-expression-y", "plot-start", "plot-end", "plot-axes"]) {
      document.querySelector(`#${id}`).addEventListener("input", () => this.updatePlotPreview());
    }
    document.querySelector("#plot-points").addEventListener("input", event => {
      document.querySelector("#plot-points-value").textContent = event.target.value;
      this.updatePlotPreview();
    });
    document.querySelector("#plot-create").addEventListener("click", () => this.createPlot());
    document.querySelector("#prop-plot-background-enabled").addEventListener("change", () => {
      this.applyPlotProperties();
    });
    document.querySelector("#prop-plot-fill-enabled").addEventListener("change", () => {
      this.applyPlotProperties();
    });
    for (const name of ["background", "fill", "stroke"]) {
      bindColorControl(`prop-plot-${name}`, () => {
        if (name === "background") document.querySelector("#prop-plot-background-enabled").checked = true;
        if (name === "fill") document.querySelector("#prop-plot-fill-enabled").checked = true;
        this.applyPlotProperties();
      });
    }
    document.querySelector("#prop-plot-stroke-width").addEventListener("change", () => this.applyPlotProperties());
    for (const id of ["prop-arrow-stroke-width", "prop-arrow-stroke-style", "prop-arrow-heads"]) {
      document.querySelector(`#${id}`).addEventListener("change", () => this.applyArrowProperties());
    }
    document.querySelector("#prop-arrow-stroke").addEventListener("change", () => this.applyArrowProperties());
    document.querySelector("#image-input").addEventListener("change", event => {
      const file = event.target.files?.[0];
      document.querySelector("#project-file-dialog").close();
      if (this.imageInputPurpose === "replace") this.replaceImage(file);
      else this.addImage(file, null, this.selectedCell?.dataset.cellId || null);
      this.imageInputPurpose = "add";
      event.target.value = "";
    });
    document.querySelector("#video-input").addEventListener("change", event => {
      const file = event.target.files?.[0];
      document.querySelector("#project-file-dialog").close();
      if (this.videoInputPurpose === "replace") this.replaceVideo(file);
      else this.addVideo(file);
      this.videoInputPurpose = "add";
      event.target.value = "";
    });
    document.querySelector("#duplicate-object").addEventListener("click", () => this.duplicate());
    document.querySelector("#delete-object").addEventListener("click", () => this.remove());
    document.querySelector("#edit-content").addEventListener("click", () => this.openContentDialog());
    document.querySelector("#choose-project-image").addEventListener("click", () => this.openProjectImageDialog("replace"));
    document.querySelector("#choose-project-video").addEventListener("click", () => this.openProjectVideoDialog("replace"));
    this.contentEditor.addEventListener("input", () => this.updateContentPreview());
    this.contentEditor.addEventListener("keydown", handleMarkdownShortcut);
    this.dialog.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
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
    document.querySelector("#prop-rotation").addEventListener("input", event => this.previewRotation(event.target.value));
    document.querySelector("#prop-rotation").addEventListener("change", () => this.applyRotation());
    document.querySelector("#prop-fit").addEventListener("change", () => this.applyImageProperties());
    document.querySelector("#prop-focus-x").addEventListener("change", () => this.applyImageProperties());
    document.querySelector("#prop-focus-y").addEventListener("change", () => this.applyImageProperties());
    document.querySelector("#prop-image-opacity").addEventListener("change", () => this.applyImageProperties());
    for (const id of ["video-fit", "video-controls", "video-autoplay", "video-loop", "video-muted", "video-poster"]) {
      document.querySelector(`#prop-${id}`).addEventListener("change", () => this.applyVideoProperties());
    }
    for (const id of ["shape", "shape-stroke-width", "shape-stroke-style", "shape-shadow"]) {
      document.querySelector(`#prop-${id}`).addEventListener("change", () => this.applyShapeProperties());
    }
    for (const id of ["arc-start-angle", "arc-end-angle", "arc-heads"]) {
      document.querySelector(`#prop-${id}`).addEventListener("change", () => this.applyShapeProperties());
    }
    for (const name of ["fill", "stroke"]) bindColorControl(`prop-shape-${name}`, () => this.applyShapeProperties());
    document.querySelector("#prop-attribution-keys").addEventListener("change", () => this.applyAttributionKeys());
    document.querySelector("#prop-font-size").addEventListener("input", event => this.previewFontSize(event.target.value));
    document.querySelector("#prop-font-size").addEventListener("change", () => this.applyFontSize());
    document.querySelector("#prop-cell-font-size").addEventListener("input", event => this.previewCellFontSize(event.target.value));
    document.querySelector("#prop-cell-font-size").addEventListener("change", () => this.applyCellFontSize());
    document.querySelector("#reset-cell-font-size").addEventListener("click", () => this.applyCellFontSize(null));
    bindColorControl("prop-text-color", () => this.applyTextColor(colorControlValue("prop-text-color")));
    document.querySelectorAll("#properties input[type=color]").forEach(input => {
      input.addEventListener("click", event => {
        event.preventDefault();
        this.openColorDialog(input);
      });
      input.addEventListener("keydown", event => {
        if (!["Enter", " "].includes(event.key)) return;
        event.preventDefault();
        this.openColorDialog(input);
      });
    });
    this.colorDialog.addEventListener("cancel", () => { this.colorDialogTarget = null; });
    this.colorDialog.addEventListener("close", () => this.applyColorDialog());
    const colorHandle = document.querySelector("#color-dialog-handle");
    colorHandle.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      event.preventDefault();
      const rect = this.colorDialog.getBoundingClientRect();
      const origin = { x: event.clientX, y: event.clientY };
      colorHandle.setPointerCapture(event.pointerId);
      const move = moveEvent => {
        const position = dialogDragPosition(rect, moveEvent.clientX - origin.x, moveEvent.clientY - origin.y, window.innerWidth, window.innerHeight);
        Object.assign(this.colorDialog.style, { inset: "auto", left: `${position.left}px`, top: `${position.top}px`, margin: "0" });
      };
      const stop = () => {
        colorHandle.removeEventListener("pointermove", move);
        colorHandle.removeEventListener("pointerup", stop);
        colorHandle.removeEventListener("pointercancel", stop);
      };
      colorHandle.addEventListener("pointermove", move);
      colorHandle.addEventListener("pointerup", stop);
      colorHandle.addEventListener("pointercancel", stop);
    });
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

  openColorDialog(input) {
    if (this.colorDialog.open) return;
    this.colorDialogTarget = input;
    document.querySelector("#color-dialog-value").value = input.value || "#000000";
    const alpha = document.querySelector(`#${input.id}-alpha`);
    document.querySelector("#color-dialog-alpha-row").hidden = !alpha;
    document.querySelector("#color-dialog-alpha").value = alpha?.value || "100";
    this.colorDialog.returnValue = "";
    this.colorDialog.showModal();
  }

  applyColorDialog() {
    const target = this.colorDialogTarget;
    this.colorDialogTarget = null;
    if (!target || this.colorDialog.returnValue !== "apply") return;
    target.value = document.querySelector("#color-dialog-value").value;
    const alpha = document.querySelector(`#${target.id}-alpha`);
    if (alpha) alpha.value = document.querySelector("#color-dialog-alpha").value;
    target.dispatchEvent(new Event("change", { bubbles: true }));
  }

  openShapePalette() {
    if (this.suppressShapePaletteFocus) return;
    this.shapePicker.classList.add("palette-open");
    this.shapePaletteButton.setAttribute("aria-expanded", "true");
  }

  closeShapePalette({ restoreFocus = false } = {}) {
    this.shapePicker.classList.remove("palette-open");
    this.shapePaletteButton.setAttribute("aria-expanded", "false");
    if (!restoreFocus) return;
    this.suppressShapePaletteFocus = true;
    this.shapePaletteButton.focus({ preventScroll: true });
    queueMicrotask(() => { this.suppressShapePaletteFocus = false; });
  }

  onShapePaletteKeyDown(event, buttons) {
    if (event.key === "Escape") {
      event.preventDefault();
      this.closeShapePalette({ restoreFocus: true });
      return;
    }
    const steps = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -4, ArrowDown: 4 };
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      buttons[event.key === "Home" ? 0 : buttons.length - 1].focus();
      return;
    }
    if (!Object.hasOwn(steps, event.key)) return;
    event.preventDefault();
    const current = Math.max(0, buttons.indexOf(document.activeElement));
    buttons[(current + steps[event.key] + buttons.length) % buttons.length].focus();
  }

  updateContentPreview() {
    const source = this.dialogTarget?.kind === "title"
      ? this.contentEditor.value.replace(/\r?\n/g, "  \n")
      : this.contentEditor.value;
    renderMarkdownPreview(source, this.preview, {
      breaks: this.dialogTarget?.kind === "overlay",
      preserveBlankLines: this.dialogTarget?.kind !== "title",
    });
  }

  refresh() {
    this.clearSelection();
    const slide = this.slide();
    if (!slide) return;
    document.querySelector("#layout-select").value = slide.layout;
  }

  onClick(event) {
    if (!this.active() || this.drag) return;
    if (this.suppressClick) { this.suppressClick = false; return; }
    const overlay = event.target.closest(".slide-overlay");
    if (overlay) {
      this.stage.focus({ preventScroll: true });
      this.selectOverlay(overlay, { additive: event.shiftKey, toggle: event.shiftKey });
      return;
    }
    const cell = event.target.closest(".slide-cell");
    if (cell) {
      this.stage.focus({ preventScroll: true });
      this.selectCell(cell);
      return;
    }
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
    if (overlay) {
      this.selectOverlay(overlay);
      if (!["citation", "arrow"].includes(overlay.dataset.objectType)) this.openContentDialog();
    }
    else if (cell) { this.selectCell(cell); this.openCellDialog(); }
    else this.openTitleDialog();
  }

  selectedOverlayElements() {
    return [...(this.section()?.querySelectorAll(".slide-overlay.selected-object") || [])];
  }

  selectOverlay(element, { additive = false, toggle = false } = {}) {
    if (!additive) this.clearSelection();
    else if (toggle && element.classList.contains("selected-object")) {
      element.classList.remove("selected-object");
      element.querySelectorAll(".resize-handle").forEach(handle => handle.remove());
      const remaining = this.selectedOverlayElements();
      if (!remaining.length) { this.clearSelection(); return false; }
      element = remaining.at(-1);
    }
    this.slideProperties.hidden = true;
    this.selected = element;
    element.classList.add("selected-object");
    document.querySelectorAll(".resize-handle").forEach(handle => handle.remove());
    const object = this.slide().overlays.find(item => item.id === element.dataset.objectId);
    const handles = object?.arrow ? ["start", "end"] : ["nw", "ne", "se", "sw"];
    for (const corner of handles) {
      const handle = document.createElement("span");
      handle.className = `resize-handle ${object?.arrow ? "arrow-endpoint" : corner}`;
      if (object?.arrow) {
        handle.dataset.endpoint = corner;
        const x = corner === "start" ? object.arrow.x1 : object.arrow.x2;
        const y = corner === "start" ? object.arrow.y1 : object.arrow.y2;
        handle.style.left = `${100 * (x - object.geometry.x) / object.geometry.w}%`;
        handle.style.top = `${100 * (y - object.geometry.y) / object.geometry.h}%`;
      } else handle.dataset.corner = corner;
      element.append(handle);
    }
    this.noSelection.hidden = true;
    this.properties.hidden = false;
    this.fillProperties(object, element);
    document.querySelector("#duplicate-object").disabled = false;
    document.querySelector("#delete-object").disabled = false;
    return true;
  }

  selectCell(element) {
    this.clearSelection();
    this.slideProperties.hidden = true;
    this.selectedCell = element;
    element.classList.add("selected-cell");
    const cell = this.slide().cells.find(item => item.id === element.dataset.cellId);
    this.noSelection.textContent = `Cell: ${element.dataset.cellId}. Double-click to edit.`;
    this.cellProperties.hidden = false;
    setRangeControl("prop-cell-font-size", cell?.fontSize || 0.72);
    if (cell?.type === "image" && cell.image) {
      this.imageProperties.hidden = false;
      document.querySelector("#prop-fit").value = cell.image.attrs.values.fit || "contain";
      const focus = (cell.image.attrs.values.focus || "50 50").split(/[\s,]+/);
      setRangeControl("prop-focus-x", focus[0] || 50);
      setRangeControl("prop-focus-y", focus[1] || 50);
      setRangeControl("prop-image-opacity", 100 * Number(cell.image.attrs.values.opacity ?? 1));
      this.loadPlotProperties(cell.image.source);
    } else if (cell?.type === "video") {
      this.noSelection.textContent = "Video cell properties must currently be edited in Source mode.";
    }
    document.querySelector("#delete-object").disabled = !cell?.source.trim();
  }

  clearSelection() {
    document.querySelectorAll(".selected-object,.selected-cell").forEach(item => item.classList.remove("selected-object", "selected-cell"));
    document.querySelectorAll(".resize-handle").forEach(item => item.remove());
    this.selected = null;
    this.selectedCell = null;
    this.properties.hidden = true;
    this.imageProperties.hidden = true;
    this.videoProperties.hidden = true;
    this.plotProperties.hidden = true;
    this.arrowProperties.hidden = true;
    this.plotAsset = null;
    this.shapeProperties.hidden = true;
    this.attributionProperties.hidden = true;
    this.fontProperties.hidden = true;
    this.noSelection.hidden = true;
    this.slideProperties.hidden = false;
    this.cellProperties.hidden = true;
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
    document.querySelector("#prop-slide-footer").checked = slide.headingAttrs.values.footer !== "none";
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
    for (const key of ["x", "y", "w", "h", "z"]) {
      const input = document.querySelector(`#prop-${key}`);
      input.value = object.geometry[key];
      input.disabled = object.type === "arrow" && key !== "z";
    }
    document.querySelector("#prop-fragment").value = object.fragment ?? "";
    setRangeControl("prop-rotation", object.rotation);
    document.querySelector("#prop-locked").checked = object.locked;
    document.querySelector("#edit-content").hidden = ["image", "video", "citation", "arrow"].includes(object.type);
    if (object.type === "image" && object.image) {
      this.imageProperties.hidden = false;
      document.querySelector("#prop-fit").value = object.image.attrs.values.fit || "contain";
      const focus = (object.image.attrs.values.focus || "50 50").split(/[\s,]+/);
      setRangeControl("prop-focus-x", focus[0] || 50);
      setRangeControl("prop-focus-y", focus[1] || 50);
      setRangeControl("prop-image-opacity", 100 * Number(object.image.attrs.values.opacity ?? 1));
      this.loadPlotProperties(object.image.source);
    } else if (object.type === "video" && object.video) {
      this.fillVideoProperties(object.video);
    } else if (object.type === "arrow" && object.arrow) {
      this.arrowProperties.hidden = false;
      document.querySelector("#prop-arrow-stroke").value = colorInputValue(getComputedStyle(element.querySelector(".arrow-line")).stroke) || "#146c7e";
      document.querySelector("#prop-arrow-stroke-width").value = object.strokeWidth;
      document.querySelector("#prop-arrow-stroke-style").value = object.strokeStyle;
      document.querySelector("#prop-arrow-heads").value = object.arrow.heads;
    } else {
      if (object.type === "shape") {
        this.shapeProperties.hidden = false;
        document.querySelector("#prop-shape").value = object.shape;
        const surfaceStyle = getComputedStyle(element.querySelector(".shape-surface"));
        setColorControl("prop-shape-fill", surfaceStyle.fill, "#dbeff2");
        setColorControl("prop-shape-stroke", surfaceStyle.stroke, "#146c7e");
        document.querySelector("#prop-shape-stroke-width").value = object.strokeWidth;
        document.querySelector("#prop-shape-stroke-style").value = object.strokeStyle;
        document.querySelector("#prop-shape-shadow").checked = object.shadow;
        const arcProperties = document.querySelector("#arc-properties");
        arcProperties.hidden = object.shape !== "arc";
        if (object.shape === "arc") {
          document.querySelector("#prop-arc-start-angle").value = object.shapeParameters.startAngle;
          document.querySelector("#prop-arc-end-angle").value = object.shapeParameters.endAngle;
          document.querySelector("#prop-arc-heads").value = object.shapeParameters.heads;
        }
      } else if (object.type === "citation") {
        this.attributionProperties.hidden = false;
        document.querySelector("#prop-attribution-keys").value = object.attrs.values.keys || object.attrs.values.key || "";
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

  previewRotation(value) {
    if (!this.selected) return;
    this.selected.style.rotate = `${value}deg`;
  }

  applyRotation() {
    if (!this.selected) return;
    const rotation = Number(document.querySelector("#prop-rotation").value);
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, {
      rotation: rotation === 0 ? null : rotation,
    }));
  }

  previewCellFontSize(value) {
    if (!this.selectedCell) return;
    this.selectedCell.style.fontSize = `${value}em`;
  }

  applyCellFontSize(value = undefined) {
    if (!this.selectedCell) return;
    const size = value === null ? null : Number(document.querySelector("#prop-cell-font-size").value);
    this.commit(updateCellProperties(this.options.getDeck(), this.slideIndex(), this.selectedCell.dataset.cellId, {
      "font-size": size === null ? null : `${Math.round(size * 100) / 100}em`,
    }));
  }

  applyTextColor(color) {
    if (!this.selected || ["image", "video"].includes(this.selected.dataset.objectType)) return;
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, { color }));
  }

  applyAttributionKeys() {
    if (!this.selected || this.selected.dataset.objectType !== "citation") return;
    const input = document.querySelector("#prop-attribution-keys");
    const keys = [...new Set(input.value.split(/[\s,;]+/).filter(Boolean))];
    const invalid = keys.find(key => !/^[a-zA-Z0-9_:./+-]+$/.test(key));
    input.setCustomValidity(!keys.length ? "Enter at least one citation key" : invalid ? `Invalid citation key: ${invalid}` : "");
    if (!input.reportValidity()) return;
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, {
      key: keys.length === 1 ? keys[0] : null,
      keys: keys.length > 1 ? keys.join(" ") : null,
    }));
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
    if (canvasLinkTarget(event.target)) return;
    if (event.target.closest(".slide-overlay, .slide-cell")) this.stage.focus({ preventScroll: true });
    const handle = event.target.closest(".resize-handle");
    const overlay = event.target.closest(".slide-overlay");
    const cell = event.target.closest(".slide-cell");
    const title = event.target.closest(".slide-title");
    const key = overlay ? `overlay:${overlay.dataset.objectId}` : cell ? `cell:${cell.dataset.cellId}` : title ? "title" : null;
    if (key) {
      const activation = { key, time: performance.now() };
      if (!handle && repeatedActivation(this.lastCanvasActivation, key, activation.time)) {
        this.lastCanvasActivation = null;
        event.preventDefault();
        event.stopPropagation();
        if (overlay) {
          this.selectOverlay(overlay);
          if (!["citation", "arrow"].includes(overlay.dataset.objectType)) this.openContentDialog();
        } else if (cell) {
          this.selectCell(cell);
          this.openCellDialog();
        } else this.openTitleDialog();
        return;
      }
      this.lastCanvasActivation = activation;
    }
    if (!overlay) {
      const section = event.target.closest(".scientific-slide");
      if (section && canvasStartsMarquee({ overlay, cell, title })) this.startMarquee(event, section);
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    this.suppressClick = true;
    if (event.shiftKey && !handle) {
      if (!this.selectOverlay(overlay, { additive: true, toggle: true })) return;
    } else if (overlay.classList.contains("selected-object")) {
      this.selectOverlay(overlay, { additive: true });
    } else this.selectOverlay(overlay);
    const elements = handle ? [overlay] : this.selectedOverlayElements();
    const items = elements.map(element => ({
      element,
      object: this.slide().overlays.find(item => item.id === element.dataset.objectId),
    })).filter(item => item.object);
    if (!items.length || items.some(item => item.object.locked)) return;
    const rect = this.section().getBoundingClientRect();
    this.drag = {
      kind: handle?.dataset.endpoint ? "arrow-endpoint" : handle ? "resize" : "move",
      corner: handle?.dataset.corner,
      endpoint: handle?.dataset.endpoint,
      element: overlay,
      items: items.map(item => ({
        ...item,
        original: { ...item.object.geometry },
        originalArrow: item.object.arrow ? { ...item.object.arrow } : null,
      })),
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      rect,
    };
    overlay.setPointerCapture(event.pointerId);
    overlay.addEventListener("pointermove", this.boundMove = moveEvent => this.moveOverlay(moveEvent));
    overlay.addEventListener("pointerup", this.boundUp = upEvent => this.finishOverlay(upEvent));
  }

  startMarquee(event, section) {
    const initialIds = event.shiftKey ? new Set(this.selectedOverlayElements().map(element => element.dataset.objectId)) : new Set();
    this.marquee = {
      section,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      initialIds,
      active: false,
      signature: null,
    };
    section.setPointerCapture(event.pointerId);
    section.addEventListener("pointermove", this.boundMarqueeMove = moveEvent => this.moveMarquee(moveEvent));
    section.addEventListener("pointerup", this.boundMarqueeUp = upEvent => this.finishMarquee(upEvent));
    section.addEventListener("pointercancel", this.boundMarqueeCancel = cancelEvent => this.finishMarquee(cancelEvent));
  }

  moveMarquee(event) {
    const drag = this.marquee;
    if (!drag) return;
    if (!drag.active && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < 4) return;
    event.preventDefault();
    if (!drag.active) {
      drag.active = true;
      drag.box = document.createElement("div");
      drag.box.className = "selection-marquee";
      drag.section.append(drag.box);
    }
    const sectionRect = drag.section.getBoundingClientRect();
    const selection = {
      left: Math.min(drag.startX, event.clientX),
      right: Math.max(drag.startX, event.clientX),
      top: Math.min(drag.startY, event.clientY),
      bottom: Math.max(drag.startY, event.clientY),
    };
    drag.box.style.left = `${100 * (selection.left - sectionRect.left) / sectionRect.width}%`;
    drag.box.style.top = `${100 * (selection.top - sectionRect.top) / sectionRect.height}%`;
    drag.box.style.width = `${100 * (selection.right - selection.left) / sectionRect.width}%`;
    drag.box.style.height = `${100 * (selection.bottom - selection.top) / sectionRect.height}%`;
    const overlays = [...drag.section.querySelectorAll(".slide-overlay")];
    const intersecting = overlays.filter(element => rectanglesIntersect(selection, element.getBoundingClientRect()));
    const selectedIds = new Set([...drag.initialIds, ...intersecting.map(element => element.dataset.objectId)]);
    const signature = overlays.filter(element => selectedIds.has(element.dataset.objectId)).map(element => element.dataset.objectId).join("\n");
    if (signature === drag.signature) return;
    drag.signature = signature;
    const selected = overlays.filter(element => selectedIds.has(element.dataset.objectId));
    if (!selected.length) this.clearSelection();
    else {
      const previousPrimary = selected.find(element => element.dataset.objectId === this.selected?.dataset.objectId);
      const primary = intersecting.at(-1) || previousPrimary || selected.at(-1);
      this.selectOverlay(primary);
      selected.filter(element => element !== primary).forEach(element => element.classList.add("selected-object"));
    }
  }

  finishMarquee(event) {
    const drag = this.marquee;
    if (!drag) return;
    if (drag.section.hasPointerCapture(event.pointerId)) drag.section.releasePointerCapture(event.pointerId);
    drag.section.removeEventListener("pointermove", this.boundMarqueeMove);
    drag.section.removeEventListener("pointerup", this.boundMarqueeUp);
    drag.section.removeEventListener("pointercancel", this.boundMarqueeCancel);
    drag.box?.remove();
    if (drag.active) this.suppressClick = true;
    this.marquee = null;
  }

  moveOverlay(event) {
    if (!this.drag) return;
    const dx = 100 * (event.clientX - this.drag.startX) / this.drag.rect.width;
    const dy = 100 * (event.clientY - this.drag.startY) / this.drag.rect.height;
    if (this.drag.kind === "arrow-endpoint") {
      const item = this.drag.items[0];
      const next = { ...item.originalArrow };
      const suffix = this.drag.endpoint === "start" ? "1" : "2";
      next[`x${suffix}`] = clamp(round(item.originalArrow[`x${suffix}`] + dx), 0, 100);
      next[`y${suffix}`] = clamp(round(item.originalArrow[`y${suffix}`] + dy), 0, 100);
      item.nextArrow = next;
      item.next = { ...arrowGeometry(next), z: item.original.z };
      this.applyArrowToElement(item.element, next);
    } else if (this.drag.kind === "move") {
      const nextGroup = moveGeometryGroup(this.drag.items.map(item => item.original), dx, dy);
      this.drag.items.forEach((item, index) => {
        item.next = nextGroup[index];
        this.applyGeometryToElement(item.element, item.next);
      });
    } else {
      const original = this.drag.items[0].original;
      const next = { ...original };
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
      this.drag.items[0].next = next;
      this.applyGeometryToElement(this.drag.element, next);
    }
    const primary = this.drag.items.find(item => item.element === this.selected)?.next;
    if (primary) for (const key of ["x", "y", "w", "h"]) document.querySelector(`#prop-${key}`).value = primary[key];
  }

  finishOverlay(event) {
    const drag = this.drag;
    if (!drag) return;
    drag.element.releasePointerCapture(event.pointerId);
    drag.element.removeEventListener("pointermove", this.boundMove);
    drag.element.removeEventListener("pointerup", this.boundUp);
    this.drag = null;
    if (drag.kind === "arrow-endpoint") {
      const item = drag.items[0];
      const arrow = item.nextArrow || item.originalArrow;
      this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), item.object.id, {
        x1: arrow.x1, y1: arrow.y1, x2: arrow.x2, y2: arrow.y2,
      }));
    } else if (drag.kind === "move") {
      this.commitGeometryChanges(drag.items.map(item => ({ id: item.object.id, geometry: item.next || item.original })));
    } else {
      const geometry = drag.items[0].next || drag.items[0].original;
      this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), drag.element.dataset.objectId, {
        x: geometry.x, y: geometry.y, w: geometry.w, h: geometry.h,
      }));
    }
  }

  applyGeometryToElement(element, geometry) {
    element.style.left = `${geometry.x}%`;
    element.style.top = `${geometry.y}%`;
    element.style.width = `${geometry.w}%`;
    element.style.height = `${geometry.h}%`;
  }

  applyArrowToElement(element, arrow) {
    const geometry = arrowGeometry(arrow);
    this.applyGeometryToElement(element, geometry);
    const svg = element.querySelector(".arrow-svg");
    if (svg) {
      svg.style.left = `${-100 * geometry.x / geometry.w}%`;
      svg.style.top = `${-100 * geometry.y / geometry.h}%`;
      svg.style.width = `${10000 / geometry.w}%`;
      svg.style.height = `${10000 / geometry.h}%`;
    }
    for (const line of element.querySelectorAll(".arrow-svg line")) {
      line.setAttribute("x1", String(arrow.x1));
      line.setAttribute("y1", String(arrow.y1));
      line.setAttribute("x2", String(arrow.x2));
      line.setAttribute("y2", String(arrow.y2));
    }
    for (const handle of element.querySelectorAll(".arrow-endpoint")) {
      const suffix = handle.dataset.endpoint === "start" ? "1" : "2";
      handle.style.left = `${100 * (arrow[`x${suffix}`] - geometry.x) / geometry.w}%`;
      handle.style.top = `${100 * (arrow[`y${suffix}`] - geometry.y) / geometry.h}%`;
    }
  }

  commitGeometryChanges(changes) {
    let deck = this.options.getDeck();
    let source = deck.source;
    for (const change of changes) {
      const object = deck.slides[this.slideIndex()].overlays.find(item => item.id === change.id);
      const updates = object?.arrow ? {
        x1: round(object.arrow.x1 + change.geometry.x - object.geometry.x),
        y1: round(object.arrow.y1 + change.geometry.y - object.geometry.y),
        x2: round(object.arrow.x2 + change.geometry.x - object.geometry.x),
        y2: round(object.arrow.y2 + change.geometry.y - object.geometry.y),
      } : { x: change.geometry.x, y: change.geometry.y };
      source = updateOverlay(deck, this.slideIndex(), change.id, updates);
      deck = parseDeck(source);
    }
    this.commit(source);
  }

  changeLayout(layout) {
    const slide = this.slide();
    if (!slide) return;
    this.commit(updateHeadingLayout(this.options.getDeck(), this.slideIndex(), layout, slide.columns, slide.rows));
  }

  applyProperties() {
    if (!this.selected) return;
    const changes = {};
    const arrow = this.selected.dataset.objectType === "arrow";
    for (const key of arrow ? ["z"] : ["x", "y", "w", "h", "z"]) changes[key] = Number(document.querySelector(`#prop-${key}`).value);
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
    const opacity = Math.min(100, Math.max(0, Number(document.querySelector("#prop-image-opacity").value) || 0)) / 100;
    const title = object.image.title ? ` ${JSON.stringify(object.image.title)}` : "";
    const opacityAttribute = opacity === 1 ? "" : ` opacity=${JSON.stringify(String(opacity))}`;
    const body = `![${object.image.alt}](${object.image.source}${title}){fit=${JSON.stringify(fit)} focus=${JSON.stringify(focus)}${opacityAttribute}}`;
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
    const object = this.slide().overlays.find(item => item.id === this.selected.dataset.objectId);
    const requestedShape = document.querySelector("#prop-shape").value;
    const shape = Object.hasOwn(SHAPES, requestedShape) ? requestedShape : object?.shape || "rectangle";
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
      "stroke-style": document.querySelector("#prop-shape-stroke-style").value === "solid" ? null : document.querySelector("#prop-shape-stroke-style").value,
      shadow: document.querySelector("#prop-shape-shadow").checked ? "true" : null,
      "start-angle": shape === "arc" && Number(document.querySelector("#prop-arc-start-angle").value) !== 0 ? Number(document.querySelector("#prop-arc-start-angle").value) : null,
      "end-angle": shape === "arc" && Number(document.querySelector("#prop-arc-end-angle").value) !== 180 ? Number(document.querySelector("#prop-arc-end-angle").value) : null,
      heads: shape === "arc" && document.querySelector("#prop-arc-heads").value !== "none" ? document.querySelector("#prop-arc-heads").value : null,
    }));
  }

  applyArrowProperties() {
    if (!this.selected || this.selected.dataset.objectType !== "arrow") return;
    const strokeWidth = Math.max(0.25, Number(document.querySelector("#prop-arrow-stroke-width").value) || 2);
    const stroke = document.querySelector("#prop-arrow-stroke").value;
    const defaultStroke = resolvedThemeColor(this.section(), "--shape-default-stroke");
    this.commit(updateOverlay(this.options.getDeck(), this.slideIndex(), this.selected.dataset.objectId, {
      stroke: stroke === defaultStroke ? null : stroke,
      "stroke-width": strokeWidth === 2 ? null : strokeWidth,
      "stroke-style": document.querySelector("#prop-arrow-stroke-style").value === "solid" ? null : document.querySelector("#prop-arrow-stroke-style").value,
      heads: document.querySelector("#prop-arrow-heads").value === "end" ? null : document.querySelector("#prop-arrow-heads").value,
    }));
  }

  openContentDialog() {
    if (this.dialog.open) return;
    if (!this.selected) return;
    const object = this.slide().overlays.find(item => item.id === this.selected.dataset.objectId);
    if (!object || ["image", "video", "arrow"].includes(object.type)) return;
    this.dialogTarget = { kind: "overlay", id: object.id };
    document.querySelector("#content-dialog-title").textContent = object.type === "equation" ? "Edit LaTeX" : object.type === "shape" ? "Edit shape label" : "Edit Markdown";
    this.contentEditor.value = object.source;
    renderMarkdownPreview(object.source, this.preview, { breaks: true, preserveBlankLines: true });
    this.dialog.showModal();
    this.contentEditor.focus();
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
    renderMarkdownPreview(cell?.source || "", this.preview, { preserveBlankLines: true });
    this.dialog.showModal();
    this.contentEditor.focus();
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
    this.contentEditor.focus();
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
    if (shape === "arrow") {
      this.commit(insertArrow(this.options.getDeck(), this.slideIndex(), {
        id: this.uniqueId(`arrow-${this.slideIndex() + 1}`),
      }));
      return;
    }
    const id = this.uniqueId(`${shape}-${this.slideIndex() + 1}`);
    const content = "Editable **label**";
    const geometry = initialShapeGeometry(shape);
    this.commit(insertOverlay(this.options.getDeck(), this.slideIndex(), {
      type: "shape",
      content,
      id,
      ...geometry,
      attributes: shape === "rectangle" ? {} : { shape },
    }));
  }

  plotSvg() {
    return createPlotSvg(
      document.querySelector("#plot-expression").value.trim(),
      Number(document.querySelector("#plot-start").value),
      Number(document.querySelector("#plot-end").value),
      Number(document.querySelector("#plot-points").value),
      document.querySelector("#plot-axes").checked,
      document.querySelector("#plot-expression-y").value.trim(),
    );
  }

  openPlotDialog() {
    document.querySelector("#plot-status").textContent = "";
    document.querySelector("#plot-overwrite").checked = false;
    this.updatePlotPreview();
    this.plotDialog.showModal();
    document.querySelector("#plot-expression").focus();
  }

  updatePlotPreview() {
    const preview = document.querySelector("#plot-preview");
    const status = document.querySelector("#plot-status");
    try {
      preview.innerHTML = this.plotSvg();
      status.textContent = "";
    } catch (error) {
      preview.replaceChildren();
      status.textContent = error.message;
    }
  }

  async createPlot() {
    const status = document.querySelector("#plot-status");
    const button = document.querySelector("#plot-create");
    try {
      let filename = document.querySelector("#plot-filename").value.trim();
      if (!filename || /[\\/]/.test(filename)) throw new Error("Enter an SVG filename without a directory");
      if (!filename.toLowerCase().endsWith(".svg")) filename += ".svg";
      const svg = this.plotSvg();
      button.disabled = true;
      status.textContent = `Creating ${filename}…`;
      const file = new File([svg], filename, { type: "image/svg+xml" });
      const path = await this.options.importAsset(file, { name: filename, overwrite: document.querySelector("#plot-overwrite").checked });
      if (!path) return;
      this.addImagePath(path, null, 800 / 450, "stretch");
      this.plotDialog.close();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  async loadPlotProperties(path) {
    if (!path?.toLowerCase().endsWith(".svg")) return;
    const selection = this.selected?.dataset.objectId || `cell:${this.selectedCell?.dataset.cellId || ""}`;
    try {
      const response = await fetch(this.options.resolveAsset(path), { cache: "no-store" });
      if (!response.ok) return;
      const documentNode = new DOMParser().parseFromString(await response.text(), "image/svg+xml");
      const root = documentNode.documentElement;
      if (root.getAttribute("data-quarkfoil-plot") !== "1") return;
      const currentSelection = this.selected?.dataset.objectId || `cell:${this.selectedCell?.dataset.cellId || ""}`;
      if (currentSelection !== selection) return;
      const background = root.querySelector(".plot-background");
      const curve = root.querySelector(".curve");
      if (!background || !curve) return;
      const area = ensurePlotArea(root, background, curve);
      if (!area) return;
      this.plotAsset = { path, documentNode };
      this.plotProperties.hidden = false;
      const backgroundFill = background.getAttribute("fill") || "none";
      document.querySelector("#prop-plot-background-enabled").checked = backgroundFill !== "none";
      setColorControl("prop-plot-background", backgroundFill, "#ffffff");
      const areaFill = area.getAttribute("fill") || "none";
      document.querySelector("#prop-plot-fill-enabled").checked = areaFill !== "none";
      setColorControl("prop-plot-fill", areaFill, "#ffffff");
      setColorControl("prop-plot-stroke", curve.getAttribute("stroke"), "#146c7e");
      document.querySelector("#prop-plot-stroke-width").value = curve.getAttribute("stroke-width") || "3";
    } catch { /* Non-Quarkfoil or unreadable SVGs retain ordinary image properties. */ }
  }

  async applyPlotProperties() {
    if (!this.plotAsset) return;
    const { path, documentNode } = this.plotAsset;
    const background = documentNode.documentElement.querySelector(".plot-background");
    const area = documentNode.documentElement.querySelector(".area");
    const curve = documentNode.documentElement.querySelector(".curve");
    if (!background || !area || !curve) return;
    background.setAttribute("fill", document.querySelector("#prop-plot-background-enabled").checked ? colorControlValue("prop-plot-background") : "none");
    area.setAttribute("fill", document.querySelector("#prop-plot-fill-enabled").checked ? colorControlValue("prop-plot-fill") : "none");
    curve.setAttribute("stroke", colorControlValue("prop-plot-stroke"));
    const strokeWidth = Math.max(0.25, Number(document.querySelector("#prop-plot-stroke-width").value) || 3);
    curve.setAttribute("stroke-width", String(strokeWidth));
    const bounds = documentNode.documentElement.getAttribute("data-plot-bounds")?.split(/\s+/).map(Number);
    if (bounds?.length === 4 && bounds.every(Number.isFinite)) {
      const allowance = strokeWidth / 2;
      const viewBox = [bounds[0] - allowance, bounds[1] - allowance, bounds[2] + 2 * allowance, bounds[3] + 2 * allowance];
      documentNode.documentElement.setAttribute("viewBox", viewBox.join(" "));
      for (const [attribute, value] of [["x", viewBox[0]], ["y", viewBox[1]], ["width", viewBox[2]], ["height", viewBox[3]]]) background.setAttribute(attribute, String(value));
    }
    const source = new XMLSerializer().serializeToString(documentNode);
    const filename = path.replaceAll("\\", "/").split("/").at(-1);
    try {
      const savedPath = await this.options.importAsset(new File([source], filename, { type: "image/svg+xml" }), { name: filename, overwrite: true });
      if (savedPath) this.options.refreshAsset(savedPath);
    } catch { /* The application import handler reports the write failure. */ }
  }

  async addImage(file, position = null, cellId = null) {
    if (!file) return false;
    const aspect = cellId ? null : await imageAspectRatio(file);
    const path = await this.options.importAsset(file);
    if (!path) return false;
    const content = `![](${path}){fit=contain focus="50 50"}`;
    if (cellId) {
      this.commit(setCellContent(this.options.getDeck(), this.slideIndex(), cellId, content));
      return true;
    }
    const id = this.uniqueId(`image-${this.slideIndex() + 1}`);
    const rect = this.section().getBoundingClientRect();
    const geometry = initialImageGeometry(aspect, rect.width / rect.height, position);
    this.commit(insertOverlay(this.options.getDeck(), this.slideIndex(), { type: "image", content, id, ...geometry }));
    return true;
  }

  addImagePath(path, cellId = null, aspect = null, fit = "contain") {
    if (!path) return;
    const content = `![](${path}){fit=${fit} focus="50 50"}`;
    if (cellId) {
      this.commit(setCellContent(this.options.getDeck(), this.slideIndex(), cellId, content));
      return;
    }
    const rect = this.section().getBoundingClientRect();
    const geometry = aspect ? initialImageGeometry(aspect, rect.width / rect.height) : { x: 25, y: 25, w: 50, h: 50 };
    this.commit(insertOverlay(this.options.getDeck(), this.slideIndex(), {
      type: "image", content, id: this.uniqueId(`image-${this.slideIndex() + 1}`), ...geometry,
    }));
  }

  addVideoPath(path) {
    if (!path) return;
    this.commit(insertOverlay(this.options.getDeck(), this.slideIndex(), {
      type: "video", content: "", id: this.uniqueId(`video-${this.slideIndex() + 1}`),
      x: 30, y: 30, w: 40, h: 22.5, attributes: { src: path },
    }));
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
    const opacity = object.image.attrs.values.opacity;
    const title = object.image.title ? ` ${JSON.stringify(object.image.title)}` : "";
    const opacityAttribute = opacity === undefined ? "" : ` opacity=${JSON.stringify(opacity)}`;
    const body = `![${object.image.alt}](${path}${title}){fit=${JSON.stringify(fit)} focus=${JSON.stringify(focus)}${opacityAttribute}}`;
    if (this.selected) this.commit(updateBlockContent(this.options.getDeck(), this.slideIndex(), object.id, body));
    else this.commit(setCellContent(this.options.getDeck(), this.slideIndex(), object.id, body));
  }

  openProjectImageDialog(purpose = "replace") {
    const cellId = this.selectedCell?.dataset.cellId || null;
    this.options.browseProjectFiles("image", path => purpose === "add" ? this.addImagePath(path, cellId) : this.replaceImagePath(path), () => {
      this.imageInputPurpose = purpose;
      document.querySelector("#image-input").click();
    });
  }

  openProjectVideoDialog(purpose = "replace") {
    this.options.browseProjectFiles("video", path => purpose === "add" ? this.addVideoPath(path) : this.replaceVideoPath(path), () => {
      this.videoInputPurpose = purpose;
      document.querySelector("#video-input").click();
    });
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
    if (file) {
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
      return;
    }
    let internal = null;
    try {
      const encoded = event.clipboardData?.getData(OVERLAY_CLIPBOARD_TYPE) || "";
      if (encoded) internal = JSON.parse(encoded);
    } catch { /* Some browsers expose only standard clipboard types. */ }
    const plainSource = event.clipboardData?.getData("text/plain") || "";
    if (!internal) internal = storedOverlayClipboard(plainSource);
    const source = internal?.source || plainSource;
    const offset = overlayPasteOffset(internal?.sourceSlideId, this.slide().id);
    const pasted = pasteOverlays(this.options.getDeck(), this.slideIndex(), source || "", offset);
    if (!pasted) return;
    event.preventDefault();
    this.options.commitSource(pasted.source);
    pasted.ids.forEach((id, index) => {
      const overlay = this.section()?.querySelector(`[data-object-id="${CSS.escape(id)}"]`);
      if (overlay) this.selectOverlay(overlay, { additive: index > 0 });
    });
  }

  onCopy(event, { cut = false } = {}) {
    if (!this.active() || this.dialog.open || !this.selected
      || ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)
      || document.activeElement?.isContentEditable) return;
    const ids = this.selectedOverlayElements().map(element => element.dataset.objectId);
    if (!ids.length || !event.clipboardData) return;
    const source = serializeOverlays(this.options.getDeck(), this.slideIndex(), ids);
    const payload = { version: 1, sourceSlideId: this.slide().id, source };
    event.preventDefault();
    event.clipboardData.setData("text/plain", source);
    try {
      event.clipboardData.setData(OVERLAY_CLIPBOARD_TYPE, JSON.stringify(payload));
    } catch { /* Plain text remains portable. */ }
    storeOverlayClipboard(payload);
    if (cut) this.commit(deleteOverlays(this.options.getDeck(), this.slideIndex(), ids));
  }

  duplicate() {
    if (!this.selected) return;
    const id = this.selected.dataset.objectId;
    const copyId = this.uniqueId(`${id}-copy`);
    this.commit(duplicateOverlay(this.options.getDeck(), this.slideIndex(), id, copyId));
    const copy = this.section()?.querySelector(`[data-object-id="${CSS.escape(copyId)}"]`);
    if (copy) this.selectOverlay(copy);
  }

  remove() {
    if (this.selected) {
      const ids = this.selectedOverlayElements().map(element => element.dataset.objectId);
      this.commit(deleteOverlays(this.options.getDeck(), this.slideIndex(), ids));
      return;
    }
    if (this.selectedCell) {
      const cell = this.slide().cells.find(item => item.id === this.selectedCell.dataset.cellId);
      if (cell?.source.trim()) this.commit(setCellContent(this.options.getDeck(), this.slideIndex(), cell.id, ""));
    }
  }

  onKeyDown(event) {
    if (!this.active() || (!this.selected && !this.selectedCell)) return;
    if (event.key === "Escape" && !event.target.closest("dialog[open]")) { event.preventDefault(); this.clearSelection(); return; }
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    if (deleteKey(event.key)) { event.preventDefault(); this.remove(); return; }
    if (!this.selected) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d") { event.preventDefault(); this.duplicate(); return; }
    const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (!directions[event.key]) return;
    event.preventDefault();
    const elements = this.selectedOverlayElements();
    const objects = elements.map(element => this.slide().overlays.find(item => item.id === element.dataset.objectId)).filter(Boolean);
    if (!objects.length || objects.some(object => object.locked)) return;
    const step = event.shiftKey ? 1 : 0.1;
    const [dx, dy] = directions[event.key];
    const moved = moveGeometryGroup(objects.map(object => object.geometry), dx * step, dy * step);
    this.commitGeometryChanges(objects.map((object, index) => ({ id: object.id, geometry: moved[index] })));
  }

  uniqueId(prefix) {
    const ids = new Set(this.options.getDeck().slides.flatMap(slide => [slide.id, ...slide.overlays.map(item => item.id)]));
    let candidate = prefix;
    let counter = 2;
    while (ids.has(candidate)) candidate = `${prefix}-${counter++}`;
    return candidate;
  }

  commit(source) {
    const overlayIds = this.selectedOverlayElements().map(element => element.dataset.objectId);
    const overlayId = this.selected?.dataset.objectId || null;
    const cellId = this.selectedCell?.dataset.cellId || null;
    this.options.commitSource(source);
    if (overlayId) {
      const overlays = [...(this.section()?.querySelectorAll(".slide-overlay") || [])];
      const orderedIds = [...overlayIds.filter(id => id !== overlayId), overlayId];
      orderedIds.forEach((id, index) => {
        const overlay = overlays.find(item => item.dataset.objectId === id);
        if (overlay) this.selectOverlay(overlay, { additive: index > 0 });
      });
    } else if (cellId) {
      const cell = [...(this.section()?.querySelectorAll(".slide-cell") || [])]
        .find(item => item.dataset.cellId === cellId);
      if (cell) this.selectCell(cell);
    }
  }
}
