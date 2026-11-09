"""Drive a headless browser installed on this computer, without dependencies.

Printing and rendering both need to wait until the player has finished laying
out the slides, then take a PDF or a picture of exactly that state. Command
line switches such as ``--print-to-pdf`` and ``--screenshot`` cannot wait for
anything except a guess at elapsed time, so Quarkfoil talks to the browser over
its own automation protocol instead:

* Chrome, Chromium, Edge, and Brave speak the Chrome DevTools Protocol (CDP).
* Firefox speaks WebDriver BiDi.

Both protocols are JSON messages over a WebSocket on a loopback port that the
browser picks and records in its (throwaway) profile directory. This module
contains a minimal RFC 6455 client and one small adapter per protocol, exposing
the same four operations: load a page, wait for a condition, capture the
viewport as PNG, and print to PDF.
"""

from __future__ import annotations

import base64
import contextlib
import itertools
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

from .exporter import CHROMIUM_BROWSERS, find_executable


FIREFOX_BROWSERS = (
    "firefox", "firefox-esr", "firefox-developer-edition",
    "/Applications/Firefox.app/Contents/MacOS/firefox",
    r"C:\Program Files\Mozilla Firefox\firefox.exe",
    r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
)

STARTUP_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.1


class BrowserError(RuntimeError):
    """The browser could not be started, or refused or failed a command."""


class BrowserStartError(BrowserError):
    """The browser never became ready for automation; another one may be tried."""


def browser_kind(program: str) -> str:
    """Classify a browser by program name: Firefox speaks BiDi, the rest CDP."""
    return "firefox" if "firefox" in Path(program).name.lower() else "chromium"


def find_browser(preferred: str | None = None, *, purpose: str = "This") -> tuple[str, str]:
    """Return the kind and path of the browser to use."""
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
        f"{purpose} needs Chrome, Chromium, Edge, or Firefox on this computer; "
        "install one or name it with --browser"
    )


def browser_candidates(preferred: str | None = None, *, purpose: str = "This") -> list[tuple[str, str]]:
    """Every distinct installed browser worth trying, in order of preference.

    A named browser is the only candidate. Otherwise the Chromium family comes
    first and Firefox last, and names that resolve to the same program (such
    as ``chromium`` and ``chromium-browser``) count once, so a browser that
    cannot start is not retried under another name.
    """
    if preferred:
        return [find_browser(preferred, purpose=purpose)]
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in (*CHROMIUM_BROWSERS, *FIREFOX_BROWSERS):
        program = find_executable((name,))
        if not program:
            continue
        identity = os.path.normcase(os.path.realpath(program))
        if identity in seen:
            continue
        seen.add(identity)
        candidates.append((browser_kind(program), program))
    if not candidates:
        find_browser(purpose=purpose)  # raises the usual "needs a browser" error
    return candidates


# --- WebSocket --------------------------------------------------------------


