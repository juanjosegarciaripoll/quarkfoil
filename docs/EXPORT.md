# Export as a static website

Quarkfoil can turn a presentation project into a presentation-only website.
The exported site has no editor, Python server, saving API, or cloud
dependency and can be hosted by any ordinary static web server.

To copy a presentation into another folder and go on editing it there, use
[`quarkfoil pack`](PACK.md) instead.

## Self-contained export

Local assets are the default and are recommended for teaching, archiving, and
reproducible deployments:

```console
quarkfoil export lecture.md --output lecture-site
```

Quarkfoil builds the site in a temporary sibling folder and publishes it only
after a complete, successful export. It copies the Markdown source, referenced
project images, player files, pinned browser libraries, fonts, and complete
third-party notices.

An existing destination directory is reused: exported files replace the entries
of the previous export, and unrelated files already in the folder, such as
`CNAME`, `.nojekyll`, or an extra deployment script, are kept. Files that a
former export wrote but the current one no longer produces are also kept, so
delete the folder first when you want a pristine site. The destination may not
be an existing file.

When a referenced SVG was downloaded by the online icon picker, its collection
notice and full license text are appended to `THIRD_PARTY_LICENSES.txt`. Unused
icon records are omitted. No attribution is rendered on the slides.

Only referenced files from `assets.figures` are copied. Directories listed
under `assets.include` in the YAML preface are copied recursively, making that
the explicit mechanism for preserving a folder wholesale. Referenced local
files outside the figure directory are also copied individually. See the
[format reference](FORMAT.md#asset-folders) for configuration and path rules.

```text
lecture-site/
├── index.html
├── presentation.md
├── figures/
├── THIRD_PARTY_LICENSES.txt
└── quarkfoil/
    ├── player.js
    ├── layout.css
    ├── themes.css
    ├── player.css
    └── vendor/
```

`quarkfoil/player.js` is the editor's own `parser.js`, `render.js`, and player
modules combined into a single classic script.

Upload that directory unchanged to GitHub Pages, CERN web hosting, Apache,
nginx, or another static host.

## Trim the bibliography

The bibliography configured in front matter is copied in full by default.
To export only entries used by the presentation:

```console
quarkfoil export lecture.md --output lecture-site --trim-bibliography
```

This includes inline citations (`[@key]`, `[@first; @second]`) and citation
overlays, including brief attributions. Citations inside code or escaped with
a backslash are ignored. References in speaker notes are retained unless
`--no-notes` is also supplied. With no citations, all ordinary entries are
removed.

Retained entries keep their original fields, formatting, and order. Entries
referenced by literal keys in `crossref`, `xref`, or `xdata` are retained recursively;
comments, `@string`, and `@preamble` directives are preserved. This option
does not remove fields such as local attachment paths from retained entries.
Dependency keys expressed using BibTeX macros or concatenation are not resolved.
Malformed BibTeX record boundaries abort the export.

Trimming changes only the exported bibliography, including when its directory
is listed in `assets.include`. The original bibliography is untouched. The
option works with both local and CDN exports and has no effect when no
bibliography is configured.

## Compact CDN export

To reference pinned packages on jsDelivr instead of copying the browser
libraries:

```console
quarkfoil export lecture.md --output lecture-site --cdn
```

This is equivalent to `--assets cdn`. Exact versions and Subresource Integrity
hashes are written into `index.html`; the Content Security Policy permits only
the selected CDN. KaTeX fonts are loaded from the same pinned package.

!!! warning "Network and privacy trade-off"
    CDN presentations require internet access. Each visitor's browser connects
    to `cdn.jsdelivr.net`, exposing normal request metadata to that service.
    Use the default local export when offline operation, privacy, or long-term
    reproducibility matters.

Both modes retain `THIRD_PARTY_LICENSES.txt`. CDN mode changes where executable
dependencies are fetched; it does not remove their notices.

## Open it locally

An export opens by double-clicking `lecture-site/index.html`, with no web
server: the player ships as one ordinary script instead of ES modules, which
browsers refuse to load from `file://` pages, and `index.html` carries a copy
of the deck and its bibliography because those pages cannot fetch neighbouring
files either. Use a `local` export for this; a `--cdn` export still needs the
network for its libraries.

Serving the folder over HTTP works exactly as before and stays the right way
to share it. Over HTTP the player reads `presentation.md` and the bibliography
from the server, so editing those files in an exported site keeps working; the
embedded copy is only the fallback for `file://`. One simple preview server is:

```console
python -m http.server --directory lecture-site
```

Then open `http://127.0.0.1:8000/`. Reveal.js keyboard, touch, overview,
fragments, URL hashes, and speaker notes remain available. To publish without
speaker notes, add `--no-notes`; this removes the notes from the exported
`presentation.md` rather than merely hiding them in the player:

```console
quarkfoil export lecture.md --output lecture-site --no-notes
```

## Link-sharing preview

Add `--preview` to create a PNG suitable for services that inspect Open Graph
or Twitter card metadata:

```console
quarkfoil export lecture.md --output lecture-site --preview
```

Quarkfoil asks Chrome, Chromium, or Edge to capture the first slide directly at
1280 × 720 pixels. The browser runs headlessly, waits for the slide's fonts and
images, and hides presentation controls from the captured viewport. No PDF
renderer or image-conversion program is required.
For `lecture.md`, the resulting image is `figures/lecture-preview.png`, or the
equivalent location selected by `assets.figures`. Its reference in `index.html`
remains relative so the exported folder can be deployed at any URL.

The exported HTML also contains the presentation title, author, description
(or subtitle), and corresponding link-sharing metadata directly in its
`<head>`; crawlers do not need to run the presentation JavaScript to read it.

## Print or save as PDF

Use **Print / PDF** in an exported presentation, or press <kbd>Ctrl</kbd>+<kbd>P</kbd>
(<kbd>Command</kbd>+<kbd>P</kbd> on macOS). Quarkfoil reloads the presentation in
Reveal.js's PDF layout and opens the browser print dialog after fonts and images
are ready. Choose **Save as PDF** to create a multi-page file with one slide per
page.

Reveal.js recommends Chrome or another Chromium-based browser for PDF export;
other browsers may show the print layout but are not guaranteed to produce the
same PDF output.

The editor toolbar offers the same action when Quarkfoil is running through its
local server. It validates and saves the Markdown, then opens the deck in a
dedicated presentation-only print view equivalent to the static player.
Browser-only presentations opened through the file picker must instead be
run locally or exported as a static website, because reloading into print mode
would lose the browser's file handle.

## Live example

The [published sample presentation](https://juanjosegarciaripoll.github.io/quarkfoil/example/)
is regenerated with `--cdn` during every documentation deployment. It therefore
exercises the exporter and browser player from the same Quarkfoil revision as
the documentation site.
