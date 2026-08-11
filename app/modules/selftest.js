import {
  deleteOverlay,
  deleteSlide,
  duplicateSlide,
  importSlide,
  insertOverlay,
  insertSlide,
  moveSlide,
  duplicateOverlay,
  parseDeck,
  setCellContent,
  updateBlockContent,
  updateHeadingLayout,
  updateOverlay,
  updateSlideTitle,
  updateSlideProperties,
} from "./parser.js";
import { renderDeck, syncVideoPlayback } from "./render.js";
import { bindRangeControl, clipboardImageFile, deleteKey, initialImageGeometry, moveGeometryGroup, pageSlideIndex, projectAssetPage, rectanglesIntersect, renameClipboardImage, repeatedActivation, videoFile } from "./editor.js";
import { parseBibliography, prepareBibliography } from "./bibliography.js";
import { compileExpression, createPlotSvg } from "./plot.js";

const source = `---
title: Test deck
assets:
  figures: artwork
  include:
    - references
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

::: overlay {#eq type="equation" x="62" y="31" w="24" h="9" font-size="1.4em" align="right"}
\\[
E=mc^2
\\]
:::

::: overlay {#movie type="video" src="artwork/demo.mp4" poster="artwork/poster.jpg" x="10" y="70" w="30" h="17" autoplay="true" muted="true"}
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

function assertFrontLayout() {
  const fixture = document.createElement("div");
  fixture.id = "layout-fixture";
  fixture.className = "reveal";
  const slides = document.createElement("div");
  slides.className = "slides";
  fixture.append(slides);
  document.body.append(fixture);
  const parsed = parseDeck(`## Front title {.layout-front}\n\n::: core\nAuthor and affiliation\n:::`);
  renderDeck(parsed, slides, source => source);
  const section = fixture.querySelector(".scientific-slide");
  section.classList.add("present");
  const title = fixture.querySelector(".slide-title").getBoundingClientRect();
  const core = fixture.querySelector(".slide-core").getBoundingClientRect();
  const sectionRect = section.getBoundingClientRect();
  const style = getComputedStyle(section);
  const contentHeight = sectionRect.height - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
  assert(parsed.slides[0].layout === "front", "front-page layout parses");
  assert(Math.abs(title.height - core.height) <= 1, `front page divides title and details equally (${title.height.toFixed(1)} / ${core.height.toFixed(1)})`);
  assert(Math.abs(title.height + core.height - contentHeight) <= 1, `front page fills the padded content height (${(title.height + core.height).toFixed(1)} / ${contentHeight.toFixed(1)})`);
  assert(getComputedStyle(fixture.querySelector(".slide-cell")).justifyContent === "flex-start", "front-page details align to the top of the lower region");
  fixture.remove();
}

function assertEmptyLayouts() {
  const fixture = document.createElement("div");
  fixture.id = "layout-fixture";
  fixture.className = "reveal";
  const slides = document.createElement("div");
  slides.className = "slides";
  fixture.append(slides);
  document.body.append(fixture);
  const parsed = parseDeck(`---\ndefaults:\n  footer: Footer\n---\n\n## Title and footer {.layout-0}\n\n---\n\n## Hidden structure {.layout-free}\n\n::: overlay {#free-text type="markdown" x="20" y="20" w="40" h="20" font-size="0.25em" align="center"}\nFree overlay\n:::\n\n::: overlay {#free-equation type="equation" x="20" y="50" w="60" h="20" align="right"}\n\\[E=mc^2\\]\n:::`);
  renderDeck(parsed, slides, source => source);
  const zero = fixture.querySelector(".layout-0");
  const free = fixture.querySelector(".layout-free");
  assert(zero.querySelectorAll(".slide-cell").length === 0, "layout 0 creates no core cells");
  assert(getComputedStyle(zero.querySelector(".slide-frame")).display === "grid", "layout 0 keeps title and footer structure");
  assert(getComputedStyle(free.querySelector(".slide-frame")).display === "none", "free layout hides title, core and footer");
  assert(free.querySelectorAll(".slide-overlay").length === 2, "free layout retains positioned overlays");
  assert(free.querySelector(".overlay-markdown").style.fontSize === "0.25em", "Markdown overlays render relative font sizes down to 0.25 em");
  assert(free.querySelector(".overlay-markdown").dataset.align === "center", "Markdown overlays render explicit alignment");
  assert(getComputedStyle(free.querySelector(".overlay-equation .katex-display > .katex")).textAlign === "right", "equation alignment overrides KaTeX inner alignment");
  fixture.remove();
}

