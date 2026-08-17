# Changelog

All notable changes to Quarkfoil are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

- Export deck metadata directly in static HTML and optionally create a
  link-sharing preview by capturing the first slide in a headless browser.
- Copy only referenced files from `assets.figures` during static export while
  retaining complete directories explicitly listed under `assets.include`.

## [0.4.0] - 2026-08-16

This release strengthens day-to-day editing and recovery, expands diagram and
plot creation, and adds an offline-safe workflow for reusable open-source icons.

### Added

- Move unwanted slides to a collapsible Trash section, restore them later, or
  empty the trash with confirmation. Trashed slides remain in readable Markdown
  but are omitted from presentations.
- Create parameterized arc shapes with editable start and end angles and
  optional arrowheads. New arcs start with a 1:1 aspect ratio.
- Generate two-dimensional parametric SVG plots from separate `X(t)` and `Y(t)`
  expressions in the existing plot dialog.
- Apply global opacity to raster and SVG images without modifying the source
  asset or its own alpha channel.
- Search allowlisted Material Symbols, Tabler Icons, and IconPark collections
  through Iconify. Imported SVGs are stored locally, reused without downloading
  when already present, and never require a network connection during playback.
- Track imported-icon provenance outside the slide source and merge the notices
  and complete Apache 2.0 or MIT license text into exported
  `THIRD_PARTY_LICENSES.txt` files.
- Open relative, absolute, and Zotero-style bibliography PDF attachments from
  the bibliography editor and from brief slide attributions.
- Add cross, X, and star diagram shapes plus solid, dashed, dash-dot, and dotted
  line styles for shapes and arrows.
- Toggle Markdown bold and italic with `Ctrl+B`/`Command+B` and
  `Ctrl+I`/`Command+I` in Source, content, and speaker-notes editors. Escape now
  also clears the active Design selection.
- Run the browser integration suite with Safari on macOS in CI.

### Changed

- Keep static export independent of the editor server: export-only commands no
  longer load source monitoring, browser launch, or restart machinery.
- Preserve the selected slide in the URL and restore it after a page reload.
- Preserve existing slide content more reliably when changing layouts and allow
  slides to move naturally across section boundaries.
- Define label-safe regions alongside each shape's SVG geometry and support
  centered multiline Markdown labels without changing horizontal alignment.
- Use deck metadata for the browser-window title.
- Keep bibliography drafts synchronized with files changed outside the editor.
- Fit the slide-list controls and content-editing dialogs within their available
  width and height, including compact windows.

### Fixed

- Keep a running Quarkfoil process alive across forced `uv tool` reinstalls by
  waiting for installed files to stabilize and restarting through a valid
  launcher when the original interpreter has been replaced.
- Keep cross-window clipboard operations and textarea undo/redo isolated from
  Quarkfoil's structural history, with consistent behavior across browsers and
  operating systems.
- Render Markdown fragments correctly when bold text immediately precedes a
  fragment annotation.
- Keep shape labels vertically centered when they contain multiple paragraphs.
- Preserve the same slide-edge insets in PDF exports as in presentation mode,
  despite Reveal's print-specific section reset, and retain assets assigned to
  negative layers when Reveal removes its normal slide transform.
- Resolve macOS temporary-directory aliases consistently when locating
  bibliography attachments.
- Make repeated Markdown formatting shortcuts toggle reliably in Safari.

## [0.3.0] - 2026-08-12

This release expands direct manipulation, media handling, plotting, and
bibliography workflows while preserving compatibility with earlier decks.

### Added

- Cut, copy, and paste selected overlays and multi-object selections through
  the system clipboard using readable Quarkfoil Markdown. Cross-slide pastes
  preserve positions, while same-slide copies receive a visible offset.
- Select, move, duplicate, and delete multiple slide objects together.
- Create editable arrows with configurable endpoints, arrowheads, color, and
  line width.
- Generate SVG plot assets from mathematical expressions and style their fill,
  curve color, and line width.
- Organize slides into collapsible sections, with slide counts shown when a
  section is folded.
- Reveal Markdown headings, paragraphs, and list items progressively using
  explicit fragment indices.
- Edit optional Reveal speaker notes in a resizable pane below the Design-mode
  slide canvas.

### Changed

- Unified project browsing for presentations, images, and videos; paginated
  large media galleries and added explicit rename or overwrite handling for
  import collisions.
- Improved video imports by reusing compatible streams when possible and
  reporting conversion progress for media that requires optimization.
- Streamlined bibliography editing, consistently formatted and sorted entries,
  refreshed shared bibliography changes before editing, and exposed newly
  retrieved DOI references immediately.
- Normalize presentation source when saving while preserving intentional extra
  Markdown spacing and fenced-code content.
