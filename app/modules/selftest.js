import {
  deleteOverlay,
  deleteOverlays,
  deleteSection,
  deleteSlide,
  duplicateSlide,
  emptyTrash,
  importSlide,
  insertArrow,
  insertOverlay,
  insertSection,
  insertSlide,
  moveSection,
  moveSlide,
  permanentlyDeleteSlide,
  duplicateOverlay,
  normalizeDeck,
  parseDeck,
  restoreSlide,
  pasteOverlays,
  serializeOverlays,
  setCellContent,
  updateCellProperties,
  trashSlide,
  updateBlockContent,
  updateHeadingLayout,
  updateOverlay,
  updateSectionTitle,
  updateSlideTitle,
  updateSlideProperties,
  updateSlideNotes,
} from "./parser.js";
import { renderDeck, syncVideoPlayback } from "./render.js";
import { applyMarkdownStyle, arrowGeometry, bindRangeControl, boundarySlideShortcut, buildShapePalette, buildShapeSelect, canvasLinkTarget, canvasStartsMarquee, clipboardImageFile, deleteKey, DesignEditor, dialogDragPosition, handleMarkdownShortcut, initialImageGeometry, moveGeometryGroup, overlayPasteOffset, pageSlideIndex, projectAssetPage, rectanglesIntersect, refreshConvertedVideoAssets, renameClipboardImage, repeatedActivation, resolveImportDestination, storeOverlayClipboard, storedOverlayClipboard, videoConflictDestination, videoFile, videoPathAttributes } from "./editor.js";
import { briefReference, formatBibliography, parseBibliography, prepareBibliography, renameBibliographyEntry, uniqueCitationKey } from "./bibliography.js";
import { compileExpression, createPlotSvg } from "./plot.js";
import { externalDeckAction, externalMergePlan, renderExternalMerge } from "./external.js";
import { initialShapeGeometry, makeShapeSvg, shapeLabelInsets, SHAPES } from "./shapes.js";
import { pdfPrintUrl, pdfPrintView, printShortcut } from "./print.js";

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

function assertPrintLayout() {
  const fixture = document.createElement("div");
  fixture.id = "layout-fixture";
  fixture.className = "reveal";
  fixture.style.setProperty("width", "1000px", "important");
  fixture.style.setProperty("height", "700px", "important");
  const slides = document.createElement("div");
  slides.className = "slides";
  fixture.append(slides);
  document.body.append(fixture);
  const parsed = parseDeck(`## Printed {.layout-1}\n\n::: core\nPrint content\n:::\n\n::: overlay {#print-overlay type="markdown" x="20" y="30" w="40" h="20" z="-2"}\nOverlay\n:::`);
  renderDeck(parsed, slides, source => source);
  const section = fixture.querySelector(".scientific-slide");
  section.classList.add("present");
  const normal = getComputedStyle(section);
  const expectedVariables = ["--slide-padding-top", "--slide-padding-x", "--slide-padding-bottom"]
    .map(name => normal.getPropertyValue(name).trim());
  const expectedBackground = normal.backgroundColor;
  const expectedOverlayPosition = getComputedStyle(section.querySelector(".slide-overlay")).position;
  document.documentElement.classList.add("reveal-print");
  try {
    const printed = getComputedStyle(section);
    const printedPadding = [printed.paddingTop, printed.paddingRight, printed.paddingBottom, printed.paddingLeft];
    const printedVariables = ["--slide-padding-top", "--slide-padding-x", "--slide-padding-bottom"]
      .map(name => printed.getPropertyValue(name).trim());
    assert(printedPadding.every(value => parseFloat(value) > 0)
      && printedVariables.every((value, index) => value === expectedVariables[index]),
    `PDF mode preserves the presentation slide insets (${printedPadding.join(" ")}; ${printedVariables.join(" ")})`);
    assert(getComputedStyle(section.querySelector(".slide-frame")).display === "grid"
      && getComputedStyle(section.querySelector(".slide-grid")).display === "grid",
    "PDF mode preserves Quarkfoil frame and grid layouts");
    assert(getComputedStyle(section.querySelector(".slide-overlay")).position === expectedOverlayPosition
      && expectedOverlayPosition === "absolute" && printed.backgroundColor === expectedBackground,
    "PDF mode preserves overlays and theme surfaces");
    assert(printed.isolation === "isolate" && section.querySelector(".slide-overlay").style.zIndex === "-2",
      "PDF mode keeps negative overlay layers inside the slide stacking context");
  } finally {
    document.documentElement.classList.remove("reveal-print");
    fixture.remove();
  }
}

