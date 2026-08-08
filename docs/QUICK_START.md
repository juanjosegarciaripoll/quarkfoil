# Quick start

The shortest path from installation to a new presentation takes three steps.

## 1. Install Quarkfoil

With [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer:

```console
uv tool install quarkfoil
```

For an unpublished development checkout, run `uv tool install .` in the
repository instead.

## 2. Create a project

Create an empty Markdown file. Quarkfoil will create the `figures/` directory
when you import the first image.

```text
my-lecture/
└── lecture.md
```

An initial deck can be as small as:

```markdown
---
title: My lecture
author: Ada Lovelace
defaults:
  footer: Summer school · 2026
---

## Opening {.layout-front}

::: core
Ada Lovelace

Quantum Simulation School
:::

---

## First model {.layout-1}

::: core
The exchange scale is $J_{\mathrm{ex}} \sim t^2/U$.
:::
```

## 3. Open it

```console
quarkfoil my-lecture/lecture.md
```

The editor opens in your browser. Double-click content to edit it, select a
region or floating object to expose its properties, and press `Ctrl+S` to save.

![The main Quarkfoil editing surface](assets/editor-overview.png)

## Where to go next

- Learn the [editing modes, layouts, and controls](USER_GUIDE.md).
- Consult the complete [Markdown format](FORMAT.md).
- Copy the repository's [`example/`](https://github.com/juanjosegarciaripoll/quarkfoil/tree/main/example)
  directory as a working template.
