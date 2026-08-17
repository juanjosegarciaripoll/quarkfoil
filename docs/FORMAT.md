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
| `subtitle` | Presentation description used by exported link-sharing metadata | Empty |
| `description` | Explicit exported description; takes precedence over `subtitle` | Empty |
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

Static export copies only referenced files from the configured figure folder.
Every folder in `assets.include` is copied recursively, including unreferenced
files, and local Markdown assets referenced outside the figure folder are
copied individually. A configured folder that does not yet exist is ignored; a
configured path that exists but is not a directory is an export error:

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
::: left {font-size="1.1em"}
Markdown for the left region.
:::

::: top-right
![](figures/apparatus.svg){fit=contain focus="50 50"}
:::
```

Valid region names are `core`, `left`, `right`, `top-left`, `bottom-left`, `top-right`, and `bottom-right`, according to the selected layout.
The optional `font-size` attribute sets a region's text size in `em`; the
Design properties expose values from `0.25em` through `3em`. Removing the
attribute restores the default `0.72em` region size.
Within a grid region, one empty line has its usual Markdown meaning and
separates blocks such as paragraphs or lists. Each additional consecutive
empty line adds one line of visible vertical space. Empty lines inside fenced
code blocks remain part of the code and are not converted into spacing. The
same spacing rule applies to positioned Markdown and shape labels.

Markdown headings, paragraphs, and list items can participate in Reveal.js
fragment sequencing by ending the relevant source line with `{fragment=N}`,
where `N` is a zero-based index:

```markdown
### Staged explanation {fragment=0}

The first detail appears next. {fragment=1}

- Then this item {fragment=2}
- And finally this one {fragment=3}
```

The annotation is not displayed. Elements with the same index appear together.
Fragment annotations inside inline or fenced code remain literal code.

Image `fit` values are `contain`, `cover`, `stretch`, `width`, `height`, and
`native`. `stretch` reshapes the external image resource to the exact region or
overlay dimensions without changing the source file.

### Per-slide appearance

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
also supply accent, muted, font, citation, and implicit shape colors. Colors
use six-digit `#RRGGBB` or eight-digit `#RRGGBBAA` hexadecimal notation; the
last byte controls alpha.

A slide can suppress its inherited or slide-specific footer with a heading
attribute:

```markdown
## Full-bleed result {.layout-1 footer="none"}
```

Removing `footer="none"` restores the footer.

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
![](figures/example.svg){fit=contain focus="50 50" opacity="0.65"}
```

Supported `fit` values:

- `contain`: show the complete image.
- `cover`: fill the region and crop overflow.
- `width`: fit the width.
- `height`: fit the height.
- `native`: retain intrinsic size within region bounds.

`focus="X Y"` gives the crop focus as percentages.
`opacity` sets the opacity of the complete image from `0` (transparent) to `1`
(opaque, the default). It applies without modifying raster or SVG source files
and multiplies any transparency already present in the image.

Clipboard paste preserves JPEG, GIF, PNG, WebP, or SVG bytes when the browser
provides that original file representation. Some browsers expose copied
rendered pixels—such as an image copied from a web page or a screenshot—only as
a synthesized PNG. Quarkfoil cannot recover the original encoding or GIF
animation from that PNG; drag, upload, or paste the original file to preserve
it. When both an original JPEG/GIF and a synthesized PNG are available,
Quarkfoil prefers the original representation.

## Sections

Section markers organize the editor sidebar without creating presentation
slides:

```markdown
# Methods {#methods .section}
```

Place a section marker between the same `---` separators used for slides. It
groups every following slide up to the next section marker. The ID is stable
editor state, while `.section` distinguishes the heading from a slide. Section
markers may be collapsed, renamed, deleted, or moved in the sidebar. Moving a
marker changes the boundary between neighboring groups; it does not reorder the
slides themselves. Static and interactive presentations omit section markers.

### Slide Trash

The editor keeps discarded slides in a final, readable Trash section:

```markdown
# Trash {#quarkfoil-trash .section .trash}

---

## Superseded result {.layout-1 .trashed}
```

Slides carrying `.trashed` remain editable in Design and Source modes but are
omitted from Present mode and static exports. Restoring a slide removes
`.trashed` and places it immediately before the Trash section. When the last
trashed slide is restored or permanently deleted, the empty Trash section is
removed. Deleting the Trash section through the editor empties all of its
slides after confirmation. At least one active slide must remain in every deck.

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
- `type`: `markdown`, `equation`, `image`, `video`, `shape`, or `arrow`.
- `x`, `y`, `w`, `h`: percentages of the full slide.
- `z`: layer order.
- `locked="true"`: prevent graphical movement.
- `fragment`: zero-based Reveal fragment index.
- `font-size`: relative `em` scale for Markdown and equations; the editor exposes `0.25em` through `3em`.
- `color`: an optional six- or eight-digit hexadecimal text color, such as
  `#c92a2a` or the 50%-opaque `#c92a2a80`.
- `align`: `left`, `center`, or `right`.

### Videos

