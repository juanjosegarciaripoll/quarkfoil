# Scientific Slides

A browser-native scientific presentation editor built from Markdown, Reveal.js and KaTeX. It supports structured grids and PowerPoint-like placement of live Markdown, LaTeX and image overlays. It uses no Node/npm toolchain and copies no framework code into presentation projects.

## Run the example

From this directory in PowerShell:

```powershell
& 'C:\Users\juanj\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe' run scientific-slides example\deck.md
```

The launcher opens `http://127.0.0.1:8765/`. Stop it with `Ctrl+C`.

To open any presentation stored elsewhere:

```powershell
& 'C:\Users\juanj\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe' run scientific-slides 'C:\path\to\lecture.md'
```

The application and presentation remain separate. The server grants the browser access only to the directory containing the selected Markdown deck.

## Editing workflow

- **Source:** edit the complete Markdown in a plain text area and apply it.
- **Design:** resize grid dividers; select, drag and resize overlays; double-click Markdown or equation objects.
- **Present:** use normal Reveal navigation. Press `Escape` to return to Design mode.

Use `Ctrl+S` to save and `Ctrl+Z` / `Ctrl+Shift+Z` for undo/redo. Saves are atomic in local-project mode. The browser keeps recovery snapshots independently.

## Minimal source

```markdown
---
title: My lecture
aspect-ratio: 16:9
defaults:
  footer: Course · 2026
---

## Two regions {.layout-1-1 columns="42 58"}

::: left
Markdown and \(\LaTeX\).
:::

::: right
![](figures/experiment.svg){fit=contain}
:::

::: overlay {#gap type="equation" x="62" y="31" w="24" h="9"}
\[
\Delta=E_1-E_0
\]
:::
```

See [FORMAT.md](FORMAT.md) for the supported syntax and [SECURITY.md](SECURITY.md) for the trust model.

## Vendored libraries

The repository vendors pinned Reveal.js, KaTeX, Marked and js-yaml assets under `app/vendor/`. To reproduce them without Node/npm:

```powershell
& 'C:\Users\juanj\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe' run python tools\fetch_vendor.py
```

Release archives are verified against pinned SHA-256 hashes. Individual-file hashes are printed by the fetcher and recorded in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
