# Installation and command-line use

## Requirements

- Windows, macOS, or Linux.
- Python 3.11 or newer.
- A modern browser. Quarkfoil's browser tests cover Safari on macOS, Microsoft
  Edge on Windows, and Firefox on Linux.
- Optional: `ffmpeg` and `ffprobe` on `PATH` to import AVI and MKV video. MP4 and WebM imports do not require them.

No Node.js or npm installation is required.

## Install with uv

Install a published release as an isolated command-line tool:

```console
uv tool install quarkfoil
```

Upgrade it later with:

```console
uv tool upgrade quarkfoil
```

For a local source checkout:

```console
uv tool install .
```

Use `--reinstall` after changing the local source:

```console
uv tool install --reinstall .
```

## Open a presentation

```console
quarkfoil path/to/deck.md
```

The deck path must end in `.md` or `.markdown`. If the file does not exist, or
exists but contains only whitespace, Quarkfoil initializes it with a minimal
front-page presentation. Its parent directory must already exist. A nonempty
file is never replaced during initialization. Quarkfoil grants the browser
access only to the directory containing that file.

Options:

```text
--host HOST     Address to bind; defaults to 127.0.0.1
--port PORT     Port to use; defaults to 8765; use 0 for an available port
--open          Open the browser automatically; this is the default
--no-open       Start the server without opening a browser
--verbose       Log individual HTTP requests; quiet by default
--reload        Restart after Quarkfoil Python files change; this is the default
--no-reload     Disable development source restarts; installed-tool replacement still restarts
```

With reloading enabled, changes to Quarkfoil's Python files restart the local
server with the same arguments. Changes to editor HTML, JavaScript, or CSS also
refresh an editor page when it next gains focus, becomes visible, or receives
keyboard or pointer input. Idle editor pages do not poll the server.
Presentation Markdown is monitored independently of application reloading.
Valid external edits load automatically while the browser is clean. If the
browser has unsaved edits, or the external Markdown is invalid, Quarkfoil blocks
saving and opens an explicit comparison and reconciliation workflow. Existing
figure files are not watched; reload the page after replacing an asset without
also changing its Markdown reference.

For example:

```console
quarkfoil lecture.md --open --port 9000
quarkfoil lecture.md --no-open --port 0
```

To start a new presentation directly:

```console
quarkfoil my-new-lecture.md
```

For a script or coding assistant that should initialize the presentation and
exit instead of starting the editor server:

```console
quarkfoil deck create my-new-lecture.md \
  --title "My new lecture" \
  --author "Ada Lovelace"
```

Run `quarkfoil deck guide` to discover the version-matched agent workflow and
its focused Markdown, layout, asset, citation, and authoring references.

Binding to a non-loopback address exposes the editor to the corresponding network. Do so only on a trusted network and after reviewing the security implications.

## Export a presentation website

Create a self-contained static site with:

```console
quarkfoil export lecture.md --output lecture-site
```

Add `--cdn` for a smaller, network-dependent export. See the
[static export guide](EXPORT.md) for the generated structure, deployment, and
security trade-offs.

## Print a presentation as a PDF

To hand a deck out as pages rather than as a website:

```console
quarkfoil print lecture.md
```

A headless Chrome, Chromium, Edge, or Firefox renders `lecture.pdf` with one
page per slide, each page the size of a slide rather than a sheet of A4. See
the [printing guide](PRINT.md).

## Copy a presentation project

To move or hand over a presentation you intend to keep editing, copy it with
its figures and bibliography into a new project folder:

```console
quarkfoil pack lecture.md --output ~/talks/cern-2026
```

The result is source, not a website, and opens like any other presentation.
See the [packing guide](PACK.md).

## Publish a talk to a website

To put a talk on a site where many of them live together, sharing one player
and one pool of figures behind a generated listing:

```console
quarkfoil publish lecture.md --site homepage:talks/
```

The destination is a local directory or an rsync destination. Several decks
can go up at once, and a `series` field folds a course into a single entry.
See the [publishing guide](PUBLISH.md).

## Which command produces what

Quarkfoil writes a presentation out in four ways, and they do not overlap:

| Command | Produces | Use it to |
|---|---|---|
| `quarkfoil export` | one self-contained folder, openable from the file system | hand a deck over, archive it, or deploy it on its own |
| `quarkfoil pack` | an editable project folder | move a presentation, or split one folder into one project per talk |
| `quarkfoil publish` | one talk inside a shared collection | build up a site of talks that share a runtime and their figures |
| `quarkfoil print` | one PDF file, one page per slide | hand out or archive the slides where a browser is not wanted |

`export` and `publish` both produce a website; the difference is whether the
deck stands alone or joins others. `pack` produces no website at all: its
output is source you go on editing. `print` produces neither: it is the deck
frozen into pages.

To let a coding assistant make safe, structured slide changes, follow
[Use Quarkfoil with an AI assistant](AGENT_CLI.md). No additional plugin or
service is required beyond an assistant that can run local terminal commands.

## Project structure

A presentation project is deliberately small:

```text
my-lecture/
├── presentation.md
└── figures/
    ├── apparatus.svg
    └── results.png
```

Imported images are copied into `figures/`, and the Markdown stores relative paths. The Quarkfoil application is installed separately.