function assertShapes() {
  const fixture = document.createElement("div");
  fixture.id = "layout-fixture";
  fixture.className = "reveal";
  const slides = document.createElement("div");
  slides.className = "slides";
  fixture.append(slides);
  document.body.append(fixture);
  const parsed = parseDeck(`## Shapes {.layout-free}

::: overlay {#cloud type="shape" shape="cloud" x="5" y="5" w="25" h="20" fill="#ffeecc80" stroke="#112233" stroke-width="3" shadow="true"}
Thought
:::

::: overlay {#callout type="shape" shape="callout" x="35" y="5" w="25" h="20"}
\\(E=mc^2\\)
:::`);
  renderDeck(parsed, slides, source => source);
  const cloud = fixture.querySelector('[data-object-id="cloud"]');
  assert(parsed.slides[0].overlays[0].shape === "cloud", "shape kind parses");
  assert(parsed.slides[0].overlays[0].fill === "#ffeecc80" && parsed.slides[0].overlays[0].strokeWidth === 3, "shape styles including alpha parse");
  assert(getComputedStyle(cloud.querySelector(".shape-surface")).fill.includes("0.5"), "shape color alpha renders");
  assert(parsed.slides[0].overlays[0].shadow && cloud.dataset.shadow === "true", "shape shadow parses and renders");
  assert(cloud.querySelector(".shape-background path") && cloud.querySelector(".shape-label").textContent.includes("Thought"), "cloud renders with a Markdown label");
  assert(fixture.querySelector('[data-object-id="callout"] .katex'), "comic callout renders an equation label");
  const calloutSurface = getComputedStyle(fixture.querySelector('[data-object-id="callout"] .shape-surface'));
  assert(calloutSurface.fill === "rgb(219, 239, 242)" && calloutSurface.stroke === "rgb(20, 108, 126)", "implicit shape colors inherit from the theme");
  fixture.remove();
}

function assertCitations() {
  const fixture = document.createElement("div");
  fixture.id = "layout-fixture";
  fixture.className = "reveal";
  const slides = document.createElement("div"); slides.className = "slides"; fixture.append(slides); document.body.append(fixture);
  const parsed = parseDeck(`## References {.layout-1}\n\nInline [@einstein1905], repeated [@einstein1905], and code \`[@ignored]\`.\n\n::: overlay {#source type="citation" keys="smith2024 einstein1905" display="brief" x="50" y="80" w="45" h="8"}\n\n:::`);
  const bib = `@article{einstein1905, author={Einstein, Albert}, journal={Annalen der Physik}, volume={17}, pages={891--921}, year={1905}, doi={10.1002/test}}\n@article{smith2024, author={Smith, Alice and Jones, Bob}, journal={Physical Review Letters}, volume={132}, number={123456}, year={2024}}`;
  const bibliography = prepareBibliography(bib, parsed);
  const doiEntry = parseBibliography("@article{wallraff2004, month={Sept}, doi={10.1038/nature02851}}")[0];
  assert(doiEntry.key === "wallraff2004" && doiEntry.fields.month === "Sept" && doiEntry.fields.doi === "10.1038/nature02851", "normalized DOI BibTeX and citation key parse");
  let bibliographyError = "";
  try { parseBibliography("@article{broken, month=Sept}"); } catch (error) { bibliographyError = error.message; }
  assert(bibliographyError.startsWith("Invalid BibTeX:"), "BibTeX parser failures produce visible error messages");
  renderDeck(parsed, slides, source => source, bibliography);
  assert(bibliography.numbers.get("einstein1905") === 1 && !bibliography.numbers.has("smith2024"), "attributions do not consume citation numbers");
  assert(fixture.querySelectorAll(".citation-number").length === 2, "only inline citations display numbers while code remains literal");
  const attribution = fixture.querySelector(".overlay-citation").textContent;
  assert(attribution.includes("Smith et al.") && attribution.includes("Einstein"), "positioned attribution renders multiple selected references");
  const attributionStyle = getComputedStyle(fixture.querySelector(".overlay-citation"));
  assert(attributionStyle.backgroundColor === "rgba(0, 0, 0, 0)" && attributionStyle.boxShadow === "none", "attributions render without a background panel");
  fixture.remove();
}

