import { parseDeck } from "./parser.js";
import { renderDeck, syncVideoPlayback } from "./render.js";
import { prepareBibliography } from "./bibliography.js";
import { openPrintDialogWhenReady, pdfPrintUrl, pdfPrintView, printShortcut } from "./print.js";

const localPlayer = document.body.dataset.playerSource === "local";

function assetPath(source) {
  if (!source || /^(?:javascript|data:text\/html):/i.test(source)) return "";
  const path = source.replaceAll("\\", "/").split("/").map(part => encodeURIComponent(part)).join("/");
  return localPlayer ? `/project/${path}` : path;
}

function showError(error) {
  const loading = document.querySelector("#loading");
  loading.className = "player-error";
  loading.textContent = `Cannot open presentation: ${error.message}`;
}

async function initialize() {
  const deckUrl = localPlayer ? "/api/deck" : "presentation.md";
  const response = await fetch(deckUrl, { cache: "no-store" });
  if (!response.ok) throw new Error(`${deckUrl} returned HTTP ${response.status}`);
  const deck = parseDeck(await response.text());
  const errors = deck.diagnostics.filter(item => item.level === "error");
  if (errors.length) throw new Error(errors.map(item => item.message).join("; "));

  if (deck.metadata?.title) document.title = String(deck.metadata.title);
  const bibliographyPath = typeof deck.metadata?.bibliography === "string" ? deck.metadata.bibliography : null;
  let bibliographySource = "";
  let bibliographyPdfs = {};
  if (bibliographyPath) {
    const bibliographyUrl = localPlayer
      ? `/api/bibliography?path=${encodeURIComponent(bibliographyPath)}`
      : assetPath(bibliographyPath);
    const bibliographyResponse = await fetch(bibliographyUrl, { cache: "no-store" });
    if (!bibliographyResponse.ok) throw new Error(`Bibliography returned HTTP ${bibliographyResponse.status}`);
    if (localPlayer) {
      const bibliography = await bibliographyResponse.json();
      bibliographySource = bibliography.source;
      bibliographyPdfs = bibliography.pdfs || {};
    } else bibliographySource = await bibliographyResponse.text();
  }
  renderDeck(deck, document.querySelector("#slides"), assetPath, prepareBibliography(bibliographySource, deck, bibliographyPdfs), { includeTrashed: false });
  const reveal = new window.Reveal(document.querySelector(".reveal"), {
    controls: true,
    progress: true,
    hash: true,
    history: true,
    keyboard: true,
    touch: true,
    overview: true,
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
  document.querySelector("#loading").remove();
  if (pdfPrintView()) {
    document.querySelector("#print-button")?.remove();
    if (new URLSearchParams(location.search).has("print-dialog")) openPrintDialogWhenReady();
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