function assertShapes() {
  const palette = document.createElement("div");
  let chosenShape = null;
  const shapeButtons = buildShapePalette(palette, shape => { chosenShape = shape; });
  assert(shapeButtons.length === Object.keys(SHAPES).length && shapeButtons.every(button => button.querySelector(".shape-background .shape-surface")),
    "shape palette uses every insertable shape SVG as an icon");
  const shapeSelect = document.createElement("select");
  buildShapeSelect(shapeSelect);
  assert([...shapeSelect.options].map(option => option.value).join(" ") === Object.keys(SHAPES).join(" "),
    "shape properties list every insertable template");
  assert(shapeButtons.every(button => button.getAttribute("aria-label")?.startsWith("Add ")), "shape palette icons have accessible names");
  shapeButtons.find(button => button.dataset.shape === "diamond").click();
  assert(chosenShape === "diamond", "shape palette icons choose their matching insertion template");
  for (const name of ["cross", "x", "star"]) {
    assert(shapeButtons.find(button => button.dataset.shape === name)?.querySelector("polygon"), `${name} palette entry uses trusted polygon geometry`);
  }
  const leftBrace = shapeButtons.find(button => button.dataset.shape === "left-brace")?.querySelector("path");
  const rightBrace = shapeButtons.find(button => button.dataset.shape === "right-brace")?.querySelector("path");
  assert(leftBrace?.classList.contains("shape-brace") && rightBrace?.classList.contains("shape-brace"), "brace palette entries use trusted open-path geometry");
  assert(leftBrace.getAttribute("d") !== rightBrace.getAttribute("d"), "left and right braces use mirrored orientations");
  assert(shapeLabelInsets("left-brace")[3] > shapeLabelInsets("left-brace")[1]
    && shapeLabelInsets("right-brace")[1] > shapeLabelInsets("right-brace")[3], "brace labels stay on each brace's open side");
  for (const name of ["rectangle", "cross", "star", "arc"]) {
    const geometry = initialShapeGeometry(name);
    assert(Math.abs(geometry.w * 1280 / 100 - geometry.h * 720 / 100) < 0.01, `${name} is inserted at a visual 1:1 aspect ratio`);
  }
  assert(initialShapeGeometry("x").w === 30 && initialShapeGeometry("x").h === 20, "X retains the general resizable-shape insertion geometry");

  const fixture = document.createElement("div");
  fixture.id = "layout-fixture";
  fixture.className = "reveal";
  const slides = document.createElement("div");
  slides.className = "slides";
  fixture.append(slides);
  document.body.append(fixture);
  const parsed = parseDeck(`## Shapes {.layout-free}

::: overlay {#cloud type="shape" shape="cloud" x="5" y="5" w="25" h="20" fill="#ffeecc80" stroke="#112233" stroke-width="3" stroke-style="dash" shadow="true"}
Thought

Second thought
:::

::: overlay {#callout type="shape" shape="callout" x="35" y="5" w="25" h="20"}
\\(E=mc^2\\)
:::

::: overlay {#arc type="shape" shape="arc" x="62" y="5" w="25" h="20" rotation="15" start-angle="45" end-angle="300" heads="both" stroke="#c92a2a"}
:::`);
  renderDeck(parsed, slides, source => source);
  slides.querySelector(".scientific-slide").classList.add("present");
  const cloud = fixture.querySelector('[data-object-id="cloud"]');
  assert(parsed.slides[0].overlays[0].shape === "cloud", "shape kind parses");
  assert(parsed.slides[0].overlays[0].fill === "#ffeecc80" && parsed.slides[0].overlays[0].strokeWidth === 3
    && parsed.slides[0].overlays[0].strokeStyle === "dash", "shape styles including alpha and line pattern parse");
  assert(cloud.style.getPropertyValue("--shape-stroke-dasharray") === "12 9", "shape dash spacing scales with line width");
  assert(getComputedStyle(cloud.querySelector(".shape-surface")).fill.includes("0.5"), "shape color alpha renders");
  assert(parsed.slides[0].overlays[0].shadow && cloud.dataset.shadow === "true", "shape shadow parses and renders");
  assert(cloud.querySelector(".shape-background path") && cloud.querySelector(".shape-label").textContent.includes("Thought"), "cloud renders with a Markdown label");
  const cloudRect = cloud.getBoundingClientRect();
  const cloudLabelRect = cloud.querySelector(".shape-label").getBoundingClientRect();
  const cloudParagraphs = cloud.querySelectorAll(".shape-label > p");
  assert(cloudParagraphs.length === 2 && cloudParagraphs[1].getBoundingClientRect().top > cloudParagraphs[0].getBoundingClientRect().bottom,
    "multiple shape-label paragraphs flow vertically");
  const paragraphTop = cloudParagraphs[0].getBoundingClientRect().top;
  const paragraphBottom = cloudParagraphs[1].getBoundingClientRect().bottom;
  assert(Math.abs((paragraphTop + paragraphBottom) / 2 - (cloudLabelRect.top + cloudLabelRect.bottom) / 2) < 1,
    "multiple shape-label paragraphs remain vertically centered");
  assert(Math.abs(cloudLabelRect.width / cloudRect.width - 0.76) < 0.01 && Math.abs(cloudLabelRect.height / cloudRect.height - 0.75) < 0.01,
    "shape metadata constrains the cloud label to its safe text region");
  const callout = fixture.querySelector('[data-object-id="callout"]');
  assert(callout.querySelector(".katex"), "comic callout renders an equation label");
  const calloutRect = callout.getBoundingClientRect();
  const calloutLabelRect = callout.querySelector(".shape-label").getBoundingClientRect();
  assert(Math.abs(calloutLabelRect.height / calloutRect.height - 0.78) < 0.01 && Math.abs(calloutLabelRect.top - calloutRect.top) <= 1,
    `comic callout centers its label within the rounded body above the tail (${calloutLabelRect.height.toFixed(1)} / ${calloutRect.height.toFixed(1)})`);
  const calloutSurface = getComputedStyle(callout.querySelector(".shape-surface"));
  assert(calloutSurface.fill === "rgb(219, 239, 242)" && calloutSurface.stroke === "rgb(20, 108, 126)", "implicit shape colors inherit from the theme");
  const arc = parsed.slides[0].overlays.find(item => item.id === "arc");
  const arcElement = fixture.querySelector('[data-object-id="arc"]');
  const arcPath = arcElement.querySelector(".shape-arc");
  assert(arc.rotation === 15 && arcElement.style.rotate === "15deg", "overlay rotation parses and renders");
  assert(arc.shapeParameters.startAngle === 45 && arc.shapeParameters.endAngle === 300 && arc.shapeParameters.heads === "both",
    "arc angles and arrowheads parse");
  assert(arcPath.getAttribute("d").includes("A 42 42 0 1 1") && arcPath.hasAttribute("marker-start") && arcPath.hasAttribute("marker-end"),
    "parameterized arc geometry and optional arrowheads render");
  assert(getComputedStyle(arcPath).fill === "none" && getComputedStyle(arcElement.querySelector(".shape-arrow-head")).fill === "rgb(201, 42, 42)",
    "arc stays open and its arrowheads follow the line color");
  const changedArc = parseDeck(updateOverlay(parsed, 0, "arc", { "start-angle": 90, "end-angle": 225, heads: "end" }));
  assert(changedArc.slides[0].overlays.find(item => item.id === "arc").shapeParameters.endAngle === 225
    && changedArc.slides[0].overlays.find(item => item.id === "arc").shapeParameters.heads === "end", "arc parameters serialize");
  const triangle = makeShapeSvg("triangle");
  assert(Object.hasOwn(SHAPES, "triangle") && triangle.querySelector('polygon[points="50,0 100,100 0,100"]')
    && shapeLabelInsets("triangle").join(" ") === "40 20 8 20", "triangle geometry and label-safe region are defined");
  const rotated = updateOverlay(parsed, 0, "arc", { rotation: -30 });
  assert(rotated.includes('rotation="-30"') && parseDeck(rotated).slides[0].overlays.find(item => item.id === "arc").rotation === -30, "overlay rotation serializes");
  fixture.remove();
}

function assertArrows() {
  let deck = parseDeck("## Arrows {.layout-free}\n");
  deck = parseDeck(insertArrow(deck, 0, {
    id: "flow", x1: 12, y1: 18, x2: 76, y2: 64,
    attributes: { heads: "both", stroke: "#c92a2a", "stroke-width": 4, "stroke-style": "dash-dot" },
  }));
  const arrow = deck.slides[0].overlays[0];
  assert(arrow.type === "arrow" && arrow.arrow.x1 === 12 && arrow.arrow.y2 === 64, "arrow endpoints parse");
  assert(arrow.arrow.heads === "both" && arrow.stroke === "#c92a2a" && arrow.strokeWidth === 4
    && arrow.strokeStyle === "dash-dot", "arrow styles parse");
  assert(JSON.stringify(arrowGeometry(arrow.arrow)) === JSON.stringify({ x: 11, y: 17, w: 66, h: 48 }), "arrow endpoint geometry is derived consistently");

  const fixture = document.createElement("div");
  fixture.className = "reveal mode-design";
  const slides = document.createElement("div");
  slides.className = "slides";
  fixture.append(slides);
  document.body.append(fixture);
  renderDeck(deck, slides, source => source);
  const line = fixture.querySelector(".arrow-svg .arrow-line");
  const marker = fixture.querySelector(".arrow-svg .arrow-marker");
  assert(line && line.getAttribute("marker-start") && line.getAttribute("marker-end"), "two-headed arrow renders trusted SVG markers");
  assert(line.getAttribute("stroke") === "#c92a2a" && line.getAttribute("stroke-width") === "4", "arrow line styling renders");
  assert(line.getAttribute("stroke-dasharray") === "16 8 0 8" && line.getAttribute("stroke-linecap") === "round",
    "arrow dash-dot spacing scales with line width and renders round dots");
  assert(!fixture.querySelector(".arrow-hit").hasAttribute("stroke-dasharray"), "dashed arrows retain a continuous editing hit target");
  assert(marker.getAttribute("refX") === "8" && marker.querySelector(".arrow-head").getAttribute("stroke") === "none",
    "arrow markers cover thick shafts before tapering to their tips");
  assert(line.getAttribute("paint-order") === "stroke markers", "arrow shafts paint beneath SVG markers");
  assert(line.getAttribute("x1") === "12" && line.getAttribute("y2") === "64", "arrow SVG retains full-slide coordinates instead of squashing its endpoints");
  assert(getComputedStyle(fixture.querySelector(".arrow-hit")).pointerEvents === "stroke", "arrow editing hit target follows the line rather than its bounding box");
  fixture.remove();

  deck = parseDeck(updateOverlay(deck, 0, "flow", { x2: 82, y2: 40, heads: "start", stroke: "#146c7e", "stroke-style": "dotted" }));
  assert(deck.slides[0].overlays[0].arrow.x2 === 82 && deck.slides[0].overlays[0].arrow.heads === "start"
    && deck.slides[0].overlays[0].strokeStyle === "dotted", "arrow endpoint, head, and line-style changes serialize");
  const duplicated = parseDeck(duplicateOverlay(deck, 0, "flow", "flow-copy"));
  const copy = duplicated.slides[0].overlays.find(item => item.id === "flow-copy");
  assert(copy.arrow.x1 === 14 && copy.arrow.x2 === 84 && !copy.attrs.values.x, "duplicated arrow offsets both endpoints without box geometry");
}

