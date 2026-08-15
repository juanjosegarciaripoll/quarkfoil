import { deleteSection, duplicateSlide, emptyTrash, importSlide, insertOverlay, insertSection, insertSlide, moveSection, moveSlide, normalizeDeck, parseDeck, permanentlyDeleteSlide, restoreSlide, trashSlide, updateSectionTitle, updateSlideNotes } from "./parser.js";
import { renderDeck, syncVideoPlayback } from "./render.js";
import { DesignEditor, handleMarkdownShortcut, pageSlideIndex, projectAssetPage, resolveImportDestination } from "./editor.js";
import { saveSnapshot } from "./storage.js";
import { briefReference, formatBibliography, parseBibliography, prepareBibliography, renameBibliographyEntry, uniqueCitationKey } from "./bibliography.js";
import { externalDeckAction, responseRevision } from "./external.js";

const STARTER = `---
title: Quarkfoil
author: Your name
aspect-ratio: 16:9
theme: scientific-light
defaults:
  footer: Editable Markdown · Reveal.js
---

# Quarkfoil {.title-slide .layout-1}

A browser-native scientific presentation

---

## Structured and free-form {.layout-1-2 columns="42 58" rows="54 46"}

::: left
### Markdown remains the source

- Resize this grid in **Design** mode.
- Double-click Markdown overlays to edit them.
- Equations stay as LaTeX.

\\[
H = -J \\sum_{\\langle i,j\\rangle}
  (S_i^xS_j^x+S_i^yS_j^y)
\\]
:::

::: top-right
### Images

Drop an image onto the slide or add one from the toolbar.
:::

::: bottom-right
### Presentation

Switch to **Present** mode for normal Reveal navigation.
:::

::: overlay {#annotation type="equation" x="50" y="57" w="40" h="12" z="10"}
\\[
J_{\\mathrm{ex}} \\sim \\frac{t^2}{U}
\\]
:::
`;

const query = new URLSearchParams(location.search);

const state = {
  source: STARTER,
  savedSource: "",
  deck: null,
  mode: ["source", "design", "present"].includes(query.get("mode")) ? query.get("mode") : "design",
  currentSlide: Math.max(0, Number(query.get("slide") || 1) - 1),
  selectedSection: null,
  collapsedSections: new Set(),
  local: false,
  config: null,
  serverHash: null,
  fileHandle: null,
  directoryHandle: null,
  filename: "presentation.md",
  undo: [],
  redo: [],
  objectUrls: new Map(),
  assetVersions: new Map(),
  bibliographySource: "",
  bibliographyHash: null,
  bibliographyPdfs: {},
  bibliography: null,
  externalChange: null,
};

const elements = {
  workspace: document.querySelector("#workspace"),
  slides: document.querySelector("#slides"),
  slideList: document.querySelector("#slide-list"),
  source: document.querySelector("#source-editor"),
  sourcePane: document.querySelector("#source-pane"),
  notes: document.querySelector("#slide-notes"),
  notesResizer: document.querySelector("#notes-resizer"),
  save: document.querySelector("#save-button"),
  download: document.querySelector("#download-button"),
  saveState: document.querySelector("#save-state"),
};

let reveal;
let editor;
let snapshotTimer;
let reloadToken = null;
let reloadCheckPending = false;
let lastReloadCheck = 0;
let deckCheckPending = false;
let lastDeckCheck = 0;
let deckChannel = null;
let deckClaim = null;
let bibliographyOpenPending = false;

function assetResolver(source) {
  if (state.objectUrls.has(source)) return state.objectUrls.get(source);
  if (state.local) {
    const path = `/project/${source.replaceAll("\\", "/").split("/").map(encodeURIComponent).join("/")}`;
    const version = state.assetVersions.get(source);
    return version ? `${path}?v=${version}` : path;
  }
  return source;
}

function refreshAsset(path) {
  state.assetVersions.set(path, Math.max(Date.now(), (state.assetVersions.get(path) || 0) + 1));
  const resolved = assetResolver(path);
  document.querySelectorAll(".slide-image").forEach(element => {
    if (element.dataset.source !== path) return;
    if (element instanceof HTMLImageElement) element.src = resolved;
    else element.querySelector("image")?.setAttribute("href", resolved);
  });
}

async function pollForReload() {
  if (!state.local || !state.config?.reload || document.hidden || reloadCheckPending) return;
  const now = Date.now();
  if (now - lastReloadCheck < 750) return;
  lastReloadCheck = now;
  reloadCheckPending = true;
  try {
    const response = await fetch("/api/reload", { cache: "no-store" });
    if (!response.ok) return;
    const { token } = await response.json();
    if (reloadToken && token !== reloadToken) location.reload();
    reloadToken = token;
  } catch {
    // A Python reload briefly closes the listener; the next action reconnects.
  } finally {
    reloadCheckPending = false;
  }
}

function bindReloadChecks() {
  window.addEventListener("focus", pollForReload);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) pollForReload();
  });
  document.addEventListener("pointerdown", pollForReload, { capture: true });
  document.addEventListener("keydown", pollForReload, { capture: true });
}

async function hashText(text) {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join("");
}

function currentBrowserSource() {
  return state.mode === "source" && elements.source.value !== state.source ? elements.source.value : state.source;
}

function browserHasUnsavedChanges() {
  return currentBrowserSource() !== state.savedSource;
}

function textEditingTarget(target) {
  return target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
}

function deckValidationError(source) {
  try {
    const deck = parseDeck(source);
    const fatal = deck.diagnostics.find(item => item.level === "error");
    if (!fatal) return "";
    const location = fatal.slide ? `Slide ${fatal.slide}: ` : "";
    return `${location}${fatal.message}`;
  } catch (error) { return error.message; }
}

function clearExternalChange() {
  state.externalChange = null;
  document.querySelector("#external-change-banner").hidden = true;
  updateDirtyState();
}

function showExternalChange(source, hash, error = "") {
  state.externalChange = { source, hash, error };
  const message = error
    ? `The presentation changed on disk but is invalid: ${error}`
    : "The presentation changed on disk while the browser had unsaved or active edits.";
  document.querySelector("#external-change-message").textContent = message;
  document.querySelector("#external-change-banner").hidden = false;
  updateDirtyState();
  const dialog = document.querySelector("#external-change-dialog");
  if (dialog.open) {
    document.querySelector("#external-disk-source").value = source;
    document.querySelector("#external-change-detail").textContent = error
      ? `The disk version cannot be loaded until its Markdown is repaired: ${error}`
      : "A newer disk version arrived while this comparison was open. Review it before applying a merge.";
    document.querySelector("#external-use-disk").disabled = Boolean(error);
  }
}

function resetHistory() {
  state.undo.length = 0;
  state.redo.length = 0;
  updateHistoryButtons();
}

function applyExternalDeck(source, hash, message) {
  const error = deckValidationError(source);
  if (error) throw new Error(error);
  state.serverHash = hash;
  state.savedSource = source;
  state.externalChange = null;
  resetHistory();
  parseAndRender(source, { preserveSlide: true });
  document.querySelector("#external-change-banner").hidden = true;
  if (message) showStatus(message);
}

function openExternalChangeDialog() {
  const change = state.externalChange;
  if (!change) return;
  const browserSource = currentBrowserSource();
  document.querySelector("#external-browser-source").value = browserSource;
  document.querySelector("#external-disk-source").value = change.source;
  document.querySelector("#external-merged-source").value = browserSource;
  document.querySelector("#external-change-detail").textContent = change.error
    ? `The disk version is invalid and cannot be loaded directly: ${change.error}`
    : "Compare both revisions, use the disk version, or edit a reconciled result below.";
  document.querySelector("#external-use-disk").disabled = Boolean(change.error);
  const status = document.querySelector("#external-merge-status");
  status.textContent = "Saving remains blocked until the external change is reconciled.";
  status.classList.remove("error");
  const dialog = document.querySelector("#external-change-dialog");
  if (!dialog.open) dialog.showModal();
}

