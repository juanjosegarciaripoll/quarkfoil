"""Installed, version-matched guidance for presentation agents."""

from __future__ import annotations


GUIDE = """Quarkfoil agent protocol v1

Create a presentation without starting the editor server:
  quarkfoil deck create DECK [--title TITLE] [--author AUTHOR] [--theme THEME]

Before editing, read the workflow and the topics relevant to the request:
  quarkfoil deck guide workflow
  quarkfoil deck guide format
  quarkfoil deck guide layouts
  quarkfoil deck guide overlays
  quarkfoil deck guide assets
  quarkfoil deck guide citations
  quarkfoil deck guide publishing
  quarkfoil deck guide authoring
  quarkfoil deck guide reproduction
  quarkfoil deck guide examples

Use `quarkfoil deck guide --all` for the complete installed reference.
Use `quarkfoil deck protocol` for the machine-readable editing contract.
For a whole-deck reconstruction from PowerPoint, PDF, or screenshots, read
`guide reproduction`, `guide layouts`, and `guide format` before writing.

The safe editing loop is:
  quarkfoil deck inspect DECK --slides N --format edit > slide.md
  quarkfoil deck apply DECK --edit slide.md

Citations resolve keys from the front-matter `bibliography` BibTeX file. Use
`[@key]` inline or an empty `type="citation"` overlay for a positioned reference.

Never edit the deck directly. Keep the generated YAML header and its revision
guards. Exit 3 means the deck changed: inspect again and rebuild the edit.
Use --no-notes when notes must remain outside the agent context.
"""


WORKFLOW = """Quarkfoil editing workflow

1. Inspect before changing anything. For narrative or deck-wide consistency,
   inspect the whole deck. For a local change, project only the relevant slides.
2. Use literal Markdown edit documents:
     quarkfoil deck inspect DECK --slides 4 --format edit > slide-4.md
3. Keep the YAML header. Edit only the operation fields and Markdown body that
   the operation permits.
4. Apply one or more documents in a single atomic transaction:
     quarkfoil deck apply DECK --edit slide-4.md --edit conclusion.md
5. Inspect the affected slides again. Parser validation does not prove that a
   slide is visually balanced; use the browser editor for layout-sensitive work.

Edit operations:
  replace     Replace one slide. Existing notes are preserved when notes is
              `preserve`, replaced from the body with `replace`, or removed
              with `remove`.
  insert      Insert one slide at the resulting `slide` position.
  delete      Delete the addressed slide. Never delete without user intent;
              Quarkfoil rejects deletion of the final slide.
  move        Move the addressed slide after another slide; `after: 0` means
              the beginning.
  substitute  Replace an exact literal fragment. `expect` must occur exactly
              `count` times (one by default).

Repeat --edit to apply ordered operations with one write. All documents must
carry the same deck revision. Operations use sequential slide numbering.
Target slide fingerprints prevent a shifted number from changing the wrong
slide. Any invalid operation leaves the presentation byte-for-byte unchanged.

Exit status 3 is a deck revision conflict: inspect again and reconstruct the
edit. Exit status 4 is a narrower precondition failure such as a changed target
slide or substitution count: inspect the target and reconsider the operation.

Speaker notes are included by default. Add --no-notes to inspection when they
are private; generated replacement documents then use `notes: preserve`.
JSON transactions remain available; run `quarkfoil deck protocol` for their
machine-readable contract.

Create structural edit documents with these exact headers. Replace the example
revisions with values from the current inspection.

Insert a new slide at resulting position N:

```markdown
---
quarkfoil_edit: 1
operation: insert
deck_revision: sha256:...
slide: N
---

## New slide {.layout-1}

::: core
Content.
:::
```

Delete or move an inspected slide using its fingerprint:

```yaml
---
quarkfoil_edit: 1
operation: delete
deck_revision: sha256:...
slide: N
slide_revision: sha256:...
---
```

```yaml
---
quarkfoil_edit: 1
operation: move
deck_revision: sha256:...
slide: N
slide_revision: sha256:...
after: 3
---
```

For a narrow literal change, use YAML block scalars so Markdown and LaTeX stay
unescaped:

```yaml
---
quarkfoil_edit: 1
operation: substitute
deck_revision: sha256:...
slide: N
slide_revision: sha256:...
count: 1
expect: |-
  Old literal text
replacement: |-
  New literal text
---
```
"""


