# AGENTS.md

This file is the operational handoff for agents working on Quarkfoil. It
applies to the entire repository. Keep it focused on durable, portable project
rules; do not add workstation paths, usernames, local permission incidents, or
other machine-specific state.

## Project intent

Quarkfoil is a local, browser-based editor for scientific presentations. A
presentation is a readable Markdown file plus project-relative figures. The
editor combines structured slide layouts with freely positioned Markdown,
LaTeX, and image objects, then presents them with Reveal.js.

The project deliberately uses a small toolchain:

- Python 3.11 or newer and `uv` for packaging, running, and tests.
- Browser-native JavaScript, HTML, and CSS.
- No Node.js or npm requirement.
- No runtime CDN in the editor or default exported presentation.
- No database, build daemon, or cloud service.

Preserve these constraints unless the user explicitly changes them.

## Sources of truth

- The presentation Markdown is the content source of truth. Graphical edits
  must serialize back into readable Markdown annotations.
- `app/modules/parser.js` is the canonical presentation-format parser.
- `app/modules/render.js` is the shared renderer for editor and static player.
  Do not implement a second renderer in Python.
- `docs/` is both repository documentation and the source of the public MkDocs
  site. Do not maintain a second documentation tree.
- `THIRD_PARTY_LICENSES.md` is the canonical dependency inventory. Complete
  upstream notices remain beside the vendored files under `app/vendor/`.
- `example/deck.md` is the canonical demonstration deck. The live website
  example is regenerated from it; generated exports are not committed.

## Repository map

```text
app/                       Browser editor, player, styles, and vendored assets
app/modules/parser.js      Markdown/YAML presentation parser and source edits
app/modules/render.js      Shared slide and Markdown/KaTeX renderer
app/modules/editor.js      Direct-manipulation editor behavior
app/modules/app.js         Editor application state and UI orchestration
app/modules/player.js      Presentation-only static player
src/scientific_slides/     Python launcher, local server, and exporter
example/                   Maintained sample presentation and figures
tests/                     Python tests and the Edge browser CI harness
docs/                      User, format, security, export, and developer docs
tools/fetch_vendor.py      Pinned browser-dependency fetcher
.github/workflows/ci.yml   Tests and ephemeral distribution-build verification
.github/workflows/docs.yml Documentation build, live example, and Pages deploy
```

The Python import package retains the historical name `scientific_slides`.
The distribution and command-line tool are named `quarkfoil`.

## Product invariants

### Editing and document structure

- Source, Design, and Present modes operate on the same in-memory Markdown.
- Leaving Source applies valid edits automatically. Invalid source remains
  visible and reports an error.
- Selection must survive property-panel changes so consecutive adjustments do
  not require reselecting the object.
- Slide-local object IDs need only be unique within their slide.
- A deck must contain at least one slide. Deleting the final slide is rejected.
- Opening a missing or whitespace-only `.md`/`.markdown` path initializes a
  small valid front-page presentation. The parent directory must already
  exist. Never replace a nonempty file, including a malformed one.
- The seven layouts are `1`, `1+1`, `1+2`, `2+1`, `0`, Front page, and Free.
- A newly inserted slide copies the preceding slide's layout and proportions,
  not its content or overlays.
- Free slides have no visible frame; their organizational title remains
  editable from the slide list or Source mode.
- Keep each shape's label-safe insets beside its SVG geometry in
  `app/modules/shapes.js`. Render labels inside that region rather than adding
  shape-specific positioning rules to CSS.
- Images imported through the editor go into the presentation's `figures/`
  directory by default and are referenced with relative paths.
- `assets.figures` in front matter selects the image-import directory;
  `assets.include` lists additional directories copied by static export. All
  configured paths remain inside the presentation directory.

### Local server and security

- Bind to `127.0.0.1` by default. Non-loopback binding is an explicit user
  choice and must remain documented as a security decision.
- Enforce the selected presentation directory as the filesystem boundary.
- Keep saves UTF-8 validated, size-limited, conflict-checked, and atomic.
- Continue escaping raw Markdown HTML. Do not introduce executable Markdown.
- Keep the editor Content Security Policy restrictive and dependencies local.
- Treat SVG as an image resource; do not inject untrusted SVG markup into the
  application DOM.

### Static export

- `quarkfoil export DECK --output DIRECTORY` creates a presentation-only static
  website with local assets by default.
- The destination must not already exist. Export through a temporary sibling
  and rename only after success; never partially overwrite a user directory.
- The static player must reuse `parser.js` and `render.js`.
- Copy referenced assets only within the presentation-directory boundary.
- Local export must contain all runtime libraries, KaTeX fonts, and notices.
- `--cdn`/`--assets cdn` is explicit and network-dependent. Use exact package
  versions, Subresource Integrity, CORS attributes, and a restrictive CSP.
