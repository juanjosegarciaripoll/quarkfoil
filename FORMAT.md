# Presentation format

The source of truth is one UTF-8 Markdown file. YAML front matter contains presentation-wide settings. Slides are separated by a line containing `---`.

## Layouts

```markdown
## One {.layout-1}
## Two columns {.layout-1-1 columns="42 58"}
## Left plus stacked right {.layout-1-2 columns="42 58" rows="55 45"}
## Stacked left plus right {.layout-2-1 columns="42 58" rows="55 45"}
## Free canvas {.layout-free}
```

Cells are fenced directives named `core`, `left`, `right`, `top-left`, `bottom-left`, `top-right` or `bottom-right` as appropriate.

## Images

```markdown
![](figures/example.svg){fit=contain}
![](figures/example.png){fit=cover focus="70 35"}
![](figures/example.svg){fit=width}
![](figures/example.svg){fit=height}
![](figures/example.svg){fit=native}
```

## Overlays

```markdown
::: overlay {#unique-id type="equation" x="62" y="31" w="24" h="9" z="10" fragment="1"}
\[
\Delta=E_1-E_0
\]
:::
```

Overlay types are `markdown`, `equation` and `image`. Coordinates and sizes are percentages of the entire slide. Optional `locked="true"` prevents graphical movement. `fragment` supplies Reveal's fragment index.

## Footers and notes

```markdown
::: footer
Paper citation or slide-specific footer
:::

::: notes
Speaker notes are not displayed on the slide.
:::
```

Raw HTML and executable JavaScript are not part of the supported format.