FORMAT = """Quarkfoil Markdown format

The UTF-8 Markdown file is the source of truth. YAML front matter holds
deck-wide metadata, and a line containing only `---` separates items.

Common front-matter fields are `title`, `author`, `subtitle`, `date`, `event`,
`series`, `part`, `aspect-ratio`, `theme`, `bibliography`, `assets`, and
`defaults.footer`. Publishing requires `date`. Themes are `scientific-light`
and `scientific-dark`; the current canvas is 16:9.

Minimal document:

```markdown
---
title: Quantum simulation
author: Ada Lovelace
aspect-ratio: "16:9"
theme: scientific-light
defaults:
  footer: Summer school · 2026
---

## Opening {.layout-front}

::: core
**Ada Lovelace**

Quantum Simulation School
:::
```

Every slide starts with a Markdown heading carrying a `.layout-*` class.
Consecutive heading lines belong to the visible title region. A section is an
editor-only item such as `# Methods {#methods .section}`. A trashed slide has
the `.trashed` class and is omitted from Present mode and exports.

Grid cells are fenced directives. Their valid names depend on the layout:

```markdown
::: left {font-size="1.1em"}
Markdown and inline $J_{\\mathrm{ex}}$.
:::
```

Normal Markdown uses Marked and equations use KaTeX. Use `$...$` inline or
`\\[...\\]` for display equations. Raw HTML is escaped. A heading, paragraph,
or list item ending in `{fragment=N}` appears at zero-based fragment step N.

Slide-local directives include:

```markdown
::: footer
Slide-specific footer
:::

::: notes
Speaker-only notes
:::
```

One ordinary blank line separates Markdown blocks. Additional consecutive
blank lines create visible vertical spacing in titles, cells, overlays, and
shape labels. Fenced code blocks must open and close within one slide.
"""


LAYOUTS = """Quarkfoil layouts

Use the smallest layout that expresses the content. Layout classes and cells:

  1       `.layout-1`    core
  1+1     `.layout-1-1`  left, right
  1+2     `.layout-1-2`  left, top-right, bottom-right
  2+1     `.layout-2-1`  top-left, bottom-left, right
  0       `.layout-0`    title and optional footer; no grid cells
  Front   `.layout-front` title plus core
  Free    `.layout-free` positioned overlays only; title is organizational

`columns="42 58"` controls horizontal proportions on split layouts.
`rows="55 45"` controls stacked proportions. Values are relative and are
normalized. Do not put a cell into a layout that does not provide it.

```markdown
## Comparison {.layout-1-1 columns="42 58"}

::: left
### Existing approach

- Simple
- Robust
:::

::: right
### Proposed approach

- Faster {fragment=0}
- More accurate {fragment=1}
:::
```

Prefer `1` for a single argument or figure, `1+1` for comparisons, `1+2` or
`2+1` when one item should dominate two supporting items, `0` for section
breaks, Front for opening material, and Free only when a grid cannot express
the composition. If a slide becomes dense, split it instead of shrinking text.
"""


OVERLAYS = """Quarkfoil positioned overlays

Overlays are fenced directives. IDs need only be unique within their slide.
Coordinates and sizes are percentages of the 1280x720 slide canvas.

```markdown
::: overlay {#exchange type="equation" x="58" y="30" w="34" h="14" z="10" font-size="1.2em" align="right" fragment="1"}
\\[
J_{\\mathrm{ex}} \\sim \\frac{t^2}{U}
\\]
:::
```

Common attributes are `#id`, `type`, `x`, `y`, `w`, `h`, `z`, `rotation`,
`locked="true"`, `fragment`, `font-size`, `color`, and `align`. Types include
`markdown`, `equation`, `image`, `video`, `shape`, `arrow`, and `citation`.

Positioned paper references have their own box type; figure credits are only
one use. Do not type a formatted reference into a Markdown overlay. The
canonical form for key `smith2024` is:

```markdown
::: overlay {#paper-reference type="citation" key="smith2024" display="brief" x="55" y="82" w="40" h="8" font-size="0.7em"}

:::
```

`type="citation"` resolves BibTeX keys and renders a transparent attribution
box. Run `quarkfoil deck guide citations` for numbered and brief display modes.

An image overlay puts its image Markdown inside the directive. Image fit is
`contain`, `cover`, `stretch`, `width`, `height`, or `native`:

```markdown
::: overlay {#apparatus type="image" x="8" y="20" w="42" h="55"}
![](figures/apparatus.svg){fit=contain focus="50 50"}
:::
```

Shapes use `shape`, `fill`, `stroke`, `stroke-width`, and `stroke-style`.
Available shapes are rectangle, rounded-rectangle, ellipse, circle, diamond,
triangle, hexagon, cross, x, star, cloud, callout, left-brace, right-brace, and
arc. Arrows use `x1`, `y1`, `x2`, `y2`, and `heads` instead of a bounding box.

Prefer grid cells for ordinary content. Use overlays for genuine spatial
relationships, annotations, callouts, or full-slide compositions. Keep objects
inside the slide and avoid overlapping text unless that is intentional.
"""


