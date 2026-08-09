# Editor guide

## Modes

### Source

Source displays the complete Markdown document. When you leave Source for Design or Present, valid edits are applied automatically. Invalid Markdown keeps Source open and reports the error. Saving also applies a pending Source draft before writing it to disk.

Entering Source positions the caret at the currently selected slide.

### Design

Design renders one slide and exposes graphical controls:

- Click a grid region or overlay to select it.
- Double-click a title, Markdown region, text overlay, or equation overlay to edit its content.
- Drag floating overlays to move them and use their corner handles to resize them.
- Use Properties to adjust geometry, layer, fragment, image fit/focus, font scale, and alignment.

The image toolbar action is contextual:

- With a grid region selected, it replaces that region with an image.
- With no grid region selected, it creates a floating image overlay.

Pasting an image from the system clipboard follows the same rule in Design
mode. Select a grid region before pasting to replace its contents, or clear the
grid selection to create a centered floating image. Quarkfoil asks for the
asset filename before importing it and suggests a unique timestamped name;
cancelling the prompt cancels the paste. Clipboard text is left untouched, and
image pasting is disabled while a text field or content dialog is active.

An image embedded alongside text in a Markdown region remains part of that Markdown document block and is not independently selectable.

### Present

Present hides the editor chrome and enables normal Reveal.js navigation. Press `Escape` to return to Design.

## Slides

The left sidebar selects slides. Its top controls add a blank slide with the current layout, duplicate the selected slide, or delete it. The bottom controls move the selected slide up or down.

Double-click a sidebar title to rename a slide. This is especially useful for Free slides, whose organizational title is hidden on the canvas.
The title editor exposes Markdown headings while hiding the structural `{...}`
attributes. Use `#`, `##`, and smaller heading levels on consecutive lines to
create differently sized title lines. Quarkfoil restores the attributes to the
first heading when applying the edit. Leave an empty line between headings to
add vertical space between them. See [Title Markdown and spacing](FORMAT.md#title-markdown-and-spacing)
for a complete source example.

## Layouts

- `1`: one core region.
- `1+1`: two columns.
- `1+2`: one left region and two stacked right regions.
- `2+1`: two stacked left regions and one right region.
- `0`: title and footer, without core regions.
- `Front page`: title in the upper half and details in the lower half.
- `Free (nothing)`: no title, footer, or grid; only positioned overlays.

## Images

Image-only regions and image overlays support:

- Fit: contain, crop/fill, fit width, fit height, or native size.
- Horizontal and vertical crop focus.

New and pasted files are copied to the presentation project's `figures/`
directory. Repeated clipboard filenames are made unique. Undo restores content
replaced during the current editing session.

New floating images preserve their intrinsic aspect ratio. Their initial box is
centered and limited to 35% of the slide in its larger dimension; dropped
images use the drop point instead and are kept inside the slide. Images placed
in grid regions use the size of that region.

## Shapes

Choose a template from the Shape palette in Design mode, then use the adjacent
button to add it to the current slide. The palette includes rectangles,
ellipses, a circle, diamond, hexagon, thought cloud, comic callout, and sine and
cosine curves covering one cycle from 0 to 2π.

Shapes resize and move like other overlays. Their Properties include the
template, background color, line color, line width, and an optional shadow.
Default-valued styles are omitted from the Markdown source. Double-click a
shape to edit its label as Markdown or LaTeX; the label is rendered
independently of the SVG background so equations use the same KaTeX renderer as
the rest of the presentation.

Shapes without explicit background or line colors inherit those colors from
the active presentation theme. Selecting a specific color creates a fixed
override in the Markdown source.

## Saving and recovery

The Save button and `Ctrl+S` write the Markdown file. Unsaved changes are identified in the toolbar. Local-server saves use a content hash to detect external modifications and an atomic replacement to avoid partial files.

The browser also keeps recovery snapshots in IndexedDB. These snapshots supplement the Markdown file; they are not a substitute for version control or backups.

## Bibliography

The Bibliography toolbar button opens a searchable reference list and complete
BibTeX source. The source is saved losslessly to the file selected by
`bibliography` in front matter, or `references.bib` by default. Saves are
atomic and reject external conflicts.

Enter a DOI and choose **Add DOI** to retrieve BibTeX metadata. Quarkfoil shows
a preview before appending it to the draft and detects duplicate keys and DOIs.
DOI lookup is the only bibliography operation that requires the network.

**Insert [n]** inserts an inline citation at the Source editor caret. **Add
attribution** creates a positioned, resizable brief reference for crediting a
copied figure. Both forms share deck-wide numbering.

## Keyboard shortcuts

- `Ctrl+S`: save.
- `Ctrl+Z`: undo.
- `Ctrl+Shift+Z`: redo.
- `Ctrl+Enter`: accept a content-editing dialog.
- `Escape`: cancel a dialog or leave Present mode.
- Arrow keys: nudge a selected overlay by `0.1%`.
- `Shift` + arrow keys: nudge by `1%`.
- `Delete`: delete a selected overlay.
- `Ctrl+D`: duplicate a selected overlay.
- `Ctrl+V`: paste a clipboard image in Design mode.
