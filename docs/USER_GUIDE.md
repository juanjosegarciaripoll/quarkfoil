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
- Shift-click floating overlays to add or remove them from a selection. Drag any
  selected object or use the arrow keys to move the group while preserving its
  spacing. The solid primary selection owns the properties and resize handles;
  resizing affects only that object, never the group. The toolbar trashcan and
  the `Delete` key remove every object in the selection. Duplicating copies the
  primary object and moves the selection to the new copy.
- Drag from an empty part of the slide to select every overlay intersecting the
  selection rectangle. Shift-drag adds the intersecting overlays to the current
  selection.
- Use Properties to adjust geometry, layer, fragment, image fit/focus, font scale, text color, and alignment. Resetting an explicit text color returns the object to its slide theme.

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

Videos remain paused in Source and Design modes unless you explicitly use their
play control. Changing slides or editor modes pauses playback. Present mode
continues to honor each video's autoplay setting.

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

Changing a slide's layout keeps regions that exist in both layouts and removes
the Markdown for regions that the new layout does not use. Positioned objects,
speaker notes, and footers are unaffected.

In Design mode, edit optional speaker notes in the pane below the slide. Drag
the divider to give the notes more or less room. Notes are stored as Markdown
in the slide's `::: notes` block and remain available in Reveal's speaker view.

Inside a layout region, one empty line separates Markdown blocks normally.
Additional consecutive empty lines add visible vertical space. This also works
in positioned Markdown and shape labels without altering fenced code blocks.

To reveal parts of Markdown progressively in Present mode, end a heading,
paragraph, or list-item line with `{fragment=N}`. Indices start at zero, and
elements sharing an index appear together. For example:

```markdown
- First result {fragment=0}
- Supporting evidence {fragment=1}
- Conclusion {fragment=2}
```

## Slide appearance

Click an empty part of the slide to show slide-wide Properties. Theme chooses
the deck default, Scientific light, or Scientific dark for that slide.
Background and Foreground create explicit color overrides; the reset buttons
beside them remove those attributes and return to the theme colors. Omitted
theme and color values do not occupy Markdown state. Color pickers include an
alpha control for partial or full transparency. Numeric values beside sliders
are editable and validated against the same limits as their sliders.

## Images

Image-only regions and image overlays support:

- Fit: contain, crop/fill, stretch, fit width, fit height, or native size. Stretch
  reshapes raster images and SVG resources to the overlay's exact dimensions.
- Horizontal and vertical crop focus.
- Global opacity from fully transparent to fully opaque. This is applied by the
  presentation without modifying the raster or SVG source file.
- Upload replacement: import a new file from the browser's computer.
- Choose project image: select an existing image from the configured figures
  folder. Both replacement actions retain the object's position, size, fit,
  focus, and stable ID.
- Online icons: search the allowlisted Material Symbols, Tabler Icons, and
  IconPark collections through Iconify. Quarkfoil downloads the chosen SVG into
  `<figures>/icons/`; presentations never depend on Iconify at viewing time.

New and pasted files are copied to the presentation project's `figures/`
directory. Repeated clipboard filenames are made unique. Undo restores content
replaced during the current editing session. Pasting while an image is selected
replaces that image in place; otherwise it creates a new floating image or
fills the selected grid region.

Online icon imports also update `<figures>/icons/.quarkfoil-icons.json`. This
hidden project file records the collection, original icon name, upstream source,
author, and SPDX license without adding attribution to a slide. Keep it with the
project. Static export folds the applicable notices and complete license texts
into its existing `THIRD_PARTY_LICENSES.txt`.

New floating images preserve their intrinsic aspect ratio. Their initial box is
centered and limited to 35% of the slide in its larger dimension; dropped
images use the drop point instead and are kept inside the slide. Images placed
in grid regions use the size of that region.

## Sections

Use the section button above the slide list to add a named boundary before the
current slide. A section groups that slide and the slides that follow it until the next
section. Use its disclosure arrow to collapse or expand those slides, click the
section name to select it, and use the ordinary up/down buttons to move the
boundary. A collapsed section shows its number of slides in parentheses beside
its name. Double-click its name to rename it. The delete button removes only the
section marker and leaves its slides intact.

Sections organize the editor only; they are not displayed during the
presentation or static export. Their names and stable IDs remain visible in the
Markdown source as `.section` headings.

## Slide Trash