- Verify CDN bytes against the corresponding vendored files before changing
  URLs or integrity generation.
- Both export strategies include `THIRD_PARTY_LICENSES.txt`.
- Exported folders are meant to be served over HTTP; reliable `file://`
  operation is not currently promised.

## Dependencies and licensing

Vendored browser dependencies are pinned and fetched without Node/npm:

```console
uv run python tools/fetch_vendor.py
```

Current dependencies are Reveal.js, KaTeX, Marked, and js-yaml. When updating
one of them:

1. Review the exact new upstream license and bundled assets.
2. Update the pinned version and SHA-256 in `tools/fetch_vendor.py`.
3. Retain the complete upstream notice under `app/vendor/`.
4. Update `THIRD_PARTY_LICENSES.md`, README links, and `docs/LICENSES.md`.
5. Rebuild both package archives and verify that all notices are present.
6. Recheck CDN byte identity and browser rendering if CDN URLs change.

Do not describe Marked as MIT-only: its distributed notice also retains
BSD-3-Clause terms for Markdown-derived portions.

## Development workflow

Use native `git` and `uv`. Do not introduce WSL, Node, npm, or generated
dependency directories into the workflow.

Before editing:

1. Inspect `git status --short`.
2. Treat existing changes as user-owned; do not discard or rewrite unrelated
   work.
3. Read the relevant implementation and documentation rather than assuming
   behavior from an earlier conversation.

Use `apply_patch` for deliberate source edits. Keep changes focused. Prefer
small, imperative commit messages such as `Fix asymmetric grid layouts` or
`Export presentations as static websites`. Separate unrelated features into
separate commits, especially infrastructure changes versus product behavior.

Do not use destructive Git operations. Do not solve ownership or permission
problems by adding broad `safe.directory` exceptions or changing repository
ownership without explicit user direction.

## Running and testing

Run the editor from source:

```console
uv run quarkfoil example/deck.md
```

Run all Python tests:

```console
uv run python -m unittest discover -s tests -v
```

Run the browser self-test on Windows with Microsoft Edge available:

```console
uv run python tests/browser_ci.py
```

The browser self-test must finish with `data-status="passed"`; a successful
HTTP response alone is not sufficient. When changing layout, selection,
parsing, rendering, or source-edit behavior, extend `app/modules/selftest.js`
so the invariant is exercised in a real browser.

Run a strict documentation build:

```console
uv sync --group docs
uv run --no-sync mkdocs build --strict
uv run --no-sync quarkfoil export example/deck.md --output site/example --cdn
```

`site/`, `dist/`, and browser captures are generated artifacts and remain
ignored. If a generated output directory already exists, rebuild the parent
site or select a new destination rather than weakening the exporter's
no-overwrite guarantee.

Build distributions:

```console
uv build
```

For packaging changes, verify the wheel independently of the checkout: inspect
its contents, launch the installed command, and test export from the wheel.

## Documentation and GitHub Pages

The public documentation is:

- `https://juanjosegarciaripoll.github.io/quarkfoil/`
- `https://juanjosegarciaripoll.github.io/quarkfoil/example/`

The Pages workflow builds documentation once, exports the sample with `--cdn`,
and deploys only on `main`. The general CI workflow must not duplicate the
documentation job.

Keep documentation dependencies locked through `uv.lock`. Theme assets should
be local: no analytics, comments, remote fonts, or runtime integrations. Check
both light and dark palettes when changing CSS, including ordinary link and
button contrast.

GitHub Actions must use Node 24-compatible official actions pinned to immutable
commit SHAs. Do not set `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION`. When updating
an action, inspect its exact `action.yml`, including nested actions used by
composite actions.

## CI and publication policy

The CI workflow covers:

- minimum Python on Linux and Windows;
- a current Python on Linux;
- the Edge browser self-test on Windows; and
- wheel/source-archive build verification after tests pass.

CI build outputs are ephemeral. Do not upload or retain distribution artifacts.
There is no automated PyPI/package publication, and adding one requires an
explicit user request.

## Completion checklist

Before handing off a change, perform the checks proportional to its risk:

- Python unit tests for server, CLI, or exporter changes.
- Browser self-test for parser, renderer, editor, or layout changes.
- Real local and CDN browser loads for static-player/export changes.
- `mkdocs build --strict` for documentation or site-style changes.
- `uv build` plus wheel inspection for packaging changes.
- YAML validation and action-runtime review for workflow changes.
- `git diff --check` and a final `git status --short`.

Report what was verified and any remaining limitation. Do not claim a workflow
or deployment succeeded merely because its configuration parsed locally.
