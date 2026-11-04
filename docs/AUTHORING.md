# Authoring and source reconstruction

This guide covers failures that parse successfully but render incorrectly. It
is especially useful when reconstructing a PowerPoint, PDF, or set of slide
images without reviewing every intermediate edit in the browser.

For the compact, installed version available to an assistant, run:

```console
quarkfoil deck guide reproduction
```

## First-pass recipe

1. Choose the layout from the content shape: text plus one figure uses `1+1`;
   text plus two figures uses `1+2`; two text panels plus one figure uses
   `2+1`; a positioned canvas with a normal title and footer uses `0`; a
   full-bleed or chrome-free divider uses Free.
2. Set `font-size` explicitly on every text region and text overlay.
3. Keep every image alone in its grid region.
4. Keep each overlay paragraph on one source line.
5. Use `type="citation"` boxes for positioned paper references or credits;
   do not recreate them as Markdown overlays.
6. Add overlays after the grid content is stable.
7. Render and inspect every page. `deck inspect` validates structure, not fit.

## Resolved typography

Quarkfoil uses a 1280×720 canvas with a Reveal base size of 32 CSS pixels.
The same `font-size` multiplier resolves differently depending on context:

| Context | Effective size | Source default |
|---|---:|---:|
| Grid-region prose | `font-size × 32px` | `0.72em` → 23.0px |
| Markdown-overlay prose | `font-size × 0.68 × 32px` | `1em` → 21.8px |
| Shape-label prose | `font-size × 0.68 × 32px` | `1em` → 21.8px |
| Equation overlay | `font-size × 32px` | `1em` → 32.0px |
| Grid-region table | `font-size × 0.72 × 32px` | `0.72em` → 16.6px |
| Overlay table | `font-size × 0.72 × 32px` | `1em` → 23.0px |
| `##` slide title | `1.28 × 32px` | 41.0px |
| Footer | `0.36 × 32px` | 11.5px |

A PowerPoint 24pt font is 32px at 96 dpi. Useful starting values for a similar
body size are:

- Grid-region prose: `font-size="1em"`.
- Markdown overlays and shape labels: `font-size="1.45em"`.
- Equation overlays: `font-size="1em"`.

These values only match nominal size; they do not guarantee that the content
fits. The extra `0.68` factor applies to paragraphs and lists in Markdown
overlays and shape labels, but not to equation overlays. An annotation and an
equation with the same multiplier will therefore look different.

Source Markdown accepts any positive decimal `font-size`, with or without the
`em` suffix. Invalid or nonpositive values are parser errors. The Design
controls expose and clamp values from `0.25em` through `3em` in `0.05em`
steps.

## Keep images alone in grid regions

A grid region becomes an image region only when its complete trimmed body is a
single image. If prose, a caption, or any other content shares the region, the
whole body becomes ordinary Markdown. Marked does not interpret Quarkfoil's
image attribute block, so `{fit=contain}` can appear as literal text.

Wrong:

```markdown
::: left
Some explanation.

![](figures/plot.png){fit=contain focus="50 50"}
:::
```

Right:

```markdown
::: left
Some explanation.
:::

::: right
![](figures/plot.png){fit=contain focus="50 50"}
:::
```

Use `1+2` or `2+1` when a figure needs its own caption or supporting panel.
Do not place a caption beneath an image in the same image region.

## Choose the correct free canvas

The two gridless layouts serve different purposes:

| Required result | Layout |
|---|---|
| Positioned content with the normal heading and footer | `.layout-0` |
| Full-slide content without title or footer chrome | `.layout-free` |

Free suppresses the complete slide frame, not only its grid. Do not rebuild a
normal slide title as an overlay merely because the content is positioned.

## Keep overlay paragraphs on one source line

Markdown overlays and shape labels turn soft source newlines into hard line
breaks. Grid regions do not. Source wrapping inside an overlay therefore
becomes visible wrapping.