async function pollForExternalDeck({ force = false } = {}) {
  if (!state.local || document.hidden || deckCheckPending) return false;
  if (document.querySelector("#content-dialog[open]") || editor?.drag || editor?.marquee) return false;
  const now = Date.now();
  if (!force && now - lastDeckCheck < 900) return false;
  lastDeckCheck = now;
  deckCheckPending = true;
  try {
    const observedHash = state.externalChange?.hash || state.serverHash;
    const response = await fetch(`/api/deck?path=${encodeURIComponent(state.config.deck)}`, {
      cache: "no-store",
      headers: observedHash ? { "If-None-Match": `"${observedHash}"` } : {},
    });
    if (response.status === 304) return await pollForExternalBibliography();
    if (!response.ok) {
      if (response.status === 400) {
        const result = await response.json().catch(() => ({}));
        if (result.hash && result.hash !== observedHash) {
          showExternalChange("", result.hash, result.error || "The disk version cannot be read");
          return true;
        }
      }
      return false;
    }
    const source = await response.text();
    const hash = responseRevision(response) || await hashText(source);
    const error = deckValidationError(source);
    const action = externalDeckAction({
      knownHash: observedHash,
      diskHash: hash,
      dirty: browserHasUnsavedChanges() || Boolean(state.externalChange),
      valid: !error,
    });
    if (action === "unchanged") return false;
    if (action === "reload") {
      applyExternalDeck(source, hash, "Reloaded external changes");
      await pollForExternalBibliography();
    }
    else showExternalChange(source, hash, error);
    return true;
  } catch {
    return false;
  } finally {
    deckCheckPending = false;
  }
}

function bindExternalDeckChecks() {
  window.addEventListener("focus", () => pollForExternalDeck());
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) pollForExternalDeck({ force: true });
  });
  document.addEventListener("pointerdown", () => pollForExternalDeck(), { capture: true });
  document.addEventListener("keydown", () => pollForExternalDeck(), { capture: true });
  setInterval(() => pollForExternalDeck(), 1200);
}

function parseAndRender(source, { preserveSlide = true } = {}) {
  const previous = preserveSlide ? state.currentSlide : 0;
  const previousId = preserveSlide ? state.deck?.slides[state.currentSlide]?.id : null;
  const deck = parseDeck(source);
  const fatal = deck.diagnostics.find(item => item.level === "error");
  if (fatal) {
    const location = fatal.slide ? `Slide ${fatal.slide}: ` : "";
    throw new Error(`${location}${fatal.message}. The last valid presentation is unchanged.`);
  }
  state.source = source;
  state.deck = deck;
  document.title = deck.metadata?.title ? String(deck.metadata.title) : "Quarkfoil";
  const matchingSlide = previousId ? deck.slides.findIndex(slide => slide.id === previousId) : -1;
  state.currentSlide = matchingSlide >= 0 ? matchingSlide : Math.min(previous, Math.max(0, deck.slides.length - 1));
  if (!deck.sections.some(section => section.id === state.selectedSection)) state.selectedSection = null;
  state.collapsedSections = new Set([...state.collapsedSections].filter(id => deck.sections.some(section => section.id === id)));
  elements.source.value = source;
  elements.notes.value = deck.slides[state.currentSlide]?.notes || "";
  updateDirtyState();
  state.bibliography = prepareBibliography(state.bibliographySource, deck, state.local ? state.bibliographyPdfs : {});
  renderDeck(deck, elements.slides, assetResolver, state.bibliography);
  rebuildSlideList();
  if (reveal) {
    reveal.sync();
    reveal.slide(state.currentSlide);
  }
  editor?.refresh();
  scheduleSnapshot();
  return deck;
}

function commitSource(source, record = true) {
  if (source === state.source) return true;
  const previous = state.source;
  try {
    parseAndRender(source);
    if (record) {
      state.undo.push(previous);
      if (state.undo.length > 100) state.undo.shift();
      state.redo.length = 0;
      updateHistoryButtons();
    }
    return true;
  } catch (error) {
    showStatus(error.message, true);
    elements.source.value = source;
    return false;
  }
}

function undo() {
  const source = state.undo.pop();
  if (source === undefined) return;
  state.redo.push(state.source);
  parseAndRender(source);
  updateHistoryButtons();
}

function redo() {
  const source = state.redo.pop();
  if (source === undefined) return;
  state.undo.push(state.source);
  parseAndRender(source);
  updateHistoryButtons();
}

function updateHistoryButtons() {
  document.querySelector("#undo-button").disabled = !state.undo.length;
  document.querySelector("#redo-button").disabled = !state.redo.length;
}

