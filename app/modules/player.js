import { parseDeck } from "./parser.js";
import { renderDeck, syncVideoPlayback } from "./render.js";
import { prepareBibliography } from "./bibliography.js";
import { openPrintDialogWhenReady, pdfPrintUrl, pdfPrintView, printShortcut, waitForRenderAssets } from "./print.js";

const localPlayer = document.body.dataset.playerSource === "local";
const search = new URLSearchParams(location.search);
const previewView = search.has("preview");

// Published decks share one asset pool, so the page carries a map from the
// deck's own paths to it. Exports and the editor have none and resolve as before.
const assetMap = (() => {
  const element = document.querySelector("#quarkfoil-assets");
  if (!element) return null;
  try {
    return JSON.parse(element.textContent);
  } catch {
    return null;
  }
})();

function assetPath(source) {
  if (!source || /^(?:javascript|data:text\/html):/i.test(source)) return "";
  const raw = source.replaceAll("\\", "/");
  const pooled = assetMap?.[raw];
  if (pooled) return pooled;
  const path = raw.split("/").map(part => encodeURIComponent(part)).join("/");
  return localPlayer ? `/project/${path}` : path;
}

function embeddedSource() {
  const element = document.querySelector("#quarkfoil-source");
  if (!element) return null;
  try {
    return JSON.parse(element.textContent);
  } catch {
    return null;
  }
}

// Exports embed the deck so the site also opens straight from the file system,
// where fetch() has no origin to read from.
async function readSource(url, embedded) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (response.ok) return await response.text();
    if (embedded == null) throw new Error(`${url} returned HTTP ${response.status}`);
  } catch (error) {
    if (embedded == null) throw error;
  }
  return embedded;
}

function showError(error) {
  const loading = document.querySelector("#loading");
  loading.className = "player-error";
  loading.textContent = `Cannot open presentation: ${error.message}`;
}

async function initialize() {
  const requestedDeck = search.get("deck");
  const embedded = localPlayer ? null : embeddedSource();
  const deckUrl = localPlayer
    ? `/api/deck${requestedDeck ? `?path=${encodeURIComponent(requestedDeck)}` : ""}`
    : "presentation.md";
  const deck = parseDeck(await readSource(deckUrl, embedded?.deck ?? null));
  const errors = deck.diagnostics.filter(item => item.level === "error");
  if (errors.length) throw new Error(errors.map(item => item.message).join("; "));

  if (deck.metadata?.title) document.title = String(deck.metadata.title);
  const bibliographyPath = typeof deck.metadata?.bibliography === "string" ? deck.metadata.bibliography : null;
  let bibliographySource = "";
  let bibliographyPdfs = {};
  if (bibliographyPath) {
    if (localPlayer) {
      const bibliographyUrl = `/api/bibliography?path=${encodeURIComponent(bibliographyPath)}`;
      const bibliographyResponse = await fetch(bibliographyUrl, { cache: "no-store" });
      if (!bibliographyResponse.ok) throw new Error(`Bibliography returned HTTP ${bibliographyResponse.status}`);
      const bibliography = await bibliographyResponse.json();
      bibliographySource = bibliography.source;
      bibliographyPdfs = bibliography.pdfs || {};
    } else bibliographySource = await readSource(assetPath(bibliographyPath), embedded?.bibliography ?? null);
  }
  renderDeck(deck, document.querySelector("#slides"), assetPath, prepareBibliography(bibliographySource, deck, bibliographyPdfs), { includeTrashed: false });
  const reveal = new window.Reveal(document.querySelector(".reveal"), {
    controls: !previewView,
    progress: !previewView,
    hash: !previewView,
    history: !previewView,
    keyboard: !previewView,
    touch: !previewView,
    overview: !previewView,
    center: false,
    transition: "none",
    width: 1280,
    height: 720,
    margin: 0,
    minScale: 0.1,
    maxScale: 3,
    pdfMaxPagesPerSlide: 1,
    pdfSeparateFragments: false,
    plugins: window.RevealNotes ? [window.RevealNotes] : [],
  });
  await reveal.initialize();
  reveal.on("slidechanged", event => syncVideoPlayback(event.currentSlide));
  syncVideoPlayback(reveal.getCurrentSlide());
  if (previewView) {
    document.querySelector("#print-button")?.remove();
    await waitForRenderAssets();
    document.querySelector("#loading").remove();
    await waitForRenderAssets();
    document.documentElement.dataset.previewReady = "true";
  } else document.querySelector("#loading").remove();
  if (pdfPrintView()) {
    document.querySelector("#print-button")?.remove();
    if (search.has("print-dialog")) openPrintDialogWhenReady();
  }
}

document.querySelector("#print-button")?.addEventListener("click", () => window.location.assign(pdfPrintUrl()));
document.addEventListener("keydown", event => {
  if (printShortcut(event) && !pdfPrintView()) {
    event.preventDefault();
    window.location.assign(pdfPrintUrl());
  }
});

initialize().catch(showError);
