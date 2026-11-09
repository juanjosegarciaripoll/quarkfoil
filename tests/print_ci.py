"""End-to-end check of `quarkfoil print` and `quarkfoil deck render` in real browsers.

The unit tests drive fake browsers. This script launches the browsers installed
on the machine (GitHub-hosted runners ship Chrome and Firefox on every
platform) and runs the real command-line tools against the example deck:

* the PDF must have one page per presented slide, each 960 x 540 pt; and
* every rendered PNG must be 1280 x 720 and show more than a blank canvas.

It begins by reporting the platform and each browser's exact version, so a
failure caused by a runner image or browser update can be audited from the log
alone. It uses only the standard library and Quarkfoil itself.
"""

from __future__ import annotations

import argparse
import json
import locale
import os
import platform
import re
import struct
import subprocess
import sys
import tempfile
import time
import traceback
import zlib
from pathlib import Path

from scientific_slides.browser import FIREFOX_BROWSERS, browser_kind, open_page
from scientific_slides.exporter import CHROMIUM_BROWSERS, find_executable
from scientific_slides.parser import parse_deck

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECK = ROOT / "example" / "deck.md"
PAGE_SIZE_POINTS = (960.0, 540.0)
IMAGE_SIZE = (1280, 720)
GITHUB = os.environ.get("GITHUB_ACTIONS") == "true"
RUNNER_VARIABLES = (
    "RUNNER_OS", "RUNNER_ARCH", "RUNNER_NAME", "RUNNER_ENVIRONMENT", "ImageOS", "ImageVersion",
    "GITHUB_WORKFLOW", "GITHUB_JOB", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_REF", "GITHUB_SHA",
)


class CheckFailed(Exception):
    pass


def group(title: str) -> None:
    print(f"::group::{title}" if GITHUB else f"\n=== {title} ===", flush=True)


def end_group() -> None:
    if GITHUB:
        print("::endgroup::", flush=True)


def annotate_error(title: str, message: str) -> None:
    if GITHUB:
        flat = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title={title}::{flat}", flush=True)


def field(name: str, value: object) -> None:
    print(f"  {name:<22} {value}", flush=True)


# --- Platform report --------------------------------------------------------


def _os_release() -> str:
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    return ""


def _quarkfoil_version() -> str:
    try:
        from importlib.metadata import version

        return version("quarkfoil")
    except Exception as error:  # noqa: BLE001 - informational only
        return f"unknown ({error})"


def _git_commit() -> str:
    try:
        result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def report_platform() -> None:
    group("Platform")
    field("platform", platform.platform())
    field("system", f"{platform.system()} {platform.release()} ({platform.version()})")
    distribution = _os_release()
    if distribution:
        field("distribution", distribution)
    if sys.platform == "darwin":
        field("macOS", platform.mac_ver()[0])
    if sys.platform == "win32":
        release, build, _, kind = platform.win32_ver()
        field("Windows", f"{release} build {build} {kind}".strip())
    field("machine", f"{platform.machine()} ({platform.processor() or 'processor unknown'})")
    field("cpus", os.cpu_count())
    field("python", f"{platform.python_implementation()} {platform.python_version()} at {sys.executable}")
    field("encoding", f"preferred {locale.getpreferredencoding(False)}, filesystem {sys.getfilesystemencoding()}")
    field("temporary directory", tempfile.gettempdir())
    field("quarkfoil", _quarkfoil_version())
    field("commit", os.environ.get("GITHUB_SHA") or _git_commit())
    for name in RUNNER_VARIABLES:
        if os.environ.get(name):
            field(name, os.environ[name])
    print("  installed browsers:", flush=True)
    for candidate in (*CHROMIUM_BROWSERS, *FIREFOX_BROWSERS):
        program = find_executable((candidate,))
        if program:
            print(f"    {candidate:<20} -> {os.path.realpath(program)}", flush=True)
    end_group()


# --- Output checks ----------------------------------------------------------


