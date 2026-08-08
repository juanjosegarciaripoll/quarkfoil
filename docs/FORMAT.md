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
| `theme` | Presentation theme identifier | `scientific-light` |
| `defaults.footer` | Markdown footer inherited by slides | Empty |
| `assets.figures` | Folder used for newly imported images | `figures` |
| `assets.include` | Additional folders copied completely during static export | Empty list |

The current renderer uses a 16:9 canvas and the bundled scientific theme.
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

Each slide begins with a level-one or level-two heading and layout attributes:

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

## Markdown and equations

Normal Markdown is rendered with Marked. Inline and display LaTeX are rendered with KaTeX:

```markdown
The exchange scale is $J_{\mathrm{ex}}$.

\[
J_{\mathrm{ex}} \sim \frac{t^2}{U}.
\]
```

Raw HTML is escaped and executable JavaScript is unsupported.

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
- `type`: `markdown`, `equation`, or `image`.
- `x`, `y`, `w`, `h`: percentages of the full slide.
- `z`: layer order.
- `locked="true"`: prevent graphical movement.
- `fragment`: zero-based Reveal fragment index.
- `font-size`: relative `em` scale for Markdown and equations; the editor exposes `0.25em` through `3em`.
- `align`: `left`, `center`, or `right`.

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
