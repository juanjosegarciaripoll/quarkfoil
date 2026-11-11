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

### Shared fixtures

Some behaviour exists both in the browser (`app/modules/parser.js`) and in
Python. Shared fixture files hold both to the same results:

- `app/parser-fixtures.json`: the document model, checked by
  `tests/test_parser.py` and the browser self-test.
- `app/edit-fixtures.json`: trashing and restoring slides, checked by
  `tests/test_deck_cli.py` and the browser self-test, so the editor and
  `quarkfoil deck apply` write identical text.

The editor is the reference for edits. After deliberately changing one, or to
add a case (a name, operation, slide, and source deck), regenerate the expected
results from `parser.js` in a headless browser:

```console
uv run python tools/edit_fixtures.py
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
- `quarkfoil print` and `quarkfoil deck render` end to end, with every browser
  preinstalled on the Linux, Windows, and macOS runner images and with the
  default browser selection. At least one Chromium-family browser and Firefox
  must pass; a browser that cannot start on the runner is reported as a
  warning with its diagnostics;
- wheel and source-archive creation after all checks pass.

The print-and-render check is also a local command. It reports the platform
and each browser's version, prints and renders `example/deck.md`, and checks
for one 960 × 540 pt page per slide and 1280 × 720 images that are not blank:

```console
uv run python tests/print_ci.py
uv run python tests/print_ci.py --browser firefox --allow-missing
```

It deliberately uses the browsers the runner image ships rather than pinned
ones, so a browser release that breaks printing fails CI. The platform report
at the top of the job log (runner image version, operating system, and the
exact browser builds) is the first thing to compare when it does.

Nobody can log in to a hosted runner, so a Chromium-family browser that will
not start diagnoses itself in the log. The script reports the Linux sandbox
settings (AppArmor and user namespaces), the browser's sandbox helper,
AppArmor profiles, and missing libraries. It then launches the browser twice
to print an empty page, with and without its sandbox, and concludes whether
the sandbox, Quarkfoil's launch options, or the installation is at fault.
These probes exist only in the test script; Quarkfoil never disables the
sandbox.

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