class WebSocket:
    """Just enough of RFC 6455 for one loopback automation connection."""

    def __init__(self, host: str, port: int, path: str, timeout: float = 30.0) -> None:
        self._socket = socket.create_connection((host, port), timeout=timeout)
        try:
            self._handshake(host, port, path)
        except BaseException:
            self._socket.close()
            raise

    def _handshake(self, host: str, port: int, path: str) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        # No Origin header: both browsers refuse automation connections that
        # claim to come from a web page.
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._socket.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise BrowserError("The browser closed the automation connection during the handshake")
            response += chunk
        head, _, rest = response.partition(b"\r\n\r\n")
        self._buffer = bytearray(rest)
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status + b" ":
            raise BrowserError(f"The browser refused the automation connection: {status.decode(errors='replace')}")

    def settimeout(self, timeout: float | None) -> None:
        self._socket.settimeout(timeout)

    def _read(self, count: int) -> bytes:
        while len(self._buffer) < count:
            chunk = self._socket.recv(max(65536, count - len(self._buffer)))
            if not chunk:
                raise BrowserError("The browser closed the automation connection")
            self._buffer += chunk
        data = bytes(self._buffer[:count])
        del self._buffer[:count]
        return data

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 1 << 16:
            header.append(0x80 | 126)
            header += struct.pack("!H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._socket.sendall(bytes(header) + mask + masked)

    def send(self, text: str) -> None:
        self._send_frame(0x1, text.encode("utf-8"))

    def receive(self) -> str:
        message = bytearray()
        while True:
            first, second = self._read(2)
            opcode, final = first & 0x0F, bool(first & 0x80)
            length = second & 0x7F
            if length == 126:
                (length,) = struct.unpack("!H", self._read(2))
            elif length == 127:
                (length,) = struct.unpack("!Q", self._read(8))
            mask = self._read(4) if second & 0x80 else None
            payload = self._read(length)
            if mask:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                raise BrowserError("The browser closed the automation connection")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            message += payload
            if final:
                return message.decode("utf-8")

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._send_frame(0x8, b"")
        with contextlib.suppress(OSError):
            self._socket.close()


# --- Protocol adapters ------------------------------------------------------


class _Session:
    """Shared request/response bookkeeping; events are read and discarded."""

    def __init__(self, connection: WebSocket) -> None:
        self._connection = connection
        self._ids = itertools.count(1)
        # What the browser says about itself, for reports and error audits.
        self.details: dict[str, str] = {}

    def _request(self, message: dict[str, Any], timeout: float) -> dict[str, Any]:
        identifier = next(self._ids)
        self._connection.settimeout(timeout)
        self._connection.send(json.dumps({"id": identifier, **message}))
        deadline = time.monotonic() + timeout
        while True:
            try:
                reply = json.loads(self._connection.receive())
            except (socket.timeout, TimeoutError) as error:
                raise BrowserError(f"The browser did not answer {message.get('method')}") from error
            if reply.get("id") == identifier:
                return reply
            if time.monotonic() > deadline:
                raise BrowserError(f"The browser did not answer {message.get('method')}")


class ChromiumPage(_Session):
    """One page target, driven through the Chrome DevTools Protocol."""

    def __init__(self, connection: WebSocket, width: int, height: int) -> None:
        super().__init__(connection)
        version = self._browser("Browser.getVersion")
        self.details = {
            "protocol": f"CDP {version.get('protocolVersion', '?')}",
            "product": str(version.get("product", "")),
            "user_agent": str(version.get("userAgent", "")),
        }
        target = self._browser("Target.createTarget", {"url": "about:blank"})["targetId"]
        self._session = self._browser("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        self.command("Page.enable")
        self.set_viewport(width, height)

    def _browser(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
        reply = self._request({"method": method, "params": params or {}}, timeout)
        if "error" in reply:
            raise BrowserError(f"{method}: {reply['error'].get('message', reply['error'])}")
        return reply.get("result", {})

    def command(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
        reply = self._request({"method": method, "params": params or {}, "sessionId": self._session}, timeout)
        if "error" in reply:
            raise BrowserError(f"{method}: {reply['error'].get('message', reply['error'])}")
        return reply.get("result", {})

    def set_viewport(self, width: int, height: int) -> None:
        self.command("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
        })

    def navigate(self, url: str) -> None:
        result = self.command("Page.navigate", {"url": url})
        if result.get("errorText"):
            raise BrowserError(f"Could not open {url}: {result['errorText']}")

    def evaluate(self, expression: str) -> Any:
        result = self.command("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if "exceptionDetails" in result:
            raise BrowserError(result["exceptionDetails"].get("text", "Script failed"))
        return result.get("result", {}).get("value")

    def screenshot(self) -> bytes:
        return base64.b64decode(self.command("Page.captureScreenshot", {"format": "png"})["data"])

    def print_pdf(self, width_inches: float, height_inches: float, timeout: float) -> bytes:
        result = self.command("Page.printToPDF", {
            "printBackground": True,
            "preferCSSPageSize": True,
            "paperWidth": width_inches,
            "paperHeight": height_inches,
            "marginTop": 0, "marginBottom": 0, "marginLeft": 0, "marginRight": 0,
            "displayHeaderFooter": False,
        }, timeout=timeout)
        return base64.b64decode(result["data"])

    def close(self) -> None:
        with contextlib.suppress(BrowserError, OSError):
            self._browser("Browser.close", timeout=5)


class FirefoxPage(_Session):
    """The first browsing context of a WebDriver BiDi session."""

    def __init__(self, connection: WebSocket, width: int, height: int) -> None:
        super().__init__(connection)
        capabilities = self.command("session.new", {"capabilities": {}}).get("capabilities", {})
        self.details = {
            "protocol": "WebDriver BiDi",
            "product": f"{capabilities.get('browserName', '?')}/{capabilities.get('browserVersion', '?')}",
            "user_agent": str(capabilities.get("userAgent", "")),
            "platform": str(capabilities.get("platformName", "")),
        }
        contexts = self.command("browsingContext.getTree", {"maxDepth": 0})["contexts"]
        if not contexts:
            raise BrowserError("Firefox opened no browsing context")
        self._context = contexts[0]["context"]
        self.set_viewport(width, height)

    def command(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
        reply = self._request({"method": method, "params": params or {}}, timeout)
        if reply.get("type") == "error":
            raise BrowserError(f"{method}: {reply.get('message') or reply.get('error')}")
        return reply.get("result", {})

    def set_viewport(self, width: int, height: int) -> None:
        self.command("browsingContext.setViewport", {
            "context": self._context, "viewport": {"width": width, "height": height}, "devicePixelRatio": 1,
        })

    def navigate(self, url: str) -> None:
        self.command("browsingContext.navigate", {"context": self._context, "url": url, "wait": "interactive"})

    def evaluate(self, expression: str) -> Any:
        result = self.command("script.evaluate", {
            "expression": expression, "target": {"context": self._context}, "awaitPromise": False,
        })
        if result.get("type") == "exception":
            details = result.get("exceptionDetails", {})
            raise BrowserError(details.get("text", "Script failed"))
        return result.get("result", {}).get("value")

    def screenshot(self) -> bytes:
        result = self.command("browsingContext.captureScreenshot", {"context": self._context, "origin": "viewport"})
        return base64.b64decode(result["data"])

    def print_pdf(self, width_inches: float, height_inches: float, timeout: float) -> bytes:
        result = self.command("browsingContext.print", {
            "context": self._context,
            "background": True,
            "margin": {"top": 0, "bottom": 0, "left": 0, "right": 0},
            "page": {"width": width_inches * 2.54, "height": height_inches * 2.54},
            "shrinkToFit": False,
        }, timeout=timeout)
        return base64.b64decode(result["data"])

    def close(self) -> None:
        with contextlib.suppress(BrowserError, OSError):
            self.command("browser.close", timeout=5)


# --- Launching --------------------------------------------------------------


# Keep the throwaway Firefox profile quiet: no first-run page, update check, or
# session restore competing with the page Quarkfoil opens.
FIREFOX_PREFERENCES = {
    "browser.shell.checkDefaultBrowser": False,
    "browser.startup.homepage_override.mstone": "ignore",
    "browser.sessionstore.resume_from_crash": False,
    "datareporting.policy.dataSubmissionEnabled": False,
    "toolkit.telemetry.reportingpolicy.firstRun": False,
    "app.update.auto": False,
}


def launch_command(kind: str, program: str, profile: Path) -> list[str]:
    """Command line that starts a headless browser listening on a free loopback port."""
    if kind == "firefox":
        # --no-remote keeps this out of a Firefox the user already has open.
        return [program, "--headless", "--no-remote", "--profile", str(profile),
                "--remote-debugging-port", "0", "about:blank"]
    return [
        program,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-extensions",
        f"--user-data-dir={profile}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=0",
        "about:blank",
    ]


# Both browsers also announce the endpoint on their console. That is the only
# source for Firefox releases that predate WebDriverBiDiServer.json, and for
# sandboxed packages (such as snaps) whose view of the temporary directory
# differs from Quarkfoil's.
ANNOUNCED_ENDPOINT = re.compile(r"(?:DevTools|WebDriver BiDi) listening on ws://([0-9.]+|\[[0-9a-f:]+\]|localhost):(\d+)(/\S*)?")


def read_endpoint(kind: str, profile: Path, log: Path | None = None) -> tuple[str, int, str] | None:
    """The host, port, and path the browser recorded in its profile or console, once it has."""
    try:
        if kind == "firefox":
            data = json.loads((profile / "WebDriverBiDiServer.json").read_text(encoding="utf-8"))
            return str(data["ws_host"]), int(data["ws_port"]), "/session"
        lines = (profile / "DevToolsActivePort").read_text(encoding="utf-8").split()
        return "127.0.0.1", int(lines[0]), lines[1]
    except (OSError, ValueError, KeyError, IndexError):
        pass
    if log is None:
        return None
    try:
        console = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = ANNOUNCED_ENDPOINT.search(console)
    if not match:
        return None
    host, port, path = match.group(1).strip("[]"), int(match.group(2)), match.group(3)
    return host, port, ("/session" if kind == "firefox" else path or "/")


SANDBOX_HINT = (
    "Chromium could not start its sandbox. On Ubuntu 23.10 and later AppArmor "
    "blocks it for Chromium builds installed without an AppArmor profile; use a "
    "packaged Google Chrome, Edge, or Firefox, named with --browser if needed."
)


STACK_FRAME = re.compile(r"#\d+\s+0x[0-9a-f]+", re.IGNORECASE)


def log_excerpt(log: Path, *, lines: int = 6) -> str:
    """The lines of a browser's console that explain why it stopped.

    A crashing Chromium ends its output with a stack trace, so the last line
    alone ("[end of stack trace]") says nothing. Report every FATAL line, then
    the last few lines, and recognise the common sandbox failure.
    """
    try:
        console = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    reported = [line.strip()[:300] for line in console if line.strip()]
    fatal = [line for line in reported if "FATAL" in line][:3]
    # Stack frames ("#12 0x55d4... (/opt/chrome+0x...)") are noise to a reader.
    readable = [line for line in reported if not STACK_FRAME.match(line)]
    chosen = fatal + [line for line in readable[-lines:] if line not in fatal]
    excerpt = "\n  ".join(chosen)
    if any("sandbox" in line.lower() for line in reported):
        excerpt += f"\n  {SANDBOX_HINT}"
    return excerpt


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


@contextlib.contextmanager
def open_page(
    kind: str, program: str, *, width: int = 1280, height: int = 720, startup_timeout: float = STARTUP_TIMEOUT_SECONDS
) -> Iterator[ChromiumPage | FirefoxPage]:
    """Start a headless browser in a throwaway profile and yield one page of it."""
    workspace = Path(tempfile.mkdtemp(prefix="quarkfoil-browser-"))
    try:
        profile = workspace / "profile"
        profile.mkdir()
        if kind == "firefox":
            lines = [f"user_pref({json.dumps(name)}, {json.dumps(value)});" for name, value in FIREFOX_PREFERENCES.items()]
            (profile / "user.js").write_text("\n".join(lines) + "\n", encoding="utf-8")
        log = workspace / "browser.log"
        with log.open("wb") as stream:
            process = subprocess.Popen(
                launch_command(kind, program, profile), stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
            )
        page: ChromiumPage | FirefoxPage | None = None
        connection: WebSocket | None = None
        try:
            deadline = time.monotonic() + startup_timeout
            endpoint = None
            while endpoint is None:
                endpoint = read_endpoint(kind, profile, log)
                if endpoint is not None:
                    break
                if process.poll() is not None:
                    detail = log_excerpt(log)
                    raise BrowserStartError(
                        f"The browser stopped before it was ready (exit {process.returncode})"
                        + (f":\n  {detail}" if detail else "")
                    )
                if time.monotonic() > deadline:
                    detail = log_excerpt(log)
                    raise BrowserStartError(
                        "Timed out waiting for the browser to start" + (f":\n  {detail}" if detail else "")
                    )
                time.sleep(POLL_INTERVAL_SECONDS)
            connection = WebSocket(*endpoint)
            page = (FirefoxPage if kind == "firefox" else ChromiumPage)(connection, width, height)
            yield page
        finally:
            if page is not None:
                page.close()
            if connection is not None:
                connection.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _stop(process)
    finally:
        # Firefox may still be releasing profile files for a moment.
        for _ in range(20):
            shutil.rmtree(workspace, ignore_errors=True)
            if not workspace.exists():
                break
            time.sleep(0.1)


@contextlib.contextmanager
def open_first_page(
    candidates: list[tuple[str, str]], *, width: int = 1280, height: int = 720,
    startup_timeout: float = STARTUP_TIMEOUT_SECONDS,
) -> Iterator[tuple[ChromiumPage | FirefoxPage, str]]:
    """Yield a page of the first candidate browser that starts, and its program.

    Only a failure to start moves on to the next candidate, with a note on
    stderr; once a browser is running, its errors are the caller's.
    """
    failures: list[str] = []
    for index, (kind, program) in enumerate(candidates):
        stack = contextlib.ExitStack()
        try:
            page = stack.enter_context(
                open_page(kind, program, width=width, height=height, startup_timeout=startup_timeout)
            )
        except BrowserStartError as error:
            failures.append(f"{program}: {error}")
            if index + 1 < len(candidates):
                print(f"quarkfoil: {program} could not start; trying {candidates[index + 1][1]}\n  {error}",
                      file=sys.stderr, flush=True)
            continue
        with stack:
            yield page, program
        return
    if len(failures) == 1:
        raise BrowserStartError(failures[0])
    raise BrowserStartError("No installed browser could be started:\n" + "\n".join(failures))


def wait_for(page: ChromiumPage | FirefoxPage, expression: str, timeout: float) -> Any:
    """Evaluate `expression` until it returns something truthy.

    A string beginning with ``error:`` is the page reporting a failure and is
    raised. Evaluation errors while a page is still loading are retried.
    """
    deadline = time.monotonic() + timeout
    last_error = ""
    while True:
        try:
            value = page.evaluate(expression)
        except BrowserError as error:
            value, last_error = None, str(error)
        if isinstance(value, str) and value.startswith("error:"):
            raise BrowserError(value[len("error:"):].strip())
        if value:
            return value
        if time.monotonic() > deadline:
            raise BrowserError("Timed out waiting for the presentation to finish rendering" + (f": {last_error}" if last_error else ""))
        time.sleep(POLL_INTERVAL_SECONDS)


__all__ = [
    "BrowserError",
    "BrowserStartError",
    "browser_candidates",
    "log_excerpt",
    "open_first_page",
    "ChromiumPage",
    "FIREFOX_BROWSERS",
    "FirefoxPage",
    "WebSocket",
    "browser_kind",
    "find_browser",
    "launch_command",
    "open_page",
    "read_endpoint",
    "wait_for",
]
