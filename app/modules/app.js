import { deleteSlide, duplicateSlide, insertSlide, moveSlide, parseDeck } from "./parser.js";
import { renderDeck } from "./render.js";
import { DesignEditor } from "./editor.js";
import { saveSnapshot } from "./storage.js";

const STARTER = `---
title: Scientific Slides
author: Your name
aspect-ratio: 16:9
theme: scientific-light
defaults:
  footer: Editable Markdown · Reveal.js
---

# Scientific Slides {.title-slide .layout-1}

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
  local: false,
  config: null,
  serverHash: null,
  fileHandle: null,
  directoryHandle: null,
  filename: "presentation.md",
  undo: [],
  redo: [],
  objectUrls: new Map(),
};

const elements = {
  workspace: document.querySelector("#workspace"),
  slides: document.querySelector("#slides"),
  slideList: document.querySelector("#slide-list"),
  source: document.querySelector("#source-editor"),
  sourcePane: document.querySelector("#source-pane"),
  save: document.querySelector("#save-button"),
  download: document.querySelector("#download-button"),
  saveState: document.querySelector("#save-state"),
};

let reveal;
let editor;
let snapshotTimer;

function assetResolver(source) {
  if (state.objectUrls.has(source)) return state.objectUrls.get(source);
  if (state.local) return `/project/${source.replaceAll("\\", "/").split("/").map(encodeURIComponent).join("/")}`;
  return source;
}

async function hashText(text) {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join("");
}

function parseAndRender(source, { preserveSlide = true } = {}) {
  const previous = preserveSlide ? state.currentSlide : 0;
  const deck = parseDeck(source);
  const fatal = deck.diagnostics.find(item => item.level === "error");
  if (fatal) {
    const location = fatal.slide ? `Slide ${fatal.slide}: ` : "";
    throw new Error(`${location}${fatal.message}. The last valid presentation is unchanged.`);
  }
  state.source = source;
  state.deck = deck;
  elements.source.value = source;
  renderDeck(deck, elements.slides, assetResolver);
  rebuildSlideList();
  state.currentSlide = Math.min(previous, Math.max(0, deck.slides.length - 1));
  if (reveal) {
    reveal.sync();
    reveal.slide(state.currentSlide);
  }
  editor?.refresh();
  updateDirtyState();
  scheduleSnapshot();
  return deck;
}

function commitSource(source, record = true) {
  if (source === state.source) return;
  const previous = state.source;
  try {
    parseAndRender(source);
    if (record) {
      state.undo.push(previous);
      if (state.undo.length > 100) state.undo.shift();
      state.redo.length = 0;
      updateHistoryButtons();
    }
  } catch (error) {
    showStatus(error.message, true);
    elements.source.value = source;
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
  elements.slideList.replaceChildren(...state.deck.slides.map((slide, index) => {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${index + 1}. ${slide.title || "Untitled"}`;
    button.title = "Click to select; double-click to rename";
    button.classList.toggle("current", index === state.currentSlide);
    button.addEventListener("click", () => { reveal.slide(index); setMode(state.mode === "source" ? "design" : state.mode); });
    button.addEventListener("dblclick", event => {
      event.preventDefault();
      state.currentSlide = index;
      reveal.slide(index);
      setMode("design");
      setTimeout(() => editor?.openTitleDialog(), 0);
    });
    li.append(button);
    return li;
  }));
  document.querySelector("#duplicate-slide").disabled = !state.deck.slides.length;
  document.querySelector("#delete-slide").disabled = state.deck.slides.length <= 1;
  document.querySelector("#move-slide-up").disabled = state.currentSlide <= 0;
  document.querySelector("#move-slide-down").disabled = state.currentSlide >= state.deck.slides.length - 1;
}

function duplicateSelectedSlide() {
  const index = state.currentSlide;
  state.currentSlide = index + 1;
  commitSource(duplicateSlide(state.deck, index));
}

function addSlideAfterSelection() {
  const index = state.currentSlide;
  state.currentSlide = index + 1;
  commitSource(insertSlide(state.deck, index));
}

function deleteSelectedSlide() {
  const index = state.currentSlide;
  const slide = state.deck.slides[index];
  if (!slide || !confirm(`Delete slide ${index + 1}, “${slide.title || "Untitled"}”?`)) return;
  state.currentSlide = Math.min(index, state.deck.slides.length - 2);
  commitSource(deleteSlide(state.deck, index));
}

function moveSelectedSlide(direction) {
  const from = state.currentSlide;
  const to = from + direction;
  if (to < 0 || to >= state.deck.slides.length) return;
  state.currentSlide = to;
  commitSource(moveSlide(state.deck, from, to));
}

function onSlideChanged(event) {
  state.currentSlide = event.indexh;
  rebuildSlideList();
  editor?.refresh();
}

function setMode(mode) {
  state.mode = mode;
  document.body.classList.toggle("presenting", mode === "present");
  elements.workspace.className = `workspace mode-${mode}`;
  elements.sourcePane.hidden = mode !== "source";
  document.querySelectorAll("[data-mode]").forEach(button => button.classList.toggle("active", button.dataset.mode === mode));
  if (reveal) {
    reveal.configure({
      controls: mode === "present",
      progress: mode === "present",
      keyboard: mode === "present",
      touch: mode === "present",
      overview: mode === "present",
      embedded: mode !== "present",
    });
    setTimeout(() => { reveal.layout(); reveal.slide(state.currentSlide); editor?.refresh(); }, 0);
  }
  if (mode === "source") elements.source.focus();
}