Local MP4 and WebM files are first-class media overlays. AVI and MKV imports
are automatically converted to browser-compatible MP4 (or WebM as a fallback) by the local Quarkfoil server when
`ffmpeg` and `ffprobe` are available on `PATH`. Quarkfoil extracts the first
frame as a poster, inserts the video immediately, and shows conversion progress
in a non-modal dialog, so the preview can still be moved and resized. Browser-only
directory mode cannot perform this conversion. The source and playback options
are stored directly in the overlay annotation:

```markdown
::: overlay {#experiment type="video" src="figures/experiment.mp4" poster="figures/experiment-poster.jpg" x="10" y="18" w="80" h="60" controls="true" muted="true"}
:::
```

`fit` is `contain` by default or may be `cover`. Native controls are enabled by
default; set `controls="false"` to hide them. The optional `autoplay`, `loop`,
and `muted` flags are enabled with `"true"`. Browsers generally permit autoplay
only for muted video. Videos pause when their slide is left. Source and Design
modes never start autoplay; videos there play only after an explicit click on
their controls and pause when the editor changes slides or modes. `poster` names
an optional project-relative image displayed before playback. The editor imports
video into the configured `assets.figures` directory, and static export copies
both the video and poster assets.

AVI and MKV source files are temporary import inputs: a successful conversion
keeps the generated `.mp4` or `.webm` and poster image, not the original container. H.264 video and AAC/MP3 audio are copied directly into MP4 when possible; only incompatible streams are re-encoded. A
failed or cancelled conversion removes its temporary files and restores or
removes the provisional overlay. If FFmpeg has no supported H.264 encoder,
conversion falls back to VP9 video and Opus audio in WebM.

### Shapes

Shape overlays use trusted, scalable SVG templates with Markdown or KaTeX
content rendered as a separate label:

```markdown
::: overlay {#idea type="shape" shape="cloud" x="12" y="24" w="30" h="22" fill="#fff3bf" stroke="#e67700" stroke-width="2" stroke-style="dash" align="center"}
\[
E = mc^2
\]
:::
```

The available shapes are `rectangle`, `rounded-rectangle`, `ellipse`, `circle`,
`diamond`, `hexagon`, `cross`, `x`, `star`, `cloud`, `callout`, `left-brace`,
`right-brace`, and `arc`.
`fill` controls the background, `stroke` controls the outline, and `stroke-width` controls
its width. `stroke-style` may be `solid` (the default), `dash`, `dash-dot`, or
`dotted`; dash and gap lengths scale with the line width. Eight-digit colors can make either surface partly or fully
transparent; for example, `fill="#fff3bf00"` removes the visible background.
Shape geometry and labels have no implicit padding, so an overlay at
a slide boundary reaches that boundary. Set `shadow="true"` to enable a drop shadow. Default-valued shape
styles are normally omitted: rectangle, theme fill and stroke colors, line
width `2`, centered label, and no shadow. Consequently, implicit shape colors
follow the presentation theme while explicit `fill` and `stroke` values remain
fixed.

The `arc` template is parameterized:

```markdown
::: overlay {#orbit type="shape" shape="arc" x="20" y="25" w="40" h="30" start-angle="30" end-angle="300" heads="end"}
:::
```

`start-angle` and `end-angle` are degrees measured clockwise from the right of
the overlay. They default to `0` and `180`. Equal angles draw a complete circle.
`heads` may be `none` (the default), `start`, `end`, or `both`. Arc arrowheads
use the shape's line color and width. Because an arc is an open path, `fill`
does not affect it.

### Arrows

Arrows are dedicated editable overlays whose endpoints are stored directly as
slide percentages:

```markdown
::: overlay {#flow type="arrow" x1="20" y1="30" x2="75" y2="62" heads="end" stroke="#146c7e" stroke-width="2" stroke-style="dash-dot"}
:::
```

`x1`, `y1`, `x2`, and `y2` define the two endpoints. `heads` may be `end`
(the default), `start`, `both`, or `none`. `stroke` controls the line and head
color, while `stroke-width` controls their thickness. `stroke-style` accepts the
same thickness-scaled line patterns as shapes. Arrows also support the
common `z`, `fragment`, and `locked` attributes. Their bounding box is derived
from the endpoints and is not serialized as `x`, `y`, `w`, and `h`. An omitted
`stroke` follows the presentation theme.

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
::: overlay {#figure-source type="citation" keys="smith2024 jones2022" display="brief" x="55" y="82" w="40" h="8" font-size="0.7em"}

:::
```

`display="number"` shows a citation's shared number. `display="brief"` is an
attribution: it shows generated abbreviated references without citation
numbers and does not affect numbering. Its `key` attribute selects one paper;
`keys` selects multiple space-separated papers. Both are editable from the
attribution's Design properties. Attributions have a transparent background,
without a border or shadow, so they can be placed over other slide content.
DOI and URL fields become links. In the local editor, an attribution also shows
a small document link when its bibliography entry has an available `file` or
`pdf` attachment. Missing keys are shown as visible errors.
