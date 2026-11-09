"""End-to-end check of `quarkfoil print` and `quarkfoil deck render` in real browsers.

The unit tests drive fake browsers. This script launches the browsers installed
on the machine (GitHub-hosted runners ship Chrome and Firefox on every
platform) and runs the real command-line tools against the example deck:

* the PDF must have one page per presented slide, each 960 x 540 pt; and
* every rendered PNG must be 1280 x 720 and show more than a blank canvas.

Every distinct installed browser is tried. At least one Chromium-family browser
and Firefox must pass; another browser that cannot start on the machine (such
as an unsandboxable Chromium build) is reported with its diagnostics as a
warning. The default selection, without --browser, is checked as well.

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

from scientific_slides.browser import FIREFOX_BROWSERS, BrowserStartError, browser_candidates, browser_kind, open_page
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


def annotate(level: str, title: str, message: str) -> None:
    if GITHUB:
        flat = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        safe_title = title.replace(",", ";").replace("::", ":")
        print(f"::{level} title={safe_title}::{flat}", flush=True)


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
    if sys.platform.startswith("linux"):
        # What decides whether Chromium's Linux sandbox can start.
        for name, path in SANDBOX_SETTINGS:
            field(name, _read_text(path) or "absent")
    print("  installed browsers:", flush=True)
    for candidate in (*CHROMIUM_BROWSERS, *FIREFOX_BROWSERS):
        program = find_executable((candidate,))
        if program:
            print(f"    {candidate:<20} -> {os.path.realpath(program)}", flush=True)
    end_group()


SANDBOX_SETTINGS = (
    ("apparmor enabled", "/sys/module/apparmor/parameters/enabled"),
    ("apparmor userns limit", "/proc/sys/kernel/apparmor_restrict_unprivileged_userns"),
    ("unprivileged userns", "/proc/sys/kernel/unprivileged_userns_clone"),
    ("max user namespaces", "/proc/sys/user/max_user_namespaces"),
)


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


# --- Diagnosing a browser that does not start ---------------------------------
#
# Nobody can log in to a hosted runner, so a browser that will not start has
# to explain itself in the log. These probes run only in this script and only
# after a failed start; Quarkfoil never disables the sandbox.


def _short_output(text: str) -> str:
    lines = [line.strip()[:240] for line in text.splitlines() if line.strip()]
    fatal = [line for line in lines if "FATAL" in line][:2]
    readable = [line for line in lines if not re.match(r"#\d+\s+0x", line)]
    chosen = fatal + [line for line in readable[-2:] if line not in fatal]
    return " | ".join(chosen) or "(no output)"


def _probe(program: str, extra: list[str]) -> tuple[bool, str]:
    """Launch the browser to print an empty page and report whether it worked."""
    with tempfile.TemporaryDirectory(prefix="quarkfoil-probe-") as profile:
        command = [program, "--headless=new", "--disable-gpu", "--no-first-run",
                   f"--user-data-dir={profile}", *extra, "--dump-dom", "about:blank"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=60, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return False, "timed out after 60 s"
        except OSError as error:
            return False, f"could not run: {error}"
    worked = result.returncode == 0 and "<body" in result.stdout
    return worked, f"exit {result.returncode}: {_short_output(result.stderr + result.stdout)}"


def _sandbox_helper(program: str) -> str:
    folder = Path(os.path.realpath(program)).parent
    for name in ("chrome-sandbox", "chrome_sandbox"):
        helper = folder / name
        if helper.exists():
            status = helper.stat()
            setuid = bool(status.st_mode & 0o4000)
            return (f"{helper} mode {oct(status.st_mode & 0o7777)} owner uid {status.st_uid}"
                    + (" (setuid root: usable)" if setuid and status.st_uid == 0 else " (not setuid root: unusable)"))
    return f"none beside {folder}"


def _apparmor_profiles(program: str) -> str:
    target = os.path.realpath(program)
    folder = Path("/etc/apparmor.d")
    if not folder.is_dir():
        return "no /etc/apparmor.d"
    matches = []
    for profile in sorted(folder.iterdir()):
        if profile.is_file() and target in _read_text(str(profile)):
            matches.append(profile.name)
    return ", ".join(matches) or f"none mentions {target}"


def _missing_libraries(program: str) -> str:
    try:
        result = subprocess.run(["ldd", os.path.realpath(program)], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "ldd unavailable"
    missing = [line.split()[0] for line in result.stdout.splitlines() if "not found" in line]
    return ", ".join(missing) or "none"


def diagnose_chromium_start(program: str) -> str:
    """Narrow down why a Chromium-family browser will not start, and say so."""
    if sys.platform.startswith("linux"):
        field("sandbox helper", _sandbox_helper(program))
        field("apparmor profiles", _apparmor_profiles(program))
        field("missing libraries", _missing_libraries(program))
    sandboxed, sandboxed_detail = _probe(program, [])
    field("probe: sandboxed", ("works" if sandboxed else "fails") + f" ({sandboxed_detail})")
    unsandboxed, unsandboxed_detail = _probe(program, ["--no-sandbox"])
    field("probe: --no-sandbox", ("works" if unsandboxed else "fails") + f" ({unsandboxed_detail})")
    if sandboxed:
        conclusion = ("the browser starts on its own, so Quarkfoil's launch options or its "
                      "remote-debugging startup are what fail")
    elif unsandboxed:
        conclusion = ("the browser starts only without its sandbox: this machine does not let "
                      "it create one (AppArmor user-namespace rules or the sandbox helper)")
    else:
        conclusion = "the browser does not start even without its sandbox: the installation itself is broken here"
    field("conclusion", conclusion)
    return conclusion


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


class StartFailed(Exception):
    """The browser never became ready; its diagnostics are the message."""


def check_browser(kind: str, program: str, deck: Path, presented: int, workspace: Path, timeout: float) -> dict[str, str]:
    field("program", program)
    field("resolved", os.path.realpath(program))
    started = time.monotonic()
    try:
        with open_page(kind, program) as page:
            details = dict(page.details)
    except BrowserStartError as error:
        raise StartFailed(str(error)) from error
    field("started in", f"{time.monotonic() - started:.1f} s")
    for name, value in details.items():
        field(name, value)

    stem = re.sub(r"[^A-Za-z0-9]+", "-", program).strip("-")[-60:]
    pdf = workspace / f"{stem}.pdf"
    run_quarkfoil(["print", str(deck), "--output", str(pdf), "--browser", program, "--timeout", str(timeout)], timeout + 60)
    field("pdf", check_pdf(pdf, presented))

    images = workspace / f"{stem}-render"
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


def check_default_selection(deck: Path, presented: int, workspace: Path, timeout: float) -> str:
    """Print and render without --browser, as a user would, and report what was chosen."""
    pdf = workspace / "default.pdf"
    result = run_quarkfoil(["print", str(deck), "--output", str(pdf), "--timeout", str(timeout)], timeout * 4)
    field("pdf", check_pdf(pdf, presented))
    chosen = re.search(r"printed with (.+)$", result.stdout.strip())
    result = run_quarkfoil(
        ["deck", "render", str(deck), "--slides", "1", "--output", str(workspace / "default-render"),
         "--timeout", str(timeout), "--compact"],
        timeout * 4,
    )
    image = json.loads(result.stdout)["images"][0]
    field("slide 1", check_png(Path(image["file"])))
    return chosen.group(1) if chosen else "unknown"


def discover(names: list[str] | None) -> tuple[list[tuple[str, str]], list[str]]:
    """The browsers to test: every distinct installed one, or those named."""
    if not names:
        try:
            return browser_candidates(), []
        except RuntimeError:
            return [], ["any browser"]
    found, missing = [], []
    for name in names:
        program = find_executable((name,))
        (found.append((browser_kind(program), program)) if program else missing.append(name))
    return found, missing


FAMILIES = {"chromium": "Chrome, Chromium, or Edge", "firefox": "Firefox"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check quarkfoil print and deck render in installed browsers")
    parser.add_argument("--browser", action="append",
                        help="Browser to test (repeatable; default: every distinct installed browser)")
    parser.add_argument("--deck", type=Path, default=DEFAULT_DECK, help="Presentation to print and render")
    parser.add_argument("--allow-missing", action="store_true",
                        help="Do not fail when a browser family is missing or none of its browsers starts")
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
            annotate("error", "Browser missing", f"{message} on {platform.platform()}")
            failures.append(message)

    results: list[tuple[str, str, str]] = []
    passed_families: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="quarkfoil-print-ci-") as directory:
        workspace = Path(directory)
        for kind, program in browsers:
            group(f"{kind}: {program}")
            try:
                details = check_browser(kind, program, deck, presented, workspace, args.timeout)
                results.append(("PASS", program, details.get("product", "")))
                passed_families.add(kind)
            except StartFailed as error:
                # A browser that cannot start on this machine is reported in
                # full. It fails the run only when it was named explicitly or
                # leaves its family without a browser that works (below);
                # Quarkfoil itself moves on to the next installed browser.
                print(f"  could not start:\n  {error}", flush=True)
                conclusion = ""
                if kind == "chromium":
                    try:
                        conclusion = diagnose_chromium_start(program)
                    except Exception:  # noqa: BLE001 - diagnostics must not hide the result
                        traceback.print_exc()
                if conclusion:
                    error = StartFailed(f"{error}\n  Diagnosis: {conclusion}")
                lines = str(error).splitlines()
                results.append(("NOSTART", program, (lines[1] if len(lines) > 1 else lines[0]).strip()[:200]))
                level = "error" if args.browser else "warning"
                annotate(level, f"{program} could not start", f"{error}\n{platform.platform()}")
                if args.browser:
                    failures.append(f"{program}: {error}")
            except Exception as error:  # noqa: BLE001 - report every browser, then fail
                traceback.print_exc()
                message = f"{program}: {error}"
                failures.append(message)
                results.append(("FAIL", program, str(error)[:200]))
                annotate("error", f"Print/render failed in {kind}", f"{message}\n{platform.platform()}")
            finally:
                end_group()

        if not args.browser:
            for kind, label in FAMILIES.items():
                if kind not in passed_families:
                    tried = [program for family, program in browsers if family == kind]
                    message = f"no {label} browser printed and rendered the deck (tried: {', '.join(tried) or 'none installed'})"
                    print(f"{'SKIP' if args.allow_missing else 'FAIL'}: {message}", flush=True)
                    if not args.allow_missing:
                        annotate("error", f"No working {label}", f"{message}\n{platform.platform()}")
                        failures.append(message)
            if browsers:
                group("Default browser selection (no --browser)")
                try:
                    chosen = check_default_selection(deck, presented, workspace, args.timeout)
                    field("chosen", chosen)
                    results.append(("PASS", "(default selection)", chosen))
                except Exception as error:  # noqa: BLE001
                    traceback.print_exc()
                    failures.append(f"default selection: {error}")
                    results.append(("FAIL", "(default selection)", str(error)[:200]))
                    annotate("error", "Default browser selection failed", f"{error}\n{platform.platform()}")
                finally:
                    end_group()

    print(f"\nSummary for {deck.name} ({presented} presented slides) on {platform.platform()}:", flush=True)
    for status, program, note in results:
        print(f"  {status:<8} {program}  {note}", flush=True)
    if not browsers:
        failures.append("no browser was tested")
    if failures:
        print(f"\n{len(failures)} failure(s).", flush=True)
        return 1
    print("\nPrinting and rendering work on this platform.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