function assertThemes() {
  let deck = parseDeck("---\ntheme: scientific-light\n---\n\n## Light {.layout-1}\n\n---\n\n## Dark {.layout-1 theme=\"scientific-dark\" background=\"#101820\" foreground=\"#f0f4f8\"}\n");
  const fixture = document.createElement("div");
  renderDeck(deck, fixture, source => source);
  const [light, dark] = fixture.querySelectorAll(".scientific-slide");
  assert(light.classList.contains("theme-scientific-light"), "slide inherits the deck theme");
  assert(dark.classList.contains("theme-scientific-dark"), "slide selects its own theme");
  assert(dark.style.getPropertyValue("--slide-background") === "#101820" && dark.style.getPropertyValue("--slide-foreground") === "#f0f4f8", "slide colors override theme variables");
  const overview = document.createElement("div");
  overview.className = "reveal overview";
  const overviewSlides = document.createElement("div");
  overviewSlides.className = "slides";
  overview.append(overviewSlides);
  document.body.append(overview);
  renderDeck(deck, overviewSlides, source => source);
  const [overviewLight, overviewDark] = overviewSlides.querySelectorAll(".scientific-slide");
  overviewLight.hidden = true;
  overviewDark.hidden = true;
  assert(getComputedStyle(overviewLight).display === "block" && getComputedStyle(overviewDark).display === "block", "overview reveals non-current slide surfaces");
  assert(getComputedStyle(overviewLight).backgroundColor !== getComputedStyle(overviewDark).backgroundColor, "overview keeps slide themes independent");
  overview.remove();
  deck = parseDeck(updateSlideProperties(deck, 1, { theme: null, background: null, foreground: null }));
  assert(!deck.slides[1].headingAttrs.values.theme && !deck.slides[1].headingAttrs.values.background, "inherited slide theme values do not occupy source state");
}

function assertTables() {
  const fixture = document.createElement("div");
  fixture.className = "reveal";
  document.body.append(fixture);
  const deck = parseDeck("## Data {.layout-1 theme=\"scientific-dark\"}\n\n::: core\n| Parameter | Value |\n|---|---:|\n| Tunnelling | 1.2 |\n| Interaction | 8.4 |\n:::\n");
  renderDeck(deck, fixture, source => source);
  const table = fixture.querySelector("table");
  assert(table?.querySelectorAll("tbody tr").length === 2, "Markdown tables render with header and body rows");
  assert(getComputedStyle(table.querySelector("th")).backgroundColor !== "rgba(0, 0, 0, 0)", "table headers receive theme-aware styling");
  fixture.remove();
}

