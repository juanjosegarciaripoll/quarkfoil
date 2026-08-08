# Installation and command-line use

## Requirements

- Windows, macOS, or Linux.
- Python 3.11 or newer.
- A modern browser. Quarkfoil is primarily developed with Microsoft Edge and Chromium-compatible browsers.

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
```

For example:

```console
quarkfoil lecture.md --open --port 9000
quarkfoil lecture.md --no-open --port 0
```

To start a new presentation directly:

```console
quarkfoil my-new-lecture.md
```

Binding to a non-loopback address exposes the editor to the corresponding network. Do so only on a trusted network and after reviewing the security implications.

## Export a presentation website

Create a self-contained static site with:

```console
quarkfoil export lecture.md --output lecture-site
```

Add `--cdn` for a smaller, network-dependent export. See the
[static export guide](EXPORT.md) for the generated structure, deployment, and
security trade-offs.

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
