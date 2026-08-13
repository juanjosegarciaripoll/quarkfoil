# Desktop packaging implementation plan

## Objective

Distribute Quarkfoil as an installable, double-clickable application for
Windows and macOS without requiring users to install Python or `uv`.

The first desktop release should preserve Quarkfoil's existing architecture:
the packaged Python process serves the editor on loopback and opens it in the
user's default browser. An embedded webview is explicitly deferred until the
browser-launching package is stable and its value justifies a second browser
runtime and test matrix.

## Constraints and decisions

- Preserve the browser-native JavaScript editor and shared renderer.
- Do not introduce Node.js, npm, Electron, a cloud service, or runtime CDN
  dependencies.
- Keep the current `quarkfoil` command and wheel installation working.
- Package the existing `scientific_slides/app` assets and all third-party
  notices.
- Bind only to `127.0.0.1` in desktop mode and choose an available port.
- Disable source-development reloading in frozen applications.
- Do not weaken deck-directory filesystem boundaries, atomic saves, conflict
  checks, CSP, or Markdown/SVG protections.
- Build each artifact on its target operating system. Do not attempt to
  cross-compile Windows or macOS applications from Linux.
- Use PyInstaller one-directory bundles for the initial implementation. On
  macOS, produce a windowed `.app`; do not combine one-file and windowed modes.
- Signing, notarization, Store submission, and public release remain separate
  authorization-dependent release steps. Development artifacts may be
  unsigned but must be labeled accordingly.

## Target user experience

1. The user launches Quarkfoil from the Start menu, Applications folder, or an
   associated Markdown document.
2. If no deck was supplied, a native Open/New launcher asks for a `.md` or
   `.markdown` path.
3. Quarkfoil starts its local server on an available loopback port and opens
   the editor in the default browser.
4. The launcher remains available while the server is running and offers at
   least **Open editor** and **Quit**. If a durable cross-platform tray/menu
   implementation would add a large GUI dependency, a small status window is
   acceptable for the first version.
5. Startup failures are shown graphically rather than disappearing or opening
   a console traceback.
6. The user can open an existing deck or choose a new deck path. Existing
   server rules initialize only a missing or whitespace-only Markdown file and
   never overwrite a nonempty file.

## Phase 1: refactor the server lifecycle

Extract a reusable server-running API from `scientific_slides.server.main`
without changing CLI behavior.

The API should:

- accept the deck path, host, port, reload setting, and browser-opening policy;
- expose the resolved URL after binding;
- allow another thread or GUI event to request clean shutdown;
- close the server and join watcher threads deterministically;
- retain current `KeyboardInterrupt` and development-reload behavior for the
  CLI; and
- never execute `sys.executable -m scientific_slides` from frozen desktop
  mode.

Prefer a small context-managed or object-based lifecycle over duplicating the
server loop. Extend Python tests for ephemeral ports, programmatic shutdown,
and unchanged CLI argument behavior.

## Phase 2: add a desktop entry point

Add a dedicated module, for example `scientific_slides.desktop`, rather than
placing desktop-specific behavior in the command-line parser.

Responsibilities:

- detect whether the process is frozen without making source execution depend
  on PyInstaller;
- accept zero or one document path from platform launch/file association;
- show native Open and Save/New dialogs when necessary;
- validate `.md` and `.markdown` suffixes and display useful errors;
- start the server with `host="127.0.0.1"`, `port=0`, `reload=False`, and no
  automatic browser launch from the server layer;
- open the resulting URL once through the system browser;
- keep a minimal status/control UI alive until the user quits;
- make repeated **Open editor** actions reuse the current URL;
- stop the server cleanly on application exit; and
- send diagnostics to an application log in a platform-appropriate user data
  directory when no console is present.

Choose the smallest GUI mechanism that gives reliable native file dialogs and
lifecycle behavior on both targets. Evaluate standard-library Tk first in the
packaged prototypes. If its appearance or deployment is unacceptable, compare
a tiny platform-specific launcher layer with pywebview; do not add a large GUI
framework without documenting the bundle-size and maintenance tradeoff.

Opening multiple decks requires an explicit decision after the first
prototype. The safe first behavior is one server/deck per application process.
If the OS delivers another document to an already-running process, either
launch another process or report that the current deck must be closed; do not
silently change the server's project root.

## Phase 3: make packaged resources explicit

Add a PyInstaller spec and a small, reproducible build script or documented
command that:

- uses the desktop module as its entry point;
- collects `scientific_slides/app` at the location expected by `APP_ROOT`;
- collects `THIRD_PARTY_LICENSES.md` and complete notices beside vendored
  libraries;
- excludes development-only Selenium, documentation, tests, and generated
  files;
- includes application icons and Windows version metadata;
- creates a one-directory, no-console bundle;
- creates a macOS `.app` bundle in windowed one-directory mode; and
- records/pins the packaging tool version in a dedicated dependency group and
  `uv.lock`.

