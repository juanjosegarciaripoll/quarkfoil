"""Shared construction of a minimal Quarkfoil presentation."""

from __future__ import annotations

import json


STARTER_DECK = """---
title: New presentation
author: Your name
aspect-ratio: "16:9"
theme: scientific-light
defaults:
  footer: Quarkfoil · Reveal.js
---

# New presentation {.layout-front}

::: core
**Your name**

Presentation subtitle
:::
"""


def starter_deck(
    *,
    title: str = "New presentation",
    author: str = "Your name",
    theme: str = "scientific-light",
) -> str:
    """Return a readable one-slide starter with safely quoted metadata."""
    if title == "New presentation" and author == "Your name" and theme == "scientific-light":
        return STARTER_DECK
    details = f"**{author}**\n\n" if author else ""
    return f"""---
title: {json.dumps(title, ensure_ascii=False)}
author: {json.dumps(author, ensure_ascii=False)}
aspect-ratio: "16:9"
theme: {theme}
defaults:
  footer: Quarkfoil · Reveal.js
---

# {title} {{.layout-front}}

::: core
{details}Presentation subtitle
:::
"""


__all__ = ["STARTER_DECK", "starter_deck"]