- Added editable numeric values beside sliders, opacity controls for colors,
  a visual shape palette, and Page Up/Page Down slide navigation in the editor.
- Normalized slide typography and increased table text size for readability.
- Run the browser self-test in Firefox as well as Microsoft Edge.

### Fixed

- Keep the slide visible at full brightness while editing a color.
- Decode standard LaTeX accents and Latin letter commands when displaying
  BibTeX authors, titles, and other fields.
- Include the thesis type and institution in abbreviated thesis attributions.
- Prevent Enter in Properties fields from submitting their surrounding forms
  and use it to commit the active value instead. Edit colors and opacity in a
  compact, movable confirmation dialog so native color browsing never mutates
  or closes slides.
- Detect and reconcile presentation changes made outside the editor without
  silently replacing either the browser draft or the disk revision.
- Keep image focus effective for width- and height-fitted images, and add a
  stretch fitting mode when deliberate distortion is required.
- Preserve reliable single-click cell selection and correct slide rendering in
  Reveal's overview mode.
- Pause video playback when returning to Design mode or leaving its slide.
- Keep attribution links usable in Design mode, render abbreviated
  attributions without an unwanted panel, and repair DOI bibliography imports.
- Render thick arrowheads correctly and avoid partial or unintended overwrites
  when importing project files.
- Separate generated-plot background color from a fillable area between the
  curve and the zero baseline, keep both color pickers available, and support
  alpha channels for the background, area, and curve colors.
- Empty selected Markdown layout regions and remove other selected canvas
  objects with Delete, Del, or the Backspace value used by compact keyboards.
- Return keyboard focus to the Design canvas when selecting an object or region
  so arrow-key movement works after editing a value in Properties.
- Refresh unsaved state as soon as presentation Markdown changes, including
  slide reordering, and treat an active speaker-notes draft as needing a save.
- Keep presentation opening and conflict-checking server tests byte-stable
  across Windows and POSIX newline conventions.

## [0.2.0] - 2026-08-09

This release remains compatible with presentations created by 0.1.0 while
substantially expanding visual editing and scientific-presentation support.

### Added

- Paste images directly from the clipboard, choose their filenames, and
  replace a selected image by pasting. Preserve JPEG and GIF representations
  when the browser provides the original file rather than synthesized PNG.
- Import images at a size derived from their intrinsic aspect ratio and replace
  them either by uploading a file or choosing one already in the presentation.
- Create scalable rectangle, rounded rectangle, ellipse, circle, diamond,
  hexagon, cloud, comic callout, sine, and cosine shapes. Shape labels support
  Markdown and equations; fill, line, width, and optional shadow are editable.
- Maintain a BibTeX bibliography, retrieve BibTeX by DOI, insert numbered
  citations in Markdown, and add standalone numbered or abbreviated figure
  attributions without an inline citation.
- Choose a theme per slide and override slide foreground and background colors.
- Set or reset the text color of floating Markdown, equations, citations, and
  shape labels independently of the slide theme.
- Add local MP4 and WebM video objects with native controls, autoplay, loop,
  mute, poster, fitting, replacement, project selection, and byte-range serving
  for playback and seeking. Videos pause when their slide is left.
- Automatically restart the development server after Python changes and reload
  editor assets on the next page interaction, focus, or visibility change.

### Changed

- Split application, layout, and theme styling responsibilities. Theme colors
  now provide shape defaults, while the surrounding editor canvas consistently
  uses the darker application palette.
- Expanded the example presentation to demonstrate recent features and improved
  the default styling of tables.
- Made request logging quiet by default; `--verbose` restores individual HTTP
  request messages.
- Exposed real heading Markdown in the structured title editor while preserving
  hidden slide annotations.

### Fixed

- Allow direct editing of cells in asymmetric `1+1`, `1+2`, and `2+1` layouts.
- Preserve multiple title lines, heading levels, and spacing without leaking
  structural directive markers into the editor.
- Preserve line breaks and paragraph spacing from positioned text and shape-label
  editors in the rendered slide.
- Avoid unnecessary default-valued shape annotations in presentation source.

## [0.1.0] - 2026-08-08

- Initial release of the local Markdown presentation editor, Reveal.js player,
  static exporter, scientific layouts, image objects, equations, documentation,
  packaging, and CI workflow.

[Unreleased]: https://github.com/juanjosegarciaripoll/quarkfoil/compare/0.4.0...HEAD
[0.4.0]: https://github.com/juanjosegarciaripoll/quarkfoil/compare/0.3.0...0.4.0
[0.3.0]: https://github.com/juanjosegarciaripoll/quarkfoil/compare/0.2.0...0.3.0
[0.2.0]: https://github.com/juanjosegarciaripoll/quarkfoil/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/juanjosegarciaripoll/quarkfoil/releases/tag/0.1.0
