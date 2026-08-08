from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PACKAGE_APP_ROOT = Path(__file__).resolve().parent / "app"
SOURCE_APP_ROOT = Path(__file__).resolve().parents[2] / "app"
APP_ROOT = PACKAGE_APP_ROOT if PACKAGE_APP_ROOT.is_dir() else SOURCE_APP_ROOT
MAX_WRITE_BYTES = 20 * 1024 * 1024
MAX_ASSET_BYTES = 100 * 1024 * 1024


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class SlideHandler(SimpleHTTPRequestHandler):
    server_version = "Quarkfoil/0.1"

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
                }
            )
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
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            data = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path in {"", "/"}:
            self.path = "/index.html"
        return super().do_GET()

    def do_PUT(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
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
        if requested in {"", ".", ".."}:
            requested = "asset.bin"
        try:
            body = self._read_body(MAX_ASSET_BYTES)
        except ValueError as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        asset_dir = self.project_root / "figures"
        asset_dir.mkdir(exist_ok=True)
        stem, suffix = Path(requested).stem, Path(requested).suffix.lower()
        allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
        if suffix not in allowed:
            self._send_json({"error": "Unsupported image type"}, HTTPStatus.BAD_REQUEST)
            return
        candidate = asset_dir / f"{stem}{suffix}"
        counter = 2
        while candidate.exists():
            candidate = asset_dir / f"{stem}-{counter}{suffix}"
            counter += 1
        candidate.write_bytes(body)
        relative = candidate.relative_to(self.project_root).as_posix()
        self._send_json({"ok": True, "path": relative}, HTTPStatus.CREATED)


def create_server(deck: Path, host: str, port: int) -> ThreadingHTTPServer:
    resolved = deck.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Presentation not found: {resolved}")
    if resolved.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("Presentation source must be Markdown")
    server = ThreadingHTTPServer((host, port), lambda *args, **kwargs: SlideHandler(*args, directory=APP_ROOT, **kwargs))
    server.project_root = resolved.parent  # type: ignore[attr-defined]
    server.deck_path = resolved  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open a scientific Markdown presentation in Quarkfoil")
    parser.add_argument("deck", type=Path, help="Markdown presentation to open")
    parser.add_argument("--host", default="127.0.0.1", help="Address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port to use; 0 chooses an available port (default: 8765)")
    browser = parser.add_mutually_exclusive_group()
    browser.add_argument("--open", dest="open_browser", action="store_true", default=True, help="Open the editor in a browser (default)")
    browser.add_argument("--no-open", dest="open_browser", action="store_false", help="Start the server without opening a browser")
    args = parser.parse_args(argv)
    server = create_server(args.deck, args.host, args.port)
    url = f"http://{args.host}:{server.server_port}/"
    print(f"Quarkfoil: {args.deck.resolve()}")
    print(f"Open {url}")
    if args.open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
