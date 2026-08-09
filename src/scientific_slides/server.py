from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PACKAGE_APP_ROOT = Path(__file__).resolve().parent / "app"
SOURCE_APP_ROOT = Path(__file__).resolve().parents[2] / "app"
APP_ROOT = PACKAGE_APP_ROOT if PACKAGE_APP_ROOT.is_dir() else SOURCE_APP_ROOT
MAX_WRITE_BYTES = 20 * 1024 * 1024
MAX_ASSET_BYTES = 100 * 1024 * 1024
MAX_BIBLIOGRAPHY_BYTES = 5 * 1024 * 1024
MAX_DOI_BYTES = 1024 * 1024
MAX_LISTED_ASSETS = 1000
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
VIDEO_SUFFIXES = {".mp4", ".webm"}
ASSET_SUFFIXES = IMAGE_SUFFIXES | VIDEO_SUFFIXES
STARTER_DECK = """---
title: New presentation
author: Your name
aspect-ratio: 16:9
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


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _python_snapshot(root: Path) -> tuple[tuple[str, int, int], ...]:
    snapshot = []
    for path in sorted(root.rglob("*.py")):
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot.append((path.relative_to(root).as_posix(), stat.st_mtime_ns, stat.st_size))
    return tuple(snapshot)


def _app_reload_token() -> str:
    entries = []
    for path in sorted(APP_ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".html", ".js", ".css"} or "vendor" in path.parts:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(f"{path.relative_to(APP_ROOT).as_posix()}:{stat.st_mtime_ns}:{stat.st_size}")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def _watch_python_changes(server: ThreadingHTTPServer, stop: threading.Event, reload_requested: threading.Event) -> None:
    root = Path(__file__).resolve().parent
    baseline = _python_snapshot(root)
    while not stop.wait(0.5):
        if _python_snapshot(root) != baseline:
            reload_requested.set()
            server.shutdown()
            return


def initialize_deck(deck: Path) -> Path:
    resolved = deck.resolve()
    if resolved.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("Presentation source must be Markdown")
    if not resolved.parent.is_dir():
        raise FileNotFoundError(f"Presentation directory not found: {resolved.parent}")
    if not resolved.exists():
        with resolved.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(STARTER_DECK)
        return resolved
    if not resolved.is_file():
        raise FileNotFoundError(f"Presentation is not a file: {resolved}")

    current = resolved.read_bytes()
    if current.strip():
        return resolved
    fd, temporary = tempfile.mkstemp(prefix=".quarkfoil-starter-", suffix=".tmp", dir=resolved.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(STARTER_DECK.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        if resolved.read_bytes() != current:
            raise RuntimeError("Presentation changed while it was being initialized")
        os.replace(temporary, resolved)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return resolved


class SlideHandler(SimpleHTTPRequestHandler):
    server_version = "Quarkfoil/0.2.0"

    @property
    def project_root(self) -> Path:
        return self.server.project_root  # type: ignore[attr-defined]

    @property
    def deck_path(self) -> Path:
        return self.server.deck_path  # type: ignore[attr-defined]

    def end_headers(self) -> None:
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' blob: data:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        if getattr(self.server, "verbose", False):
            print(f"{self.address_string()} - {format % args}")

    def _send_json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = _json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self, limit: int) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid Content-Length") from error
        if length < 0 or length > limit:
            raise ValueError(f"Request exceeds {limit} bytes")
        return self.rfile.read(length)

    def _project_file(self, relative: str) -> Path:
        decoded = urllib.parse.unquote(relative).replace("\\", "/")
        candidate = (self.project_root / decoded).resolve()
        if not _inside(self.project_root, candidate):
            raise PermissionError("Path leaves the selected project")
        return candidate

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/config":
            self._send_json(
                {
                    "mode": "local",
                    "deck": self.deck_path.relative_to(self.project_root).as_posix(),
                    "projectName": self.project_root.name,
                    "reload": getattr(self.server, "reload", True),
                }
            )
            return
        if parsed.path == "/api/reload":
            self._send_json({"token": _app_reload_token()})
            return
        if parsed.path == "/api/bibliography":
            try:
                relative = urllib.parse.parse_qs(parsed.query).get("path", ["references.bib"])[0]
                path = self._project_file(relative)
                if path.suffix.lower() != ".bib":
                    raise ValueError("Bibliography must be a .bib file")
                data = path.read_bytes() if path.is_file() else b""
                data.decode("utf-8")
                self._send_json({"source": data.decode("utf-8"), "hash": hashlib.sha256(data).hexdigest(), "path": path.relative_to(self.project_root).as_posix()})
            except (OSError, PermissionError, UnicodeDecodeError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/doi":
            doi = urllib.parse.parse_qs(parsed.query).get("doi", [""])[0]
            try:
                self._send_json({"doi": doi, "bibtex": fetch_doi_bibtex(doi)})
            except (OSError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_GATEWAY)
            return
        if parsed.path == "/api/assets":
            try:
                query = urllib.parse.parse_qs(parsed.query)
                relative = query.get("folder", ["figures"])[0]
                kind = query.get("kind", ["image"])[0]
                suffixes = IMAGE_SUFFIXES if kind == "image" else VIDEO_SUFFIXES if kind == "video" else None
                if suffixes is None:
                    raise ValueError("Asset kind must be image or video")
                folder = self._project_file(relative)
                if folder == self.project_root:
                    raise PermissionError("Asset folder must not be the project root")
                assets = []
                if folder.is_dir():
                    for path in sorted(folder.rglob("*"), key=lambda item: item.as_posix().lower()):
                        if len(assets) >= MAX_LISTED_ASSETS:
                            break
                        if path.is_file() and path.suffix.lower() in suffixes and _inside(folder, path):
                            assets.append({"path": path.relative_to(self.project_root).as_posix(), "name": path.name})
                self._send_json({"assets": assets, "folder": folder.relative_to(self.project_root).as_posix(), "truncated": len(assets) >= MAX_LISTED_ASSETS})
            except (OSError, PermissionError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/deck":
            data = self.deck_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path.startswith("/project/"):
            try:
                path = self._project_file(parsed.path[len("/project/") :])
            except PermissionError:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._send_project_asset(path)
            return
        if parsed.path in {"", "/"}:
            self.path = "/index.html"
        return super().do_GET()

    def _send_project_asset(self, path: Path, *, head_only: bool = False) -> None:
        size = path.stat().st_size
        start, end = 0, max(0, size - 1)
        status = HTTPStatus.OK
        requested_range = self.headers.get("Range")
        if requested_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested_range.strip())
            if not match or size == 0:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            elif last:
                length = min(int(last), size)
                start, end = size - length, size - 1
            if start >= size or start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1 if size else 0
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head_only:
            return
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = length
            while remaining:
                chunk = stream.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_HEAD(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path.startswith("/project/"):
            try:
                path = self._project_file(parsed.path[len("/project/") :])
            except PermissionError:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._send_project_asset(path, head_only=True)
            return
        return super().do_HEAD()

    def do_PUT(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/bibliography":
            try:
                relative = urllib.parse.parse_qs(parsed.query).get("path", ["references.bib"])[0]
                target = self._project_file(relative)
                if target.suffix.lower() != ".bib":
                    raise ValueError("Bibliography must be a .bib file")
                body = self._read_body(MAX_BIBLIOGRAPHY_BYTES)
                body.decode("utf-8")
                current = target.read_bytes() if target.is_file() else b""
                expected = self.headers.get("If-Match")
                if expected and expected.strip('"') != hashlib.sha256(current).hexdigest():
                    self._send_json({"error": "Bibliography changed on disk"}, HTTPStatus.CONFLICT)
                    return
                fd, temporary = tempfile.mkstemp(prefix=".quarkfoil-bib-", suffix=".tmp", dir=target.parent)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
                self._send_json({"ok": True, "hash": hashlib.sha256(body).hexdigest()})
            except (OSError, PermissionError, UnicodeDecodeError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            finally:
                if "temporary" in locals() and os.path.exists(temporary):
                    os.unlink(temporary)
            return
        if parsed.path != "/api/deck":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = self._read_body(MAX_WRITE_BYTES)
            body.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        expected = self.headers.get("If-Match")
        current = self.deck_path.read_bytes() if self.deck_path.exists() else b""
        current_hash = hashlib.sha256(current).hexdigest()
        if expected and expected.strip('"') != current_hash:
            self._send_json(
                {"error": "Deck changed on disk", "currentHash": current_hash},
                HTTPStatus.CONFLICT,
            )
            return

        fd, temporary = tempfile.mkstemp(prefix=".slides-", suffix=".tmp", dir=self.deck_path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.deck_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self._send_json({"ok": True, "hash": hashlib.sha256(body).hexdigest()})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/api/asset":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        query = urllib.parse.parse_qs(parsed.query)
        requested = Path(query.get("name", ["asset.bin"])[0]).name
        folder = query.get("folder", ["figures"])[0]
        if requested in {"", ".", ".."}:
            requested = "asset.bin"
        try:
            body = self._read_body(MAX_ASSET_BYTES)
        except ValueError as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        try:
            asset_dir = self._project_file(folder)
            if asset_dir == self.project_root:
                raise PermissionError("Asset folder must not be the project root")
            asset_dir.mkdir(parents=True, exist_ok=True)
            if not asset_dir.is_dir():
                raise ValueError("Asset folder is not a directory")
        except (OSError, PermissionError, ValueError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        stem, suffix = Path(requested).stem, Path(requested).suffix.lower()
        if suffix not in ASSET_SUFFIXES:
            self._send_json({"error": "Unsupported image or video type"}, HTTPStatus.BAD_REQUEST)
            return
        candidate = asset_dir / f"{stem}{suffix}"
        counter = 2
        while candidate.exists():
            candidate = asset_dir / f"{stem}-{counter}{suffix}"
            counter += 1
        candidate.write_bytes(body)
        relative = candidate.relative_to(self.project_root).as_posix()
        self._send_json({"ok": True, "path": relative}, HTTPStatus.CREATED)


def create_server(deck: Path, host: str, port: int, *, verbose: bool = False, reload: bool = True) -> ThreadingHTTPServer:
    resolved = initialize_deck(deck)
    server = ThreadingHTTPServer((host, port), lambda *args, **kwargs: SlideHandler(*args, directory=APP_ROOT, **kwargs))
    server.project_root = resolved.parent  # type: ignore[attr-defined]
    server.deck_path = resolved  # type: ignore[attr-defined]
    server.verbose = verbose  # type: ignore[attr-defined]
    server.reload = reload  # type: ignore[attr-defined]
    return server


def fetch_doi_bibtex(value: str) -> str:
    doi = urllib.parse.unquote(value).strip()
    doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:").strip()
    if not re.fullmatch(r"10\.\d{4,9}/\S{1,500}", doi, re.IGNORECASE):
        raise ValueError("Invalid DOI")
    request = urllib.request.Request(
        f"https://doi.org/{urllib.parse.quote(doi, safe='/():;._-')}",
        headers={"Accept": "application/x-bibtex", "User-Agent": "Quarkfoil/0.2.0 (BibTeX DOI import)"},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        data = response.read(MAX_DOI_BYTES + 1)
    if len(data) > MAX_DOI_BYTES:
        raise ValueError("DOI metadata response is too large")
    text = data.decode("utf-8").strip()
    if not text.startswith("@"):
        raise ValueError("DOI service did not return BibTeX")
    return text + "\n"


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["export"]:
        from .exporter import export_presentation

        export_parser = argparse.ArgumentParser(
            prog="quarkfoil export",
            description="Export a Quarkfoil presentation as a static website",
        )
        export_parser.add_argument("deck", type=Path, help="Markdown presentation to export")
        export_parser.add_argument("--output", "-o", type=Path, required=True, help="New directory to create")
        assets = export_parser.add_mutually_exclusive_group()
        assets.add_argument("--assets", choices=("local", "cdn"), default="local", help="Dependency source (default: local)")
        assets.add_argument("--cdn", dest="assets", action="store_const", const="cdn", help="Use pinned jsDelivr dependencies")
        export_args = export_parser.parse_args(arguments[1:])
        destination = export_presentation(export_args.deck, export_args.output, assets=export_args.assets)
        print(f"Exported Quarkfoil presentation to {destination}")
        print(f"Serve {destination / 'index.html'} from any static web server")
        return 0

    parser = argparse.ArgumentParser(description="Open a scientific Markdown presentation in Quarkfoil")
    parser.add_argument("deck", type=Path, help="Markdown presentation to open")
    parser.add_argument("--host", default="127.0.0.1", help="Address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to use; 0 chooses an available port (default: 8765)")
    parser.add_argument("--verbose", action="store_true", help="Log HTTP requests")
    reload_group = parser.add_mutually_exclusive_group()
    reload_group.add_argument("--reload", dest="reload", action="store_true", default=True, help="Restart when Quarkfoil Python files change (default)")
    reload_group.add_argument("--no-reload", dest="reload", action="store_false", help="Disable automatic server restarts")
    browser = parser.add_mutually_exclusive_group()
    browser.add_argument("--open", dest="open_browser", action="store_true", default=True, help="Open the editor in a browser (default)")
    browser.add_argument("--no-open", dest="open_browser", action="store_false", help="Start the server without opening a browser")
    args = parser.parse_args(arguments)
    server = create_server(args.deck, args.host, args.port, verbose=args.verbose, reload=args.reload)
    url = f"http://{args.host}:{server.server_port}/"
    print(f"Quarkfoil: {args.deck.resolve()}")
    print(f"Open {url}")
    if args.open_browser and os.environ.get("QUARKFOIL_RELOADED") != "1":
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    reload_requested = threading.Event()
    watcher_stop = threading.Event()
    watcher = None
    if args.reload:
        watcher = threading.Thread(target=_watch_python_changes, args=(server, watcher_stop, reload_requested), daemon=True)
        watcher.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        watcher_stop.set()
        server.server_close()
        if watcher:
            watcher.join(timeout=1)
    if reload_requested.is_set():
        print("Quarkfoil changed; restarting…")
        environment = os.environ.copy()
        environment["QUARKFOIL_RELOADED"] = "1"
        os.execve(sys.executable, [sys.executable, "-m", "scientific_slides", *arguments], environment)
    return 0