try {
  const rangeFixture = document.createElement("div");
  rangeFixture.innerHTML = '<input id="test-range" type="range" min="0.25" max="3" step="0.05" value="1"><input id="test-range-value" type="number">';
  document.body.append(rangeFixture);
  bindRangeControl("test-range");
  rangeFixture.querySelector("#test-range").value = "1.7";
  rangeFixture.querySelector("#test-range").dispatchEvent(new Event("input"));
  assert(rangeFixture.querySelector("#test-range-value").value === "1.7", "slider changes update the editable numeric value");
  rangeFixture.querySelector("#test-range-value").value = "9";
  rangeFixture.querySelector("#test-range-value").dispatchEvent(new Event("change"));
  assert(rangeFixture.querySelector("#test-range").value === "3" && rangeFixture.querySelector("#test-range-value").value === "3", "editable slider values clamp to their declared bounds");
  rangeFixture.remove();

  assert(pageSlideIndex(2, 5, "PageUp") === 1 && pageSlideIndex(2, 5, "PageDown") === 3, "page keys navigate to adjacent editor slides");
  assert(pageSlideIndex(0, 5, "PageUp") === 0 && pageSlideIndex(4, 5, "PageDown") === 4, "page-key slide navigation stays within deck bounds");
  const movedGroup = moveGeometryGroup([{ x: 5, y: 10, w: 20, h: 10 }, { x: 40, y: 30, w: 30, h: 20 }], -10, 60);
  assert(movedGroup[0].x === 0 && movedGroup[0].y === 60 && movedGroup[1].x === 35 && movedGroup[1].y === 80, "group movement preserves spacing and stays inside the slide");
  assert(rectanglesIntersect({ left: 0, top: 0, right: 20, bottom: 20 }, { left: 20, top: 10, right: 30, bottom: 30 }), "marquee selection includes objects touching its boundary");
  assert(!rectanglesIntersect({ left: 0, top: 0, right: 19, bottom: 20 }, { left: 20, top: 10, right: 30, bottom: 30 }), "marquee selection excludes separated objects");

  const clipboardPng = new File([new Uint8Array([137, 80, 78, 71])], "", { type: "image/png" });
  const pastedPng = clipboardImageFile({
    items: [{ kind: "file", type: "image/png", getAsFile: () => clipboardPng }],
  }, 1234);
  assert(pastedPng.name === "pasted-image-1234.png" && pastedPng.type === "image/png", "clipboard images receive an importable filename");
  const clipboardJpeg = new File([new Uint8Array([255, 216, 255])], "photo.jpg", { type: "image/jpeg" });
  const pastedJpeg = clipboardImageFile({
    files: [clipboardPng],
    items: [{ kind: "file", type: "image/jpeg", getAsFile: () => clipboardJpeg }],
  });
  assert(pastedJpeg === clipboardJpeg && pastedJpeg.type === "image/jpeg", "an original JPEG clipboard representation is preferred over synthesized PNG");
  const clipboardGif = new File([new Uint8Array([71, 73, 70])], "animation.gif", { type: "image/gif" });
  assert(clipboardImageFile({ files: [clipboardGif] }) === clipboardGif, "pasted GIF files retain their original bytes and animation");
  assert(renameClipboardImage(pastedPng, "experiment-result").name === "experiment-result.png", "pasted images accept a chosen filename and infer its extension");
  assert(renameClipboardImage(pastedPng, "plots/result")?.name === "plots-result.png", "pasted image filenames cannot introduce directories");
  assert(renameClipboardImage(pastedPng, "  ") === null, "an empty pasted image filename cancels the import");
  assert(videoFile(new File([], "recording.mkv")) && videoFile(new File([], "recording.avi")), "MKV and AVI drops are recognized without MIME metadata");
  assert(repeatedActivation({ key: "overlay:text-1", time: 100 }, "overlay:text-1", 300), "a repeated canvas click is recognized for editing");
  assert(repeatedActivation({ key: "cell:left", time: 100 }, "cell:left", 300), "a repeated layout-cell click is recognized for editing");
  assert(!repeatedActivation({ key: "cell:left", time: 100 }, "cell:right", 300), "clicks on different canvas elements do not trigger editing");
  assert(deleteKey("Delete") && deleteKey("Del"), "Delete and Del keys remove selected images and overlays");
  const expression = compileExpression("Math.sin(x) + x ** 2");
  assert(Math.abs(expression(2) - (Math.sin(2) + 4)) < 1e-10, "plot expressions support JavaScript-style Math functions and operators");
  const barePlot = createPlotSvg("sin(x)", 0, 2 * Math.PI, 40, false);
  assert(barePlot.includes('<svg xmlns="http://www.w3.org/2000/svg"') && barePlot.includes('data-quarkfoil-plot="1"') && !barePlot.includes('class="axes"'), "axis-free plots serialize as identifiable standalone SVG without axes");
  assert(/<path d="M0\.00 /.test(barePlot) && barePlot.includes("800.00"), "axis-free plot curves use the full SVG width without padding");
  const plotViewBox = barePlot.match(/viewBox="([^"]+)"/)[1].split(/\s+/).map(Number);
  assert(plotViewBox[0] < 0 && plotViewBox[1] < 0 && plotViewBox[0] + plotViewBox[2] > 800 && plotViewBox[1] + plotViewBox[3] > 450, "plot viewports include spline overshoot and stroke instead of clipping at the data bounds");
  const axesPlot = createPlotSvg("x", -1, 1, 20, true);
  assert(axesPlot.includes('class="axes"') && axesPlot.includes(" C"), "plots optionally include axes and spline interpolation");
  const projectAssets = Array.from({ length: 30 }, (_, index) => ({ path: `figures/result-${index}.png` }));
  const firstAssetPage = projectAssetPage(projectAssets, "", 0);
  assert(firstAssetPage.assets.length === 24 && firstAssetPage.pages === 2, "project asset navigation shows 24 items per page");
  const assetPage = projectAssetPage(projectAssets, "result-2", 1, 4);
  assert(assetPage.count === 11 && assetPage.page === 1 && assetPage.assets.length === 4, "project asset search and pagination stay bounded");
  assert(clipboardImageFile({ items: [{ kind: "string", type: "text/plain", getAsFile: () => null }] }) === null, "text-only clipboard data is ignored");
  const landscapeGeometry = initialImageGeometry(2, 16 / 9);
  assert(landscapeGeometry.w === 35 && landscapeGeometry.h === 31.1, "landscape image overlays preserve their pixel aspect ratio");
  assert(landscapeGeometry.x === 32.5 && landscapeGeometry.y === 34.5, "new image overlays are centered");
  const portraitGeometry = initialImageGeometry(0.5, 16 / 9, { x: 95, y: 90 });
  assert(portraitGeometry.w === 9.8 && portraitGeometry.h === 35, "portrait image overlays preserve their pixel aspect ratio");
  assert(portraitGeometry.x === 90.2 && portraitGeometry.y === 65, "dropped image overlays stay inside the slide");

  let deck = parseDeck(source);
  assert(deck.metadata.title === "Test deck", "front matter parses");
  assert(deck.metadata.assets.figures === "artwork" && deck.metadata.assets.include[0] === "references", "asset folders parse from front matter");
  assert(deck.slides.length === 2, "slides split");
  assert(deck.slides[0].layout === "1-2", "layout parses");
  assert(Math.round(deck.slides[0].columns[0]) === 40, "column ratios parse");
  assert(deck.slides[0].cells.find(cell => cell.id === "top-right").image.attrs.values.fit === "cover", "image attributes parse");
  const clearedImageCell = parseDeck(setCellContent(deck, 0, "top-right", ""));
  assert(!clearedImageCell.slides[0].cells.find(cell => cell.id === "top-right")?.image, "deleting a selected layout image clears its cell content");
  const stretchDeck = parseDeck('## Stretch {.layout-1}\n\n::: core\n![](figures/stretch.svg){fit=stretch}\n:::\n');
  const stretchFixture = document.createElement("div");
  renderDeck(stretchDeck, stretchFixture, asset => `/test/${asset}`);
  const stretchWrapper = stretchFixture.querySelector('svg.slide-image[data-fit="stretch"]');
  const stretchedResource = stretchWrapper?.querySelector("image");
  assert(stretchWrapper?.getAttribute("preserveAspectRatio") === "none" && stretchedResource?.getAttribute("preserveAspectRatio") === "none", "stretch fit reshapes image resources without modifying their files");
  assert(stretchedResource?.getAttribute("href") === "/test/figures/stretch.svg", "stretched SVG resources remain external images");
  assert(deck.slides[0].overlays[0].id === "eq", "overlay ID parses");
  assert(deck.slides[0].overlays[0].fontSize === 1.4, "relative overlay font size parses");
  assert(deck.slides[0].overlays[0].alignment === "right", "overlay alignment parses");
  const video = deck.slides[0].overlays.find(item => item.id === "movie");
  assert(video.type === "video" && video.video.source === "artwork/demo.mp4", "video source parses from overlay attributes");
  assert(video.video.controls && video.video.autoplay && video.video.muted && !video.video.loop, "video playback defaults and options parse");
  const videoFixture = document.createElement("div");
  renderDeck(deck, videoFixture, asset => `/test/${asset}`);
  const videoElement = videoFixture.querySelector(".overlay-video video");
  assert(videoElement.src.endsWith("/test/artwork/demo.mp4") && videoElement.poster.endsWith("/test/artwork/poster.jpg"), "video and poster assets resolve");
  assert(videoElement.controls && videoElement.muted && videoElement.dataset.autoplay === "true", "native video options render");
  document.body.append(videoFixture);
  let videoPlays = 0; let videoPauses = 0;
  videoElement.play = () => { videoPlays += 1; return Promise.resolve(); };
  videoElement.pause = () => { videoPauses += 1; };
  syncVideoPlayback(videoFixture.querySelector(".scientific-slide"), { autoplay: false });
  assert(videoPlays === 0 && videoPauses === 0, "editor playback sync preserves explicit playback without starting autoplay");
  syncVideoPlayback(videoFixture.querySelector(".scientific-slide"));
  assert(videoPlays === 1, "presentation playback sync honors autoplay");
  syncVideoPlayback(videoFixture.querySelector(".scientific-slide"), { autoplay: false, pauseActive: true });
  assert(videoPauses === 1, "leaving presentation mode pauses the active video");
  videoFixture.remove();
  assert(deck.slides[1].cells[0]?.range !== null, "ordinary core Markdown retains an editable range");

  let defaultShapeSource = insertOverlay(deck, 0, { type: "shape", content: "Label", id: "default-shape", attributes: {} });
  assert(!defaultShapeSource.includes("fill=") && !defaultShapeSource.includes("stroke=") && !defaultShapeSource.includes("shadow="), "new shapes omit default style attributes");
  let defaultShapeDeck = parseDeck(defaultShapeSource);
  const defaultShape = defaultShapeDeck.slides[0].overlays.find(item => item.id === "default-shape");
  assert(defaultShape.shape === "rectangle" && defaultShape.alignment === "center" && !defaultShape.fill && !defaultShape.stroke && !defaultShape.shadow, "omitted shape styles resolve to theme defaults");
  defaultShapeSource = updateOverlay(defaultShapeDeck, 0, "default-shape", { shadow: "true" });
  assert(defaultShapeSource.includes('shadow="true"'), "enabled shape shadow serializes");
  defaultShapeDeck = parseDeck(defaultShapeSource);
  defaultShapeSource = updateOverlay(defaultShapeDeck, 0, "default-shape", { shadow: null });
  assert(!defaultShapeSource.includes("shadow="), "disabled shape shadow returns to implicit default");

  const changedVideo = updateOverlay(deck, 0, "movie", { controls: "false", loop: "true", fit: "cover" });
  assert(changedVideo.includes('controls="false"') && changedVideo.includes('loop="true"') && changedVideo.includes('fit="cover"'), "video properties serialize as readable attributes");

  const duplicated = parseDeck(duplicateSlide(deck, 0));
  assert(duplicated.slides.length === 3 && duplicated.slides[1].title === "First", "selected slide duplicates after itself");
  assert(duplicated.slides[1].overlays[0].id === "eq", "duplicated slide keeps slide-local overlay IDs");
  assert(!duplicated.diagnostics.some(item => item.level === "error"), "duplicated slide remains valid");
  const deleted = parseDeck(deleteSlide(deck, 0));
  assert(deleted.slides.length === 1 && deleted.slides[0].title === "Second", "selected slide deletes");
  let finalDeleteRejected = false;
  try { deleteSlide(deleted, 0); } catch (error) { finalDeleteRejected = /at least one slide/.test(error.message); }
  assert(finalDeleteRejected, "final slide cannot be deleted");
  const inserted = parseDeck(insertSlide(deck, 0));
  assert(inserted.slides.length === 3 && inserted.slides[1].title === "New slide", "blank slide inserts after selection");
  assert(inserted.slides[1].layout === "1-2", "new slide copies the previous layout");
  assert(Math.round(inserted.slides[1].columns[0]) === 40 && Math.round(inserted.slides[1].rows[0]) === 55, "new slide copies grid proportions");
  assert(inserted.slides[1].overlays.length === 0, "new slide does not copy overlays");
  assert(inserted.slides[1].cells.every(cell => !cell.source.trim()), "new slide cells contain no content");
  const importedDeck = parseDeck('## Imported {#imported .layout-free}\n\n::: overlay {#note type="markdown"}\nCopied content\n:::\n');
  const imported = parseDeck(importSlide(deck, 0, importedDeck.slides[0]));
  assert(imported.slides.length === 3 && imported.slides[1].title === "Imported", "slide imports after the selection");
  assert(imported.slides[1].raw.includes("Copied content"), "slide import copies its Markdown content");
  const moved = parseDeck(moveSlide(deck, 0, 1));
  assert(moved.slides[0].title === "Second" && moved.slides[1].title === "First", "selected slide moves within the deck");

  assertCompoundLayout("1-2", ["left", "top-right", "bottom-right"], "left");
  assertCompoundLayout("2-1", ["top-left", "bottom-left", "right"], "right");
  assertFrontLayout();
  assertEmptyLayouts();
  assertShapes();
  assertCitations();
  assertThemes();
  assertTables();

  const multilineFixture = document.createElement("div");
  document.body.append(multilineFixture);
  const multilineDeck = parseDeck("## Multiline {.layout-free}\n\n::: overlay {#multiline type=\"markdown\"}\nFirst line\nSecond line\n\nLast line\n:::\n");
  renderDeck(multilineDeck, multilineFixture, asset => asset);
  assert(multilineFixture.querySelector(".overlay-markdown br"), "text overlays preserve textarea line breaks");
  const spacedParagraph = multilineFixture.querySelector(".overlay-markdown p + p");
  assert(spacedParagraph && parseFloat(getComputedStyle(spacedParagraph).marginTop) > 0, "text overlay paragraph spacing matches the editor preview");
  multilineFixture.remove();

  let next = updateOverlay(deck, 0, "eq", { x: 51.5, y: 22, locked: "true" });
  assert(next.includes('x="51.5"'), "overlay geometry patches source");
  assert(next.includes("E=mc^2"), "overlay patch preserves content");
  deck = parseDeck(next);

  next = updateOverlay(deck, 0, "eq", { color: "#c92a2a80" });
  let coloredDeck = parseDeck(next);
  assert(coloredDeck.slides[0].overlays[0].color === "#c92a2a80", "floating text color with alpha serializes");
  const colorFixture = document.createElement("div");
  renderDeck(coloredDeck, colorFixture, asset => asset);
  const translucentText = colorFixture.querySelector(".overlay-equation").style.color;
  assert(translucentText.includes("201, 42, 42") && translucentText.includes("0.5"), "floating text color with alpha renders");
  next = updateOverlay(coloredDeck, 0, "eq", { color: null });
  assert(!next.includes('color="#c92a2a80"'), "reset floating text color returns to the theme default");
  deck = parseDeck(next);

  next = updateSlideTitle(deck, 0, "## Edited title");
  assert(next.includes('## Edited title {.layout-1-2'), "title patches without losing layout attributes");
  deck = parseDeck(next);

  next = updateSlideTitle(deck, 0, "# First line\n\n### Second line");
  assert(next.includes("# First line {.layout-1-2") && next.includes("### Second line"), "multiline title preserves heading levels and layout attributes");
  assert(next.includes("### Second line\n\n::: left"), "multiline title remains separated from the first content block");
  const titleFixture = document.createElement("div");
  renderDeck(parseDeck(next), titleFixture, source => source);
  assert(titleFixture.querySelector(".slide-title h1") && titleFixture.querySelector(".slide-title h3"), "multiline title renders as separate headings");
  assert(titleFixture.querySelector(".slide-title-spacer"), "blank title line renders as vertical space");
  deck = parseDeck(next);

  const tightFront = parseDeck("# Front {.layout-front}\n::: core\nDetails\n:::\n");
  const editedFront = updateSlideTitle(tightFront, 0, "# Front\n## *A simple roadmap*");
  assert(editedFront.includes("## *A simple roadmap*\n::: core"), "title editing preserves an adjacent core directive boundary");
  assert(parseDeck(editedFront).slides[0].cells.some(cell => cell.id === "core" && cell.source === "Details"), "adjacent core directive remains parsed as content");

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
  const detail = error.stack?.includes(error.message)
    ? error.stack
    : `${error.name}: ${error.message}${error.stack ? `\n${error.stack}` : ""}`;
  document.querySelector("#results").textContent = `${checks.join("\n")}\n\nFAIL ${detail}`;
}