function rebuildSlideList() {
  let activeSection = null;
  let currentSection = null;
  for (const item of state.deck.items) {
    if (item.kind === "section") activeSection = item.id;
    else if (item.index === state.currentSlide) currentSection = activeSection;
  }
  activeSection = null;
  const entries = [];
  for (const item of state.deck.items) {
    if (item.kind === "section") {
      activeSection = item.id;
      const li = document.createElement("li");
      li.className = "section-entry";
      li.classList.toggle("trash-section", item.isTrash);
      li.classList.toggle("section-selected", item.id === state.selectedSection);
      li.classList.toggle("contains-current", item.id === currentSection);
      const collapsed = state.collapsedSections.has(item.id);
      const collapse = document.createElement("button");
      collapse.type = "button";
      collapse.className = "section-collapse";
      collapse.textContent = collapsed ? "▸" : "▾";
      collapse.title = collapsed ? `Expand ${item.title}` : `Collapse ${item.title}`;
      collapse.setAttribute("aria-expanded", String(!collapsed));
      collapse.addEventListener("click", event => {
        event.stopPropagation();
        if (collapsed) state.collapsedSections.delete(item.id);
        else state.collapsedSections.add(item.id);
        rebuildSlideList();
      });
      const button = document.createElement("button");
      button.type = "button";
      button.className = "section-title";
      button.textContent = collapsed ? `${item.title} (${item.slideCount})` : item.title;
      button.title = item.isTrash ? "Select Trash" : "Click to select; double-click to rename";
      button.addEventListener("click", () => {
        if (!requestMode(state.mode === "source" ? "design" : state.mode)) return;
        state.selectedSection = item.id;
        rebuildSlideList();
      });
      if (!item.isTrash) {
        button.addEventListener("dblclick", event => {
          event.preventDefault();
          renameSection(item.id);
        });
      }
      li.append(collapse, button);
      entries.push(li);
      continue;
    }
    if (activeSection && state.collapsedSections.has(activeSection)) continue;
    const li = document.createElement("li");
    li.classList.toggle("trashed-slide", item.trashed);
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${item.trashed ? "↺" : `${item.index + 1}.`} ${item.title || "Untitled"}`;
    button.title = "Click to select; double-click to rename";
    button.classList.toggle("current", item.index === state.currentSlide);
    button.addEventListener("click", () => {
      state.selectedSection = null;
      reveal.slide(item.index);
      requestMode(state.mode === "source" ? "design" : state.mode);
      rebuildSlideList();
    });
    button.addEventListener("dblclick", event => {
      event.preventDefault();
      state.selectedSection = null;
      state.currentSlide = item.index;
      reveal.slide(item.index);
      if (requestMode("design")) setTimeout(() => editor?.openTitleDialog(), 0);
    });
    li.append(button);
    entries.push(li);
  }
  elements.slideList.replaceChildren(...entries);
  const selectedSection = state.deck.sections.find(section => section.id === state.selectedSection);
  const selectedSlide = selectedSection ? null : state.deck.slides[state.currentSlide];
  const trashed = Boolean(selectedSlide?.trashed);
  const activeCount = state.deck.slides.filter(slide => !slide.trashed).length;
  const sectionPosition = selectedSection ? state.deck.items.indexOf(selectedSection) : -1;
  const slidePosition = state.deck.items.indexOf(state.deck.slides[state.currentSlide]);
  for (const id of ["add-slide", "add-section", "import-slide", "duplicate-slide"]) document.querySelector(`#${id}`).disabled = Boolean(selectedSection) || trashed;
  const restoreButton = document.querySelector("#restore-slide");
  restoreButton.hidden = !trashed;
  restoreButton.disabled = !trashed;
  const deleteButton = document.querySelector("#delete-slide");
  deleteButton.disabled = !selectedSection && !trashed && activeCount <= 1;
  deleteButton.title = selectedSection?.isTrash ? "Empty Trash" : selectedSection ? "Delete selected section" : trashed ? "Delete slide permanently" : "Move slide to Trash";
  deleteButton.setAttribute("aria-label", deleteButton.title);
  document.querySelector("#move-slide-up").disabled = trashed || selectedSection?.isTrash || (selectedSection ? sectionPosition <= 0 : slidePosition <= 0);
  document.querySelector("#move-slide-down").disabled = trashed || selectedSection?.isTrash || (selectedSection ? sectionPosition >= state.deck.items.length - 1 : slidePosition >= state.deck.items.length - 1);
}

function duplicateSelectedSlide() {
  state.selectedSection = null;
  const index = state.currentSlide;
  state.currentSlide = index + 1;
  commitSource(duplicateSlide(state.deck, index));
}

function addSlideAfterSelection() {
  state.selectedSection = null;
  const index = state.currentSlide;
  state.currentSlide = index + 1;
  commitSource(insertSlide(state.deck, index));
}

function addSectionAfterSelection() {
  const title = prompt("Section name", "New section");
  if (title === null) return;
  try {
    const source = insertSection(state.deck, state.currentSlide, title);
    const previousIds = new Set(state.deck.sections.map(section => section.id));
    state.selectedSection = parseDeck(source).sections.find(section => !previousIds.has(section.id))?.id || null;
    commitSource(source);
  } catch (error) {
    showStatus(error.message, true);
  }
}

function renameSection(sectionId) {
  const section = state.deck.sections.find(item => item.id === sectionId);
  if (!section) return;
  const title = prompt("Section name", section.title);
  if (title === null || title.trim() === section.title) return;
  try { commitSource(updateSectionTitle(state.deck, sectionId, title)); }
  catch (error) { showStatus(error.message, true); }
}

async function chooseSlideToImport(path) {
  const response = await fetch(assetResolver(path), { cache: "no-store" });
  if (!response.ok) throw new Error("Cannot read presentation");
  const imported = parseDeck(await response.text());
  const fatal = imported.diagnostics.find(item => item.level === "error");
  if (fatal) throw new Error(`Cannot import from ${path}: ${fatal.message}`);
  const dialog = document.querySelector("#project-file-dialog");
  const gallery = document.querySelector("#project-file-gallery");
  document.querySelector("#project-file-title").textContent = `Import slide from ${path}`;
  document.querySelector("#project-file-search").closest(".project-asset-tools").hidden = true;
  document.querySelector("#project-file-new").hidden = true;
  document.querySelector("#project-file-upload").hidden = true;
  document.querySelector("#project-file-status").textContent = `${imported.slides.length} slide${imported.slides.length === 1 ? "" : "s"}`;
  gallery.replaceChildren(...imported.slides.map((slide, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "project-image-choice project-slide-choice";
    button.title = `Import slide ${index + 1}: ${slide.title || "Untitled"}`;
    const preview = document.createElement("span");
    preview.className = "project-slide-preview";
    preview.textContent = slide.raw.replace(/^\s*#{1,6}\s*/, "").slice(0, 180);
    const label = document.createElement("span");
    label.textContent = `${index + 1}. ${slide.title || "Untitled"}`;
    button.append(preview, label);
    button.onclick = () => {
      dialog.close();
      const destination = state.currentSlide;
      state.currentSlide = destination + 1;
      commitSource(importSlide(state.deck, destination, slide));
    };
    return button;
  }));
  dialog.showModal();
}

function importSlideFromPresentation() {
  if (!state.local) {
    showStatus("Slide import requires the local Quarkfoil server", true);
    return;
  }
  browseProjectFiles("presentation", path => chooseSlideToImport(path).catch(error => showStatus(error.message, true)), () => {}, { newFile: false, upload: false });
}

function deleteSelectedSlide() {
  if (state.selectedSection) {
    const section = state.deck.sections.find(item => item.id === state.selectedSection);
    if (!section) return;
    if (section.isTrash) {
      const count = state.deck.slides.filter(slide => slide.trashed).length;
      if (!confirm(`Permanently delete ${count} slide${count === 1 ? "" : "s"} from Trash? This cannot be undone after the editor is closed.`)) return;
      state.selectedSection = null;
      commitSource(emptyTrash(state.deck));
      return;
    }
    if (!confirm(`Delete section “${section.title}”? Its slides will remain.`)) return;
    const id = state.selectedSection;
    state.selectedSection = null;
    state.collapsedSections.delete(id);
    commitSource(deleteSection(state.deck, id));
    return;
  }
  const index = state.currentSlide;
  const slide = state.deck.slides[index];
  if (!slide) return;
  if (slide.trashed) {
    if (!confirm(`Permanently delete “${slide.title || "Untitled"}”? This cannot be undone after the editor is closed.`)) return;
    const active = state.deck.slides.findIndex(item => !item.trashed);
    state.currentSlide = Math.max(0, active);
    commitSource(permanentlyDeleteSlide(state.deck, index));
    return;
  }
  if (!confirm(`Move slide ${index + 1}, “${slide.title || "Untitled"}”, to Trash?`)) return;
  const remaining = state.deck.slides.filter(item => !item.trashed && item.index !== index);
  state.currentSlide = remaining[Math.min(index, remaining.length - 1)]?.index || 0;
  commitSource(trashSlide(state.deck, index));
}

function restoreSelectedSlide() {
  const slide = state.deck.slides[state.currentSlide];
  if (!slide?.trashed) return;
  commitSource(restoreSlide(state.deck, state.currentSlide));
}

function moveSelectedSlide(direction) {
  if (state.selectedSection) {
    commitSource(moveSection(state.deck, state.selectedSection, direction));
    return;
  }
  const from = state.currentSlide;
  const position = state.deck.items.indexOf(state.deck.slides[from]);
  const neighbor = state.deck.items[position + direction];
  if (!neighbor) return;
  if (neighbor.kind === "slide") state.currentSlide = from + direction;
  commitSource(moveSlide(state.deck, from, direction));
}

function rememberCurrentSlide() {
  const url = new URL(location.href);
  url.searchParams.set("slide", String(state.currentSlide + 1));
  history.replaceState(history.state, "", url);
}

function onSlideChanged(event) {
  state.currentSlide = event.indexh;
  rememberCurrentSlide();
  elements.notes.value = state.deck.slides[state.currentSlide]?.notes || "";
  syncVideoPlayback(event.currentSlide, { autoplay: state.mode === "present" });
  rebuildSlideList();
  editor?.refresh();
}

function updateNotes() {
  try { commitSource(updateSlideNotes(state.deck, state.currentSlide, elements.notes.value)); }
  catch (error) { showStatus(error.message, true); }
}

function resizeNotes(event) {
  if (event.button !== 0) return;
  event.preventDefault();
  elements.notesResizer.setPointerCapture(event.pointerId);
  const move = moveEvent => {
    const bounds = document.querySelector("#stage").getBoundingClientRect();
    const height = Math.max(72, Math.min(bounds.height - 160, bounds.bottom - moveEvent.clientY));
    document.querySelector("#stage").style.setProperty("--notes-height", `${Math.round(height)}px`);
    reveal?.layout();
  };
  const stop = () => {
    elements.notesResizer.removeEventListener("pointermove", move);
    elements.notesResizer.removeEventListener("pointerup", stop);
    elements.notesResizer.removeEventListener("pointercancel", stop);
  };
  elements.notesResizer.addEventListener("pointermove", move);
  elements.notesResizer.addEventListener("pointerup", stop);
  elements.notesResizer.addEventListener("pointercancel", stop);
}

function resizeNotesByKeyboard(event) {
  if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const stage = document.querySelector("#stage");
  const bounds = stage.getBoundingClientRect();
  const current = document.querySelector(".notes-pane").getBoundingClientRect().height;
  const maximum = Math.max(72, bounds.height - 160);
  const height = event.key === "Home" ? 72
    : event.key === "End" ? maximum
      : Math.max(72, Math.min(maximum, current + (event.key === "ArrowUp" ? 16 : -16)));
  stage.style.setProperty("--notes-height", `${Math.round(height)}px`);
  reveal?.layout();
}

function setMode(mode) {
  if (reveal && state.mode === "present" && mode !== "present" && reveal.isOverview()) {
    reveal.toggleOverview(false);
  }
  state.mode = mode;
  document.body.classList.toggle("presenting", mode === "present");
  elements.workspace.className = `workspace mode-${mode}`;
  elements.sourcePane.hidden = mode !== "source";
  document.querySelectorAll("[data-mode]").forEach(button => button.classList.toggle("active", button.dataset.mode === mode));
  if (reveal) {
    if (mode === "present" && state.deck.slides[state.currentSlide]?.trashed) {
      state.currentSlide = Math.max(0, state.deck.slides.findIndex(slide => !slide.trashed));
    }
    document.querySelectorAll('.scientific-slide[data-trashed="true"]').forEach(slide => {
      if (mode === "present") slide.dataset.visibility = "hidden";
      else delete slide.dataset.visibility;
    });
    reveal.sync();
    syncVideoPlayback(reveal.getCurrentSlide(), { autoplay: mode === "present", pauseActive: mode !== "present" });
    reveal.configure({
      controls: mode === "present",
      progress: mode === "present",
      keyboard: mode === "present",
      touch: mode === "present",
      overview: mode === "present",
      embedded: mode !== "present",
    });
    setTimeout(() => {
      reveal.layout();
      reveal.slide(state.currentSlide);
      editor?.refresh();
    }, 0);
  }
  if (mode === "source") requestAnimationFrame(focusSourceOnCurrentSlide);
}

function requestMode(mode) {
  if (state.mode === "source" && mode !== "source" && elements.source.value !== state.source) {
    if (!commitSource(elements.source.value)) return false;
  }
  setMode(mode);
  return true;
}

function focusSourceOnCurrentSlide() {
  const slide = state.deck?.slides[state.currentSlide];
  if (!slide) return;
  const offset = slide.range.start;
  elements.source.focus();
  elements.source.setSelectionRange(offset, offset);
  const lineCount = state.source.slice(0, offset).split(/\r\n|\r|\n/).length - 1;
  const lineHeight = Number.parseFloat(getComputedStyle(elements.source).lineHeight) || 20;
  elements.source.scrollTop = Math.max(0, lineCount * lineHeight);
  elements.source.scrollLeft = 0;
}

function updateDirtyState() {
  const sourceDraft = state.mode === "source" && elements.source.value !== state.source;
  const notesDraft = state.mode === "design" && elements.notes.value !== (state.deck?.slides[state.currentSlide]?.notes || "");
  const dirty = state.source !== state.savedSource || sourceDraft || notesDraft;
  elements.save.disabled = !state.deck || !dirty || Boolean(state.externalChange);
  elements.download.disabled = !state.deck;
  elements.saveState.textContent = state.externalChange ? "Changed on disk" : sourceDraft ? "Source edited" : notesDraft ? "Notes edited" : dirty ? "Unsaved" : "Saved";
  elements.saveState.classList.toggle("dirty", dirty || Boolean(state.externalChange));
}

function showStatus(message, error = false) {
  elements.saveState.textContent = message;
  elements.saveState.style.color = error ? "#ff8787" : "#8ce99a";
  setTimeout(() => { elements.saveState.style.color = ""; updateDirtyState(); }, 2400);
}

function scheduleSnapshot() {
  clearTimeout(snapshotTimer);
  snapshotTimer = setTimeout(() => saveSnapshot(state.config?.deck || state.filename, state.source).catch(() => {}), 1500);
}

function lastDeckStorageKey() {
  return `quarkfoil:last-deck:${state.config?.projectName || "project"}`;
}

function rememberLastDeck(path) {
  try { localStorage.setItem(lastDeckStorageKey(), path); } catch { /* Storage may be disabled. */ }
}

function recalledLastDeck() {
  try { return localStorage.getItem(lastDeckStorageKey()); } catch { return null; }
}

function deckUrl(path) {
  const url = new URL(location.href);
  url.searchParams.set("deck", path);
  return url.href;
}

function pinDeckInCurrentUrl(path) {
  history.replaceState(null, "", deckUrl(path));
}

function reserveProjectWindow() {
  const opened = window.open("about:blank", "_blank");
  if (!opened) throw new Error("The browser blocked the new presentation window");
  opened.opener = null;
  return opened;
}

function openProjectWindow(path, opened = null) {
  const target = opened || reserveProjectWindow();
  target.location.replace(deckUrl(path));
}

async function claimDeckWindow(path) {
  if (!("BroadcastChannel" in window)) return true;
  deckChannel?.close();
  const channel = new BroadcastChannel("quarkfoil-open-decks");
  const requestId = crypto.randomUUID();
  deckChannel = channel;
  deckClaim = { path, ready: false };
  let occupied = false;
  channel.onmessage = event => {
    const message = event.data;
    if (!message || message.path !== deckClaim?.path) return;
    if (message.type === "probe" && deckClaim.ready) {
      channel.postMessage({ type: "occupied", path: deckClaim.path, requestId: message.requestId });
      window.focus();
    } else if (message.type === "occupied" && message.requestId === requestId) occupied = true;
  };
  channel.postMessage({ type: "probe", path, requestId });
  await new Promise(resolve => setTimeout(resolve, 180));
  if (occupied) {
    channel.close();
    deckChannel = null;
    deckClaim = null;
    window.close();
    const message = document.createElement("p");
    message.style.cssText = "margin:2rem;font:16px system-ui;color:#edf2f4";
    message.textContent = `${path} is already open in another Quarkfoil window.`;
    document.body.replaceChildren(message);
    return false;
  }
  deckClaim.ready = true;
  return true;
}

async function loadLocalDeck() {
  try {
    const fetchDuringRestart = async (url, options = {}) => {
      let lastError;
      for (let attempt = 0; attempt < 20; attempt += 1) {
        try {
          const response = await fetch(url, options);
          if (response.status < 500) return response;
          lastError = new Error(`${url} returned ${response.status}`);
        } catch (error) {
          lastError = error;
        }
        await new Promise(resolve => setTimeout(resolve, 250));
      }
      throw lastError || new Error(`Cannot load ${url}`);
    };
    const configResponse = await fetchDuringRestart("/api/config", { cache: "no-store" });
    if (!configResponse.ok) return false;
    state.config = await configResponse.json();
    state.local = state.config.mode === "local";
    state.filename = state.config.deck;
    const requested = query.get("deck");
    const recalled = requested || recalledLastDeck();
    let source;
    if (recalled && recalled !== state.config.deck) {
      const restoredResponse = await fetch(`/api/open?path=${encodeURIComponent(recalled)}`, { method: "POST" });
      if (restoredResponse.ok) {
        const restored = await restoredResponse.json();
        state.filename = restored.path;
        state.config.deck = restored.path;
        state.serverHash = restored.hash;
        source = restored.source;
      } else {
        try { localStorage.removeItem(lastDeckStorageKey()); } catch { /* Storage may be disabled. */ }
      }
    }
    if (source === undefined) {
      const response = await fetchDuringRestart("/api/deck", { cache: "no-store" });
      if (!response.ok) throw new Error("Cannot load deck");
      source = await response.text();
      state.serverHash = await hashText(source);
    }
    state.savedSource = source;
    rememberLastDeck(state.config.deck);
    pinDeckInCurrentUrl(state.config.deck);
    if (!await claimDeckWindow(state.config.deck)) {
      state.duplicateDeck = true;
      return true;
    }
    parseAndRender(source, { preserveSlide: true });
    return true;
  } catch (error) {
    console.warn(error);
    return false;
  }
}

async function openPortable() {
  if (window.showDirectoryPicker) {
    const directory = await window.showDirectoryPicker({ mode: "readwrite" });
    const markdown = [];
    for await (const [name, handle] of directory.entries()) {
      if (handle.kind === "file" && /\.(?:md|markdown)$/i.test(name)) markdown.push([name, handle]);
    }
    if (!markdown.length) throw new Error("The selected directory has no top-level Markdown presentation");
    let selected = markdown[0];
    if (markdown.length > 1) {
      const choices = markdown.map(([name], index) => `${index + 1}: ${name}`).join("\n");
      const response = prompt(`Choose a presentation:\n${choices}`, "1");
      if (response === null) return;
      const answer = Number(response) - 1;
      if (!Number.isInteger(answer) || !markdown[answer]) throw new Error("No presentation selected");
      selected = markdown[answer];
    }
    const [name, handle] = selected;
    const file = await handle.getFile();
    state.directoryHandle = directory;
    state.fileHandle = handle;
    state.filename = file.name;
    const source = await file.text();
    await preloadPortableAssets(source);
    state.savedSource = source;
    state.local = false;
    state.undo = [];
    state.redo = [];
    parseAndRender(source, { preserveSlide: false });
  } else if (window.showOpenFilePicker) {
    const [handle] = await window.showOpenFilePicker({ types: [{ description: "Markdown", accept: { "text/markdown": [".md", ".markdown"] } }] });
    const file = await handle.getFile();
    state.fileHandle = handle;
    state.filename = file.name;
    const source = await file.text();
    state.savedSource = source;
    state.local = false;
    state.undo = [];
    state.redo = [];
    parseAndRender(source, { preserveSlide: false });
  } else document.querySelector("#file-input").click();
}

async function listProjectFiles(kind) {
  const response = await fetch(`/api/files?kind=${encodeURIComponent(kind)}`);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Cannot list presentation files");
  return result.files;
}

async function createProjectPresentation(name, source, overwrite = false) {
  const response = await fetch(`/api/presentation?name=${encodeURIComponent(name)}&overwrite=${overwrite}`, {
    method: "POST",
    headers: { "Content-Type": "text/markdown; charset=utf-8" },
    body: source,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Cannot create presentation");
  return result.path;
}

function chooseImportDestination(proposedName, { title = "File already exists", extensions = [], message = "Choose another filename or enable overwrite." } = {}) {
  const dialog = document.querySelector("#import-dialog");
  const filename = document.querySelector("#import-filename");
  const overwrite = document.querySelector("#import-overwrite");
  const status = document.querySelector("#import-status");
  document.querySelector("#import-dialog-title").textContent = title;
  filename.value = proposedName;
  overwrite.checked = false;
  status.textContent = message;
  dialog.returnValue = "";
  dialog.showModal();
  filename.focus();
  filename.select();
  return new Promise(resolve => {
    let selection = null;
    document.querySelector("#import-confirm").onclick = () => {
      const name = filename.value.trim();
      const suffix = name.match(/\.[^.]+$/)?.[0]?.toLowerCase() || "";
      if (!name || /[\\/]/.test(name)) { status.textContent = "Enter a filename without a directory"; return; }
      if (extensions.length && !extensions.includes(suffix)) { status.textContent = `Filename must end in ${extensions.join(" or ")}`; return; }
      selection = { name, overwrite: overwrite.checked };
      dialog.close("confirm");
    };
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm" ? selection : null), { once: true });
  });
}

async function projectPathExists(path) {
  if (state.local) {
    const response = await fetch(assetResolver(path), { method: "HEAD", cache: "no-store" });
    return response.ok;
  }
  if (state.directoryHandle) {
    try { await nestedFileHandle(state.directoryHandle, path); return true; }
    catch { return false; }
  }
  return state.objectUrls.has(path);
}

async function browseProjectFiles(kind, select, upload, { newFile: showNew = true, upload: showUpload = true } = {}) {
  if (!state.local) { upload(); return; }
  const dialog = document.querySelector("#project-file-dialog");
  const gallery = document.querySelector("#project-file-gallery");
  const status = document.querySelector("#project-file-status");
  const search = document.querySelector("#project-file-search");
  search.closest(".project-asset-tools").hidden = false;
  const previous = document.querySelector("#project-file-previous");
  const next = document.querySelector("#project-file-next");
  const labels = { presentation: "presentation", image: "image", video: "video" };
  document.querySelector("#project-file-title").textContent = `Presentation folder — Choose ${labels[kind]}`;
  gallery.replaceChildren();
  search.value = "";
  status.textContent = `Loading ${labels[kind]}s…`;
  const uploadButton = document.querySelector("#project-file-upload");
  uploadButton.hidden = !showUpload;
  uploadButton.textContent = kind === "presentation" ? "Upload" : `Upload ${labels[kind]} from computer…`;
  uploadButton.onclick = upload;
  const onlineButton = document.querySelector("#project-file-online-icons");
  onlineButton.hidden = kind !== "image";
  onlineButton.onclick = () => {
    dialog.close();
    openOnlineIcons(select);
  };
  const newButton = document.querySelector("#project-file-new");
  newButton.hidden = kind !== "presentation" || !showNew;
  newButton.onclick = async () => {
    let name = prompt("Name the new presentation", "presentation.md");
    if (name === null) return;
    name = name.trim();
    if (!name) {
      status.textContent = "Enter a filename for the new presentation";
      return;
    }
    if (!/\.(?:md|markdown)$/i.test(name)) name += ".md";
    let opened;
    try { opened = reserveProjectWindow(); }
    catch (error) { status.textContent = error.message; return; }
    newButton.disabled = true;
    status.textContent = "Creating presentation…";
    try {
      const path = await createProjectPresentation(name, STARTER);
      openProjectWindow(path, opened);
      dialog.close();
    } catch (error) {
      opened.close();
      status.textContent = error.message;
    } finally {
      newButton.disabled = false;
    }
  };
  dialog.showModal();
  try {
    const files = await listProjectFiles(kind);
    let page = 0;
    const render = () => {
      const result = projectAssetPage(files, search.value, page);
      page = result.page;
      gallery.replaceChildren(...result.assets.map(file => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `project-image-choice project-file-choice--${kind}`;
        button.title = file.path;
        let preview;
        if (kind === "image") {
          preview = document.createElement("img"); preview.alt = ""; preview.src = assetResolver(file.path);
        } else if (kind === "video") {
          preview = document.createElement("video"); preview.muted = true; preview.preload = "metadata"; preview.src = assetResolver(file.path);
        } else {
          preview = document.createElement("span"); preview.className = "project-file-icon"; preview.textContent = "MD";
        }
        const label = document.createElement("span"); label.textContent = file.path;
        button.append(preview, label);
        button.onclick = () => { dialog.close(); select(file.path); };
        return button;
      }));
      previous.disabled = page === 0;
      next.disabled = page + 1 >= result.pages;
      status.textContent = result.count ? `${result.count} ${labels[kind]}${result.count === 1 ? "" : "s"} · Page ${page + 1} of ${result.pages}` : `No ${labels[kind]}s found`;
    };
    search.oninput = () => { page = 0; render(); };
    search.onkeydown = event => { if (event.key === "Enter") event.preventDefault(); };
    previous.onclick = () => { page -= 1; render(); };
    next.onclick = () => { page += 1; render(); };
    render();
    search.focus();
  } catch (error) { status.textContent = error.message; }
}

function openOnlineIcons(select) {
  const dialog = document.querySelector("#icon-dialog");
  const search = document.querySelector("#icon-search");
  const button = document.querySelector("#icon-search-button");
  const gallery = document.querySelector("#icon-gallery");
  const status = document.querySelector("#icon-status");
  gallery.replaceChildren();
  status.textContent = "Material Symbols, Tabler Icons, and IconPark · imported SVGs remain local";
  const run = async () => {
    const query = search.value.trim();
    if (query.length < 2) { status.textContent = "Enter at least two characters"; return; }
    button.disabled = true;
    status.textContent = "Searching Iconify…";
    gallery.replaceChildren();
    try {
      const response = await fetch(`/api/icons/search?q=${encodeURIComponent(query)}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Icon search failed");
      gallery.replaceChildren(...result.icons.map(icon => {
        const choice = document.createElement("button");
        choice.type = "button";
        choice.className = "project-image-choice";
        choice.title = `${icon.collection}: ${icon.name}`;
        const preview = document.createElement("img");
        preview.alt = "";
        preview.src = `/api/icons/svg?prefix=${encodeURIComponent(icon.prefix)}&name=${encodeURIComponent(icon.name)}`;
        const label = document.createElement("span");
        label.textContent = `${icon.name}\n${icon.collection}`;
        choice.append(preview, label);
        choice.onclick = async () => {
          choice.disabled = true;
          status.textContent = `Importing ${icon.name}…`;
          try {
            const imported = await fetch(`/api/icons/import?folder=${encodeURIComponent(figureFolder())}&prefix=${encodeURIComponent(icon.prefix)}&name=${encodeURIComponent(icon.name)}`, { method: "POST" });
            const payload = await imported.json();
            if (!imported.ok) throw new Error(payload.error || "Icon import failed");
            dialog.close();
            select(payload.path);
          } catch (error) { status.textContent = error.message; choice.disabled = false; }
        };
        return choice;
      }));
      status.textContent = result.icons.length ? `${result.icons.length} icons found` : "No icons found";
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  };
  button.onclick = run;
  search.onkeydown = event => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); run(); } };
  dialog.showModal();
  search.focus();
}

async function nestedFileHandle(root, path, create = false) {
  const parts = path.replaceAll("\\", "/").split("/").filter(part => part && part !== ".");
  if (parts.some(part => part === "..")) throw new Error("Asset path leaves the selected directory");
  let directory = root;
  for (const part of parts.slice(0, -1)) directory = await directory.getDirectoryHandle(part, { create });
  return directory.getFileHandle(parts.at(-1), { create });
}

async function preloadPortableAssets(source) {
  if (!state.directoryHandle) return;
  for (const url of state.objectUrls.values()) URL.revokeObjectURL(url);
  state.objectUrls.clear();
  const paths = new Set([...source.matchAll(/!\[[^\]]*\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/g)].map(match => match[1]));
  for (const match of source.matchAll(/\b(?:src|poster)=(?:"([^"]+)"|'([^']+)'|([^\s}]+))/g)) {
    paths.add(match[1] || match[2] || match[3]);
  }
  for (const path of paths) {
    if (/^[a-z]+:/i.test(path)) continue;
    try {
      const handle = await nestedFileHandle(state.directoryHandle, path);
      const file = await handle.getFile();
      state.objectUrls.set(path, URL.createObjectURL(file));
    } catch { /* Missing assets are diagnosed by the browser media event. */ }
  }
}

async function saveDeck() {
  try {
    if (state.local) {
      while (deckCheckPending) await new Promise(resolve => setTimeout(resolve, 20));
      await pollForExternalDeck({ force: true });
      if (state.externalChange) { openExternalChangeDialog(); return; }
    }
    if (state.mode === "design" && elements.notes.value !== (state.deck.slides[state.currentSlide]?.notes || "")) {
      if (!commitSource(updateSlideNotes(state.deck, state.currentSlide, elements.notes.value))) return;
    }
    if (elements.source.value !== state.source && !commitSource(elements.source.value)) return;
    const normalized = normalizeDeck(state.deck);
    if (normalized !== state.source && !commitSource(normalized)) return;
    if (state.local) {
      const response = await fetch(`/api/deck?path=${encodeURIComponent(state.config.deck)}`, {
        method: "PUT",
        headers: { "Content-Type": "text/markdown; charset=utf-8", ...(state.serverHash ? { "If-Match": `"${state.serverHash}"` } : {}) },
        body: state.source,
      });
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 409) {
          await pollForExternalDeck({ force: true });
          if (state.externalChange) { openExternalChangeDialog(); return; }
        }
        throw new Error(result.error || "Save failed");
      }
      state.serverHash = result.hash;
    } else if (state.fileHandle) {
      const writable = await state.fileHandle.createWritable();
      await writable.write(state.source);
      await writable.close();
    } else {
      downloadSource();
      return;
    }
    state.savedSource = state.source;
    updateDirtyState();
    showStatus("Saved");
  } catch (error) { showStatus(error.message, true); }
}

function downloadSource() {
  downloadMarkdown(currentBrowserSource(), state.filename);
}

function downloadMarkdown(source, filename) {
  const blob = new Blob([source], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename.split(/[\\/]/).pop() || "presentation.md";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function downloadBrowserDraft() {
  const name = state.filename.split(/[\\/]/).pop() || "presentation.md";
  const dot = name.lastIndexOf(".");
  const filename = dot > 0 ? `${name.slice(0, dot)}-browser-draft${name.slice(dot)}` : `${name}-browser-draft.md`;
  downloadMarkdown(currentBrowserSource(), filename);
}

function useExternalDiskVersion() {
  const change = state.externalChange;
  if (!change || change.error) return;
  try {
    applyExternalDeck(change.source, change.hash, "Loaded disk version");
    document.querySelector("#external-change-dialog").close();
  } catch (error) {
    const status = document.querySelector("#external-merge-status");
    status.textContent = error.message;
    status.classList.add("error");
  }
}

function applyExternalMerge() {
  const change = state.externalChange;
  if (!change) return;
  const source = document.querySelector("#external-merged-source").value;
  const error = deckValidationError(source);
  const status = document.querySelector("#external-merge-status");
  if (error) {
    status.textContent = error;
    status.classList.add("error");
    return;
  }
  state.serverHash = change.hash;
  state.savedSource = change.source;
  clearExternalChange();
  resetHistory();
  parseAndRender(source, { preserveSlide: true });
  document.querySelector("#external-change-dialog").close();
  showStatus(source === change.source ? "Loaded disk version" : "Merged draft ready to save");
}

function bibliographyPath() {
  const value = state.deck?.metadata?.bibliography;
  return typeof value === "string" && value.trim() ? value.trim().replaceAll("\\", "/") : "references.bib";
}

async function loadBibliography() {
  if (!state.local) return;
  const response = await fetch(`/api/bibliography?path=${encodeURIComponent(bibliographyPath())}`, { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Cannot load bibliography");
  state.bibliographySource = result.source;
  state.bibliographyHash = result.hash;
  state.bibliographyPdfs = result.pdfs || {};
}

async function pollForExternalBibliography() {
  if (document.querySelector("#bibliography-dialog[open]") || bibliographyOpenPending) return false;
  const previousHash = state.bibliographyHash;
  await loadBibliography();
  if (state.bibliographyHash === previousHash) return false;
  parseAndRender(state.source);
  showStatus("Reloaded external bibliography changes");
  return true;
}

function bibliographyMessage(message, error = false) {
  const element = document.querySelector("#bibliography-status");
  element.textContent = message;
  element.classList.toggle("error", error);
}

function rebuildBibliographyList(revealKey = null) {
  const target = document.querySelector("#bibliography-list");
  const query = document.querySelector("#bibliography-search").value.toLowerCase();
  let entries;
  try { entries = parseBibliography(document.querySelector("#bibliography-source").value); }
  catch (error) { bibliographyMessage(error.message, true); return; }
  target.replaceChildren();
  let revealedRow = null;
  for (const entry of entries.filter(item => `${item.key} ${Object.values(item.fields).join(" ")}`.toLowerCase().includes(query))) {
    const row = document.createElement("div");
    row.className = "bibliography-entry";
    row.dataset.citationKey = entry.key;
    if (entry.key === revealKey) revealedRow = row;
    const description = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = entry.key;
    const summary = document.createElement("span");
    summary.textContent = `${entry.fields.title || "Untitled"} — ${briefReference(entry)}`;
    description.append(title, summary);
    const cite = document.createElement("button");
    cite.type = "button"; cite.textContent = "Insert [n]";
    cite.title = "Save the bibliography draft and insert an inline citation";
    cite.addEventListener("click", () => insertInlineCitation(entry.key));
    const attribute = document.createElement("button");
    attribute.type = "button"; attribute.textContent = "Add attribution";
    attribute.title = "Save the bibliography draft and add an attribution to the current slide";
    attribute.addEventListener("click", () => insertCitationOverlay(entry.key));
    row.append(description);
    const pdf = state.bibliographyPdfs[entry.key];
    if (pdf) {
      const openPdf = document.createElement("a");
      openPdf.className = "button bibliography-pdf";
      openPdf.href = pdf;
      openPdf.target = "_blank";
      openPdf.rel = "noopener noreferrer";
      openPdf.textContent = "PDF";
      openPdf.title = "Open the attached PDF";
      row.append(openPdf);
    }
    row.append(cite, attribute);
    target.append(row);
  }
  bibliographyMessage(`${entries.length} reference${entries.length === 1 ? "" : "s"}`);
  if (revealedRow) requestAnimationFrame(() => revealedRow.scrollIntoView({ block: "nearest" }));
}

async function openBibliography() {
  const dialog = document.querySelector("#bibliography-dialog");
  if (dialog.open || bibliographyOpenPending) return;
  bibliographyOpenPending = true;
  try {
    await loadBibliography();
    document.querySelector("#bibliography-source").value = state.bibliographySource;
    document.querySelector("#bibliography-search").value = "";
    rebuildBibliographyList();
    dialog.showModal();
  } catch (error) {
    showStatus(error.message || "Cannot reload bibliography", true);
  } finally { bibliographyOpenPending = false; }
}

function remapSourceOffset(before, after, offset) {
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix += 1;
  if (offset <= prefix) return offset;
  let beforeSuffix = before.length;
  let afterSuffix = after.length;
  while (beforeSuffix > prefix && afterSuffix > prefix && before[beforeSuffix - 1] === after[afterSuffix - 1]) {
    beforeSuffix -= 1;
    afterSuffix -= 1;
  }
  return offset >= beforeSuffix ? afterSuffix + offset - beforeSuffix : prefix;
}

async function insertInlineCitation(key) {
  if (state.mode !== "source") { bibliographyMessage("Switch to Source mode to insert an inline citation", true); return; }
  const editor = elements.source;
  const draft = editor.value;
  const selectionStart = editor.selectionStart;
  const selectionEnd = editor.selectionEnd;
  if (draft !== state.source && !commitSource(draft)) return;
  const sourceBeforeSave = state.source;
  if (!await saveBibliography()) return;
  const start = remapSourceOffset(sourceBeforeSave, state.source, selectionStart);
  const end = remapSourceOffset(sourceBeforeSave, state.source, selectionEnd);
  editor.setSelectionRange(start, end);
  editor.setRangeText(`[@${key}]`, editor.selectionStart, editor.selectionEnd, "end");
  editor.dispatchEvent(new Event("input"));
  document.querySelector("#bibliography-dialog").close();
  editor.focus();
}

async function insertCitationOverlay(key) {
  if (!await saveBibliography()) return;
  const base = `citation-${key.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const used = new Set(state.deck.slides[state.currentSlide].overlays.map(item => item.id));
  let id = base; let counter = 2;
  while (used.has(id)) id = `${base}-${counter++}`;
  if (commitSource(insertOverlay(state.deck, state.currentSlide, { type: "citation", content: "", id, x: 55, y: 82, w: 40, h: 8, attributes: { key, display: "brief", align: "left", "font-size": "0.7em" } }))) {
    document.querySelector("#bibliography-dialog").close();
  }
}

async function fetchDoi() {
  if (!state.local) { bibliographyMessage("DOI import requires the local Quarkfoil server", true); return; }
  const doi = document.querySelector("#doi-input").value.trim();
  if (!doi) { bibliographyMessage("Enter a DOI to import", true); return; }
  bibliographyMessage("Fetching DOI…");
  try {
    const response = await fetch(`/api/doi?doi=${encodeURIComponent(doi)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "DOI lookup failed");
    const source = document.querySelector("#bibliography-source");
    const parsed = parseBibliography(result.bibtex);
    const existing = parseBibliography(source.value);
    let incoming = parsed[0];
    if (!incoming) throw new Error("DOI service returned no bibliography entry");
    if (existing.some(entry => entry.fields.doi && entry.fields.doi.toLowerCase() === incoming.fields.doi?.toLowerCase())) throw new Error("This DOI already exists");
    const key = uniqueCitationKey(incoming.key, existing.map(entry => entry.key));
    const bibtex = key === incoming.key ? result.bibtex : renameBibliographyEntry(result.bibtex, key);
    if (key !== incoming.key) incoming = parseBibliography(bibtex)[0];
    if (!window.confirm(`Add ${incoming.key}?\n\n${incoming.fields.title || "Untitled"}\n${briefReference(incoming)}`)) { bibliographyMessage("DOI import cancelled"); return; }
    const combined = `${source.value.trimEnd()}${source.value.trim() ? "\n\n" : ""}${bibtex.trim()}\n`;
    source.value = formatBibliography(combined);
    document.querySelector("#doi-input").value = "";
    document.querySelector("#bibliography-search").value = "";
    rebuildBibliographyList(incoming.key);
    bibliographyMessage(`Added ${incoming.key}; it will be saved when the dialog closes or the reference is used`);
  } catch (error) { bibliographyMessage(error.message, true); }
}

function reformatBibliographyDraft() {
  const source = document.querySelector("#bibliography-source");
  if (!source.value.trim()) { bibliographyMessage("The bibliography is empty"); return; }
  if (!window.confirm("Reformat and alphabetize the complete bibliography draft?")) {
    bibliographyMessage("Reformat cancelled");
    return;
  }
  try {
    source.value = formatBibliography(source.value);
    rebuildBibliographyList();
    bibliographyMessage("Bibliography draft reformatted and alphabetized");
  } catch (error) { bibliographyMessage(error.message, true); }
}

async function saveBibliography() {
  const source = document.querySelector("#bibliography-source").value;
  try { parseBibliography(source); }
  catch (error) { bibliographyMessage(error.message, true); return false; }
  if (!state.local) { bibliographyMessage("Saving requires the local Quarkfoil server", true); return false; }
  if (state.mode === "source" && elements.source.value !== state.source && !commitSource(elements.source.value)) return false;
  try {
    const response = await fetch(`/api/bibliography?path=${encodeURIComponent(bibliographyPath())}`, { method: "PUT", headers: { "Content-Type": "application/x-bibtex; charset=utf-8", "If-Match": `"${state.bibliographyHash}"` }, body: source });
    const result = await response.json();
    if (!response.ok) { bibliographyMessage(result.error || "Save failed", true); return false; }
    state.bibliographySource = source;
    state.bibliographyHash = result.hash;
    if (!state.deck.metadata?.bibliography && /^---\r?\n/.test(state.source)) {
      if (!commitSource(state.source.replace(/^---\r?\n/, `---\nbibliography: ${bibliographyPath()}\n`))) return false;
    } else parseAndRender(state.source);
    return true;
  } catch (error) {
    bibliographyMessage(error.message || "Save failed", true);
    return false;
  }
}

async function closeBibliography() {
  if (!await saveBibliography()) return;
  document.querySelector("#bibliography-dialog").close();
}

function figureFolder() {
  const configured = state.deck?.metadata?.assets?.figures;
  const folder = typeof configured === "string" && configured.trim() ? configured.trim().replaceAll("\\", "/") : "figures";
  const parts = folder.split("/").filter(Boolean);
  if (/^(?:\/|[a-z]:)/i.test(folder) || !parts.length || parts.some(part => part === "." || part === "..")) {
    throw new Error("assets.figures must be a project-relative folder");
  }
  return parts.join("/");
}

async function importAsset(file, destination = null) {
  const originalSuffix = file?.name?.match(/\.[^.]+$/)?.[0]?.toLowerCase() || "";
  const assetFolder = figureFolder();
  if (!destination) {
    const proposed = { name: file.name, overwrite: false };
    const proposedPath = `${assetFolder}/${proposed.name}`;
    destination = await resolveImportDestination(projectPathExists(proposedPath), proposed,
      () => chooseImportDestination(proposed.name, { extensions: originalSuffix ? [originalSuffix] : [], message: `${proposedPath} already exists. Choose another filename or enable overwrite.` }));
  }
  if (!destination) return null;
  const suffix = destination.name.match(/\.[^.]+$/)?.[0]?.toLowerCase() || "";
  const convertible = [".avi", ".mkv"].includes(suffix);
  if (!file || (!convertible && !["image/", "video/"].some(prefix => file.type.startsWith(prefix)))) throw new Error("Only image and video files are supported");
  if (convertible) {
    if (!state.local) throw new Error("AVI and MKV conversion requires the local Quarkfoil server");
    const result = await uploadVideoForConversion(file, assetFolder, destination);
    return { path: result.path, poster: result.poster, completion: monitorVideoConversion(result.id) };
  }
  if (state.local) {
    const response = await fetch(`/api/asset?name=${encodeURIComponent(destination.name)}&folder=${encodeURIComponent(assetFolder)}&overwrite=${destination.overwrite}`, { method: "POST", headers: { "Content-Type": file.type }, body: file });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Asset import failed");
    if (destination.overwrite) refreshAsset(result.path);
    return result.path;
  }
  const safe = destination.name.replace(/[^a-zA-Z0-9._-]/g, "-");
  let path = `${assetFolder}/${safe}`;
  if (state.directoryHandle) {
    try {
      await nestedFileHandle(state.directoryHandle, path);
      if (!destination.overwrite) throw new Error(`${path} already exists`);
    } catch (error) {
      if (error instanceof Error && /already exists$/.test(error.message)) throw error;
    }
    const handle = await nestedFileHandle(state.directoryHandle, path, true);
    const writable = await handle.createWritable();
    await writable.write(file);
    await writable.close();
  }
  state.objectUrls.set(path, URL.createObjectURL(file));
  return path;
}

function uploadVideoForConversion(file, assetFolder, destination) {
  const dialog = document.querySelector("#video-conversion-dialog");
  const progress = document.querySelector("#video-conversion-progress");
  const status = document.querySelector("#video-conversion-status");
  const cancel = document.querySelector("#cancel-video-conversion");
  if (dialog.open) dialog.close();
  progress.value = 0;
  status.textContent = `Uploading ${file.name}… 0%`;
  cancel.disabled = false;
  cancel.textContent = "Cancel conversion";
  dialog.show();
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `/api/video-conversion?name=${encodeURIComponent(destination.name)}&folder=${encodeURIComponent(assetFolder)}&overwrite=${destination.overwrite}`);
    request.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    request.upload.addEventListener("progress", event => {
      if (!event.lengthComputable) {
        progress.removeAttribute("value");
        status.textContent = `Uploading ${file.name}…`;
        return;
      }
      const percentage = Math.round(100 * event.loaded / event.total);
      progress.value = percentage;
      status.textContent = `Uploading ${file.name}… ${percentage}%`;
    });
    request.upload.addEventListener("load", () => {
      progress.removeAttribute("value");
      status.textContent = "Extracting preview frame…";
    });
    request.addEventListener("load", () => {
      let result;
      try { result = JSON.parse(request.responseText); }
      catch { reject(new Error("Video upload returned an invalid response")); return; }
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(result.error || "Video conversion could not start"));
        return;
      }
      status.textContent = "Preview ready. Starting conversion…";
      resolve(result);
    });
    request.addEventListener("error", () => reject(new Error("Video upload failed")));
    request.addEventListener("abort", () => reject(new Error("Video upload cancelled")));
    cancel.onclick = () => request.abort();
    request.send(file);
  }).catch(error => {
    status.textContent = error.message;
    cancel.textContent = "Close";
    cancel.onclick = () => dialog.close();
    throw error;
  });
}

async function monitorVideoConversion(jobId) {
  const dialog = document.querySelector("#video-conversion-dialog");
  const progress = document.querySelector("#video-conversion-progress");
  const status = document.querySelector("#video-conversion-status");
  const cancel = document.querySelector("#cancel-video-conversion");
  progress.value = 0;
  status.textContent = "Preview ready. Optimizing for browser playback…";
  dialog.show();
  cancel.textContent = "Cancel conversion";
  let cancelled = false;
  cancel.onclick = async () => {
    cancelled = true;
    cancel.disabled = true;
    status.textContent = "Cancelling conversion…";
    await fetch(`/api/video-conversion/${encodeURIComponent(jobId)}`, { method: "DELETE" }).catch(() => {});
  };
  let completed = false;
  try {
    while (true) {
      await new Promise(resolve => setTimeout(resolve, 500));
      const response = await fetch(`/api/video-conversion/${encodeURIComponent(jobId)}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Cannot read conversion progress");
      if (result.progress === null) progress.removeAttribute("value");
      else progress.value = result.progress;
      status.textContent = result.status === "queued"
        ? "Waiting to convert…"
        : result.status === "extracting"
          ? "Extracting preview frame…"
          : result.progress === null ? "Optimizing video…" : `Optimizing video… ${Math.round(result.progress)}%`;
      if (result.status === "complete") {
        completed = true;
        status.textContent = "Video conversion complete";
        return result;
      }
      if (["failed", "cancelled"].includes(result.status)) throw new Error(result.error || (cancelled ? "Conversion cancelled" : "Video conversion failed"));
    }
  } catch (error) {
    status.textContent = error.message;
    cancel.textContent = "Close";
    cancel.onclick = () => dialog.close();
    throw error;
  } finally {
    cancel.disabled = false;
    if (completed) setTimeout(() => { if (dialog.open) dialog.close(); }, 1200);
  }
}

function bindUi() {
  document.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => requestMode(button.dataset.mode)));
  document.querySelector("#open-button").addEventListener("click", () => (state.local
    ? browseProjectFiles("presentation", path => {
      try { openProjectWindow(path); } catch (error) { showStatus(error.message, true); }
    }, () => document.querySelector("#file-input").click())
    : openPortable()).catch(error => {
    if (error?.name !== "AbortError") showStatus(error.message, true);
  }));
  elements.save.addEventListener("click", saveDeck);
  elements.download.addEventListener("click", downloadSource);
  document.querySelector("#external-change-review").addEventListener("click", openExternalChangeDialog);
  document.querySelector("#external-download-browser").addEventListener("click", downloadBrowserDraft);
  document.querySelector("#external-use-disk").addEventListener("click", useExternalDiskVersion);
  document.querySelector("#external-apply-merge").addEventListener("click", applyExternalMerge);
  elements.source.addEventListener("input", updateDirtyState);
  elements.notes.addEventListener("input", updateDirtyState);
  elements.notes.addEventListener("change", updateNotes);
  elements.notesResizer.addEventListener("pointerdown", resizeNotes);
  elements.notesResizer.addEventListener("keydown", resizeNotesByKeyboard);
  elements.source.addEventListener("keydown", handleMarkdownShortcut);
  elements.notes.addEventListener("keydown", handleMarkdownShortcut);
  document.querySelector("#file-input").addEventListener("change", async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (state.local) {
      const proposed = { name: file.name, overwrite: false };
      const destination = await resolveImportDestination(projectPathExists(file.name), proposed,
        () => chooseImportDestination(file.name, { extensions: [".md", ".markdown"], message: `${file.name} already exists. Choose another filename or enable overwrite.` }));
      if (!destination) { event.target.value = ""; return; }
      let opened;
      try { opened = reserveProjectWindow(); }
      catch (error) { showStatus(error.message, true); event.target.value = ""; return; }
      try {
        const path = await createProjectPresentation(destination.name, file, destination.overwrite);
        openProjectWindow(path, opened);
        document.querySelector("#project-file-dialog").close();
      } catch (error) {
        opened.close();
        showStatus(error.message || "Upload failed", true);
      }
      event.target.value = "";
      return;
    }
    state.filename = file.name;
    const source = await file.text();
    state.savedSource = source;
    state.local = false;
    parseAndRender(source, { preserveSlide: false });
  });
  document.querySelector("#bibliography-button").addEventListener("click", openBibliography);
  document.querySelector("#bibliography-search").addEventListener("input", () => rebuildBibliographyList());
  document.querySelector("#bibliography-search").addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.isComposing) event.preventDefault();
  });
  document.querySelector("#bibliography-source").addEventListener("input", () => rebuildBibliographyList());
  document.querySelector("#doi-fetch").addEventListener("click", fetchDoi);
  document.querySelector("#bibliography-reformat").addEventListener("click", reformatBibliographyDraft);
  document.querySelector("#doi-input").addEventListener("keydown", event => {
    if (event.key !== "Enter" || event.isComposing) return;
    event.preventDefault();
    fetchDoi();
  });
  document.querySelector("#bibliography-close").addEventListener("click", closeBibliography);
  document.querySelector("#bibliography-dialog").addEventListener("cancel", event => {
    event.preventDefault();
    closeBibliography();
  });
  document.querySelector("#undo-button").addEventListener("click", undo);
  document.querySelector("#redo-button").addEventListener("click", redo);
  document.querySelector("#add-slide").addEventListener("click", addSlideAfterSelection);
  document.querySelector("#add-section").addEventListener("click", addSectionAfterSelection);
  document.querySelector("#import-slide").addEventListener("click", importSlideFromPresentation);
  document.querySelector("#duplicate-slide").addEventListener("click", duplicateSelectedSlide);
  document.querySelector("#restore-slide").addEventListener("click", restoreSelectedSlide);
  document.querySelector("#delete-slide").addEventListener("click", deleteSelectedSlide);
  document.querySelector("#move-slide-up").addEventListener("click", () => moveSelectedSlide(-1));
  document.querySelector("#move-slide-down").addEventListener("click", () => moveSelectedSlide(1));
  document.addEventListener("keydown", event => {
    const editing = textEditingTarget(event.target);
    const draftEditorOpen = state.mode === "source" || Boolean(document.querySelector("#content-dialog[open]"));
    const undoShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z";
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); saveDeck(); }
    if (!editing && draftEditorOpen && undoShortcut) event.preventDefault();
    if (!editing && !draftEditorOpen && undoShortcut && !event.shiftKey) { event.preventDefault(); undo(); }
    if (!editing && !draftEditorOpen && undoShortcut && event.shiftKey) { event.preventDefault(); redo(); }
    if (event.key === "Escape" && state.mode === "present") setMode("design");
    if (state.mode === "design" && reveal && state.deck && !editing && !document.querySelector("dialog[open]") && !event.ctrlKey && !event.metaKey && !event.altKey && ["PageUp", "PageDown"].includes(event.key)) {
      event.preventDefault();
      reveal.slide(pageSlideIndex(state.currentSlide, state.deck.slides.length, event.key));
    }
  });
  window.addEventListener("beforeunload", event => {
    if (state.source !== state.savedSource) { event.preventDefault(); event.returnValue = ""; }
  });
}

