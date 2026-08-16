---
title: Quarkfoil Demonstration
author: John Wick
aspect-ratio: 16:9
theme: scientific-light
bibliography: references.bib
assets:
  figures: figures
defaults:
  footer: Browser-native Markdown · Reveal.js · KaTeX
---

# Quarkfoil {.title-slide .layout-front}

## *Scientific presentations as readable Markdown*

::: core
**John Wick**

Scientific presentation editor
:::

---

## One content region {.layout-1}

::: core
### The simple case remains simple

This slide uses one Markdown region. Equations are written as LaTeX:

\[
H_{\mathrm{BH}}=-t\sum_{\langle i,j\rangle}
  (a_i^\dagger a_j+\mathrm{h.c.})
  +\frac{U}{2}\sum_i n_i(n_i-1).
\]

No visual editor is required to author or revise it.
:::

---

## Two columns {.layout-1-1 columns="42 58"}

::: left
### Hardware controls

- lattice depth → tunnelling;
- scattering length → interaction;
- local potential → chemical potential;
- imaging → occupation snapshots.
:::

::: right
![](figures/hardware-model.svg){fit=contain focus="50 50"}
:::

::: overlay {#exchange-label type="equation" x="58" y="64" w="30" h="10" z="12" fragment="1"}
\[
J_{\mathrm{ex}}\sim\frac{t^2}{U}
\]
:::

---

## One plus two {.layout-1-2 columns="44 56" rows="54 46"}

::: left
### Resizable regions

Drag the cyan dividers in Design mode. The resulting ratios are saved into this heading.

Double-click a Markdown cell or a movable equation to edit it.
:::

::: top-right
![](figures/hardware-model.svg){fit=cover focus="62 45"}
:::

::: bottom-right
### Image fitting

Choose contain, cover, fit width, fit height or native dimensions.
:::

---

## Two plus one {.layout-2-1 columns="46 54" rows="48 52"}

::: top-left
### Microscopic

\[
H=H_0+V
\]
:::

::: bottom-left
### Approximation

\[
\lVert V\rVert/\Delta\ll1
\]
:::

::: right
### Effective model

\[
H_{\mathrm{eff}}
=PHP+PVQ\frac{1}{E_0-QH_0Q}QVP+\cdots
\]
:::

---

## Annotated figure {.layout-0}

::: overlay {#full-figure type="image" x="8" y="17" w="84" h="65" z="1" locked="true"}
![](figures/hardware-model.svg){fit=contain focus="50 50"}
:::

::: overlay {#live-equation type="equation" x="57" y="27" w="28" h="12" z="10"}
\[
H_{XY}=J(XX+YY)
\]
:::

::: overlay {#live-label type="markdown" x="14" y="68" w="28" h="8" z="11" fragment="1"}
This annotation remains editable **Markdown**.
:::

::: notes
In Design mode, select and drag the equation or annotation. The underlying image is never modified.
:::

---

## Native diagram shapes {.layout-0 theme="scientific-dark"}

::: overlay {#thought type="shape" shape="cloud" x="7" y="20" w="28" h="24"}
A hypothesis
:::

::: overlay {#model-step type="shape" shape="rounded-rectangle" x="39" y="22" w="25" h="18" shadow="true"}
\(H_{\mathrm{eff}}\)
:::

::: overlay {#decision type="shape" shape="diamond" x="70" y="20" w="20" h="22"}
Valid?
:::

::: overlay {#comment type="shape" shape="callout" x="8" y="56" w="27" h="25"}
Markdown and $\LaTeX$
:::

::: overlay {#competing-terms type="shape" shape="cross" x="42" y="57" w="21" h="18"}
Competing terms
:::

::: overlay {#result type="shape" shape="star" x="69" y="57" w="21" h="18"}
Result
:::

---

## Slide-local appearance {.layout-1 background="#2b1745" foreground="#f8f0ff"}

::: core
### Themes establish defaults

This slide inherits the deck typography and accent palette, while its heading
stores explicit background and foreground overrides.

Click an empty part of the slide in Design mode to edit slide-wide Properties.
Resetting a color removes it from the Markdown and restores theme inheritance.

| Layer | Inherited | Slide override |
|---|---:|---:|
| Background | Theme | `#2b1745` |
| Foreground | Theme | `#f8f0ff` |
| Accent | Theme | — |
:::

---

## Citations and attribution {.layout-1-1 columns="48 52"}

::: left
### Numbered citations

Optical lattices provide a controlled setting for quantum many-body models
[@bloch2008]. Repeated citations retain the same number [@bloch2008].

Bibliography entries remain in a normal project-local BibTeX file.
:::

::: right
![](figures/hardware-model.svg){fit=contain focus="50 50"}
:::

::: overlay {#attribution-label type="markdown" x="54" y="74" w="40" h="5" font-size="0.6em"}
Positioned brief-reference example:
:::

::: overlay {#figure-attribution type="citation" key="bloch2008" display="brief" x="54" y="79" w="40" h="7" font-size="0.65em"}

:::

---

## Free canvas example {.layout-free}

::: overlay {#free-heading type="markdown" x="8" y="8" w="70" h="12" z="10"}
# A completely free canvas
:::

::: overlay {#free-model type="image" x="7" y="25" w="52" h="58" z="1"}
![](figures/hardware-model.svg){fit=contain focus="50 50"}
:::

::: overlay {#free-description type="markdown" x="63" y="29" w="30" h="22" z="11"}
Position text, images and equations without title, footer, or grid constraints.
:::

::: overlay {#free-equation type="equation" x="62" y="58" w="30" h="16" z="12"}
\[
H=-J\sum_{\langle i,j\rangle}
\left(S_i^xS_j^x+S_i^yS_j^y\right)
\]
:::
