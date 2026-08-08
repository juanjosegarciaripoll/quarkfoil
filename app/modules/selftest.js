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
import { renderDeck } from "./render.js";

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

function assertCompoundLayout(layout, cellIds, spanningCellId) {
  const layoutSource = `## Geometry {.layout-${layout} columns="40 60" rows="55 45"}\n\n`
    + cellIds.map(id => `::: ${id}\n${id}\n:::\n`).join("\n");
  const fixture = document.createElement("div");
  fixture.id = "layout-fixture";
  document.body.append(fixture);
  const parsed = parseDeck(layoutSource);
  renderDeck(parsed, fixture, source => source);
  const grid = fixture.querySelector(".slide-grid");
  const gridRect = grid.getBoundingClientRect();
  const rectangles = Object.fromEntries(cellIds.map(id => [id, fixture.querySelector(`.cell-${id}`).getBoundingClientRect()]));
  const epsilon = 1;
  for (const [id, rect] of Object.entries(rectangles)) {
    assert(rect.left >= gridRect.left - epsilon && rect.right <= gridRect.right + epsilon
      && rect.top >= gridRect.top - epsilon && rect.bottom <= gridRect.bottom + epsilon,
    `${layout} ${id} stays inside the grid`);
  }
  const nonSpanning = cellIds.filter(id => id !== spanningCellId).map(id => rectangles[id]);
  assert(nonSpanning[0].bottom <= nonSpanning[1].top + epsilon, `${layout} stacked cells do not overlap`);
  const spanning = rectangles[spanningCellId];
  assert(Math.abs(spanning.top - nonSpanning[0].top) <= epsilon
    && Math.abs(spanning.bottom - nonSpanning[1].bottom) <= epsilon,
  `${layout} spanning cell covers both rows`);
  fixture.remove();
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

  assertCompoundLayout("1-2", ["left", "top-right", "bottom-right"], "left");
  assertCompoundLayout("2-1", ["top-left", "bottom-left", "right"], "right");

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
