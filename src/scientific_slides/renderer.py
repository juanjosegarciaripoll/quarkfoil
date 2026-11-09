"""Render presentation slides to PNG images with an installed browser.

Like printing, rendering exports the deck to a throwaway website, serves it on
a loopback port, and drives a headless browser (see ``browser.py``). The page
is the player's preview view, which shows one slide at a time without
controls. It is loaded once and stepped through the requested slides; each is
captured after the player reports that its fonts and images have loaded.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .browser import BrowserError, browser_candidates, open_first_page, wait_for
from .exporter import export_presentation, serve_directory
from .printer import BROWSER_TIMEOUT_SECONDS, SLIDE_HEIGHT_PIXELS, SLIDE_WIDTH_PIXELS


PREVIEW_READY = """(() => {
  const failure = document.querySelector(".player-error");
  if (failure) return "error:" + failure.textContent;
  const root = document.documentElement;
  return root.dataset.previewReady === "true" ? Number(root.dataset.previewSlides) : 0;
})()"""

MIN_WIDTH = 160
MAX_WIDTH = 3840


def image_size(width: int) -> tuple[int, int]:
    """Pixel size of a rendered slide `width` pixels wide, at the canvas aspect ratio."""
    if not MIN_WIDTH <= width <= MAX_WIDTH:
        raise ValueError(f"Image width must be between {MIN_WIDTH} and {MAX_WIDTH} pixels")
    return width, round(width * SLIDE_HEIGHT_PIXELS / SLIDE_WIDTH_PIXELS)


def _shown(index: int) -> str:
    return f'document.documentElement.dataset.previewIndex === "{index}"'


def render_slides(
    deck: Path,
    targets: list[tuple[int, Path]],
    *,
    expected_slides: int,
    width: int = SLIDE_WIDTH_PIXELS,
    browser: str | None = None,
    timeout: float = BROWSER_TIMEOUT_SECONDS,
) -> str:
    """Render slides of `deck` and return the browser program used.

    `targets` pairs zero-based positions among the presented (not trashed)
    slides with the PNG file each is written to. `expected_slides` is the
    number of presented slides the caller counted; a player that disagrees is
    an error rather than a set of mislabelled pictures.
    """
    size = image_size(width)
    candidates = browser_candidates(browser, purpose="Rendering slides")
    with tempfile.TemporaryDirectory(prefix="quarkfoil-render-") as workspace:
        site = export_presentation(deck.resolve(), Path(workspace) / "site", include_notes=False)
        with serve_directory(site) as origin, \
                open_first_page(candidates, width=size[0], height=size[1]) as (page, program):
            page.navigate(f"{origin}/?preview")
            presented = wait_for(page, PREVIEW_READY, timeout)
            if presented != expected_slides:
                raise BrowserError(f"The player shows {presented} slides where {expected_slides} were expected")
            for index, destination in targets:
                page.evaluate(f'location.hash = "#/{index}"')
                wait_for(page, _shown(index), timeout)
                image = page.screenshot()
                staging = destination.with_name(f".{destination.name}.tmp")
                staging.write_bytes(image)
                os.replace(staging, destination)
    return program


__all__ = ["MAX_WIDTH", "MIN_WIDTH", "image_size", "render_slides"]
