# Changelog

All notable changes to Quarkfoil are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Add `quarkfoil download URL --output DIRECTORY` to reconstruct a published
  talk as an editable project without changing the website. It restores pooled
  and private assets to the paths written in the Markdown, remembers the
  original source file name for new publications, falls back to the talk slug
  for older ones, stages atomically, rejects unsafe paths and off-origin asset
  redirects, and protects differing destination files unless `--force` is
  given.

- Publish canonical URLs and Open Graph/Twitter cards for talk collections.
  `--site-url` stores the collection's public URL in `collection.json`; every
  published talk then gets absolute canonical and image metadata. By default
  Quarkfoil captures the Front page slide without cropping on a
  content-addressed 1200x630 PNG canvas.
  Deck metadata may instead select a stable slide ID or a project-relative
  figure through `social.slide` or `social.image`, with `social.alt` supplying
  accessible image text. The `quarkfoil deck` metadata and publishing guides
  document the guarded syntax.

- Add guarded front-matter editing to the agent interface. `quarkfoil deck
  inspect DECK --format metadata --output FILE` creates an editable metadata
  document that `deck apply --edit FILE` validates and applies atomically.
  Unknown fields and comments remain editable, invalid YAML or stale revisions
  change nothing, and slide source is preserved byte-for-byte.

- Expand `quarkfoil deck guide` into a self-teaching, version-matched reference
  with focused topics for the guarded workflow, Markdown format, layouts,
  overlays, assets, citations, collection publishing, authoring, source
  reconstruction, and canonical examples. The publishing guide documents
  required metadata, local and rsync-over-SSH targets, dry runs, and the
  external mapping from a remote directory to its public URL. The reconstruction
  guide resolves effective pixel sizes, documents
  image-only cells and overlay line breaks, distinguishes the two gridless
  layouts, derives overlay geometry, and makes rendered-page inspection part
  of whole-deck authoring. `--all`
  prints the complete reference when context size is not a concern. Add
  `quarkfoil deck create DECK` to initialize a missing or whitespace-only
  presentation without starting the browser server; optional title, author,
  and theme fields customize the starter, while nonempty files are never
  replaced.

- `quarkfoil print DECK` renders a presentation to PDF with one page per
  slide. Quarkfoil exports the deck to a temporary website, serves it on a
  loopback port, and drives a headless Chrome, Chromium, Edge, or Firefox,
  preferring Chromium and falling back to Firefox; `--browser` names another
  one. Every page is the size of a slide, 13.33 x 7.5 in, rather than the
  paper the browser's print dialog was last set to: Chromium takes the size
  from the presentation, and Firefox is given it through the throwaway profile
  it prints with. The PDF is written beside its destination and renamed into
  place, so an existing file is replaced whole or not at all. `--output` names
  the file, which defaults to the deck's name with a `.pdf` suffix, and
  `--timeout` covers a very large deck. Speaker notes are left out.
  Chrome and Edge are now also discovered in their usual Windows locations,
  which `export --preview` uses too.

- `quarkfoil publish DECK --site TARGET` publishes a talk into a collection
  that shares one player runtime and one content-addressed asset pool, with a
  static listing page grouped by year, newest first. Identical figures are
  stored once however many talks use them, while two different files with the
  same name never collide. The deck's Markdown is published unchanged; the page
  carries a map from its paths to the pool. `--site` takes a local directory or
  an rsync destination such as `homepage:talks/`, in which case the pool is
  pushed append-only and only the talk's own folder is mirrored. New front
  matter: `date` (required to publish), `event`, and `unlisted`.
  Speaker notes are left out of a published deck unless `--notes` is given.
  A `series` field folds a course into a single listing card linking to its
  own generated page, ordered by `part` or by date, described once through
  `series-description`. Several decks can be published in one command, staging
  them together so shared assets are sent once and the listing rebuilt once.

- `quarkfoil pack DECK --output DIRECTORY` copies a presentation, its
  referenced figures, its bibliography, and its `assets.include` folders into a
  separate project folder that stays editable. The copy keeps the deck's own
  file name and contains no player, browser library, or `index.html`, so it
  opens in the editor like any other presentation. `--no-notes` and
  `--trim-bibliography` work as in `export`, an existing destination is reused
  with unrelated files kept, and a destination file that differs is reported as
  a conflict rather than overwritten unless `--force` is given.

### Fixed

- Link eprint-only arXiv citations to their abstract pages, including
  `arxiv:`-prefixed and old-style archive identifiers. ArXiv DOIs now resolve
  directly to the same pages, while ordinary journal DOI links remain
  authoritative.

- Remove ordinary `%` comment lines while canonically reformatting a bibliography,
  so importing a DOI succeeds when the existing BibTeX file contains comments.
  Structural `@comment`, `@preamble`, and `@string` directives remain explicit
  errors because flattening them could change entry values.

- Keep the arXiv identifier in a brief reference when its BibTeX entry also has
  the corresponding `10.48550/arXiv.…` DOI. Journal DOI references continue to
  omit a redundant preprint identifier.