The slide toolbar trashcan moves the selected slide to a collapsible Trash
section at the end of the deck. Trashed slides remain available in Design and
Source modes, but Present mode and static exports omit them. Select a trashed
slide to restore it or delete it permanently. A restored slide returns to the
end of the active deck, where it can be reordered normally. Undo can reverse
these actions during the current editing session, and Quarkfoil will not trash
the final active slide. Select the Trash section itself and use the trashcan to
empty it after confirming permanent deletion. The Trash section disappears
when it becomes empty.

## Shapes

Hover over, focus, or click the shape button in Design mode to open its palette,
then choose a shape icon to insert it. The palette includes rectangles,
ellipses, a circle, diamond, hexagon, cross, X, five-pointed star, thought cloud,
comic callout, and a parameterized arc. Its
monochrome previews use the same geometry as the inserted shapes. The arrow has
its own adjacent toolbar button because it is an endpoint-based object. Drag
either endpoint handle to change its direction or length, and drag the line to
move the whole arrow. Its Properties select the line color, width, and solid,
dash, dash-dot, or dotted style, plus whether the start, end, both, or neither
endpoint has an arrowhead. Use the
plot tool to create spline-interpolated SVG graphs from mathematical expressions.

The plot dialog accepts one or two JavaScript-style expressions. Leave the
second expression empty for an ordinary `Y = f(x)` graph. Fill both expression
areas for a parametric `(X(t), Y(t))` curve. The start and end values define the
domain of `x` or `t`, and the point count controls sampling. The dialog previews
a cubic spline through the samples. Enable axes for a padded plot with horizontal and
vertical axes, or disable them to make the curve occupy the full SVG viewport
without padding. Choose the SVG filename before creating the plot; Quarkfoil saves
the generated file in the configured figures folder and inserts it as an ordinary
image.
Generated plots default to Stretch fitting, so resizing behaves like resizing a
shape. When a generated plot is selected, its Properties also expose background
color, an optional filled area between the curve and the zero baseline, curve
color, and line width. These controls edit the SVG asset itself, so every slide
that references the same plot file updates together.
Uploads show a destination dialog before writing. Change the proposed filename,
cancel the import, or explicitly enable overwrite when replacing an existing
presentation, image, video, or generated plot.

Shapes resize and move like other overlays. Their Properties include the
template, background color, line color, line width, line style, and an optional shadow.
Selecting the arc reveals start and end angles, measured clockwise from the
right, and optional arrowheads at either or both ends. Equal angles make a
complete circle.
Rectangle, cross, star, and arc shapes start with a visual 1:1 aspect ratio; resizing
them remains unrestricted.
Default-valued styles are omitted from the Markdown source. Double-click a
shape to edit its label as Markdown or LaTeX; the label is rendered
independently of the SVG background so equations use the same KaTeX renderer as
the rest of the presentation.

Shapes without explicit background or line colors inherit those colors from
the active presentation theme. Selecting a specific color creates a fixed
override in the Markdown source. Set the background alpha to zero to remove the
visible shape surface while retaining its outline and label.

## Saving and recovery

The Save button and `Ctrl+S` write the Markdown file. Unsaved changes are
identified in the toolbar. Local-server saves require the revision hash loaded
by the browser and use an atomic replacement to avoid partial files.

Before writing, Quarkfoil normalizes the document structure. It removes grid
regions unused by their slide layout, limits top-level Markdown to one empty
line between objects, and writes one empty line around slide and section
separators. Content inside `:::` directives—including overlays, grid regions,
notes, and footers—is preserved verbatim. Normalization is idempotent, so
repeated saves do not introduce further formatting changes.

### External editors and coding agents

In local-server mode, Quarkfoil monitors the open presentation for external
Markdown edits. A valid external change reloads automatically when the browser
has no unsaved work. Quarkfoil preserves the current slide by its stable ID when
possible, so inserted or reordered slides do not unnecessarily move the view.

If both revisions contain work, saving is blocked and a persistent **Changed on
disk** warning appears. **Review** shows the browser draft, the current disk
version, and an editable merged result. You can download the browser draft,
discard it in favor of a valid disk version, or apply valid merged Markdown and
then save it against the external revision. Closing the comparison does not
dismiss the conflict or enable saving.