Do not make PyInstaller a runtime dependency of the wheel. Keep build output in
ignored `build/` and `dist/` locations.

Verify resource resolution from an installed wheel and from both frozen
bundles. Do not rely on the repository checkout being the current directory.

## Phase 4: platform integration

### Windows

- Build on a current GitHub-hosted Windows runner using supported Python.
- Provide `.ico`, product name, file version, company/author, copyright, and
  executable description metadata.
- Prototype a portable ZIP first.
- Then wrap the verified one-directory bundle in an installer. Compare MSI or
  MSIX-capable tooling against a conventional signed installer; select based on
  signing and Microsoft Store plans rather than convenience alone.
- Register Start menu and uninstall entries.
- Consider `.md`/`.markdown` association carefully because those are generic
  file types. Prefer an **Open with Quarkfoil** verb over taking over their
  default association.
- Verify paths containing spaces, non-ASCII characters, long paths, OneDrive
  directories, and read-only locations.
- Verify behavior with the Web browser absent/misconfigured and with Windows
  Defender/SmartScreen on a clean machine.

### macOS

- Build natively on both Apple Silicon and Intel, or deliberately document a
  single architecture. A universal2 artifact is optional and must be tested on
  both architectures if produced.
- Provide an `.icns`, bundle identifier, short version, build version, and
  document-role metadata.
- Ensure Finder-launched document paths and paths containing spaces/non-ASCII
  characters reach the desktop entry point.
- Package the verified `.app` in a DMG for direct distribution.
- Verify the app from `/Applications`, from a read-only mounted DMG, and after
  quarantine is applied to a downloaded artifact.
- Before public distribution, sign all nested code with Developer ID, enable
  hardened runtime, notarize with `notarytool`, staple the ticket, and validate
  with `codesign`, `spctl`, and a clean-machine launch.

## Phase 5: tests and CI

Keep current Linux/Windows test coverage and add packaging jobs only after
local prototypes work. Packaging jobs should build and test artifacts but must
not publish or retain them unless explicitly requested; this follows the
repository's existing CI publication policy.

Required automated checks:

- all Python unit tests;
- tests of the extracted lifecycle and desktop argument/path handling;
- wheel build and content inspection;
- PyInstaller build on Windows and macOS;
- artifact inventory checks for editor assets, KaTeX fonts, vendored notices,
  and `THIRD_PARTY_LICENSES.md`;
- launch the frozen executable against a temporary deck;
- wait for its local HTTP endpoint and verify the application shell loads;
- request clean shutdown and assert that the process and port are gone; and
- run the existing browser self-test against the packaged server where
  practical, requiring `data-status="passed"` rather than only an HTTP 200.

Manual release checks on clean Windows and macOS machines:

- launch with no arguments;
- open and create decks through dialogs;
- launch through **Open with Quarkfoil**/Finder;
- edit and atomically save Markdown;
- detect an external-edit conflict;
- import images and supported video;
- enter presentation mode and exercise fullscreen/speaker behavior;
- use recovery snapshots after an interrupted session;
- export with local assets;
- confirm optional AVI/MKV conversion reports missing `ffmpeg` clearly;
- quit and confirm the local server no longer responds; and
- inspect the artifact for all license notices.

Run `git diff --check` and `git status --short` at every handoff. For each
platform artifact, record the OS version, architecture, Python version,
PyInstaller version, artifact type, signing state, and tests performed.

## Phase 6: documentation

Once packages exist, update the existing documentation rather than creating a
second documentation tree:

- `README.md`: add desktop downloads without removing `uv` installation;
- `docs/INSTALLATION.md`: describe Windows and macOS install/open/uninstall,
  browser behavior, unsigned-development warnings, and CLI availability;
- `docs/DEVELOPMENT.md`: document reproducible native builds and artifact
  verification;
- `docs/SECURITY.md`: explain the packaged loopback server, process lifetime,
  logs, and non-loopback prohibition in desktop mode;
- `docs/LICENSES.md` and `THIRD_PARTY_LICENSES.md`: add packaging or GUI
  dependencies and their exact notices if any are introduced; and
- `CHANGELOG.md`: describe the desktop launcher and supported artifact types.

Do not promise automatic updates, Store availability, universal binaries,
code signing, notarization, or embedded-window operation until each is
implemented and verified.

## Deferred embedded-window investigation

After the browser-launching packages are stable, prototype pywebview on a
branch only if a single-window experience remains desirable. Test Windows
WebView2 and macOS WKWebView independently for:

- editor rendering and all seven layouts;
- KaTeX, Reveal.js, fullscreen, speaker notes, and external links;
- clipboard, downloads, uploads, drag/drop, IndexedDB recovery, and keyboard
  shortcuts;
- CSP and navigation restrictions; and
- packaged dependency size, signing, and browser-engine availability.