ASSETS = """Quarkfoil project assets

All paths are relative to the presentation directory and must stay within it.
Absolute paths and `..` traversal are invalid. Front matter configures assets:

```yaml
assets:
  figures: figures
  include:
    - references
    - media
```

`assets.figures` is where the editor imports images and videos; it defaults to
`figures`. `assets.include` lists additional directories copied wholesale by
static export. Referenced local files outside those folders are copied only
when the export rules recognize the reference.

Grid image:

```markdown
::: core
![](figures/result.svg){fit=contain focus="50 50" opacity="1"}
:::
```

Use project-relative paths and meaningful filenames. Do not invent an asset
that is not present. SVG is loaded as an image resource rather than injected
as executable DOM. Native video overlays support MP4 and WebM; the editor can
convert AVI or MKV when FFmpeg is installed. An exported or packed deck copies
only assets allowed by the presentation-directory boundary.
"""


CITATIONS = """CITATIONS: BIBLIOGRAPHY SOURCE AND CANONICAL FORMS

Inline citations and positioned citation boxes are different features. For an
automatically formatted paper reference anywhere on a slide, use an overlay
with `type="citation"`. It is a generic positioned bibliographic reference;
do not emulate it with a Markdown or text box.

Select a project-relative BibTeX file in front matter:

```yaml
bibliography: references.bib
```

Inline citations use Pandoc-style keys and are numbered by first appearance:

```markdown
The original result is discussed in [@einstein1905].
Several works may be grouped [@einstein1905; @smith2024].
```

A positioned paper reference uses the dedicated citation overlay type. Its
canonical form has an empty body because Quarkfoil generates it from BibTeX:

```markdown
::: overlay {#paper-reference type="citation" key="smith2024" display="brief" x="55" y="82" w="40" h="8" font-size="0.7em"}

:::
```

`display="number"` shows shared citation numbers. `display="brief"` produces
an abbreviated bibliographic reference without affecting numbering. Use `key`
for one entry or `keys` for space-separated entries. Never fabricate
bibliography keys; inspect the project bibliography or ask the user when a
source is missing. The box has a transparent background and no border or shadow.
"""


PUBLISHING = """Quarkfoil collection publishing

`quarkfoil publish` adds one or more decks to a shared static collection with
one generated listing, versioned player runtimes, and a content-addressed asset
pool. It does not use SFTP. A remote target is an rsync destination, normally
transferred over SSH; Quarkfoil leaves authentication to SSH.

Every published deck needs a valid `date` in front matter. The listing also
uses `title`, `description` (falling back to `subtitle`), `event`, `series`,
`part`, `series-description`, and `unlisted` when present:

```yaml
---
title: Quantum simulation
description: An introduction to programmable quantum matter.
event: Summer school
date: 2026-09-07
---
```

Publish to a local collection or inspect a remote update without changing it:

```console
quarkfoil publish lecture.md --site ./talks
quarkfoil publish lecture.md --site homepage:talks/ --dry-run
```

When the dry run names the intended target and changes, publish by removing
`--dry-run`:

```console
quarkfoil publish lecture.md --site homepage:talks/
```

Here `homepage` is an SSH host name or alias and `talks/` is relative to the
remote account's home. An explicit target may instead be
`user@host:/var/www/talks/`. The web server, DNS, and mapping from that remote
directory to a public URL are external to Quarkfoil. Inspect the user's SSH
configuration or ask for the target; never derive it from the public URL.

Publish several decks in one staged update so assets transfer once and the
listing is rebuilt once:

```console
quarkfoil publish presentations/0*.md --site homepage:talks/
```

The deck folder defaults to the Markdown filename; `--name` changes it for a
single deck. `--index-title` and `--index-lede` initialize or update remembered
listing text. `--index-only` rebuilds the listing. Speaker notes are omitted by
default because the published Markdown is public; include them only with the
explicit `--notes` option. Use `quarkfoil publish --help` for all options.
"""


