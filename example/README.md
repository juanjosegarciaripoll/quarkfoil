# Quarkfoil example project

This directory is a complete, portable presentation project:

```text
example/
├── deck.md
└── figures/
    └── hardware-model.svg
```

From a source checkout, run it with:

```console
uv run quarkfoil example/deck.md
```

The deck demonstrates the Front page, `1`, `1+1`, `1+2`, `2+1`, `0`, and Free layouts; Markdown and LaTeX; image fitting; and positioned overlays.

To start a presentation of your own, copy this directory, rename `deck.md`, replace the content, and retain relative image paths under `figures/`.
