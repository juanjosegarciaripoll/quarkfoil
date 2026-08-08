# Quarkfoil

Quarkfoil is a local, browser-based editor for scientific presentations written in Markdown. It combines structured slide layouts with freely positioned Markdown, LaTeX, and image objects, and presents the result with Reveal.js.

**[Read the illustrated documentation](https://juanjosegarciaripoll.github.io/quarkfoil/)**
· **[View the live sample presentation](https://juanjosegarciaripoll.github.io/quarkfoil/example/)**

[![Quarkfoil editing the included example presentation](docs/assets/editor-overview.png)](https://juanjosegarciaripoll.github.io/quarkfoil/)

The presentation remains a readable Markdown file accompanied by a `figures/` directory. Quarkfoil itself is installed once; its application files are not copied into every presentation project.

## Highlights

- Seven layouts: `1`, `1+1`, `1+2`, `2+1`, `0`, Front page, and Free canvas.
- Markdown and KaTeX equations remain editable rather than becoming screenshots.
- Image fit, crop focus, overlay position, size, typography, alignment, and fragments are editable graphically.
- Source, Design, and Present modes use the same Markdown source of truth.
- Local assets and pinned browser libraries require no runtime CDN or Node/npm toolchain.
- Presentations export as self-contained static websites, with an optional pinned-CDN mode.
- Saves are atomic, conflict-checked, and restricted to the selected presentation directory.

## Install

Quarkfoil requires Python 3.11 or newer. The recommended installation uses [uv](https://docs.astral.sh/uv/):

```powershell
uv tool install quarkfoil
```

Until a package is published, install from a local checkout:

```powershell
uv tool install .
```

Run a presentation with:

```powershell
quarkfoil path\to\presentation.md
```

Quarkfoil opens a local address such as `http://127.0.0.1:8765/`. Stop the server with `Ctrl+C` in its terminal.

## Try the included example

From a source checkout:

```powershell
uv run quarkfoil example\deck.md
```

The [`example/`](example/) directory is also a template for new presentation projects.

## Export a static website

```powershell
quarkfoil export path\to\presentation.md --output presentation-site
```

The generated folder can be served by GitHub Pages or any ordinary static web
server. Add `--cdn` to reference exact, integrity-checked jsDelivr packages
instead of copying the browser libraries. See the
[export guide](docs/EXPORT.md) for details.

## Documentation

- [Installation and command-line use](docs/INSTALLATION.md)
- [Editor guide](docs/USER_GUIDE.md)
- [Markdown format reference](docs/FORMAT.md)
- [Security and trust model](docs/SECURITY.md)
- [Development and release guide](docs/DEVELOPMENT.md)
- [Third-party components and licenses](THIRD_PARTY_LICENSES.md)

## Licenses

Quarkfoil itself is released under the [MIT License](LICENSE).

Quarkfoil includes pinned, locally served copies of the following permissively
licensed components. Their complete license texts are kept in the repository
and included in distributed packages:

- [Reveal.js 5.2.1 — MIT](app/vendor/reveal/LICENSE)
- [KaTeX 0.16.22, including its distributed fonts — MIT](app/vendor/katex/LICENSE)
- [Marked 15.0.12 — MIT and BSD-3-Clause notices](app/vendor/marked/LICENSE.md)
- [js-yaml 4.1.0 — MIT](app/vendor/yaml/LICENSE)

Versions, copyright holders, source checksums, and redistribution details are
listed in the [complete third-party licensing notice](THIRD_PARTY_LICENSES.md).
