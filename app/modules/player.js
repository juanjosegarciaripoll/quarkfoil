import { parseDeck } from "./parser.js";
import { renderDeck } from "./render.js";

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
  renderDeck(deck, document.querySelector("#slides"), assetPath);
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
  document.querySelector("#loading").remove();
}

initialize().catch(showError);
