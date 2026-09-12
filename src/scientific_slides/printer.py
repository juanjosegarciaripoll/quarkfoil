"""Render a presentation to PDF with a browser installed on this computer.

Quarkfoil has no PDF renderer of its own. It exports the presentation to a
throwaway static website, serves it on a loopback port, and asks a headless
browser to print it. The point of the exercise is the page box: a browser's
own print dialog puts 16:9 slides on whatever paper it was last set to, while
both browsers driven from here produce pages the size of a slide.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .exporter import CHROMIUM_BROWSERS, export_presentation, find_executable, serve_directory


FIREFOX_BROWSERS = (
    "firefox", "firefox-esr", "firefox-developer-edition",
    "/Applications/Firefox.app/Contents/MacOS/firefox",
    r"C:\Program Files\Mozilla Firefox\firefox.exe",
    r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
)

# Slides are laid out on the fixed 1280x720 canvas configured in
# app/modules/player.js, and a CSS pixel is 1/96 in. Reveal's print stylesheet
# asks for exactly that page box. Chromium obeys it, because --print-to-pdf
# prefers the CSS page size; Firefox prints on the paper its settings name, so
# the same size is written into the throwaway profile below.
SLIDE_WIDTH_INCHES = 1280 / 96
SLIDE_HEIGHT_INCHES = 720 / 96

# Firefox's built-in PDF destination. Its settings live under a preference
# branch named after the printer, with spaces replaced by underscores.
FIREFOX_PDF_PRINTER = "Mozilla Save to PDF"

BROWSER_TIMEOUT_SECONDS = 180.0


def browser_kind(program: str) -> str:
    """Classify a browser by program name: Firefox and Chromium print differently."""
    return "firefox" if "firefox" in Path(program).name.lower() else "chromium"


def find_browser(preferred: str | None = None) -> tuple[str, str]:
    """Return the kind and path of the browser to print with."""
    if preferred:
        program = find_executable((preferred,))
        if not program:
            raise FileNotFoundError(f"Browser not found: {preferred}")
        return browser_kind(program), program
    for candidates in (CHROMIUM_BROWSERS, FIREFOX_BROWSERS):
        program = find_executable(candidates)
        if program:
            return browser_kind(program), program
    raise RuntimeError(
        "Printing a PDF needs Chrome, Chromium, Edge, or Firefox on this computer; "
        "install one or name it with --browser"
    )


def print_url(origin: str, kind: str) -> str:
    """Address of the print view. Firefox also needs the page to call print()."""
    return f"{origin}/?print-pdf&print-dialog" if kind == "firefox" else f"{origin}/?print-pdf"


def _chromium_command(browser: str, output: Path, url: str, profile: Path) -> list[str]:
    return [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--no-first-run",
        "--disable-background-networking",
        f"--user-data-dir={profile}",
        "--virtual-time-budget=30000",
        # Both spellings of one switch; without it every slide is stamped with
        # the page title, the loopback URL, and today's date. Chromium ignores
        # the spelling it does not know.
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={output}",
        url,
    ]


def _firefox_command(browser: str, url: str, profile: Path) -> list[str]:
    # --no-remote keeps this out of a Firefox the user already has open, which
    # would open a tab there and never print.
    return [browser, "--headless", "--no-remote", "--profile", str(profile), url]


def firefox_preferences(output: Path) -> str:
    """Preferences that make Firefox print one slide-sized page per slide, silently."""
    branch = f"print.printer_{FIREFOX_PDF_PRINTER.replace(' ', '_')}."
    values: dict[str, object] = {
        # Print on load, into the file Quarkfoil asked for, with no dialog.
        "print.always_print_silent": True,
        "print.show_print_progress": False,
        "print.prefer_system_dialog": False,
        "print_printer": FIREFOX_PDF_PRINTER,
        branch + "print_to_file": True,
        branch + "print_to_filename": str(output),
        # One page the size of a slide, printed edge to edge at full scale.
        branch + "print_paper_id": "",
        branch + "print_paper_size_unit": 0,
        branch + "print_paper_width": f"{SLIDE_WIDTH_INCHES:.5f}",
        branch + "print_paper_height": f"{SLIDE_HEIGHT_INCHES:.5f}",
        branch + "print_orientation": 0,
        branch + "print_scaling": "1.0",
        branch + "print_shrink_to_fit": False,
        branch + "print_bgcolor": True,
        branch + "print_bgimages": True,
        # Slide artwork reaches the paper edge, and nothing else does.
        branch + "print_headerleft": "",
        branch + "print_headercenter": "",
        branch + "print_headerright": "",
        branch + "print_footerleft": "",
        branch + "print_footercenter": "",
        branch + "print_footerright": "",
        # Keep the throwaway profile quiet: no first-run tab, update check, or
        # session restore competing with the page being printed.
        "browser.shell.checkDefaultBrowser": False,
        "browser.startup.homepage_override.mstone": "ignore",
        "browser.sessionstore.resume_from_crash": False,
        "datareporting.policy.dataSubmissionEnabled": False,
        "toolkit.telemetry.reportingpolicy.firstRun": False,
        "app.update.auto": False,
    }
    for margin in ("top", "bottom", "left", "right"):
        values[f"{branch}print_margin_{margin}"] = "0"
        values[f"{branch}print_unwriteable_margin_{margin}"] = 0
    lines = [f"user_pref({json.dumps(name)}, {json.dumps(value)});" for name, value in values.items()]
    return "\n".join(lines) + "\n"


def _complete_pdf(path: Path) -> bool:
    """A PDF the browser has finished writing ends with its end-of-file marker."""
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if not size:
        return False
    with path.open("rb") as stream:
        stream.seek(max(0, size - 1024))
        return b"%%EOF" in stream.read()


def _wait_for_pdf(process: subprocess.Popen[bytes], output: Path, timeout: float) -> None:
    # Chromium exits once it has written the file; Firefox keeps running, so
    # the file itself reports progress. A complete PDF whose size stopped
    # changing is finished.
    deadline = time.monotonic() + timeout
    previous = -1
    while True:
        exited = process.poll() is not None
        if _complete_pdf(output):
            size = output.stat().st_size
            if size == previous:
                return
            previous = size
        elif exited:
            raise RuntimeError("The browser stopped without writing the PDF")
        if time.monotonic() > deadline:
            raise RuntimeError("Timed out waiting for the browser to write the PDF")
        time.sleep(0.4)


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _browser_detail(log: Path) -> str:
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    reported = [line.strip() for line in lines if line.strip()]
    return reported[-1][:300] if reported else ""


def run_browser(command: list[str], output: Path, log: Path, timeout: float) -> None:
    """Run a browser until it has written `output`, then stop it."""
    with log.open("wb") as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        try:
            _wait_for_pdf(process, output, timeout)
        except RuntimeError as error:
            detail = _browser_detail(log)
            raise RuntimeError(f"{error}: {detail}" if detail else str(error)) from error
        finally:
            _stop(process)


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
    kind, program = find_browser(browser)

    # The browser prints beside the destination so the finished file arrives in
    # one rename. A half-written PDF never carries the name the user asked for.
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        pdf = staging / "presentation.pdf"
        with tempfile.TemporaryDirectory(prefix="quarkfoil-print-") as workspace:
            site = export_presentation(resolved, Path(workspace) / "site", include_notes=False)
            profile = Path(workspace) / "profile"
            profile.mkdir()
            with serve_directory(site) as origin:
                url = print_url(origin, kind)
                if kind == "firefox":
                    (profile / "user.js").write_text(firefox_preferences(pdf), encoding="utf-8")
                    command = _firefox_command(program, url, profile)
                else:
                    command = _chromium_command(program, pdf, url, profile)
                run_browser(command, pdf, staging / "browser.log", timeout)
        os.replace(pdf, destination)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return destination, program


__all__ = [
    "SLIDE_HEIGHT_INCHES",
    "SLIDE_WIDTH_INCHES",
    "browser_kind",
    "find_browser",
    "firefox_preferences",
    "print_presentation",
    "print_url",
    "run_browser",
]
