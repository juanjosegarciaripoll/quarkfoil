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
- the browser self-test in Firefox on Linux, Microsoft Edge on Windows, and
  Safari on macOS;
- wheel and source-archive creation after all checks pass.

Distribution archives exist only inside the ephemeral CI runner and are not
uploaded or retained. Quarkfoil has no automated package-publication workflow.
The separate documentation workflow performs the strict site build, exports
the live example, and deploys GitHub Pages from `main` without duplicating
those tasks in CI.

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