Wrong:

```markdown
::: overlay {#note type="markdown" x="4" y="58" w="27" h="30" font-size="1.45em"}
What a register of qubits can hold, and what an algorithm can
do with it.
:::
```

Right:

```markdown
::: overlay {#note type="markdown" x="4" y="58" w="27" h="30" font-size="1.45em"}
What a register of qubits can hold, and what an algorithm can do with it.
:::
```

In grid regions, source paragraphs may be wrapped freely.

## Use citation boxes for positioned references

Inline citations such as `[@smith2024]` belong inside ordinary Markdown.
Automatically formatted paper references positioned anywhere on a slide have
their own overlay box type. Figure attribution is one use, not the meaning of
the type. In the web interface, choose **Bibliography**, find the entry, and
click **Add attribution**. For key `smith2024`, it inserts:

```markdown
::: overlay {#citation-smith2024 type="citation" x="55" y="82" w="40" h="8" key="smith2024" display="brief" align="left" font-size="0.7em"}

:::
```

Do not reproduce this as a Markdown overlay containing hand-formatted reference
text. A `type="citation"` box resolves `key` or space-separated `keys` from the
front-matter bibliography, uses a transparent background, and stays connected
to Quarkfoil's citation numbering. Use `display="brief"` for an attribution
without a number and `display="number"` for the shared numbered citation.

## Geometry

Overlay `x`, `y`, `w`, and `h` are percentages of the full 1280×720 slide.
The current default geometry is derived from `app/styles/layout.css`:

| Measurement | Value |
|---|---:|
| Horizontal padding | 4.5% = 57.6px per side |
| Top/bottom padding | 3.2% / 2.4% of slide width = 41.0 / 30.7px |
| Content box | 1164.8 × 648.3px |
| Title/footer rows | 11% / 6% of content height = 71.3 / 38.9px |
| Grid core with title and footer | y = 15.6% through 90.3%; height 538.1px |
| Grid gap | 2.2% of content width = 25.6px |

CSS percentage padding resolves against the slide width on all four sides.
On layout `0`, keep ordinary overlays within the core band to avoid the title
and footer. The lower boundary changes when the footer is suppressed. Free
makes the whole slide available.

For example, in layout `1+1` with `columns="40 60"`, the two columns share
`1164.8 - 25.6 = 1139.2px`. The left cell is 455.7px wide. A square
`fit=contain` image fills that width and centers vertically in the 538.1px
core, approximately:

```text
x = 4.5%   y = 21.3%   w = 35.6%   h = 63.3%
```

Those coordinates can align a shape, arrow, or annotation with the image.

## Budget for overflow

Grid regions and shape labels hide overflow. A deck may parse without errors
while prose, tables, or equations are clipped. At a cell size of `1em`, use
roughly 35–40 characters per line in a half-width column and about 12 body
lines in a full-height cell as initial budgets, then inspect the render.

Display equations do not wrap. Prefer these remedies, in order:

1. Split the equation into separate display blocks.
2. Use a KaTeX `aligned` environment with intentional line breaks.
3. Split the slide.
4. Reduce the region font size only when the preceding options are unsuitable.

## Visual verification

After applying a whole deck, print and rasterize it when the required browser
and Poppler tools are installed:

```console
quarkfoil print deck.md --output /tmp/deck.pdf
pdftoppm -r 96 -png /tmp/deck.pdf /tmp/deck-page
```

At 96 dpi, Quarkfoil's 13.33×7.5-inch pages rasterize to approximately
1280×720, making one output pixel equal to one CSS pixel. Inspect every page
for:

- clipped text, tables, and equations;
- literal attribute strings;
- type that is too small for the room;
- overlays outside the slide or colliding with title/footer chrome;
- unintended line breaks caused by wrapped overlay source; and
- mismatches against the reference slide.

Always report when visual verification was not possible. A clean `deck
inspect` result is not a visual check.
