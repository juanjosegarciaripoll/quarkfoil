# Installation and command-line use

## Requirements

- Windows, macOS, or Linux.
- Python 3.11 or newer.
- A modern browser. Quarkfoil is primarily developed with Microsoft Edge and Chromium-compatible browsers.
- Optional: `ffmpeg` and `ffprobe` on `PATH` to import AVI and MKV video. MP4 and WebM imports do not require them.

No Node.js or npm installation is required.

## Desktop application

Quarkfoil has an unsigned desktop launcher for Linux, Windows, and macOS development
bundles. A frozen bundle includes Python and all editor assets, so the target
computer does not need Python or `uv`. Signed installers, notarized macOS
images, automatic updates, and public downloads are not available yet.

Double-click Quarkfoil, then open an existing `.md`/`.markdown` deck or choose
to create one. The small launcher window stays open while Quarkfoil serves the
deck to the default browser. **Open editor** reopens the same address and
**Quit** stops the local server. Opening a document from Finder or **Open
with** starts one application process and one project root for that document.

Development bundles are portable: extract the Linux directory and run
`Quarkfoil/Quarkfoil`, extract the Windows directory before running
`Quarkfoil.exe`, or copy `Quarkfoil.app` into `/Applications`. Remove that
directory or app to uninstall it. Because these prototypes are unsigned,
Windows SmartScreen or macOS Gatekeeper may refuse them; do not bypass an OS
warning for a bundle whose origin and checksum you have not verified. The
command-line `quarkfoil` program remains a separate `uv` installation.

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
--no-reload     Disable automatic server restarts
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
