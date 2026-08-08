import {
  deleteOverlay,
  duplicateOverlay,
  parseDeck,
  setCellContent,
  updateBlockContent,
  updateHeadingLayout,
  updateOverlay,
  updateSlideTitle,
} from "./parser.js";

const source = `---
title: Test deck
defaults:
  footer: Footer
---

## First {.layout-1-2 columns="40 60" rows="55 45"}

::: left
Left **Markdown**.
:::

::: top-right
![](figures/a.svg){fit=cover focus="70 30"}
:::

::: overlay {#eq type="equation" x="62" y="31" w="24" h="9"}
\\[
E=mc^2
\\]
:::

---

## Second {.layout-free}
`;

const checks = [];
function assert(condition, message) {
  if (!condition) throw new Error(message);
  checks.push(`PASS ${message}`);
}

try {
  let deck = parseDeck(source);
  assert(deck.metadata.title === "Test deck", "front matter parses");
  assert(deck.slides.length === 2, "slides split");
  assert(deck.slides[0].layout === "1-2", "layout parses");
  assert(Math.round(deck.slides[0].columns[0]) === 40, "column ratios parse");
  assert(deck.slides[0].cells.find(cell => cell.id === "top-right").image.attrs.values.fit === "cover", "image attributes parse");
  assert(deck.slides[0].overlays[0].id === "eq", "overlay ID parses");
  assert(deck.slides[1].cells[0]?.range !== null, "ordinary core Markdown retains an editable range");

  let next = updateOverlay(deck, 0, "eq", { x: 51.5, y: 22, locked: "true" });
  assert(next.includes('x="51.5"'), "overlay geometry patches source");
  assert(next.includes("E=mc^2"), "overlay patch preserves content");
  deck = parseDeck(next);

  next = updateSlideTitle(deck, 0, "Edited title");
  assert(next.includes('## Edited title {.layout-1-2'), "title patches without losing layout attributes");
  deck = parseDeck(next);

  next = updateBlockContent(deck, 0, "eq", "\\[F=ma\\]");
  assert(next.includes("F=ma"), "block content patches source");
  deck = parseDeck(next);

  next = updateHeadingLayout(deck, 0, "1-1", [35, 65], [50, 50]);
  assert(next.includes(".layout-1-1"), "layout patches heading");
  assert(next.includes('columns="35 65"'), "layout ratios serialize");
  deck = parseDeck(next);

  next = setCellContent(deck, 0, "right", "New cell");
  assert(next.includes("::: right\nNew cell"), "missing cell inserts declaratively");
  deck = parseDeck(next);

  next = duplicateOverlay(deck, 0, "eq", "eq-copy");
  assert(next.includes("#eq-copy"), "overlay duplicates with stable ID");
  deck = parseDeck(next);

  next = deleteOverlay(deck, 0, "eq-copy");
  assert(!next.includes("#eq-copy"), "overlay deletes narrowly");

  document.body.dataset.status = "passed";
  document.querySelector("#results").textContent = `${checks.join("\n")}\n\n${checks.length} checks passed.`;
} catch (error) {
  document.body.dataset.status = "failed";
  document.querySelector("#results").textContent = `${checks.join("\n")}\n\nFAIL ${error.stack || error.message}`;
}