- Quote `aspect-ratio: "16:9"` in generated starter presentations and format
  examples so Python-side deck inspection retains the ratio as a string instead
  of interpreting YAML 1.1 sexagesimal notation as the integer `969`.

- Open exported presentations directly from the file system. The exported
  player is now one classic script rather than ES modules, and `index.html`
  embeds the deck and bibliography, so double-clicking `index.html` works in
  browsers that refuse module loading and `fetch` on `file://` pages. Serving
  the export over HTTP is unchanged: the player still reads `presentation.md`
  and the bibliography from the server and only falls back to the embedded
  copy when there is no server to ask.

### Changed

- Reduce an ordinary remote publication to three rsync/SSH sessions: one
  combined collection-state read, one append-only shared-assets upload, and
  one batched update for the talk folders, listing, collection settings, and
  series pages. The batched delete remains scoped to explicitly named
  directories and cannot remove unrelated talks or root files.

- Define the presentation Markdown as opaque in the installed agent guide and
  machine-readable deck protocol. Agents must read through `deck inspect`,
  write through `deck apply`, and restrict generic text or patch tools to the
  generated, revision-guarded edit documents. The recommended workflow now
  uses `inspect --output` instead of shell redirection. Keep the mandatory
  guide concise by moving detailed operation schemas into an opt-in
  `deck guide operations` topic.

- Reuse an existing `--output` directory when exporting. Quarkfoil still builds
  the site in a temporary sibling folder and publishes it only after a complete
  export, but it now writes into a directory that already exists instead of
  refusing to run. Exported files replace the previous export, unrelated files
  in the folder are kept, and an existing file at the destination is still
  never overwritten.

## [0.5.0] - 2026-08-19

This release introduces a revision-safe interface for coding agents and LLM
tools, expands presentation delivery with PDF printing and presenter view, and
adds focused controls for slide styling, diagrams, export, and recovery.

### Added

- Add a first-class `quarkfoil deck` interface for coding agents and LLM tools.
  A concise built-in guide lets an assistant discover the workflow, inspect a
  presentation or selected slides, and safely apply structural edits without
  learning Quarkfoil's internal parser or modifying the deck file directly.
- Make guarded YAML-plus-Markdown edit documents the preferred agent format.
  Literal Markdown and LaTeX remain readable and unescaped while agents replace,
  insert, delete, move, or make exact substitutions within slides. Multiple
  ordered edit documents apply as one validated, atomic write and return concise
  YAML receipts.
- Guard every agent transaction with a whole-deck SHA-256 revision and every
  addressed slide with its own source fingerprint. Quarkfoil validates edits
  while holding the deck lock, reports stale revisions and failed assumptions
  as structured errors, and leaves the presentation byte-for-byte unchanged
  when any operation fails.
- Add readable multi-slide Markdown projections, strict YAML headers and literal
  substitution blocks, external Markdown files for complex slide sources, and
  `--no-notes` inspection that keeps private speaker notes out of agent context
  while preserving them during replacement.
- Retain the versioned JSON protocol for existing tool integrations, including
  machine-readable capabilities, slide projections, sequential structural
  operations, dry runs, compact output, and per-operation result mappings.
- Reject agent operations when malformed fences make slide boundaries
  unreliable, using the same presentation rules in the Python inspection layer
  and the browser's canonical parser.
- Print presentations as properly paginated PDFs through Reveal.js, with
  print-specific layout that preserves slide geometry and local assets.
- Open an automated Reveal.js presenter view with current/next-slide previews,
  speaker notes, timing, and synchronization with the editor window.
- Jump directly to the first or last slide with keyboard shortcuts, and keep the
  current slide encoded in the browser URL for reliable reloads and navigation.
- Control footer visibility independently on each slide and adjust text size for
  structured slide panels from the Design properties.
- Add left brace, right brace, and triangle diagram shapes, plus rotation for
  overlays and shapes.
- Export deck metadata directly in static HTML and optionally create a
  link-sharing preview by capturing the first slide in a headless browser.
- Omit speaker notes from static exports with `--no-notes`.
- Add Quarkfoil application icons to the packaged editor and project README.

### Changed

- Copy only referenced files from `assets.figures` during static export while
  retaining complete directories explicitly listed under `assets.include`.
- Merge non-overlapping slide edits made in the browser and on disk, and present
  slide-aware choices when both versions changed the same content.
- Capture link-sharing previews directly from the static player without keeping
  an editor server or browser-launch machinery running.
- Improve toolbar grouping and sizing so the editor controls remain usable in
  compact windows.
- Prompt before overwriting an existing destination when importing a converted
  video, and refresh generated video poster images when source media changes.

### Fixed

- Keep slide-import galleries tall when their search controls are hidden, and
  keep file-conflict actions visible within compact browser windows.
- Keep the presentation player responsive while optional resources initialize.
- Keep resize handles reachable for media placed at slide edges and preserve
  transparent video backgrounds in the editor and player.
- Keep a running installed Quarkfoil process alive when `uv tool` replaces its
  environment by waiting for files to stabilize and restarting through a valid
  launcher.

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
