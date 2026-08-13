# Development and release guide

## Repository structure

```text
app/                       Browser application and vendored assets
example/                   Example presentation project
src/scientific_slides/     Python launcher and local HTTP server
tests/                     Python server tests
tools/                     Dependency-vendoring utilities
docs/                      User and developer documentation
```

The internal Python module retains its historical name, `scientific_slides`; the distribution and command are `quarkfoil`.

## Run from source

```console
uv run quarkfoil example/deck.md
```

Run Python tests:

```console
uv run python -m unittest discover -s tests -v
```

Open the browser self-test while the example server is running:

```text
http://127.0.0.1:8765/selftest.html
```

## Documentation

The files under `docs/` are both the repository documentation and the source
of the public website. Preview them locally with:

```console
uv sync --group docs
uv run --no-sync mkdocs serve
```

Build with the same strict link and configuration checks used by continuous
integration:

```console
uv run --no-sync mkdocs build --strict
uv run --no-sync quarkfoil export example/deck.md --output site/example --cdn
```

Pushing documentation changes to `main` triggers the GitHub Pages workflow.
The workflow publishes both the documentation and this freshly exported live
example. The generated `site/` directory is disposable and is not committed.

## Continuous integration

The `CI` workflow runs for every push and pull request. It checks:

- Python 3.11 on Linux and Windows;
- the current Python release on Linux;
- the headless browser self-test in Firefox on Linux and Microsoft Edge on Windows;
- wheel and source-archive creation after all checks pass.

Distribution archives exist only inside the ephemeral CI runner and are not
uploaded or retained. Quarkfoil has no automated package-publication workflow.
The separate documentation workflow performs the strict site build, exports
the live example, and deploys GitHub Pages from `main` without duplicating
those tasks in CI.

CI also builds unsigned PyInstaller one-directory bundles natively on Linux
x86-64, Windows x86-64, and Apple Silicon macOS. It inventories their application assets,
KaTeX fonts, and license notices, but does not upload or retain the bundles.

## Build a desktop bundle

Desktop builds run on their target operating system. With Python 3.11 and
`uv` available, run:

```console
uv sync --group desktop
uv run --no-sync python tools/build_desktop.py
uv run --no-sync python tools/verify_desktop_bundle.py dist/Quarkfoil
uv run --no-sync python tools/smoke_desktop_bundle.py
```

For the macOS inventory command, use `dist/Quarkfoil.app` as the bundle path.

The build script reproducibly generates platform icon containers, then uses
the pinned PyInstaller version and `packaging/quarkfoil.spec`. Linux gets a
portable one-directory executable, Windows gets a no-console one-directory
executable with version metadata, and macOS gets a windowed one-directory
`.app` with document-role metadata. Editor assets and
complete vendored notices are copied explicitly. Build products remain under
ignored `build/` and `dist/` directories.

Test the result from outside the checkout with paths containing spaces and
non-ASCII characters. Record the OS, architecture, Python and PyInstaller
versions, signing state, and manual tests. Native signing, notarization,
installer/DMG creation, clean-machine checks, and public distribution are
deliberate release steps and are not performed by this build command.

## Vendored browser dependencies

Reveal.js, KaTeX, Marked, and js-yaml are pinned under `app/vendor/`. Refresh them without Node/npm:

```console
uv run python tools/fetch_vendor.py
```

The fetcher verifies release archives against pinned SHA-256 hashes. Review and update `THIRD_PARTY_LICENSES.md` when dependency versions change.

## Build and verify

```console
uv build
```

This creates a wheel and source archive under `dist/`. The wheel force-includes `app/` as `scientific_slides/app/`; the server prefers those packaged assets and falls back to the repository `app/` during source development.

Before release:

1. Run the Python and browser tests.
2. Inspect both archives and confirm vendored licenses are present.
3. Install the wheel in an isolated `uv tool` environment.
4. Launch a deck from outside the repository.
5. Test editing, image import, saving, and presentation mode.
6. Add public project URLs and a private security contact to the metadata and documentation.
