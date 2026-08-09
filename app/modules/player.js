import { parseDeck } from "./parser.js";
import { renderDeck, syncVideoPlayback } from "./render.js";
import { prepareBibliography } from "./bibliography.js";

function assetPath(source) {
  if (!source || /^(?:javascript|data:text\/html):/i.test(source)) return "";
  return source.replaceAll("\\", "/").split("/").map(part => encodeURIComponent(part)).join("/");
}

function showError(error) {
  const loading = document.querySelector("#loading");
  loading.className = "player-error";
  loading.textContent = `Cannot open presentation: ${error.message}`;
}

async function initialize() {
  const response = await fetch("presentation.md", { cache: "no-store" });
  if (!response.ok) throw new Error(`presentation.md returned HTTP ${response.status}`);
  const deck = parseDeck(await response.text());
  const errors = deck.diagnostics.filter(item => item.level === "error");
  if (errors.length) throw new Error(errors.map(item => item.message).join("; "));

  if (deck.metadata?.title) document.title = String(deck.metadata.title);
  const bibliographyPath = typeof deck.metadata?.bibliography === "string" ? deck.metadata.bibliography : null;
  let bibliographySource = "";
  if (bibliographyPath) {
    const bibliographyResponse = await fetch(assetPath(bibliographyPath), { cache: "no-store" });
    if (!bibliographyResponse.ok) throw new Error(`Bibliography returned HTTP ${bibliographyResponse.status}`);
    bibliographySource = await bibliographyResponse.text();
  }
  renderDeck(deck, document.querySelector("#slides"), assetPath, prepareBibliography(bibliographySource, deck));
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
    plugins: window.RevealNotes ? [window.RevealNotes] : [],
  });
  await reveal.initialize();
  reveal.on("slidechanged", event => syncVideoPlayback(event.currentSlide));
  syncVideoPlayback(reveal.getCurrentSlide());
  document.querySelector("#loading").remove();
}

initialize().catch(showError);