AUTHORING = """Quarkfoil authoring and review

Preserve scientific meaning, equations, units, caveats, citations, and speaker
notes unless the user explicitly requests a substantive change. Distinguish
copy-editing from changing a scientific claim.

For a deck-wide request:
  1. Inspect the complete deck and identify its audience, purpose, narrative,
     terminology, visual conventions, and repeated structure.
  2. Propose changes first when the request is ambiguous or destructive.
  3. Prefer one claim or question per slide, with a title that states its role.
  4. Split crowded slides. Do not solve density primarily by reducing font size.
  5. Use layouts consistently: comparisons should look like comparisons, and
     supporting panels should remain visually subordinate.
  6. Keep notation, capitalization, units, citation style, and image treatment
     consistent across the deck.
  7. Apply coherent changes atomically, then reinspect the affected sequence.

Parser success verifies structure, not appearance. Layout-sensitive changes,
overlays, long equations, tables, images, and unusual title spacing require a
browser review. Report clearly when visual validation was not performed.
"""


REPRODUCTION = """REPRODUCTION: FIRST-PASS RULES

Use these rules when reconstructing PowerPoint, PDF, or image references:

1. Choose layout from content shape: text + figure -> 1+1; text + two figures
   -> 1+2; two texts + figure -> 2+1; annotated canvas with normal title and
   footer -> 0; full-bleed or chrome-free divider -> Free.
2. Set `font-size` explicitly on every text cell and text overlay.
3. Keep an image alone in its grid cell.
4. Keep each overlay paragraph on one source line.
5. Use `type="citation"` boxes for positioned paper references or credits;
   do not recreate them as Markdown overlays.
6. Place overlays after the grid content is stable.
7. Render and inspect every page. `deck inspect` validates structure, not fit.

REPRODUCTION: RESOLVED TYPOGRAPHY AT 1280x720

The Reveal base is 32 CSS px. Effective ordinary-text sizes are:

  context                    formula                  source default
  grid-cell prose            cell x 32 px             0.72 -> 23.0 px
  overlay Markdown prose     overlay x 0.68 x 32 px   1.00 -> 21.8 px
  shape-label prose          overlay x 0.68 x 32 px   1.00 -> 21.8 px
  overlay equation           overlay x 32 px          1.00 -> 32.0 px
  grid-cell table            cell x 0.72 x 32 px      0.72 -> 16.6 px
  overlay table              overlay x 0.72 x 32 px   1.00 -> 23.0 px
  slide-title h2             1.28 x 32 px                     41.0 px
  footer                     0.36 x 32 px                     11.5 px

PowerPoint 24 pt equals 32 px at 96 dpi. Starting values for similar body
size are cell `1em`, overlay Markdown and shape labels `1.45em`, and overlay
equations `1em`. These are size matches, not guarantees that content fits.
The extra 0.68 multiplier affects overlay Markdown paragraphs/lists and shape
labels, but not equation overlays. Equal `font-size` values therefore do not
produce equal-looking prose and equations.

Source accepts any positive decimal `font-size`, with optional `em`; invalid or
nonpositive values are parser errors. Design controls expose and clamp values
to 0.25em through 3em in 0.05em steps.

REPRODUCTION: IMAGE CELLS ARE IMAGE-ONLY

A cell is an image cell only when its complete trimmed body is one image.
Mixing prose and an image turns it into Markdown; image attributes such as
`{fit=contain}` then render as literal text.

WRONG:

```markdown
::: left
Explanation.

![](figures/plot.png){fit=contain}
:::
```

RIGHT:

```markdown
::: left
Explanation.
:::

::: right
![](figures/plot.png){fit=contain}
:::
```

Use 1+2 or 2+1 when a figure needs a separate caption or supporting panel.
Do not put captions beneath images in the same image cell.

REPRODUCTION: FREE CANVAS CHOICE

`.layout-0` keeps the normal title and footer while suppressing grid cells; use
it for a free-form content slide with presentation chrome. `.layout-free`
hides the complete slide frame, including title and footer; use it for
full-bleed material or chrome-free dividers. Do not rebuild a normal title as
an overlay merely because the content is positioned.

REPRODUCTION: OVERLAY LINE BREAKS

Markdown overlays and shape labels enable hard breaks for source newlines;
grid cells do not. In an overlay, keep each paragraph on one source line unless
the line break is intentional. Source wrapping becomes visible wrapping.

WRONG:

```markdown
What a register of qubits can hold, and what an algorithm can
do with it.
```

RIGHT:

```markdown
What a register of qubits can hold, and what an algorithm can do with it.
```

REPRODUCTION: CITATION BOXES

Positioned paper references are a dedicated overlay type, not ordinary
Markdown text. Figure credits are one possible use. Citation keys come from the
BibTeX file selected by front matter, for example `bibliography:
references.bib`. The canonical positioned form is:

```markdown
::: overlay {#paper-reference type="citation" key="smith2024" display="brief" x="55" y="82" w="40" h="8" font-size="0.7em"}

:::
```

Use `display="brief"` for an attribution without a citation number and
`display="number"` for the shared numbered citation. The box resolves `key` or
space-separated `keys` from the front-matter bibliography and renders with a
transparent background. Never fabricate keys or replace this with a Markdown
overlay containing hand-formatted reference text.

REPRODUCTION: GEOMETRY

Overlay `x`, `y`, `w`, and `h` are percentages of the full 1280x720 slide.
Current default geometry, derived from layout.css:

  horizontal padding       4.5% = 57.6 px each side
  top/bottom padding       3.2% / 2.4% of slide width = 41.0 / 30.7 px
  content box              1164.8 x 648.3 px
  title/footer rows        11% / 6% of content height = 71.3 / 38.9 px
  grid core with chrome    y = 15.6% through 90.3%, height 538.1 px
  grid gap                 2.2% of content width = 25.6 px

The core band assumes both title and footer are present. On layout 0, keep
ordinary overlays inside that band to avoid the chrome. Layout Free makes the
whole slide available.

For layout 1+1 with `columns="40 60"`, the available column width is
1164.8 - 25.6 = 1139.2 px. The left cell is 455.7 px wide. A square
`fit=contain` image fills that width and centers vertically in the 538.1 px
core, approximately x=4.5%, y=21.3%, w=35.6%, h=63.3% of the full slide.

REPRODUCTION: OVERFLOW BUDGET

Cells and shape labels hide overflow. A structurally valid slide can silently
clip prose, tables, or equations. At cell `1em`, budget about 35-40 characters
per line in a half-width column and about 12 body lines in a full-height cell,
then verify the render. Display equations do not wrap. Prefer splitting a long
equation, using an `aligned` environment, or splitting the slide before
reducing the font.

REPRODUCTION: VISUAL VERIFICATION

After applying the deck, print and rasterize it when the required tools exist:

```console
quarkfoil print deck.md --output /tmp/deck.pdf
pdftoppm -r 96 -png /tmp/deck.pdf /tmp/deck-page
```

At 96 dpi, Quarkfoil's 13.33 x 7.5 inch pages rasterize to approximately
1280x720, so one output pixel is one CSS pixel. Inspect every page for clipped
text, literal attribute strings, unreadable type, off-slide overlays, long
equations, and accidental source line breaks. Report when visual verification
was not possible.
"""