function updateDirtyState() {
  const dirty = state.source !== state.savedSource;
  elements.save.disabled = !state.deck || !dirty;
  elements.download.disabled = !state.deck;
  elements.saveState.textContent = dirty ? "Unsaved" : "Saved";
  elements.saveState.classList.toggle("dirty", dirty);
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

async function loadLocalDeck() {
  try {
    const configResponse = await fetch("/api/config", { cache: "no-store" });
    if (!configResponse.ok) return false;
    state.config = await configResponse.json();
    state.local = state.config.mode === "local";
    state.filename = state.config.deck;
    const response = await fetch("/api/deck", { cache: "no-store" });
    if (!response.ok) throw new Error("Cannot load deck");
    const source = await response.text();
    state.serverHash = await hashText(source);
    state.savedSource = source;
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
      const answer = Number(prompt(`Choose a presentation:\n${choices}`, "1")) - 1;
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
  for (const path of paths) {
    if (/^[a-z]+:/i.test(path)) continue;
    try {
      const handle = await nestedFileHandle(state.directoryHandle, path);
      const file = await handle.getFile();
      state.objectUrls.set(path, URL.createObjectURL(file));
    } catch { /* Missing assets are diagnosed by the browser image event. */ }
  }
}

async function saveDeck() {
  try {
    if (state.local) {
      const response = await fetch("/api/deck", {
        method: "PUT",
        headers: { "Content-Type": "text/markdown; charset=utf-8", ...(state.serverHash ? { "If-Match": `"${state.serverHash}"` } : {}) },
        body: state.source,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Save failed");
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
  const blob = new Blob([state.source], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = state.filename.split(/[\\/]/).pop() || "presentation.md";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function importAsset(file) {
  if (!file?.type.startsWith("image/")) throw new Error("Only image files are supported");
  if (state.local) {
    const response = await fetch(`/api/asset?name=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": file.type }, body: file });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Asset import failed");
    return result.path;
  }
  const safe = file.name.replace(/[^a-zA-Z0-9._-]/g, "-");
  let path = `figures/${safe}`;
  if (state.directoryHandle) {
    const extension = safe.includes(".") ? `.${safe.split(".").pop()}` : "";
    const stem = extension ? safe.slice(0, -extension.length) : safe;
    let counter = 2;
    while (true) {
      try {
        await nestedFileHandle(state.directoryHandle, path);
        path = `figures/${stem}-${counter++}${extension}`;
      } catch { break; }
    }
    const handle = await nestedFileHandle(state.directoryHandle, path, true);
    const writable = await handle.createWritable();
    await writable.write(file);
    await writable.close();
  }
  state.objectUrls.set(path, URL.createObjectURL(file));
  return path;
}

function bindUi() {
  document.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => setMode(button.dataset.mode)));
  document.querySelector("#open-button").addEventListener("click", () => openPortable().catch(error => showStatus(error.message, true)));
  elements.save.addEventListener("click", saveDeck);
  elements.download.addEventListener("click", downloadSource);
  document.querySelector("#apply-source").addEventListener("click", () => commitSource(elements.source.value));
  document.querySelector("#revert-source").addEventListener("click", () => { elements.source.value = state.source; });
  document.querySelector("#file-input").addEventListener("change", async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    state.filename = file.name;
    const source = await file.text();
    state.savedSource = source;
    state.local = false;
    parseAndRender(source, { preserveSlide: false });
  });
  document.querySelector("#undo-button").addEventListener("click", undo);
  document.querySelector("#redo-button").addEventListener("click", redo);
  document.querySelector("#add-slide").addEventListener("click", addSlideAfterSelection);
  document.querySelector("#duplicate-slide").addEventListener("click", duplicateSelectedSlide);
  document.querySelector("#delete-slide").addEventListener("click", deleteSelectedSlide);
  document.querySelector("#move-slide-up").addEventListener("click", () => moveSelectedSlide(-1));
  document.querySelector("#move-slide-down").addEventListener("click", () => moveSelectedSlide(1));
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); saveDeck(); }
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "z") { event.preventDefault(); undo(); }
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "z") { event.preventDefault(); redo(); }
    if (event.key === "Escape" && state.mode === "present") setMode("design");
  });
  window.addEventListener("beforeunload", event => {
    if (state.source !== state.savedSource) { event.preventDefault(); event.returnValue = ""; }
  });
}

async function initialize() {
  bindUi();
  const loaded = await loadLocalDeck();
  if (!loaded) {
    state.savedSource = "";
    parseAndRender(STARTER, { preserveSlide: true });
  }
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
  editor = new DesignEditor({
    getDeck: () => state.deck,
    getMode: () => state.mode,
    getSlideIndex: () => state.currentSlide,
    commitSource,
    importAsset: async file => {
      try { return await importAsset(file); }
      catch (error) { showStatus(error.message, true); return null; }
    },
  });
  editor.refresh();
  setMode(state.mode);
}

initialize().catch(error => {
  console.error(error);
  document.body.innerHTML = `<pre style="padding:2rem;color:#ff8787">${error.message}\n\nRun tools/fetch_vendor.py before starting the application.</pre>`;
});