Invalid external Markdown never replaces the last valid presentation. It is
shown in the comparison for repair, while direct loading of that disk version
remains disabled. External tools should finish writes with an atomic replacement
and should not modify the file during the brief moment Quarkfoil itself is
saving. This workflow supports safe external editing and explicit reconciliation;
it does not silently merge simultaneous changes.

The browser also keeps recovery snapshots in IndexedDB. These snapshots supplement the Markdown file; they are not a substitute for version control or backups.

## Bibliography

The Bibliography toolbar button opens a searchable reference list and complete
BibTeX source. The source is saved losslessly to the file selected by
`bibliography` in front matter, or `references.bib` by default. Saves are
atomic and reject external conflicts.

Each time the Bibliography button is opened, Quarkfoil reloads that file and
its revision from disk before showing the dialog. Presentations that share a
bibliography therefore start each editing session from the latest saved copy;
simultaneous edits after both dialogs are open are still protected by the
save-time conflict check.

Enter a DOI and choose **Add DOI** to retrieve BibTeX metadata. Quarkfoil shows
a preview before appending it to the draft and rejects duplicate DOIs. If a
different entry would use an existing citation key, Quarkfoil adds a conventional
alphabetic suffix such as `smith2024a` before showing the preview.
After confirmation, DOI imports are formatted and the complete draft is sorted
alphabetically by citation key. **Reformat** applies the same canonical multiline
format and sorting to entries edited or pasted by hand. Because rewriting cannot
safely preserve every BibTeX extension, Reformat refuses `%` comments and
`@comment`, `@preamble`, or `@string` directives instead of silently discarding
them. **Close**, `Escape`, **Insert [n]**, and **Add attribution** save the
current valid bibliography automatically. A parse error or external-file
conflict leaves the dialog open so the draft can be repaired or reconciled.
Pressing `Enter` in the DOI field performs the same Add DOI action and keeps the
dialog open. Pressing `Enter` in the reference search field leaves the current
filter in place and does not submit or close the dialog. After a DOI is added,
the reference filter is cleared and the list scrolls to the new entry.
Imported citation keys use the lowercase first-author family name followed by
the four-digit year, such as `wallraff2004`. Latin accents are stripped for
portable ASCII keys, so Peñas becomes `penas`. DOI lookup is the only
bibliography operation that requires the network.

**Insert [n]** saves the bibliography and inserts an inline citation at the
Source editor caret. **Add attribution** saves it and then creates a positioned,
resizable brief reference for crediting a copied figure. If the bibliography
cannot be saved, neither insertion happens and the dialog reports the error.
Select an attribution in Design mode to edit its reference keys and show one or
more papers. Its generated reference text is not directly editable.
Attributions do not display or consume citation numbers; inline citations keep
deck-wide numbering.

If an entry has a `file` or `pdf` field naming an existing PDF, its row also
shows a **PDF** button. Relative paths are resolved beside the bibliography.
Absolute paths are supported as well, including PDFs outside the presentation
directory. Quarkfoil exposes those files only through unguessable links derived
from the bibliography; ordinary project URLs remain confined to the selected
presentation directory. Brief attributions on slides show a small document
marker after the reference when an attached PDF is available; select it to open
the paper in a new tab.

## Keyboard shortcuts

- `Ctrl+S`: save.
- `Ctrl+Z`: undo.
- `Ctrl+Shift+Z`: redo.
- `Ctrl+B` / `Command+B`: toggle Markdown bold around the selection in Source,
  content, and speaker-notes editors.
- `Ctrl+I` / `Command+I`: toggle Markdown italic in those editors.
- `Ctrl+Enter`: accept a content-editing dialog.
- `Escape`: cancel a dialog, clear the Design selection, or leave Present mode.
- `Page Up` / `Page Down`: select the previous or next slide in Design mode.
- Arrow keys: nudge the selected overlay or group by `0.1%`.
- `Shift` + arrow keys: nudge the selected overlay or group by `1%`.
- `Delete`: delete a selected overlay.
- `Ctrl+D`: duplicate a selected overlay.
- `Ctrl+C` / `Ctrl+X`: copy or cut the selected overlay or group.
- `Ctrl+V`: paste copied overlays or a clipboard image in Design mode.

Copied overlays use readable `::: overlay` Markdown on the system clipboard.
They may be pasted onto another slide or another Quarkfoil window. Pasted
objects retain their content and styling, receive collision-safe IDs, move
slightly when pasted back onto the same slide, and become the active selection.
Pasting onto a different slide preserves their original positions.
