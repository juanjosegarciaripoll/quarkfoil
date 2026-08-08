import {
  deleteOverlay,
  duplicateOverlay,
  insertOverlay,
  setCellContent,
  updateBlockContent,
  updateHeadingLayout,
  updateOverlay,
  updateSlideTitle,
} from "./parser.js";
import { renderMarkdownPreview } from "./render.js";

const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));
const round = value => Math.round(value * 10) / 10;

export class DesignEditor {
  constructor(options) {
    this.options = options;
    this.selected = null;
    this.selectedCell = null;
    this.drag = null;
    this.dialogTarget = null;
    this.stage = document.querySelector("#stage");
    this.properties = document.querySelector("#object-properties");
    this.imageProperties = document.querySelector("#image-properties");
    this.fontProperties = document.querySelector("#font-properties");
    this.noSelection = document.querySelector("#no-selection");
    this.dialog = document.querySelector("#content-dialog");
    this.contentEditor = document.querySelector("#content-editor");
    this.preview = document.querySelector("#content-preview");
    this.bind();
  }

  bind() {
    this.stage.addEventListener("click", event => this.onClick(event));
    this.stage.addEventListener("dblclick", event => this.onDoubleClick(event));
    this.stage.addEventListener("pointerdown", event => this.onPointerDown(event));
    document.addEventListener("keydown", event => this.onKeyDown(event));
    document.querySelector("#layout-select").addEventListener("change", event => this.changeLayout(event.target.value));
    document.querySelector("#add-text").addEventListener("click", () => this.addObject("markdown"));
    document.querySelector("#add-equation").addEventListener("click", () => this.addObject("equation"));
    document.querySelector("#add-image").addEventListener("click", () => document.querySelector("#image-input").click());
    document.querySelector("#image-input").addEventListener("change", event => {
      this.addImage(event.target.files?.[0], null, this.selectedCell?.dataset.cellId || null);
      event.target.value = "";
    });
    document.querySelector("#duplicate-object").addEventListener("click", () => this.duplicate());
    document.querySelector("#delete-object").addEventListener("click", () => this.remove());
    document.querySelector("#edit-content").addEventListener("click", () => this.openContentDialog());
    this.contentEditor.addEventListener("input", () => renderMarkdownPreview(this.contentEditor.value, this.preview));
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
    document.querySelector("#prop-font-size").addEventListener("input", event => this.previewFontSize(event.target.value));
    document.querySelector("#prop-font-size").addEventListener("change", () => this.applyFontSize());
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
    this.fillProperties(object);
    document.querySelector("#duplicate-object").disabled = false;
    document.querySelector("#delete-object").disabled = false;
  }

  selectCell(element) {
    this.clearSelection();
    this.selectedCell = element;
    element.classList.add("selected-cell");
    const cell = this.slide().cells.find(item => item.id === element.dataset.cellId);
    this.noSelection.textContent = `Cell: ${element.dataset.cellId}. Double-click to edit.`;
    if (cell?.type === "image" && cell.image) {
      this.imageProperties.hidden = false;
      document.querySelector("#prop-fit").value = cell.image.attrs.values.fit || "contain";
      const focus = (cell.image.attrs.values.focus || "50 50").split(/[\s,]+/);
      document.querySelector("#prop-focus-x").value = focus[0] || 50;
      document.querySelector("#prop-focus-y").value = focus[1] || 50;
    }
  }

  clearSelection() {
    document.querySelectorAll(".selected-object,.selected-cell").forEach(item => item.classList.remove("selected-object", "selected-cell"));
    document.querySelectorAll(".resize-handle").forEach(item => item.remove());
    this.selected = null;
    this.selectedCell = null;
    this.properties.hidden = true;
    this.imageProperties.hidden = true;
    this.fontProperties.hidden = true;
    this.noSelection.hidden = false;
    this.noSelection.textContent = "Select an overlay or cell.";
    document.querySelector("#duplicate-object").disabled = true;
    document.querySelector("#delete-object").disabled = true;
  }