EXAMPLES = """Quarkfoil slide examples

One-region explanation:

```markdown
## Exchange scale {.layout-1}

::: core
The effective coupling is

\\[
J_{\\mathrm{ex}} \\sim \\frac{t^2}{U}.
\\]

- Tunnelling sets the numerator. {fragment=0}
- Interactions suppress exchange. {fragment=1}
:::

::: notes
Define the perturbative regime before revealing the equation.
:::
```

Figure with interpretation:

```markdown
## Measured phase boundary {.layout-1-1 columns="58 42"}

::: left
![](figures/phase-boundary.svg){fit=contain}
:::

::: right
### Main observation

The transition shifts monotonically with interaction strength.

### Caveat

Finite-size effects dominate the final two points.
:::
```

Free-canvas annotation:

```markdown
## Apparatus {.layout-free}

::: overlay {#apparatus type="image" x="5" y="12" w="90" h="76"}
![](figures/apparatus.svg){fit=contain}
:::

::: overlay {#label type="markdown" x="62" y="18" w="25" h="12" z="2"}
**Detection path**
:::

::: overlay {#pointer type="arrow" x1="63" y1="29" x2="52" y2="43" heads="end" z="3"}
:::
```
"""


GUIDE_TOPICS = {
    "workflow": WORKFLOW,
    "format": FORMAT,
    "layouts": LAYOUTS,
    "overlays": OVERLAYS,
    "assets": ASSETS,
    "citations": CITATIONS,
    "publishing": PUBLISHING,
    "authoring": AUTHORING,
    "reproduction": REPRODUCTION,
    "examples": EXAMPLES,
}


def complete_guide() -> str:
    """Return the landing guide followed by every topic in discovery order."""
    return GUIDE.rstrip() + "\n\n" + "\n\n".join(GUIDE_TOPICS.values()) + "\n"


__all__ = ["GUIDE", "GUIDE_TOPICS", "complete_guide"]