function assertCitations() {
  const fixture = document.createElement("div");
  fixture.id = "layout-fixture";
  fixture.className = "reveal";
  const slides = document.createElement("div"); slides.className = "slides"; fixture.append(slides); document.body.append(fixture);
  const parsed = parseDeck(`## References {.layout-1}\n\nInline [@einstein1905], repeated [@einstein1905], and code \`[@ignored]\`.\n\n::: overlay {#source type="citation" keys="smith2024 einstein1905" display="brief" x="50" y="80" w="45" h="8" color="#c92a2a"}\n\n:::`);
  const bib = `@article{einstein1905, author={Einstein, Albert}, journal={Annalen der Physik}, volume={17}, pages={891--921}, year={1905}, doi={10.1002/test}}\n@article{smith2024, author={Smith, Alice and Jones, Bob}, journal={Physical Review Letters}, volume={132}, number={123456}, year={2024}}`;
  const bibliography = prepareBibliography(bib, parsed, { smith2024: "/api/bibliography-pdf/test-token" });
  const doiEntry = parseBibliography("@article{wallraff2004, month={Sept}, doi={10.1038/nature02851}}")[0];
  assert(doiEntry.key === "wallraff2004" && doiEntry.fields.month === "Sept" && doiEntry.fields.doi === "10.1038/nature02851", "normalized DOI BibTeX and citation key parse");
  const accentedEntry = parseBibliography(String.raw`@article{accents, author={M{\"u}ller, J{\'o}se and Pe{\~n}a, Ana}, title={The {\AA}ngstr{\"o}m and {\AE}ther}, year={2026}}`)[0];
  assert(accentedEntry.fields.author === "Müller, Jóse and Peña, Ana" && accentedEntry.fields.title === "The Ångström and Æther",
    "BibTeX LaTeX accents and letter commands render as Unicode");
  const disambiguatedKey = uniqueCitationKey("wallraff2004", ["wallraff2004", "wallraff2004a"]);
  const disambiguatedEntry = parseBibliography(renameBibliographyEntry("@article{wallraff2004, doi={10.1000/different}}", disambiguatedKey))[0];
  assert(disambiguatedEntry.key === "wallraff2004b" && disambiguatedEntry.fields.doi === "10.1000/different",
    "different DOI entries with colliding generated keys receive a unique suffix");
  const formattedBibliography = formatBibliography(`@article{zeta2025, year={2025}, title={A {Protected} Title}, author={Zulu, Zoe}}
@book{alpha2020, title={First}, author={Alpha, Alice}, publisher={Press}, year={2020}}`);
  assert(formattedBibliography.startsWith("@book{alpha2020,") && formattedBibliography.indexOf("@article{zeta2025,") > 0,
    "bibliography reformatting sorts entries alphabetically by citation key");
  assert(formattedBibliography.includes("  author    = {Alpha, Alice},\n  title     = {First},")
    && formattedBibliography.includes("title  = {A {Protected} Title},"), "bibliography reformatting orders and aligns fields while retaining protected braces");
  const thesisReference = briefReference(parseBibliography("@phdthesis{doe2020, author={Doe, Jane}, school={Example University}, year={2020}}")[0]);
  assert(thesisReference === "Doe, PhD thesis, Example University, (2020)", "thesis attributions identify their type and institution");
  const mastersReference = briefReference(parseBibliography("@mastersthesis{roe2021, author={Roe, Richard}, school={Example College}, year={2021}}")[0]);
  assert(mastersReference === "Roe, Master's thesis, Example College, (2021)", "master's thesis attributions identify their type and institution");
  let bibliographyError = "";
  try { parseBibliography("@article{broken, month=Sept}"); } catch (error) { bibliographyError = error.message; }
  assert(bibliographyError.startsWith("Invalid BibTeX:"), "BibTeX parser failures produce visible error messages");
  renderDeck(parsed, slides, source => source, bibliography);
  assert(bibliography.numbers.get("einstein1905") === 1 && !bibliography.numbers.has("smith2024"), "attributions do not consume citation numbers");
  assert(fixture.querySelectorAll(".citation-number").length === 2, "only inline citations display numbers while code remains literal");
  const attribution = fixture.querySelector(".overlay-citation").textContent;
  assert(attribution.includes("Smith et al.") && attribution.includes("Einstein"), "positioned attribution renders multiple selected references");
  const attributionPdf = fixture.querySelector(".overlay-citation .citation-pdf");
  assert(attributionPdf?.getAttribute("href") === "/api/bibliography-pdf/test-token"
    && attributionPdf.getAttribute("aria-label").includes("smith2024"), "attributions link attached PDFs with an accessible document marker");
  assert(!fixture.querySelector("p .citation-pdf"), "inline numbered citations do not add PDF links");
  const attributionStyle = getComputedStyle(fixture.querySelector(".overlay-citation"));
  assert(attributionStyle.backgroundColor === "rgba(0, 0, 0, 0)" && attributionStyle.boxShadow === "none", "attributions render without a background panel");
  assert(getComputedStyle(fixture.querySelector(".overlay-citation .citation")).color === attributionStyle.color
    && getComputedStyle(attributionPdf).color === attributionStyle.color, "attribution links inherit the assigned overlay text color");
  fixture.remove();
}

