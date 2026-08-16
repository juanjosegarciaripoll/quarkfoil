# Export as a static website

Quarkfoil can turn a presentation project into a presentation-only website.
The exported site has no editor, Python server, saving API, or cloud
dependency and can be hosted by any ordinary static web server.

## Self-contained export

Local assets are the default and are recommended for teaching, archiving, and
reproducible deployments:

```console
quarkfoil export lecture.md --output lecture-site
```

The destination must not already exist. Quarkfoil creates it atomically and
copies the Markdown source, referenced project images, player files, pinned
browser libraries, fonts, and complete third-party notices.

When a referenced SVG was downloaded by the online icon picker, its collection
notice and full license text are appended to `THIRD_PARTY_LICENSES.txt`. Unused
icon records are omitted. No attribution is rendered on the slides.

The configured `assets.figures` directory and all directories listed under
`assets.include` in the YAML preface are copied recursively. See the
[format reference](FORMAT.md#asset-folders) for configuration and path rules.

```text
lecture-site/
├── index.html
├── presentation.md
├── figures/
├── THIRD_PARTY_LICENSES.txt
└── quarkfoil/
    ├── player.js
    ├── parser.js
    ├── render.js
    ├── layout.css
    ├── themes.css
    └── vendor/
```

Upload that directory unchanged to GitHub Pages, CERN web hosting, Apache,
nginx, or another static host.

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

## Preview locally

Exported presentations must be served over HTTP because browsers normally
block module and Markdown loading from `file://` pages. One simple preview
server is:

```console
python -m http.server --directory lecture-site
```

Then open `http://127.0.0.1:8000/`. Reveal.js keyboard, touch, overview,
fragments, URL hashes, and speaker notes remain available.

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