async function initialize() {
  bindUi();
  const loaded = await loadLocalDeck();
  if (state.duplicateDeck) return;
  if (state.local && state.config?.reload) {
    await pollForReload();
    bindReloadChecks();
  }
  if (state.local) bindExternalDeckChecks();
  if (!loaded) {
    if (["http:", "https:"].includes(location.protocol)) {
      elements.save.disabled = true;
      showStatus("Cannot reconnect to the Quarkfoil server. The presentation on disk is unchanged; reload after restarting Quarkfoil.", true);
      return;
    }
    state.savedSource = "";
    parseAndRender(STARTER, { preserveSlide: true });
  }
  await loadBibliography();
  parseAndRender(state.source);
  reveal = new window.Reveal(document.querySelector(".reveal"), {
    embedded: true,
    controls: false,
    progress: false,
    hash: false,
    history: false,
    keyboard: false,
    touch: false,
    transition: "none",
    width: 1280,
    height: 720,
    margin: 0,
    minScale: 0.1,
    maxScale: 3,
    plugins: window.RevealNotes ? [window.RevealNotes] : [],
  });
  await reveal.initialize();
  reveal.on("slidechanged", onSlideChanged);
  reveal.slide(state.currentSlide);
  syncVideoPlayback(reveal.getCurrentSlide(), { autoplay: state.mode === "present", pauseActive: state.mode !== "present" });
  editor = new DesignEditor({
    getDeck: () => state.deck,
    getMode: () => state.mode,
    getSlideIndex: () => state.currentSlide,
    commitSource,
    importAsset: async (file, destination) => {
      try { return await importAsset(file, destination); }
      catch (error) {
        showStatus(error.message, true);
        if (destination) throw error;
        return null;
      }
    },
    browseProjectFiles,
    resolveAsset: assetResolver,
    refreshAsset,
  });
  editor.refresh();
  setMode(state.mode);
}

initialize().catch(error => {
  console.error(error);
  document.body.innerHTML = `<pre style="padding:2rem;color:#ff8787">${error.message}\n\nRun tools/fetch_vendor.py before starting the application.</pre>`;
});