def pdf_pages(data: bytes) -> tuple[int, set[tuple[float, ...]]]:
    """Count page objects and collect page boxes, looking inside compressed streams too."""
    parts = [data]
    for match in re.finditer(rb"stream\r?\n", data):
        end = data.find(b"endstream", match.end())
        if end < 0:
            continue
        try:
            parts.append(zlib.decompressobj().decompress(data[match.end():end]))
        except zlib.error:
            pass
    text = b"\n".join(parts)
    pages = len(re.findall(rb"/Type\s*/Page(?![s\w])", text))
    boxes = {
        tuple(float(value) for value in box.split())
        for box in re.findall(rb"/MediaBox\s*\[\s*([-\d.\s]+?)\s*\]", text)
    }
    return pages, boxes


def check_pdf(path: Path, expected_pages: int) -> str:
    data = path.read_bytes()
    if not data.startswith(b"%PDF"):
        raise CheckFailed(f"{path.name} is not a PDF")
    pages, boxes = pdf_pages(data)
    sizes = {(round(box[2] - box[0], 1), round(box[3] - box[1], 1)) for box in boxes if len(box) == 4}
    if pages != expected_pages:
        raise CheckFailed(f"PDF has {pages} pages, expected {expected_pages} (one per presented slide); boxes {sorted(sizes)}")
    if sizes != {PAGE_SIZE_POINTS}:
        raise CheckFailed(f"PDF page sizes are {sorted(sizes)} pt, expected {PAGE_SIZE_POINTS}")
    return f"{pages} pages of {PAGE_SIZE_POINTS[0]:g} x {PAGE_SIZE_POINTS[1]:g} pt, {len(data):,} bytes"