  fillProperties(object) {
    if (!object) return;
    document.querySelector("#prop-id").value = object.id;
    for (const key of ["x", "y", "w", "h", "z"]) document.querySelector(`#prop-${key}`).value = object.geometry[key];
    document.querySelector("#prop-fragment").value = object.fragment ?? "";
    document.querySelector("#prop-locked").checked = object.locked;
    if (object.type === "image" && object.image) {
      this.imageProperties.hidden = false;
      document.querySelector("#prop-fit").value = object.image.attrs.values.fit || "contain";
      const focus = (object.image.attrs.values.focus || "50 50").split(/[\s,]+/);
      document.querySelector("#prop-focus-x").value = focus[0] || 50;
      document.querySelector("#prop-focus-y").value = focus[1] || 50;
    } else {
      this.fontProperties.hidden = false;
      document.querySelector("#prop-font-size").value = object.fontSize;
      this.updateFontSizeOutput(object.fontSize);
      this.updateAlignmentButtons(object.alignment);
    }
  }

  updateFontSizeOutput(value) {
    document.querySelector("#prop-font-size-value").value = `${Number(value).toFixed(2)} em`;
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

  openContentDialog() {
    if (!this.selected) return;
    const object = this.slide().overlays.find(item => item.id === this.selected.dataset.objectId);
    if (!object || object.type === "image") return;
    this.dialogTarget = { kind: "overlay", id: object.id };
    document.querySelector("#content-dialog-title").textContent = object.type === "equation" ? "Edit LaTeX" : "Edit Markdown";
    this.contentEditor.value = object.source;
    renderMarkdownPreview(object.source, this.preview);
    this.dialog.showModal();
  }

  openCellDialog() {
    if (!this.selectedCell) return;
    const id = this.selectedCell.dataset.cellId;
    const cell = this.slide().cells.find(item => item.id === id);
    if (!cell?.range || cell.type === "image") {
      this.noSelection.textContent = cell?.type === "image"
        ? `Image cell: use the controls below or drop a replacement image.`
        : `This mixed core content must be edited in Source mode.`;
      return;
    }
    this.dialogTarget = { kind: "cell", id };
    document.querySelector("#content-dialog-title").textContent = `Edit ${id} Markdown`;
    this.contentEditor.value = cell.source;
    renderMarkdownPreview(cell.source, this.preview);
    this.dialog.showModal();
  }

  openTitleDialog() {
    const slide = this.slide();
    if (!slide?.headingRange) return;
    this.clearSelection();
    this.dialogTarget = { kind: "title", id: slide.id };
    document.querySelector("#content-dialog-title").textContent = "Edit slide title";
    this.contentEditor.value = slide.title;
    renderMarkdownPreview(slide.title, this.preview);
    this.dialog.showModal();
  }

  applyContentDialog() {
    if (!this.dialogTarget) return;
    const next = this.dialogTarget.kind === "title"
      ? updateSlideTitle(this.options.getDeck(), this.slideIndex(), this.contentEditor.value)
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

  async addImage(file, position = null, cellId = null) {
    if (!file) return;
    const path = await this.options.importAsset(file);
    if (!path) return;
    const id = this.uniqueId(`image-${this.slideIndex() + 1}`);
    const content = `![](${path}){fit=contain focus="50 50"}`;
    if (cellId) {
      this.commit(setCellContent(this.options.getDeck(), this.slideIndex(), cellId, content));
      return;
    }
    const coordinates = position || { x: 35, y: 25 };
    this.commit(insertOverlay(this.options.getDeck(), this.slideIndex(), { type: "image", content, id, x: coordinates.x, y: coordinates.y, w: 35, h: 35 }));
  }

  onDrop(event) {
    if (!this.active()) return;
    event.preventDefault();
    const file = [...event.dataTransfer.files].find(item => item.type.startsWith("image/"));
    if (!file) return;
    const cell = event.target.closest(".slide-cell");
    if (cell) {
      this.addImage(file, null, cell.dataset.cellId);
      return;
    }
    const rect = this.section().getBoundingClientRect();
    this.addImage(file, {
      x: clamp(round(100 * (event.clientX - rect.left) / rect.width), 0, 65),
      y: clamp(round(100 * (event.clientY - rect.top) / rect.height), 0, 65),
    });
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
