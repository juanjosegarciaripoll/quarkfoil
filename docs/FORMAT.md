# Markdown format reference

The UTF-8 Markdown file is the presentation's source of truth. YAML front matter contains deck-wide settings, and a line containing only `---` separates slides.

## Front matter

```yaml
---
title: Quantum simulation platforms
author: Ada Lovelace
aspect-ratio: 16:9
theme: scientific-light
assets:
  figures: artwork
  include:
    - references
    - media
defaults:
  footer: Summer school · 2026
---
```

The supported preface fields are:

| Field | Purpose | Default |
|---|---|---|
| `title` | Presentation title and exported browser-page title | `New presentation` for a generated starter |
| `author` | Presentation author metadata | Empty, except in a generated starter |
| `aspect-ratio` | Intended slide aspect ratio | `16:9` |
| `theme` | Default presentation theme (`scientific-light` or `scientific-dark`) | `scientific-light` |
| `defaults.footer` | Markdown footer inherited by slides | Empty |
| `assets.figures` | Folder used for newly imported images | `figures` |
| `assets.include` | Additional folders copied completely during static export | Empty list |
| `bibliography` | Project-relative BibTeX bibliography | `references.bib` in the editor |

The current renderer uses a 16:9 canvas. Layout behavior is defined separately
from the bundled visual themes.
`defaults.footer` supplies Markdown shown on slides without a slide-specific
footer. A heading attribute `footer="none"` suppresses it.

### Asset folders

All asset folders are relative to the directory containing the presentation
Markdown. Absolute paths, `..`, and paths that resolve outside that directory
are rejected.

`assets.figures` changes the destination used by the editor's image-import
button. In the example above, importing `apparatus.svg` produces:

```markdown
![](artwork/apparatus.svg)
```

and stores the file at `artwork/apparatus.svg`. Nested relative folders such as
`assets/images` are allowed and are created when the first image is imported.

`assets.include` lists other directories that belong to the presentation—for
example papers, videos, downloadable notebooks, or data files linked from
Markdown:

```markdown
[Experimental data](references/data.csv)
```

Static export copies the configured figure folder, every folder in
`assets.include`, and individually referenced local Markdown assets. A
configured folder that does not yet exist is ignored; a configured path that
exists but is not a directory is an export error. The default remains fully
backward compatible:

```yaml
assets:
  figures: figures
  include: []
```

## Slides and layouts

Each slide begins with a Markdown heading and layout attributes:

```markdown
## One region {.layout-1}
## Two columns {.layout-1-1 columns="42 58"}
## Left plus stacked right {.layout-1-2 columns="42 58" rows="55 45"}
## Stacked left plus right {.layout-2-1 columns="42 58" rows="55 45"}
## Title and footer only {.layout-0}
## Opening slide {.layout-front}
## Overlay canvas {.layout-free}
```

`columns` and `rows` are relative proportions and are normalized by the parser.

### Title Markdown and spacing

The Design title editor exposes the real heading Markdown but hides the
structural attribute block. For example, editing this front-page title:

```markdown
# New presentation

## *A new roadmap for life*
```

produces source like this when applied:

```markdown
# New presentation {.layout-front}

## *A new roadmap for life*
```

The first heading supplies the slide's organizational title and retains the
layout attributes. Consecutive `#` through `######` headings remain in the same
visible title region, with their Markdown heading levels determining their
relative sizes. Quarkfoil renders each empty line between those headings as
vertical spacing. Multiple empty lines create proportionally more space; no
trailing spaces or backslashes are required. If the title editor is emptied,
Quarkfoil inserts `## ---` so the slide still has a heading on which to retain
its structural attributes.

Grid regions use fenced directives:

```markdown
::: left
Markdown for the left region.
:::

::: top-right
![](figures/apparatus.svg){fit=contain focus="50 50"}
:::
```

Valid region names are `core`, `left`, `right`, `top-left`, `bottom-left`, `top-right`, and `bottom-right`, according to the selected layout.

### Per-slide themes and colors

A slide inherits the deck's front-matter theme unless its heading selects one:

```markdown
## Dark interlude {.layout-1 theme="scientific-dark"}
```

The bundled choices are `scientific-light` and `scientific-dark`. A slide may
also override its background and foreground colors independently:

```markdown
## Highlight {.layout-1 background="#402060" foreground="#ffffff"}
```

Resolution is explicit slide color, then slide theme, then deck theme, then
`scientific-light`. Removing an override restores inheritance. Theme defaults
also supply accent, muted, font, citation, and implicit shape colors.

## Markdown and equations

Normal Markdown is rendered with Marked. Inline and display LaTeX are rendered with KaTeX:

