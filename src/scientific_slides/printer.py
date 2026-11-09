"""Render a presentation to PDF with a browser installed on this computer.

Quarkfoil has no PDF renderer of its own. It exports the presentation to a
throwaway static website, serves it on a loopback port, and drives a headless
browser through its automation protocol (see ``browser.py``): open the Reveal
print view, wait until the player reports that every slide is laid out and
every font and image has loaded, and print. The point of the exercise is the
page box: a browser's own print dialog puts 16:9 slides on whatever paper it
was last set to, while the print command here names the slide size itself.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .browser import (
    FIREFOX_BROWSERS,
    BrowserError,
    browser_candidates as _browser_candidates,
    browser_kind,
    open_first_page,
    wait_for,
)
from .exporter import export_presentation, serve_directory


# Slides are laid out on the fixed 1280x720 canvas configured in
# app/modules/player.js, and a CSS pixel is 1/96 in. Reveal's print stylesheet
# asks for exactly that page box, and both protocols are also told it directly.
SLIDE_WIDTH_PIXELS = 1280
SLIDE_HEIGHT_PIXELS = 720
SLIDE_WIDTH_INCHES = SLIDE_WIDTH_PIXELS / 96
SLIDE_HEIGHT_INCHES = SLIDE_HEIGHT_PIXELS / 96

BROWSER_TIMEOUT_SECONDS = 180.0

# The player sets data-print-ready once Reveal's print layout is complete and
# every font and image has loaded; a player error is reported instead.
PRINT_READY = """(() => {
  const failure = document.querySelector(".player-error");
  if (failure) return "error:" + failure.textContent;
  return document.documentElement.dataset.printReady === "true";
})()"""


def browser_candidates(preferred: str | None = None) -> list[tuple[str, str]]:
    """The browsers to try, in order: the named one, or every one installed."""
    return _browser_candidates(preferred, purpose="Printing a PDF")


def print_url(origin: str) -> str:
    """Address of the Reveal print view of a served export."""
    return f"{origin}/?print-pdf"


def render_pdf(candidates: list[tuple[str, str]], url: str, timeout: float) -> tuple[bytes, str]:
    """Print `url` with the first candidate browser that starts; return the PDF and that browser."""
    with open_first_page(candidates, width=SLIDE_WIDTH_PIXELS, height=SLIDE_HEIGHT_PIXELS) as (page, program):
        page.navigate(url)
        wait_for(page, PRINT_READY, timeout)
        data = page.print_pdf(SLIDE_WIDTH_INCHES, SLIDE_HEIGHT_INCHES, timeout)
    if not data.startswith(b"%PDF"):
        raise BrowserError("The browser did not return a PDF")
    return data, program


def print_presentation(
    deck: Path,
    output: Path | None = None,
    *,
    browser: str | None = None,
    timeout: float = BROWSER_TIMEOUT_SECONDS,
) -> tuple[Path, str]:
    """Render a presentation to PDF and return the file and the browser used."""
    resolved = deck.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Presentation not found: {resolved}")
    if resolved.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("Presentation source must be Markdown")

    destination = (output if output is not None else resolved.with_suffix(".pdf")).resolve()
    if destination.is_dir():
        raise IsADirectoryError(f"PDF destination is a directory: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"PDF directory not found: {destination.parent}")
    candidates = browser_candidates(browser)

    # The PDF is written beside the destination so the finished file arrives in
    # one rename. A half-written PDF never carries the name the user asked for.
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        pdf = staging / "presentation.pdf"
        with tempfile.TemporaryDirectory(prefix="quarkfoil-print-") as workspace:
            site = export_presentation(resolved, Path(workspace) / "site", include_notes=False)
            with serve_directory(site) as origin:
                data, program = render_pdf(candidates, print_url(origin), timeout)
                pdf.write_bytes(data)
        os.replace(pdf, destination)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return destination, program


__all__ = [
    "FIREFOX_BROWSERS",
    "SLIDE_HEIGHT_INCHES",
    "SLIDE_WIDTH_INCHES",
    "browser_kind",
    "browser_candidates",
    "print_presentation",
    "print_url",
    "render_pdf",
]