def _unfilter(raw: bytes, width: int, height: int, channels: int) -> list[bytes]:
    stride = width * channels
    rows: list[bytes] = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        kind = raw[offset]
        line = bytearray(raw[offset + 1: offset + 1 + stride])
        offset += 1 + stride
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            corner = previous[index - channels] if index >= channels else 0
            if kind == 1:
                line[index] = (line[index] + left) & 0xFF
            elif kind == 2:
                line[index] = (line[index] + up) & 0xFF
            elif kind == 3:
                line[index] = (line[index] + (left + up) // 2) & 0xFF
            elif kind == 4:
                estimate = left + up - corner
                distances = (abs(estimate - left), abs(estimate - up), abs(estimate - corner))
                predictor = (left, up, corner)[distances.index(min(distances))]
                line[index] = (line[index] + predictor) & 0xFF
        rows.append(bytes(line))
        previous = line
    return rows


def check_png(path: Path) -> str:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise CheckFailed(f"{path.name} is not a PNG")
    offset, idat, header = 8, bytearray(), None
    while offset < len(data):
        (length,) = struct.unpack("!I", data[offset:offset + 4])
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack("!IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        offset += 12 + length
    if header is None:
        raise CheckFailed(f"{path.name} has no header")
    width, height, depth, color, _, _, interlace = header
    if (width, height) != IMAGE_SIZE:
        raise CheckFailed(f"{path.name} is {width} x {height}, expected {IMAGE_SIZE[0]} x {IMAGE_SIZE[1]}")
    channels = {2: 3, 6: 4}.get(color)
    if depth != 8 or channels is None or interlace:
        return f"{width} x {height} (color type {color}, depth {depth}: content not inspected)"
    rows = _unfilter(zlib.decompress(bytes(idat)), width, height, channels)
    # Sample a grid of pixels: a blank or failed render is one or two colors.
    colors = {
        rows[y][x * channels:(x + 1) * channels][:3]
        for y in range(0, height, 9) for x in range(0, width, 9)
    }
    if len(colors) < 8:
        raise CheckFailed(f"{path.name} looks blank: only {len(colors)} distinct colors in a sampled grid")
    return f"{width} x {height}, {len(colors)} sampled colors"


# --- Runs -------------------------------------------------------------------


def run_quarkfoil(arguments: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    # Exactly what the `quarkfoil` console script runs. (`python -m
    # scientific_slides` starts only the editor server.)
    command = [sys.executable, "-c", "import sys; from scientific_slides import main; sys.exit(main())", *arguments]
    print(f"  $ quarkfoil {' '.join(arguments)}", flush=True)
    started = time.monotonic()
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=environment
    )
    elapsed = time.monotonic() - started
    for stream in (result.stdout, result.stderr):
        for line in stream.strip().splitlines()[:12]:
            print(f"    {line}", flush=True)
    print(f"    (exit {result.returncode} after {elapsed:.1f} s)", flush=True)
    if result.returncode:
        raise CheckFailed(f"quarkfoil {arguments[0]} {arguments[1] if arguments[0] == 'deck' else ''}".strip()
                          + f" exited {result.returncode}: {(result.stderr or result.stdout).strip()[-500:]}")
    return result


def check_browser(kind: str, program: str, deck: Path, presented: int, workspace: Path, timeout: float) -> dict[str, str]:
    field("program", program)
    field("resolved", os.path.realpath(program))
    started = time.monotonic()
    with open_page(kind, program) as page:
        details = dict(page.details)
    field("started in", f"{time.monotonic() - started:.1f} s")
    for name, value in details.items():
        field(name, value)

    pdf = workspace / f"{kind}.pdf"
    run_quarkfoil(["print", str(deck), "--output", str(pdf), "--browser", program, "--timeout", str(timeout)], timeout + 60)
    field("pdf", check_pdf(pdf, presented))

    images = workspace / f"{kind}-render"
    result = run_quarkfoil(
        ["deck", "render", str(deck), "--output", str(images), "--browser", program, "--timeout", str(timeout), "--compact"],
        timeout + 60,
    )
    report = json.loads(result.stdout)
    if len(report["images"]) != presented:
        raise CheckFailed(f"deck render reported {len(report['images'])} images, expected {presented}")
    for image in report["images"]:
        field(f"slide {image['slide']}", check_png(Path(image["file"])))
    return details


def discover(names: list[str] | None) -> tuple[list[tuple[str, str]], list[str]]:
    if names:
        found, missing = [], []
        for name in names:
            program = find_executable((name,))
            (found.append((browser_kind(program), program)) if program else missing.append(name))
        return found, missing
    found, missing = [], []
    for label, candidates in (("Chrome, Chromium, or Edge", CHROMIUM_BROWSERS), ("Firefox", FIREFOX_BROWSERS)):
        program = find_executable(candidates)
        (found.append((browser_kind(program), program)) if program else missing.append(label))
    return found, missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Check quarkfoil print and deck render in installed browsers")
    parser.add_argument("--browser", action="append", help="Browser to test (repeatable; default: one Chromium-family browser and Firefox)")
    parser.add_argument("--deck", type=Path, default=DEFAULT_DECK, help="Presentation to print and render")
    parser.add_argument("--allow-missing", action="store_true", help="Skip, rather than fail, browsers that are not installed")
    parser.add_argument("--timeout", type=float, default=180.0, help="Seconds each command may wait for the browser")
    args = parser.parse_args()
    # Windows consoles default to a legacy code page; never fail on a report line.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    report_platform()
    deck = args.deck.resolve()
    presented = sum(1 for slide in parse_deck(deck.read_text(encoding="utf-8")).slides if not slide.trashed)
    browsers, missing = discover(args.browser)
    failures: list[str] = []
    for name in missing:
        message = f"{name} is not installed"
        print(f"{'SKIP' if args.allow_missing else 'FAIL'}: {message}", flush=True)
        if not args.allow_missing:
            annotate_error("Browser missing", f"{message} on {platform.platform()}")
            failures.append(message)

    results: list[tuple[str, str, str]] = []
    with tempfile.TemporaryDirectory(prefix="quarkfoil-print-ci-") as directory:
        workspace = Path(directory)
        for kind, program in browsers:
            group(f"{kind}: {program}")
            try:
                details = check_browser(kind, program, deck, presented, workspace, args.timeout)
                results.append(("PASS", program, details.get("product", "")))
            except Exception as error:  # noqa: BLE001 - report every browser, then fail
                traceback.print_exc()
                message = f"{program}: {error}"
                failures.append(message)
                results.append(("FAIL", program, str(error)[:200]))
                annotate_error(f"Print/render failed in {kind}", f"{message}\n{platform.platform()}")
            finally:
                end_group()

    print(f"\nSummary for {deck.name} ({presented} presented slides) on {platform.platform()}:", flush=True)
    for status, program, note in results:
        print(f"  {status}  {program}  {note}", flush=True)
    if not browsers:
        failures.append("no browser was tested")
    if failures:
        print(f"\n{len(failures)} failure(s).", flush=True)
        return 1
    print("\nAll browsers printed and rendered the deck correctly.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