```markdown
The exchange scale is $J_{\mathrm{ex}}$.

\[
J_{\mathrm{ex}} \sim \frac{t^2}{U}.
\]
```

Raw HTML is escaped and executable JavaScript is unsupported.

GitHub-style Markdown tables are supported and receive theme-aware headers,
rules, alternating rows, and colors:

```markdown
| Parameter | Value | Unit |
|---|---:|---|
| Tunnelling | 1.2 | kHz |
| Interaction | 8.4 | kHz |
```

## Images

```markdown
![](figures/example.svg){fit=contain focus="50 50"}
```

Supported `fit` values:

- `contain`: show the complete image.
- `cover`: fill the region and crop overflow.
- `width`: fit the width.
- `height`: fit the height.
- `native`: retain intrinsic size within region bounds.

`focus="X Y"` gives the crop focus as percentages.

Clipboard paste preserves JPEG, GIF, PNG, WebP, or SVG bytes when the browser
provides that original file representation. Some browsers expose copied
rendered pixels—such as an image copied from a web page or a screenshot—only as
a synthesized PNG. Quarkfoil cannot recover the original encoding or GIF
animation from that PNG; drag, upload, or paste the original file to preserve
it. When both an original JPEG/GIF and a synthesized PNG are available,
Quarkfoil prefers the original representation.

## Floating overlays

```markdown
::: overlay {#exchange type="equation" x="58" y="30" w="34" h="14" z="10" font-size="1.2em" align="right" fragment="1"}
\[
J_{\mathrm{ex}} \sim \frac{t^2}{U}
\]
:::
```

Attributes:

- `#id`: stable identifier, unique within the slide.
- `type`: `markdown`, `equation`, `image`, `video`, or `shape`.
- `x`, `y`, `w`, `h`: percentages of the full slide.
- `z`: layer order.
- `locked="true"`: prevent graphical movement.
- `fragment`: zero-based Reveal fragment index.
- `font-size`: relative `em` scale for Markdown and equations; the editor exposes `0.25em` through `3em`.
- `align`: `left`, `center`, or `right`.

### Videos

Local MP4 and WebM files are first-class media overlays. Their source and
playback options are stored directly in the overlay annotation:

```markdown
::: overlay {#experiment type="video" src="figures/experiment.mp4" poster="figures/experiment-poster.jpg" x="10" y="18" w="80" h="60" controls="true" muted="true"}
:::
```

`fit` is `contain` by default or may be `cover`. Native controls are enabled by
default; set `controls="false"` to hide them. The optional `autoplay`, `loop`,
and `muted` flags are enabled with `"true"`. Browsers generally permit autoplay
only for muted video. Videos pause when their slide is left. `poster` names an
optional project-relative image displayed before playback. The editor imports
video into the configured `assets.figures` directory, and static export copies
both the video and poster assets.

### Shapes

Shape overlays use trusted, scalable SVG templates with Markdown or KaTeX
content rendered as a separate label:

```markdown
::: overlay {#idea type="shape" shape="cloud" x="12" y="24" w="30" h="22" fill="#fff3bf" stroke="#e67700" stroke-width="2" align="center"}
\[
E = mc^2
\]
:::
```

The available shapes are `rectangle`, `rounded-rectangle`, `ellipse`, `circle`,
`diamond`, `hexagon`, `cloud`, `callout`, `sine`, and `cosine`. The trigonometric
curves show one complete cycle from 0 to 2π. `fill` controls the
background, `stroke` controls the outline or curve, and `stroke-width` controls
its width. Shape geometry and labels have no implicit padding, so an overlay at
a slide boundary reaches that boundary. Set `shadow="true"` to enable a drop shadow. Default-valued shape
styles are normally omitted: rectangle, theme fill and stroke colors, line
width `2`, centered label, and no shadow. Consequently, implicit shape colors
follow the presentation theme while explicit `fill` and `stroke` values remain
fixed.

## Footer and notes

```markdown
::: footer
Slide-specific citation
:::

::: notes
Speaker notes for Reveal.js.
:::
```

Notes do not appear on the slide canvas.

## Bibliographies and citations

Set a project-relative BibTeX file in front matter:

```yaml
bibliography: references.bib
```

Inline citations use Pandoc-style keys and are numbered by first appearance:

```markdown
The original result is discussed in [@einstein1905].
Several works may be grouped [@einstein1905; @smith2024].
```

Escaped citations and citations inside inline or fenced code remain literal.
A citation overlay provides a positioned figure attribution:

```markdown
::: overlay {#figure-source type="citation" key="smith2024" display="brief" x="55" y="82" w="40" h="8" font-size="0.7em"}

:::
```

`display="number"` shows only the shared number; `display="brief"` adds an
abbreviated reference. DOI and URL fields become links. Missing keys are shown
as visible errors.