function assertThemes() {
  let deck = parseDeck("---\ntheme: scientific-light\ndefaults:\n  footer: Footer\n---\n\n## Light {.layout-1}\n\n---\n\n## Dark {.layout-1 theme=\"scientific-dark\" background=\"#101820\" foreground=\"#f0f4f8\" footer=\"none\"}\n");
  const fixture = document.createElement("div");
  renderDeck(deck, fixture, source => source);
  const [light, dark] = fixture.querySelectorAll(".scientific-slide");
  assert(light.classList.contains("theme-scientific-light"), "slide inherits the deck theme");
  assert(dark.classList.contains("theme-scientific-dark"), "slide selects its own theme");
  assert(dark.style.getPropertyValue("--slide-background") === "#101820" && dark.style.getPropertyValue("--slide-foreground") === "#f0f4f8", "slide colors override theme variables");
  assert(light.querySelector(".slide-footer") && !dark.querySelector(".slide-footer"), "slide footer annotation suppresses the inherited footer");
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
  deck = parseDeck(updateSlideProperties(deck, 1, { theme: null, background: null, foreground: null, footer: null }));
  assert(!deck.slides[1].headingAttrs.values.theme && !deck.slides[1].headingAttrs.values.background && !deck.slides[1].headingAttrs.values.footer, "inherited slide appearance values do not occupy source state");
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

function assertTypography() {
  const fixture = document.createElement("div");
  fixture.className = "reveal";
  document.body.append(fixture);
  const deck = parseDeck(`## Typography {.layout-1}

::: core
### A compact heading {fragment=0}

First paragraph with enough text to establish its line height. {fragment=1}

**Reachable:**  {fragment=5}
- Ising, $\\lambda^\\perp = 0$
- Heisenberg, $\\lambda^z = \\lambda^\\perp$


Second paragraph.

Third paragraph.

- First item {fragment=2}
  - Nested item {fragment=3}
- Second item

\`\`\`
code line one


code line two {fragment=9}
\`\`\`
:::

::: overlay {#list type="markdown" x="55" y="55" w="35" h="25"}
- Overlay item
  - Nested overlay item


After an additional blank line. {fragment=4}
:::

::: overlay {#reachable type="markdown" x="5" y="55" w="40" h="30"}
**Reachable:**  {fragment=5}
- Ising, $\\lambda^\\perp = 0$
- Heisenberg, $\\lambda^z = \\lambda^\\perp$
:::
`);
  renderDeck(deck, fixture, source => source);
  const cell = fixture.querySelector(".slide-cell");
  const topItem = [...cell.querySelectorAll("li")].find(item => item.firstChild?.textContent.includes("First item"));
  const nestedItem = topItem.querySelector("li");
  const cellSize = parseFloat(getComputedStyle(cell).fontSize);
  assert(Math.abs(parseFloat(getComputedStyle(topItem).fontSize) - cellSize) < 0.1
    && Math.abs(parseFloat(getComputedStyle(nestedItem).fontSize) - cellSize) < 0.1,
  "nested layout lists retain the body font size");
  const listIndent = parseFloat(getComputedStyle(cell.querySelector("ul")).paddingLeft);
  assert(listIndent > cellSize && listIndent < cellSize * 1.5, "layout list indentation is explicit and compact");
  const paragraph = cell.querySelector("p");
  assert(Math.abs(parseFloat(getComputedStyle(paragraph).lineHeight) / cellSize - 1.4) < 0.02, "layout paragraphs use the normalized line height");
  const paragraphs = cell.querySelectorAll("p");
  assert(parseFloat(getComputedStyle(paragraphs[paragraphs.length - 1]).marginTop) > 0, "adjacent layout paragraphs use explicit block spacing");
  assert(cell.querySelectorAll(":scope > .slide-content-spacer").length === 1, "additional blank layout lines render as proportional vertical space");
  assert(cell.querySelector("pre").textContent.includes("code line one\n\n\ncode line two {fragment=9}"), "annotations and blank lines inside fenced code remain code content");
  assert(cell.querySelector("h3").matches(".fragment[data-fragment-index='0']"), "Markdown headings can be fragments");
  assert(paragraph.matches(".fragment[data-fragment-index='1']"), "Markdown paragraphs can be fragments");
  const reachable = [...cell.querySelectorAll("p")].find(item => item.textContent.includes("Reachable:"));
  assert(reachable?.matches(".fragment[data-fragment-index='5']") && reachable.querySelector("strong")?.textContent === "Reachable:",
    "fragment annotations preserve bold text immediately before them");
  assert(topItem.matches(".fragment[data-fragment-index='2']")
    && nestedItem.matches(".fragment[data-fragment-index='3']"), "nested Markdown list items can be independent fragments");
  assert([cell.querySelector("h3"), paragraph, topItem, nestedItem].every(element => !element.textContent.includes("{fragment=")),
    "Markdown fragment annotations are hidden from rendered content");
  const overlayItems = fixture.querySelectorAll(".overlay-markdown li");
  assert(Math.abs(parseFloat(getComputedStyle(overlayItems[0]).fontSize) - parseFloat(getComputedStyle(overlayItems[1]).fontSize)) < 0.1,
    "nested overlay lists retain the overlay body font size");
  assert(fixture.querySelectorAll(".overlay-markdown > .slide-content-spacer").length === 1, "additional blank overlay lines use the same spacer rendering");
  assert(fixture.querySelector(".overlay-markdown p").matches(".fragment[data-fragment-index='4']"), "positioned Markdown uses block fragments");
  const reachableOverlay = fixture.querySelector('[data-object-id="reachable"]');
  const reachableParagraph = reachableOverlay.querySelector("p");
  const reachableList = reachableOverlay.querySelector("ul");
  assert(reachableParagraph.querySelector("strong")?.textContent === "Reachable:"
    && reachableParagraph.matches(".fragment[data-fragment-index='5']"),
  "positioned Markdown preserves bold text immediately before a fragment annotation");
  assert(getComputedStyle(reachableOverlay).display === "block"
    && reachableList.getBoundingClientRect().top >= reachableParagraph.getBoundingClientRect().bottom,
  "positioned Markdown stacks a fragment heading above its list");
  fixture.remove();
}

function parserFixtureSummary(source) {
  const deck = parseDeck(source);
  return {
    metadata: deck.metadata,
    slides: deck.slides.map(slide => ({
      title: slide.title,
      layout: slide.layout,
      cells: slide.cells.map(cell => cell.id),
      overlays: slide.overlays.map(overlay => overlay.id),
      trashed: slide.trashed,
      titleSource: slide.titleSource,
      columns: slide.columns,
      rows: slide.rows,
      notes: slide.notes,
      footer: slide.footer?.source || null,
      section: slide.section ? { title: slide.section.title, id: slide.section.id } : null,
    })),
    sections: deck.sections.map(section => ({
      title: section.title,
      id: section.id,
      slideCount: section.slideCount,
      isTrash: section.isTrash,
    })),
    diagnostics: deck.diagnostics.map(item => item.message),
    diagnosticCodes: deck.diagnostics.map(item => item.code || null),
  };
}

function parserFixtureMatches(actual, expected) {
  if (Array.isArray(expected)) return Array.isArray(actual) && actual.length === expected.length
    && expected.every((item, index) => parserFixtureMatches(actual[index], item));
  if (expected && typeof expected === "object") return actual && typeof actual === "object"
    && Object.entries(expected).every(([key, value]) => parserFixtureMatches(actual[key], value));
  if (typeof expected === "number") return Math.abs(actual - expected) < 1e-10;
  return actual === expected;
}

try {
  const parserFixturesResponse = await fetch("/parser-fixtures.json");
  assert(parserFixturesResponse.ok, "shared parser fixture corpus loads");
  const parserFixtures = await parserFixturesResponse.json();
  for (const fixture of parserFixtures) {
    const summary = parserFixtureSummary(fixture.source);
    assert(parserFixtureMatches(summary, fixture.expected)
      && (fixture.diagnosticPrefixes || []).every(prefix => summary.diagnostics.some(message => message.startsWith(prefix))),
      `JavaScript parser matches shared fixture: ${fixture.name}`);
  }
  assert(pdfPrintView("?print-pdf&print-dialog"), "PDF print query is recognized");
  assert(!pdfPrintView("?print-dialog"), "ordinary pages are not mistaken for the PDF print view");
  const printUrl = new URL(pdfPrintUrl({ href: "http://127.0.0.1:8000/?deck=example%2Fdeck.md#slide-2" }));
  assert(printUrl.searchParams.has("print-pdf") && printUrl.searchParams.has("print-dialog")
    && printUrl.searchParams.get("deck") === "example/deck.md" && !printUrl.hash,
  "PDF print URL preserves the deck selection and clears the slide hash");
  assert(printShortcut({ ctrlKey: true, metaKey: false, altKey: false, key: "P" })
    && printShortcut({ ctrlKey: false, metaKey: true, altKey: false, key: "p" })
    && !printShortcut({ ctrlKey: true, metaKey: false, altKey: true, key: "p" }),
  "Ctrl-P and Cmd-P are recognized without intercepting Alt-modified shortcuts");

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
  assert(pageSlideIndex(2, 5, "Home") === 0 && pageSlideIndex(2, 5, "End") === 4, "home and end keys navigate to the editor deck boundaries");
  const editingPane = document.createElement("section");
  const editingPaneTarget = editingPane.appendChild(document.createElement("div"));
  const sidebarTarget = document.createElement("button");
  assert(boundarySlideShortcut({ key: "Home", ctrlKey: true, metaKey: false, altKey: false, shiftKey: false, target: editingPaneTarget }, editingPane)
    && !boundarySlideShortcut({ key: "End", ctrlKey: true, metaKey: false, altKey: false, shiftKey: false, target: sidebarTarget }, editingPane),
  "deck-boundary shortcuts require focus in the editing pane");
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
  const clipboardStorage = new Map();
  const storage = { getItem: key => clipboardStorage.get(key) || null, setItem: (key, value) => clipboardStorage.set(key, value) };
  const overlayClipboard = { version: 1, sourceSlideId: "slide-a", source: "::: overlay {#shared}\nCross-window\n:::" };
  assert(storeOverlayClipboard(overlayClipboard, storage) && storedOverlayClipboard("", storage)?.sourceSlideId === "slide-a",
    "Quarkfoil windows share a fallback overlay clipboard");
  assert(storedOverlayClipboard(overlayClipboard.source, storage)?.source === overlayClipboard.source
    && storedOverlayClipboard("different system clipboard text", storage) === null,
  "the shared overlay clipboard matches system text instead of replacing unrelated clipboard content");
  assert(videoFile(new File([], "recording.mkv")) && videoFile(new File([], "recording.avi")), "MKV and AVI drops are recognized without MIME metadata");
  assert(repeatedActivation({ key: "overlay:text-1", time: 100 }, "overlay:text-1", 300), "a repeated canvas click is recognized for editing");
  assert(repeatedActivation({ key: "cell:left", time: 100 }, "cell:left", 300), "a repeated layout-cell click is recognized for editing");
  assert(!repeatedActivation({ key: "cell:left", time: 100 }, "cell:right", 300), "clicks on different canvas elements do not trigger editing");
  assert(!canvasStartsMarquee({ overlay: null, cell: {}, title: null }), "single clicks on layout cells are left for cell selection");
  assert(!canvasStartsMarquee({ overlay: null, cell: null, title: {} }), "single clicks on slide titles are left for title selection");
  assert(canvasStartsMarquee({ overlay: null, cell: null, title: null }), "empty slide canvas still starts marquee selection");
  assert(JSON.stringify(dialogDragPosition({ left: 100, top: 80, width: 340, height: 240 }, 2000, -2000, 1200, 800)) === JSON.stringify({ left: 860, top: 0 }), "movable dialogs remain inside the viewport");
  const canvasLink = document.createElement("a");
  canvasLink.href = "about:blank#citation";
  const canvasLinkLabel = document.createElement("span");
  canvasLink.append(canvasLinkLabel);
  assert(canvasLinkTarget(canvasLinkLabel) === canvasLink && canvasLinkTarget(document.createElement("span")) === null, "links inside movable overlays bypass canvas drag handling");
  const overwriteDestination = await resolveImportDestination(Promise.resolve(true), { name: "figure.svg", overwrite: false },
    () => Promise.resolve({ name: "figure.svg", overwrite: true }));
  assert(overwriteDestination.name === "figure.svg" && overwriteDestination.overwrite === true, "collision imports await the editable overwrite destination");
  const videoDestination = await videoConflictDestination(Object.assign(new Error("generated video exists"), { status: 409 }),
    { name: "clip.avi", overwrite: false }, () => Promise.resolve({ name: "renamed.avi", overwrite: false }));
  assert(videoDestination.name === "renamed.avi", "converted-video collisions await the rename or overwrite destination");
  const refreshedAssets = [];
  await refreshConvertedVideoAssets(Promise.resolve({ status: "complete" }), true,
    { path: "figures/clip.mp4", poster: "figures/clip-poster.jpg" }, path => refreshedAssets.push(path));
  assert(refreshedAssets.join(" ") === "figures/clip.mp4 figures/clip-poster.jpg", "overwritten conversions refresh video and poster assets after completion");
  const replacementVideo = videoPathAttributes("figures/new.mp4", "figures/new-poster.jpg");
  assert(replacementVideo.src === "figures/new.mp4" && replacementVideo.poster === "figures/new-poster.jpg",
    "project video replacement updates the generated poster pointer");
  assert(videoPathAttributes("figures/plain.mp4").poster === null, "project videos without generated posters clear stale poster pointers");
  assert(deleteKey("Delete") && deleteKey("Del") && deleteKey("Backspace"), "Delete-key variants remove selected canvas content");
  const markdownTextarea = document.createElement("textarea");
  markdownTextarea.value = "format me";
  markdownTextarea.setSelectionRange(0, 6);
  applyMarkdownStyle(markdownTextarea, "**");
  assert(markdownTextarea.value === "**format** me" && markdownTextarea.selectionStart === 2 && markdownTextarea.selectionEnd === 8,
    "Markdown bold wraps the selected textarea text and retains its selection");
  applyMarkdownStyle(markdownTextarea, "**");
  assert(markdownTextarea.value === "format me", "repeating Markdown bold removes the surrounding markers");
  markdownTextarea.setSelectionRange(0, 6);
  let commandBoldPrevented = false;
  const commandBoldHandled = handleMarkdownShortcut({
    key: "b", metaKey: true, ctrlKey: false, altKey: false, shiftKey: false,
    currentTarget: markdownTextarea, preventDefault: () => { commandBoldPrevented = true; },
  });
  assert(commandBoldHandled && commandBoldPrevented && markdownTextarea.value === "**format** me",
    "Command-B invokes Markdown bold and prevents the browser default");
  applyMarkdownStyle(markdownTextarea, "**");
  markdownTextarea.setSelectionRange(7, 7);
  applyMarkdownStyle(markdownTextarea, "*");
  assert(markdownTextarea.value === "format **me" && markdownTextarea.selectionStart === 8,
    "Markdown italic inserts paired markers and places an empty caret between them");
  assert(externalDeckAction({ knownHash: "a", diskHash: "a", dirty: false, valid: true }) === "unchanged",
    "unchanged external deck revisions require no editor action");
  assert(externalDeckAction({ knownHash: "a", diskHash: "b", dirty: false, valid: true }) === "reload",
    "valid external edits reload automatically when the browser is clean");
  assert(externalDeckAction({ knownHash: "a", diskHash: "b", dirty: true, valid: true }) === "conflict"
    && externalDeckAction({ knownHash: "a", diskHash: "b", dirty: false, valid: false }) === "conflict",
  "dirty browser drafts and invalid external decks require explicit reconciliation");
  const mergeBase = "## Alpha {#alpha .layout-1}\n\nBase alpha.\n\n---\n\n## Beta {#beta .layout-1}\n\nBase beta.\n";
  const mergeBrowser = mergeBase.replace("Base alpha.", "Browser alpha.");
  const mergeDisk = mergeBase.replace("Base beta.", "Disk beta.");
  const automaticMerge = externalMergePlan(mergeBase, mergeBrowser, mergeDisk);
  const automaticSource = renderExternalMerge(automaticMerge);
  assert(automaticMerge.automatic && automaticMerge.changes.length === 2
    && automaticSource.includes("Browser alpha.") && automaticSource.includes("Disk beta."),
  "external reconciliation automatically combines non-overlapping slide edits");
  const overlappingDisk = mergeBase.replace("Base alpha.", "Disk alpha.");
  const conflictPlan = externalMergePlan(mergeBase, mergeBrowser, overlappingDisk);
  assert(conflictPlan.changes[0].conflict && renderExternalMerge(conflictPlan).includes("Browser alpha.")
    && renderExternalMerge(conflictPlan, { "id:alpha": "disk" }).includes("Disk alpha."),
  "external reconciliation lists overlapping slides and honors browser or disk choices");
  const structuralPlan = externalMergePlan(mergeBase, `${mergeBrowser}\n---\n\n## Added {.layout-1}\n`, mergeDisk);
  assert(!structuralPlan.automatic && structuralPlan.reason.includes("inserted"),
    "external reconciliation falls back to manual Markdown for structural slide changes");
  const expression = compileExpression("Math.sin(x) + x ** 2");
  assert(Math.abs(expression(2) - (Math.sin(2) + 4)) < 1e-10, "plot expressions support JavaScript-style Math functions and operators");
  assert(Math.abs(compileExpression("cos(t)")(Math.PI) + 1) < 1e-10, "plot expressions accept t as a parametric variable");
  const barePlot = createPlotSvg("sin(x)", 0, 2 * Math.PI, 40, false);
  assert(barePlot.includes('<svg xmlns="http://www.w3.org/2000/svg"') && barePlot.includes('data-quarkfoil-plot="1"') && !barePlot.includes('class="axes"'), "axis-free plots serialize as identifiable standalone SVG without axes");
  assert(/<path d="M0\.00 /.test(barePlot) && barePlot.includes("800.00"), "axis-free plot curves use the full SVG width without padding");
  const plotViewBox = barePlot.match(/viewBox="([^"]+)"/)[1].split(/\s+/).map(Number);
  assert(plotViewBox[0] < 0 && plotViewBox[1] < 0 && plotViewBox[0] + plotViewBox[2] > 800 && plotViewBox[1] + plotViewBox[3] > 450, "plot viewports include spline overshoot and stroke instead of clipping at the data bounds");
  const parametricPlot = createPlotSvg("cos(t)", 0, 2 * Math.PI, 80, true, "sin(t)");
  assert(parametricPlot.includes('data-plot-kind="parametric"') && parametricPlot.includes('class="axes"')
    && /<path d="M[\d.]+ [\d.]+ C/.test(parametricPlot), "two expressions create a parametric SVG curve with optional axes");
  const axesPlot = createPlotSvg("x", -1, 1, 20, true);
  assert(axesPlot.includes('class="axes"') && axesPlot.includes(" C"), "plots optionally include axes and spline interpolation");
  assert(axesPlot.includes('class="area" fill="none"') && /class="area"[^>]*><path d="[^"]+ Z"/.test(axesPlot), "plots include a closed, independently fillable area to the zero baseline");
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
  const fencedDeck = parseDeck("# Examples {#examples .section}\n\n---\n\n## Fenced\n\n```yaml\nkey: value\n---\nother: value\n```\n\n---\n\n## After\n");
  assert(fencedDeck.slides.length === 2 && fencedDeck.slides[0].raw.includes("---\nother")
    && fencedDeck.slides.every(slide => slide.section?.id === "examples"),
  "fenced delimiters do not split slides and section membership is retained");
  const emptySectionDeck = parseDeck("# Empty {#empty .section}\n\n---\n\n# Filled {#filled .section}\n\n---\n\n## Slide\n");
  assert(emptySectionDeck.diagnostics.some(item => item.code === "empty_section")
    && emptySectionDeck.slides[0].section?.id === "filled", "empty sections report a coded warning");
  const unterminatedFenceDeck = parseDeck("## One\n\n::: overlay {#note type=markdown}\n```text\nunterminated\n:::\n\n---\n\n## Two\n");
  assert(unterminatedFenceDeck.slides.length === 2
    && unterminatedFenceDeck.diagnostics.some(item => item.code === "unterminated_fence"),
  "unterminated directive fences report an error without swallowing later slide boundaries");
  assert(deck.slides[0].layout === "1-2", "layout parses");
  assert(Math.round(deck.slides[0].columns[0]) === 40, "column ratios parse");
  assert(deck.slides[0].cells.find(cell => cell.id === "top-right").image.attrs.values.fit === "cover", "image attributes parse");
  const resizedPanel = parseDeck(updateCellProperties(deck, 0, "left", { "font-size": "1.1em" }));
  assert(resizedPanel.slides[0].cells.find(cell => cell.id === "left").fontSize === 1.1, "layout panel font size serializes and parses");
  const panelFixture = document.createElement("div");
  renderDeck(resizedPanel, panelFixture, source => source);
  assert(panelFixture.querySelector(".cell-left").style.fontSize === "1.1em", "layout panel font size renders");
  const resetPanel = parseDeck(updateCellProperties(resizedPanel, 0, "left", { "font-size": null }));
  assert(!resetPanel.slides[0].cells.find(cell => cell.id === "left").attrs.values["font-size"], "layout panel font size resets to the default");
  const ordinaryPanel = parseDeck(updateCellProperties(parseDeck("## Core {.layout-1}\n\nLarger body.\n"), 0, "core", { "font-size": "1.2em" }));
  assert(ordinaryPanel.slides[0].cells[0].source === "Larger body." && ordinaryPanel.slides[0].cells[0].fontSize === 1.2, "ordinary core content converts to a styled panel without content loss");
  const emptyPanel = parseDeck(updateCellProperties(parseDeck("## Empty {.layout-1-1}\n"), 0, "right", { "font-size": "1.3em" }));
  assert(emptyPanel.slides[0].cells.find(cell => cell.id === "right")?.fontSize === 1.3, "empty layout panels accept font-size properties");
  const clearedImageCell = parseDeck(setCellContent(deck, 0, "top-right", ""));
  assert(!clearedImageCell.slides[0].cells.find(cell => cell.id === "top-right")?.image, "deleting a selected layout image clears its cell content");
  const clearedMarkdownCell = parseDeck(setCellContent(deck, 0, "left", ""));
  assert(!clearedMarkdownCell.slides[0].cells.find(cell => cell.id === "left")?.source, "deleting a selected Markdown region clears its content");
  const mixedCoreDeck = parseDeck("## Mixed {.layout-1}\n\nOrdinary Markdown.\n\n::: overlay {#kept type=\"markdown\"}\nKeep this overlay.\n:::\n");
  const clearedMixedCore = setCellContent(mixedCoreDeck, 0, "core", "");
  assert(!clearedMixedCore.includes("Ordinary Markdown.") && clearedMixedCore.includes("Keep this overlay."), "clearing mixed core Markdown preserves slide directives");
  const stretchDeck = parseDeck('## Stretch {.layout-1}\n\n::: core\n![](figures/stretch.svg){fit=stretch opacity="0.6"}\n:::\n');
  const stretchFixture = document.createElement("div");
  renderDeck(stretchDeck, stretchFixture, asset => `/test/${asset}`);
  const stretchWrapper = stretchFixture.querySelector('svg.slide-image[data-fit="stretch"]');
  const stretchedResource = stretchWrapper?.querySelector("image");
  assert(stretchWrapper?.getAttribute("preserveAspectRatio") === "none" && stretchedResource?.getAttribute("preserveAspectRatio") === "none", "stretch fit reshapes image resources without modifying their files");
  assert(stretchedResource?.getAttribute("href") === "/test/figures/stretch.svg", "stretched SVG resources remain external images");
  assert(stretchWrapper.style.opacity === "0.6", "global opacity applies to stretched SVG image wrappers");
  const focusedDeck = parseDeck(`## Focused {.layout-1-1}

::: left
![](figures/tall.png){fit=height focus="0 80" opacity="0.4"}
:::

::: right
![](figures/wide.png){fit=width focus="20 80"}
:::
`);
  const focusedFixture = document.createElement("div");
  focusedFixture.className = "reveal";
  document.body.append(focusedFixture);
  renderDeck(focusedDeck, focusedFixture, asset => asset);
  const heightFit = focusedFixture.querySelector('[data-fit="height"]');
  const widthFit = focusedFixture.querySelector('[data-fit="width"]');
  assert(heightFit.style.objectPosition === "0% 80%" && heightFit.style.getPropertyValue("--image-focus-x") === "0%", "zero is retained as a valid image focus coordinate");
  assert(heightFit.style.opacity === "0.4", "global opacity applies to ordinary image elements");
  assert(getComputedStyle(heightFit).position === "absolute" && getComputedStyle(heightFit).transform !== "none", "Focus X positions a height-fitted image within its viewport");
  assert(getComputedStyle(widthFit).position === "absolute" && getComputedStyle(widthFit).transform !== "none", "Focus Y positions a width-fitted image within its viewport");
  focusedFixture.remove();
  assert(deck.slides[0].overlays[0].id === "eq", "overlay ID parses");
  assert(deck.slides[0].overlays[0].fontSize === 1.4, "relative overlay font size parses");
  assert(deck.slides[0].overlays[0].alignment === "right", "overlay alignment parses");
  const video = deck.slides[0].overlays.find(item => item.id === "movie");
  assert(video.type === "video" && video.video.source === "artwork/demo.mp4", "video source parses from overlay attributes");
  assert(video.video.controls && video.video.autoplay && video.video.muted && !video.video.loop, "video playback defaults and options parse");
  const videoFixture = document.createElement("div");
  renderDeck(deck, videoFixture, asset => `/test/${asset}`);
  document.body.append(videoFixture);
  const videoElement = videoFixture.querySelector(".overlay-video video");
  const videoClip = videoElement.closest(".overlay-media-clip");
  assert(videoClip?.parentElement.matches(".overlay-video") && getComputedStyle(videoClip).overflow === "hidden"
    && getComputedStyle(videoClip.parentElement).overflow === "visible", "overlay media clips inside its box without clipping editor controls");
  assert(videoElement.src.endsWith("/test/artwork/demo.mp4") && videoElement.poster.endsWith("/test/artwork/poster.jpg"), "video and poster assets resolve");
  assert(videoElement.controls && videoElement.muted && videoElement.dataset.autoplay === "true", "native video options render");
  assert(videoElement.dataset.source === "artwork/demo.mp4" && videoElement.dataset.poster === "artwork/poster.jpg", "rendered videos retain refreshable source and poster paths");
  assert(getComputedStyle(videoElement).backgroundColor === "rgba(0, 0, 0, 0)", "video boxes keep a transparent background");
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
  const duplicateSelectionFixture = document.createElement("div");
  let duplicateSelectionDeck = deck;
  renderDeck(duplicateSelectionDeck, duplicateSelectionFixture, source => source);
  const duplicateEditor = Object.create(DesignEditor.prototype);
  duplicateEditor.selected = duplicateSelectionFixture.querySelector('[data-object-id="eq"]');
  duplicateEditor.options = { getDeck: () => duplicateSelectionDeck };
  duplicateEditor.slideIndex = () => 0;
  duplicateEditor.uniqueId = () => "eq-selected-copy";
  duplicateEditor.section = () => duplicateSelectionFixture.querySelector(".scientific-slide");
  duplicateEditor.commit = nextSource => {
    duplicateSelectionDeck = parseDeck(nextSource);
    renderDeck(duplicateSelectionDeck, duplicateSelectionFixture, source => source);
  };
  let selectedDuplicate = null;
  duplicateEditor.selectOverlay = element => { selectedDuplicate = element; };
  duplicateEditor.duplicate();
  assert(selectedDuplicate?.dataset.objectId === "eq-selected-copy", "duplicating an object moves selection to the rendered copy");
  const deleted = parseDeck(deleteSlide(deck, 0));
  assert(deleted.slides.length === 1 && deleted.slides[0].title === "Second", "selected slide deletes");
  let finalDeleteRejected = false;
  try { deleteSlide(deleted, 0); } catch (error) { finalDeleteRejected = /at least one slide/.test(error.message); }
  assert(finalDeleteRejected, "final slide cannot be deleted");
  const trashedDeck = parseDeck(trashSlide(deck, 0));
  assert(trashedDeck.items.map(item => item.kind).join(" ") === "slide section slide"
    && trashedDeck.sections[0].isTrash && trashedDeck.slides[1].trashed && trashedDeck.slides[1].title === "First",
  "trashing marks a slide readably and moves it beneath the final Trash section");
  const activeOnlyFixture = document.createElement("div");
  renderDeck(trashedDeck, activeOnlyFixture, source => source, null, { includeTrashed: false });
  assert(activeOnlyFixture.querySelectorAll(".scientific-slide").length === 1
    && activeOnlyFixture.querySelector(".scientific-slide").dataset.slideId === trashedDeck.slides[0].id,
  "presentation rendering excludes trashed slides");
  let finalActiveTrashRejected = false;
  try { trashSlide(trashedDeck, 0); } catch (error) { finalActiveTrashRejected = /at least one active slide/.test(error.message); }
  assert(finalActiveTrashRejected, "the final active slide cannot be trashed");
  const restoredDeck = parseDeck(restoreSlide(trashedDeck, 1));
  assert(restoredDeck.slides.length === 2 && restoredDeck.slides.every(slide => !slide.trashed)
    && !restoredDeck.sections.some(section => section.isTrash) && restoredDeck.slides[1].title === "First",
  "restoring returns a slide to the active deck and removes an empty Trash section");
  const emptiedTrash = parseDeck(permanentlyDeleteSlide(trashedDeck, 1));
  assert(emptiedTrash.slides.length === 1 && !emptiedTrash.sections.some(section => section.isTrash),
    "permanent deletion removes the trashed slide and its empty Trash section");
  const bulkEmptiedTrash = parseDeck(emptyTrash(trashedDeck));
  assert(bulkEmptiedTrash.slides.length === 1 && !bulkEmptiedTrash.sections.some(section => section.isTrash),
    "emptying Trash permanently removes every trashed slide and the Trash section");
  assert(moveSlide(trashedDeck, 0, 1) === trashedDeck.source, "active slides cannot move across the Trash boundary");
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

  let sectioned = parseDeck(insertSection(deck, 0, "Methods"));
  assert(sectioned.sections.length === 1 && sectioned.slides.length === 2, "section markers parse without becoming presentation slides");
  assert(sectioned.items.map(item => item.kind).join(" ") === "section slide slide", "new section begins at the selected slide");
  assert(sectioned.sections[0].slideCount === 2, "sections count their slides for collapsed sidebar labels");
  const sectionId = sectioned.sections[0].id;
  sectioned = parseDeck(updateSectionTitle(sectioned, sectionId, "Results"));
  assert(sectioned.sections[0].title === "Results" && sectioned.source.includes(".section"), "section titles serialize as readable Markdown markers");
  const movedSection = parseDeck(moveSection(sectioned, sectionId, 1));
  assert(movedSection.items[1].kind === "section" && movedSection.slides.map(slide => slide.title).join(" ") === "First Second", "section separators move independently of slides");
  assert(movedSection.sections[0].slideCount === 1, "section slide counts follow a moved boundary");
  const firstAcrossSection = parseDeck(moveSlide(sectioned, 0, -1));
  assert(firstAcrossSection.items.map(item => item.kind).join(" ") === "slide section slide"
    && firstAcrossSection.slides.map(slide => slide.title).join(" ") === "First Second",
  "the first slide in a section moves above its section marker");
  const sectionBetweenSlides = parseDeck(insertSection(deck, 1, "Boundary"));
  const previousAcrossSection = parseDeck(moveSlide(sectionBetweenSlides, 0, 1));
  assert(previousAcrossSection.items.map(item => item.kind).join(" ") === "section slide slide"
    && previousAcrossSection.slides.map(slide => slide.title).join(" ") === "First Second",
  "the slide before a section moves below its section marker");
  const nextAcrossSection = parseDeck(moveSlide(sectionBetweenSlides, 1, -1));
  assert(nextAcrossSection.items.map(item => item.kind).join(" ") === "slide slide section"
    && nextAcrossSection.slides.map(slide => slide.title).join(" ") === "First Second",
  "the slide after a section moves above its section marker");
  const sectionFixture = document.createElement("div");
  renderDeck(sectioned, sectionFixture, source => source);
  assert(sectionFixture.querySelectorAll(".scientific-slide").length === 2, "section markers are omitted from presentation rendering");
  assert(parseDeck(deleteSection(sectioned, sectionId)).sections.length === 0, "deleting a section retains a valid slide deck");

  assertCompoundLayout("1-2", ["left", "top-right", "bottom-right"], "left");
  assertCompoundLayout("2-1", ["top-left", "bottom-left", "right"], "right");
  assertFrontLayout();
  assertEmptyLayouts();
  assertPrintLayout();
  assertShapes();
  assertArrows();
  assertCitations();
  assertThemes();
  assertTables();
  assertTypography();

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
  assert(editedFront.includes("## *A simple roadmap*\n\n::: core"), "title editing leaves one readable blank line before slide content");
  assert(parseDeck(editedFront).slides[0].cells.some(cell => cell.id === "core" && cell.source === "Details"), "adjacent core directive remains parsed as content");

  const untidyTitle = parseDeck("## Spaced {.layout-1}\n\n\n\n::: core\nBody\n:::\n");
  const tidiedTitle = updateSlideTitle(untidyTitle, 0, untidyTitle.slides[0].titleSource);
  assert(tidiedTitle.includes("{.layout-1}\n\n::: core") && !tidiedTitle.includes("{.layout-1}\n\n\n"), "title editing removes excess trailing newlines");
  const repeatedTitleEdit = updateSlideTitle(parseDeck(tidiedTitle), 0, parseDeck(tidiedTitle).slides[0].titleSource);
  assert(repeatedTitleEdit === tidiedTitle, "repeated title edits do not accumulate newlines");

  next = updateBlockContent(deck, 0, "eq", "\\[F=ma\\]");
  assert(next.includes("F=ma"), "block content patches source");
  deck = parseDeck(next);

  const trailingBody = updateBlockContent(deck, 0, "eq", "Body\n\n\n");
  assert(trailingBody.includes("Body\n:::") && !trailingBody.includes("Body\n\n:::"), "content editing removes trailing body newlines before the closing fence");

  let notesDeck = parseDeck("## Notes {.layout-1}\n\nBody\n");
  next = updateSlideNotes(notesDeck, 0, "Explain the result.\n\nMention the caveat.");
  notesDeck = parseDeck(next);
  assert(notesDeck.slides[0].notes === "Explain the result.\n\nMention the caveat.", "slide notes insert as Markdown");
  next = updateSlideNotes(notesDeck, 0, "Revised note");
  assert((next.match(/::: notes/g) || []).length === 1 && parseDeck(next).slides[0].notes === "Revised note", "slide notes update in place");
  next = updateSlideNotes(parseDeck(next), 0, "");
  assert(!next.includes("::: notes") && parseDeck(next).slides[0].cells[0].source === "Body", "empty slide notes remove their directive without changing slide content");

  next = updateHeadingLayout(deck, 0, "1-1", [35, 65], [50, 50]);
  assert(next.includes(".layout-1-1"), "layout patches heading");
  assert(next.includes('columns="35 65"'), "layout ratios serialize");
  assert(parseDeck(next).slides[0].cells.find(cell => cell.id === "right")?.source === deck.slides[0].cells.find(cell => cell.id === "core")?.source,
    "1 to 1+1 preserves core content in the largest panel");
  deck = parseDeck(next);

  next = setCellContent(deck, 0, "right", "New cell");
  assert(next.includes("::: right\nNew cell"), "missing cell inserts declaratively");
  assert(!next.includes("\n\n\n::: right"), "new cells use one blank line between directive blocks");
  deck = parseDeck(next);

  const onePlusOne = parseDeck(`## Switch {.layout-1-1}

::: left
Keep left
:::

::: right
Remove right
:::

::: overlay {#keep type="markdown"}
Keep overlay
:::
`);
  const onePlusTwo = parseDeck(updateHeadingLayout(onePlusOne, 0, "1-2", [50, 50], [50, 50]));
  assert(onePlusTwo.slides[0].cells.some(cell => cell.id === "left") && !onePlusTwo.source.includes("Remove right"), "1+1 to 1+2 removes the obsolete right cell");
  assert(onePlusTwo.slides[0].overlays.some(overlay => overlay.id === "keep"), "layout changes retain overlays");
  const zeroLayout = parseDeck(updateHeadingLayout(onePlusTwo, 0, "0", [50, 50], [50, 50]));
  assert(zeroLayout.slides[0].cells.length === 0 && zeroLayout.slides[0].overlays.length === 1, "layout 0 removes every grid cell but retains overlays");

  const onePlusTwoCells = parseDeck(`## Reverse {.layout-1-2}

::: left
Keep left
:::

::: top-right
Remove top
:::

::: bottom-right
Remove bottom
:::
`);
  const onePlusOneAgain = parseDeck(updateHeadingLayout(onePlusTwoCells, 0, "1-1", [50, 50], [50, 50]));
  assert(onePlusOneAgain.slides[0].cells.map(cell => cell.id).join(" ") === "left", "1+2 to 1+1 removes both obsolete stacked cells");

  const collapsedOnePlusOne = parseDeck(updateHeadingLayout(onePlusOne, 0, "1", [50, 50], [50, 50]));
  assert(collapsedOnePlusOne.slides[0].cells.find(cell => cell.id === "core")?.source === "Keep left",
    "1+1 to 1 preserves the left panel as core content");
  assert(!collapsedOnePlusOne.source.includes("Remove right"), "1+1 to 1 removes the right panel");
  assert(collapsedOnePlusOne.slides[0].overlays.some(overlay => overlay.id === "keep"),
    "1+1 to 1 retains overlays");

  const mixedCore = parseDeck(`## Ordinary {.layout-1}

Ordinary core content.

::: overlay {#ordinary-overlay type="markdown"}
Overlay content
:::
`);
  const onePlusTwoFromCore = parseDeck(updateHeadingLayout(mixedCore, 0, "1-2", [40, 60], [30, 70]));
  assert(onePlusTwoFromCore.slides[0].cells.find(cell => cell.id === "bottom-right")?.source === "Ordinary core content.",
    "1 to 1+2 wraps ordinary core Markdown in the largest panel");
  assert(onePlusTwoFromCore.slides[0].overlays.some(overlay => overlay.id === "ordinary-overlay"),
    "moving ordinary core content retains adjacent overlays");
  const twoPlusOneFromCore = parseDeck(updateHeadingLayout(mixedCore, 0, "2-1", [45, 55], [80, 20]));
  assert(twoPlusOneFromCore.slides[0].cells.find(cell => cell.id === "right")?.source === "Ordinary core content.",
    "1 to 2+1 preserves ordinary core Markdown in the largest panel");
  const mixedZero = parseDeck(updateHeadingLayout(mixedCore, 0, "0", [50, 50], [50, 50]));
  assert(!mixedZero.source.includes("Ordinary core content.") && mixedZero.source.includes("Overlay content"), "layout 0 removes ordinary core Markdown without removing adjacent directives");

  const unnormalized = `---
title: Normalize
---



# Methods {#methods .section}



---


## Normalize {.layout-1}



First paragraph.



Second paragraph.



::: right
Unused panel
:::



::: overlay {#preserved type="markdown"}
Overlay first


Overlay second
:::



::: notes
Note first


Note second
:::



---


## Zero {.layout-0}



::: core
Hidden core panel
:::



::: footer
Visible footer
:::



---


## Ordinary zero {.layout-0}



Hidden ordinary content.



::: footer
Another visible footer
:::
`;
  const normalized = normalizeDeck(unnormalized);
  assert(!normalized.includes("Unused panel") && !normalized.includes("Hidden ordinary content.") && !normalized.includes("Hidden core panel"), "document normalization removes cells unused by their layouts");
  assert(normalized.includes("First paragraph.\n\nSecond paragraph.\n\n::: overlay"), "document normalization leaves one blank line between top-level objects");
  assert(normalized.includes("Overlay first\n\n\nOverlay second") && normalized.includes("Note first\n\n\nNote second"), "document normalization preserves whitespace inside directive bodies");
  assert(normalized.includes("# Methods {#methods .section}\n\n---\n\n## Normalize") && normalized.includes("::: overlay {#preserved type=\"markdown\"}\nOverlay first\n\n\nOverlay second\n:::\n\n::: notes"), "sections, slides, and directives use one blank line at their boundaries");
  assert(normalizeDeck(normalized) === normalized, "document normalization is idempotent");
  const normalizedCode = normalizeDeck("## Code {.layout-1}\n\n\n\nBefore.\n\n\n\n```text\nfirst\n\n\nsecond\n```\n");
  assert(normalizedCode.includes("Before.\n\n```text\nfirst\n\n\nsecond\n```"), "document normalization preserves blank lines inside ordinary fenced code");

  next = duplicateOverlay(deck, 0, "eq", "eq-copy");
  assert(next.includes("#eq-copy"), "overlay duplicates with stable ID");
  deck = parseDeck(next);

  next = deleteOverlay(deck, 0, "eq-copy");
  assert(!next.includes("#eq-copy"), "overlay deletes narrowly");

  let groupDeleteDeck = parseDeck(insertOverlay(deck, 0, {
    type: "markdown", content: "First removal", id: "remove-first",
  }));
  groupDeleteDeck = parseDeck(insertOverlay(groupDeleteDeck, 0, {
    type: "markdown", content: "Second removal", id: "remove-second",
  }));
  next = deleteOverlays(groupDeleteDeck, 0, ["remove-first", "remove-second"]);
  assert(!next.includes("#remove-first") && !next.includes("#remove-second") && next.includes("#eq"),
    "group deletion removes every selected overlay while preserving unselected overlays");
  assert(!next.includes("\n\n\n:::"), "block deletion does not leave excess blank lines between directives");

  const copiedOverlays = serializeOverlays(deck, 0, ["eq", "movie"]);
  assert(copiedOverlays.includes("#eq") && copiedOverlays.includes("#movie") && copiedOverlays.includes("F=ma"), "selected overlays serialize as readable clipboard directives");
  const pastedOverlays = pasteOverlays(deck, 1, copiedOverlays);
  const pastedDeck = parseDeck(pastedOverlays.source);
  assert(pastedOverlays.ids.length === 2 && pastedDeck.slides[1].overlays.length === 2, "multiple copied overlays paste into another slide");
  assert(pastedDeck.slides[1].overlays.find(item => item.type === "equation")?.geometry.x === deck.slides[0].overlays.find(item => item.id === "eq").geometry.x + 2, "pasted overlays receive a visible position offset");
  const repastedOverlays = pasteOverlays(pastedDeck, 1, copiedOverlays);
  assert(repastedOverlays.ids.every(id => !["eq", "movie"].includes(id)), "pasted overlays receive collision-safe slide-local IDs");
  assert(pasteOverlays(deck, 1, "ordinary clipboard text") === null, "ordinary clipboard text is not mistaken for an overlay");
  assert(overlayPasteOffset(deck.slides[0].id, deck.slides[0].id) === 2, "pasting onto the source slide offsets copied overlays");
  assert(overlayPasteOffset(deck.slides[0].id, deck.slides[1].id) === 0, "pasting onto another slide preserves overlay positions");

  document.body.dataset.status = "passed";
  document.querySelector("#results").textContent = `${checks.join("\n")}\n\n${checks.length} checks passed.`;
} catch (error) {
  document.body.dataset.status = "failed";
  const detail = error.stack?.includes(error.message)
    ? error.stack
    : `${error.name}: ${error.message}${error.stack ? `\n${error.stack}` : ""}`;
  document.querySelector("#results").textContent = `${checks.join("\n")}\n\nFAIL ${detail}`;
}
