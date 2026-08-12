# Changelog

All notable changes to Quarkfoil are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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

- Detect and reconcile presentation changes made outside the editor without
  silently replacing either the browser draft or the disk revision.
- Keep image focus effective for width- and height-fitted images, and add a
  stretch fitting mode when deliberate distortion is required.
- Preserve reliable single-click cell selection and correct slide rendering in
  Reveal's overview mode.
- Keep attribution links usable in Design mode, render abbreviated
  attributions without an unwanted panel, and repair DOI bibliography imports.
- Render thick arrowheads correctly and avoid partial or unintended overwrites
  when importing project files.
- Separate generated-plot background color from a fillable area between the
  curve and the zero baseline, keep both color pickers available, and support
  alpha channels for the background, area, and curve colors.
- Empty selected Markdown layout regions and remove other selected canvas
  objects with Delete, Del, or the Backspace value used by compact keyboards.

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

[0.2.0]: https://github.com/juanjosegarciaripoll/quarkfoil/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/juanjosegarciaripoll/quarkfoil/releases/tag/v0.1.0
[Unreleased]: https://github.com/juanjosegarciaripoll/quarkfoil/compare/v0.2.0...HEAD