Adopt it only if these checks pass and the native-window benefit outweighs the
new runtime dependency and expanded browser matrix. Do not replace the shared
parser or renderer.

## Progress snapshot (2026-08-13)

Implementation is on branch `implement-desktop-packaging`.

Completed in source:

- Extracted `ServerLifecycle` from the CLI server loop. It exposes the bound
  URL, supports foreground and background serving, owns the source watcher,
  opens the browser according to policy, and shuts down the server and watcher
  deterministically. Frozen processes never execute the development reload
  command.
- Added the Tk desktop entry point with zero-or-one document argument handling,
  native Open and Save/New dialogs, Markdown suffix validation, graphical
  errors, a persistent **Open editor**/**Quit** window, loopback-only ephemeral
  binding, browser reuse, clean shutdown, and platform-appropriate logs.
- Added a pinned PyInstaller 6.21.0 dependency group, one-directory spec,
  reproducible platform icons, Windows version metadata, macOS bundle/document
  metadata, explicit editor assets and notices, and bundle inventory tooling.
- Added native CI build jobs for Linux x86-64, Windows x86-64, and Apple Silicon
  macOS. Artifacts are tested ephemerally and are neither uploaded nor
  published.
- Added a frozen-bundle smoke harness that initializes Tcl/Tk without a display,
  launches a temporary deck, verifies the real application shell over HTTP,
  requests clean shutdown, and confirms that the port is released.
- Updated installation, development, security, licensing, README, and changelog
  documentation without promising signed downloads or installers.

Verified locally on Linux 6.12 x86-64 with Python 3.11.15 and PyInstaller
6.21.0:

- Built the portable `dist/Quarkfoil/` one-directory bundle natively.
- Verified all required editor assets, KaTeX fonts, vendored notices,
  `THIRD_PARTY_LICENSES.md`, the Linux icon, and the Tcl/Tk 9 shared libraries.
- Passed the frozen application lifecycle smoke test. The first prototype found
  and fixed an incorrect spec root and missing Tcl/Tk shared libraries.
- Passed 47 Python unit tests, the Firefox browser self-test with 215 checks,
  strict MkDocs build, wheel/source-archive build and content inspection, CI
  YAML parsing, and `git diff --check`.

Still pending:

- Run and inspect the Windows and macOS CI bundles, including their frozen smoke
  tests; the configurations exist but have not yet run on this Linux host.
- Perform interactive native-dialog and clean-machine editing/save/import/export
  checks on all three desktop targets. The Linux headless test validates the
  packaged Tcl/Tk runtime but does not interact with a visible window.
- Select and implement a Windows installer and macOS DMG only after the signing
  and distribution decisions are made.
- Signing, hardened runtime, notarization, Store submission, publication,
  universal binaries, and the deferred embedded-webview investigation remain
  outside the currently authorized implementation.

## Milestones and completion criteria

### Milestone A: source prototype

- Desktop entry point opens/creates a deck and starts/stops the server.
- Existing CLI behavior and tests remain green.

### Milestone B: unsigned native artifacts

- Windows portable bundle and macOS `.app` run without Python installed.
- Packaged browser self-test and manual editing/save/import/export smoke tests
  pass.
- Required application and license assets are present.

### Milestone C: installable artifacts

- Windows installer and macOS DMG install, launch, and uninstall cleanly.
- Open-with/document launch works without claiming generic Markdown ownership.
- Clean-machine testing is recorded.

### Milestone D: release readiness

- Windows artifact has the selected production signature/distribution path.
- macOS app and DMG are Developer ID signed, hardened, notarized, and stapled.
- Documentation, changelog, dependency notices, and reproducible CI build
  configuration are complete.
- Publication occurs only after explicit approval.

## Initial execution order for the next agent

1. Re-read `AGENTS.md`, inspect `git status --short`, and review the current
   server, CLI tests, wheel layout, and CI workflows.
2. Implement and test the reusable server lifecycle without changing visible
   CLI behavior.
3. Implement the source-runnable desktop launcher and test its non-GUI logic.
4. Prototype PyInstaller on the available native target; request any required
   dependency installation or network permissions rather than bypassing the
   sandbox.
5. Inspect and run the frozen artifact outside the checkout.
6. Commit logical units separately: lifecycle, launcher, packaging, platform
   integration, CI, and documentation.
7. Stop before signing, notarization, Store interaction, publication, or
   persistent artifact upload unless those actions have been explicitly
   authorized.

## Open decisions requiring evidence from prototypes

- Standard-library Tk status window versus a small platform-specific or
  pywebview launcher.
- One process per deck versus explicit multi-deck process management.
- Windows portable ZIP plus installer technology, and whether MSIX/Store is a
  release goal.
- macOS per-architecture builds versus universal2.
- Whether desktop packages include the CLI as a separately accessible command.
- Whether optional `ffmpeg` remains external or receives a separately licensed
  bundled distribution; default to external.
