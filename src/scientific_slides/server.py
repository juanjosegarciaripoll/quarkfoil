from __future__ import annotations

import argparse
import hashlib
import json
import math
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PACKAGE_APP_ROOT = Path(__file__).resolve().parent / "app"
SOURCE_APP_ROOT = Path(__file__).resolve().parents[2] / "app"
APP_ROOT = PACKAGE_APP_ROOT if PACKAGE_APP_ROOT.is_dir() else SOURCE_APP_ROOT
MAX_WRITE_BYTES = 20 * 1024 * 1024
MAX_ASSET_BYTES = 100 * 1024 * 1024
MAX_VIDEO_CONVERSION_BYTES = 2 * 1024 * 1024 * 1024
MAX_BIBLIOGRAPHY_BYTES = 5 * 1024 * 1024
MAX_DOI_BYTES = 1024 * 1024
MAX_LISTED_ASSETS = 1000
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
VIDEO_SUFFIXES = {".mp4", ".webm"}
PRESENTATION_SUFFIXES = {".md", ".markdown"}
CONVERTIBLE_VIDEO_SUFFIXES = {".avi", ".mkv"}
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


class VideoConversionJob:
    def __init__(self, source: Path, output: Path, poster: Path, project_root: Path, command: list[str]):
        self.id = uuid.uuid4().hex
        self.source = source
        self.output = output
        self.poster = poster
        self.project_root = project_root
        self.command = command
        self.status = "queued"
        self.progress: float | None = 0.0
        self.error = ""
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None
        self.cancelled = threading.Event()
        self.lock = threading.Lock()

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            result: dict[str, object] = {
                "id": self.id,
                "status": self.status,
                "progress": round(self.progress, 1) if self.progress is not None else None,
                "path": self.output.relative_to(self.project_root).as_posix(),
                "poster": self.poster.relative_to(self.project_root).as_posix(),
            }
            if self.error:
                result["error"] = self.error
            return result

    def cancel(self) -> None:
        self.cancelled.set()
        with self.lock:
            process = self.process
        if process and process.poll() is None:
            process.terminate()


def _video_duration(source: Path) -> float | None:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=duration", "-of", "json", str(source)],
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    metadata = json.loads(result.stdout)
    values = [metadata.get("format", {}).get("duration")]
    values.extend(stream.get("duration") for stream in metadata.get("streams", []))
    for value in values:
        try:
            duration = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(duration) and duration > 0:
            return duration
    return None


def _video_codecs(source: Path) -> tuple[str | None, str | None]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(source)],
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    streams = json.loads(result.stdout).get("streams", [])
    video = next((item.get("codec_name") for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item.get("codec_name") for item in streams if item.get("codec_type") == "audio"), None)
    return video, audio


def _ffmpeg_encoders() -> set[str]:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-encoders"], capture_output=True, check=True, text=True, timeout=30,
    )
    return {match.group(1) for line in result.stdout.splitlines() if (match := re.match(r"^\s*[VAS.].....\s+(\S+)", line))}


def _video_conversion_plan(source: Path) -> tuple[str, list[str]]:
    video, audio = _video_codecs(source)
    encoders = _ffmpeg_encoders()
    h264_encoder = next((name for name in ("libx264", "libopenh264") if name in encoders), None)
    if video == "h264" or h264_encoder:
        video_args = ["-c:v", "copy"] if video == "h264" else ["-c:v", h264_encoder, "-crf", "23", "-preset", "veryfast"]
        audio_args = ["-c:a", "copy"] if audio in {None, "aac", "mp3"} else ["-c:a", "aac", "-b:a", "128k"]
        return ".mp4", [*video_args, *audio_args, "-movflags", "+faststart"]
    return ".webm", [
        "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-deadline", "good", "-cpu-used", "6", "-row-mt", "1",
        "-c:a", "libopus", "-b:a", "128k",
    ]


def _video_progress(value: str, duration: float | None) -> float | None:
    if not duration:
        return None
    try:
        elapsed = float(value)
    except ValueError:
        return None
    if not math.isfinite(elapsed):
        return None
    return min(99.0, elapsed / 1_000_000 / duration * 100)


def _run_video_conversion(job: VideoConversionJob) -> None:
    temporary = job.output.with_name(f".{job.output.stem}.{job.id}.tmp{job.output.suffix}")
    temporary_poster = job.poster.with_name(f".{job.poster.name}.{job.id}.tmp.jpg")
    try:
        if job.cancelled.is_set():
            raise RuntimeError("Conversion cancelled")
        with job.lock:
            job.status = "extracting"
            job.process = subprocess.Popen(
                [
                    "ffmpeg", "-v", "error", "-i", str(job.source), "-map", "0:v:0", "-an", "-sn", "-dn",
                    "-frames:v", "1", "-q:v", "2", "-y", str(temporary_poster),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            process = job.process
        try:
            _, stderr = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError("FFmpeg took too long to extract a preview frame")
        if job.cancelled.is_set():
            raise RuntimeError("Conversion cancelled")
        if process.returncode:
            raise RuntimeError(stderr.strip() or "FFmpeg could not extract a preview frame")
        os.replace(temporary_poster, job.poster)
        duration = _video_duration(job.source)
        if job.cancelled.is_set():
            raise RuntimeError("Conversion cancelled")
        command = [
            "ffmpeg", "-v", "error", "-i", str(job.source), "-map", "0:v:0", "-map", "0:a?",
            *job.command,
            "-progress", "pipe:1", "-nostats", "-y", str(temporary),
        ]
        with job.lock:
            job.status = "converting"
            job.progress = 0.0 if duration else None
            job.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            process = job.process
        assert process.stdout is not None
        for line in process.stdout:
            key, _, value = line.strip().partition("=")
            if duration and key in {"out_time_us", "out_time_ms"}:
                progress = _video_progress(value, duration)
                if progress is not None:
                    with job.lock:
                        job.progress = progress
        _, stderr = process.communicate()
        if job.cancelled.is_set():
            raise RuntimeError("Conversion cancelled")
        if process.returncode:
            raise RuntimeError(stderr.strip() or "FFmpeg conversion failed")
        os.replace(temporary, job.output)
        with job.lock:
            job.status = "complete"
            job.progress = 100.0
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as error:
        with job.lock:
            job.status = "cancelled" if job.cancelled.is_set() else "failed"
            job.error = str(error)
    finally:
        job.source.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        temporary_poster.unlink(missing_ok=True)
        with job.lock:
            complete = job.status == "complete"
        if not complete:
            job.poster.unlink(missing_ok=True)


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

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # Browsers routinely cancel image/video responses when a preview
            # dialog closes or navigates away. That is not a server failure.
            return

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

    def _write_body(self, destination: Path, limit: int) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid Content-Length") from error
        if length < 0 or length > limit:
            raise ValueError(f"Request exceeds {limit} bytes")
        remaining = length
        with destination.open("xb") as stream:
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Upload ended before Content-Length bytes were received")
                stream.write(chunk)
                remaining -= len(chunk)
            stream.flush()
            os.fsync(stream.fileno())

    def _project_file(self, relative: str) -> Path:
        decoded = urllib.parse.unquote(relative).replace("\\", "/")
        candidate = (self.project_root / decoded).resolve()
        if not _inside(self.project_root, candidate):
            raise PermissionError("Path leaves the selected project")
        return candidate

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path.startswith("/api/video-conversion/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = self.server.video_jobs.get(job_id)  # type: ignore[attr-defined]
            if not job:
                self._send_json({"error": "Unknown video conversion"}, HTTPStatus.NOT_FOUND)
            else:
                self._send_json(job.snapshot())
            return
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
        if parsed.path == "/api/files":
            try:
                kind = urllib.parse.parse_qs(parsed.query).get("kind", ["presentation"])[0]
                suffixes = {"image": IMAGE_SUFFIXES, "video": VIDEO_SUFFIXES, "presentation": PRESENTATION_SUFFIXES}.get(kind)
                if suffixes is None:
                    raise ValueError("File kind must be presentation, image, or video")
                files = []
                for path in sorted(self.project_root.rglob("*"), key=lambda item: item.as_posix().lower()):
                    if len(files) >= MAX_LISTED_ASSETS:
                        break
                    if path.is_file() and path.suffix.lower() in suffixes and _inside(self.project_root, path):
                        files.append({"path": path.relative_to(self.project_root).as_posix(), "name": path.name})
                self._send_json({"files": files, "truncated": len(files) >= MAX_LISTED_ASSETS})
            except (OSError, PermissionError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/deck":
            try:
                relative = urllib.parse.parse_qs(parsed.query).get("path", [""])[0]
                path = self._project_file(relative) if relative else self.deck_path
                if path.suffix.lower() not in PRESENTATION_SUFFIXES or not path.is_file():
                    raise ValueError("Presentation must be an existing Markdown file")
                data = path.read_bytes()
            except (OSError, PermissionError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            digest = hashlib.sha256(data).hexdigest()
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                self._send_json({"error": "Presentation is not valid UTF-8", "hash": digest}, HTTPStatus.BAD_REQUEST)
                return
            if self.headers.get("If-None-Match", "").strip('"') == digest:
                self.send_response(HTTPStatus.NOT_MODIFIED)
                self.send_header("ETag", f'"{digest}"')
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("ETag", f'"{digest}"')
            self.send_header("Cache-Control", "no-store")
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
        if not expected:
            self._send_json({"error": "Deck saves require an If-Match revision"}, HTTPStatus.PRECONDITION_REQUIRED)
            return
        try:
            relative = urllib.parse.parse_qs(parsed.query).get("path", [""])[0]
            deck_path = self._project_file(relative) if relative else self.deck_path
            if deck_path.suffix.lower() not in PRESENTATION_SUFFIXES or not deck_path.is_file():
                raise ValueError("Presentation must be an existing Markdown file")
        except (OSError, PermissionError, ValueError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        with self.server.deck_write_lock:  # type: ignore[attr-defined]
            current = deck_path.read_bytes()
            current_hash = hashlib.sha256(current).hexdigest()
            if expected.strip('"') != current_hash:
                self._send_json(
                    {"error": "Deck changed on disk", "currentHash": current_hash},
                    HTTPStatus.CONFLICT,
                )
                return

            fd, temporary = tempfile.mkstemp(prefix=".slides-", suffix=".tmp", dir=deck_path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, deck_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        self._send_json({"ok": True, "hash": hashlib.sha256(body).hexdigest()})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/open":
            try:
                relative = urllib.parse.parse_qs(parsed.query).get("path", [""])[0]
                target = self._project_file(relative)
                if target.suffix.lower() not in PRESENTATION_SUFFIXES or not target.is_file():
                    raise ValueError("Presentation must be an existing Markdown file")
                data = target.read_bytes()
                data.decode("utf-8")
                self._send_json({"path": relative, "source": data.decode("utf-8"), "hash": hashlib.sha256(data).hexdigest()})
            except (OSError, PermissionError, UnicodeDecodeError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/presentation":
            query = urllib.parse.parse_qs(parsed.query)
            requested = Path(query.get("name", ["presentation.md"])[0]).name
            overwrite = query.get("overwrite", ["false"])[0].lower() == "true"
            temporary: str | None = None
            try:
                if Path(requested).suffix.lower() not in PRESENTATION_SUFFIXES:
                    raise ValueError("Presentation must be a Markdown file")
                body = self._read_body(MAX_WRITE_BYTES)
                body.decode("utf-8")
                candidate = self.project_root / requested
                if candidate.exists() and not overwrite:
                    self._send_json({"error": f"{requested} already exists"}, HTTPStatus.CONFLICT)
                    return
                fd, temporary = tempfile.mkstemp(prefix=".quarkfoil-import-", suffix=".tmp", dir=self.project_root)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, candidate)
                self._send_json({"path": candidate.relative_to(self.project_root).as_posix()}, HTTPStatus.CREATED)
            except (OSError, PermissionError, UnicodeDecodeError, ValueError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
            return
        if parsed.path == "/api/video-conversion":
            self._start_video_conversion(parsed)
            return
        if parsed.path != "/api/asset":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        query = urllib.parse.parse_qs(parsed.query)
        requested = Path(query.get("name", ["asset.bin"])[0]).name
        folder = query.get("folder", ["figures"])[0]
        overwrite = query.get("overwrite", ["false"])[0].lower() == "true"
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
        if candidate.exists() and not overwrite:
            self._send_json({"error": f"{candidate.name} already exists"}, HTTPStatus.CONFLICT)
            return
        fd, temporary = tempfile.mkstemp(prefix=".quarkfoil-asset-", suffix=".tmp", dir=asset_dir)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, candidate)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        relative = candidate.relative_to(self.project_root).as_posix()
        self._send_json({"ok": True, "path": relative}, HTTPStatus.CREATED)

    def _start_video_conversion(self, parsed: urllib.parse.SplitResult) -> None:
        query = urllib.parse.parse_qs(parsed.query)
        requested = Path(query.get("name", ["video"])[0]).name
        folder = query.get("folder", ["figures"])[0]
        overwrite = query.get("overwrite", ["false"])[0].lower() == "true"
        suffix = Path(requested).suffix.lower()
        if suffix not in CONVERTIBLE_VIDEO_SUFFIXES:
            self._send_json({"error": "Only AVI and MKV files require conversion"}, HTTPStatus.BAD_REQUEST)
            return
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self._send_json({"error": "AVI and MKV import requires ffmpeg and ffprobe on PATH"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        source: Path | None = None
        try:
            asset_dir = self._project_file(folder)
            if asset_dir == self.project_root:
                raise PermissionError("Asset folder must not be the project root")
            asset_dir.mkdir(parents=True, exist_ok=True)
            if not asset_dir.is_dir():
                raise ValueError("Asset folder is not a directory")
            source = asset_dir / f".quarkfoil-{uuid.uuid4().hex}{suffix}"
            self._write_body(source, MAX_VIDEO_CONVERSION_BYTES)
        except (OSError, PermissionError, ValueError) as error:
            if source:
                source.unlink(missing_ok=True)
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        try:
            output_suffix, command = _video_conversion_plan(source)
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as error:
            source.unlink(missing_ok=True)
            self._send_json({"error": f"Cannot inspect video: {error}"}, HTTPStatus.BAD_REQUEST)
            return
        stem = Path(requested).stem or "video"
        output = asset_dir / f"{stem}{output_suffix}"
        poster = output.with_name(f"{output.stem}-poster.jpg")
        if not overwrite and (output.exists() or poster.exists()):
            source.unlink(missing_ok=True)
            self._send_json({"error": f"{output.name} or its preview already exists"}, HTTPStatus.CONFLICT)
            return
        assert source is not None
        job = VideoConversionJob(source, output, poster, self.project_root, command)
        self.server.video_jobs[job.id] = job  # type: ignore[attr-defined]
        job.thread = threading.Thread(target=_run_video_conversion, args=(job,), daemon=True)
        job.thread.start()
        self._send_json(job.snapshot(), HTTPStatus.ACCEPTED)

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if not parsed.path.startswith("/api/video-conversion/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        job_id = parsed.path.rsplit("/", 1)[-1]
        job = self.server.video_jobs.get(job_id)  # type: ignore[attr-defined]
        if not job:
            self._send_json({"error": "Unknown video conversion"}, HTTPStatus.NOT_FOUND)
            return
        job.cancel()
        self._send_json({"ok": True})


class QuarkfoilServer(ThreadingHTTPServer):
    def server_close(self) -> None:
        for job in getattr(self, "video_jobs", {}).values():
            job.cancel()
        for job in getattr(self, "video_jobs", {}).values():
            if job.thread:
                job.thread.join(timeout=2)
        super().server_close()


def create_server(deck: Path, host: str, port: int, *, verbose: bool = False, reload: bool = True) -> ThreadingHTTPServer:
    resolved = initialize_deck(deck)
    server = QuarkfoilServer((host, port), lambda *args, **kwargs: SlideHandler(*args, directory=APP_ROOT, **kwargs))
    server.project_root = resolved.parent  # type: ignore[attr-defined]
    server.deck_path = resolved  # type: ignore[attr-defined]
    server.verbose = verbose  # type: ignore[attr-defined]
    server.reload = reload  # type: ignore[attr-defined]
    server.video_jobs = {}  # type: ignore[attr-defined]
    server.deck_write_lock = threading.Lock()  # type: ignore[attr-defined]
    return server


def _normalize_doi_bibtex(text: str) -> str:
    # DOI content negotiation sometimes returns nonstandard bare month names
    # such as ``month=Sept``. Bracing preserves the value and works with
    # parsers that only recognize the standard jan--dec macros.
    text = re.sub(r"(?im)(\bmonth\s*=\s*)([a-z]+)(?=\s*[,}])", r"\1{\2}", text)
    author_match = re.search(r'(?is)\bauthor\s*=\s*(?:\{([^}]*)\}|"([^"]*)")', text)
    year_match = re.search(r'(?i)\byear\s*=\s*[{"]?(\d{4})', text)
    if author_match and year_match:
        first_author = (author_match.group(1) or author_match.group(2)).split(" and ", 1)[0].strip()
        family_name = first_author.split(",", 1)[0] if "," in first_author else first_author.split()[-1]
        ascii_name = unicodedata.normalize("NFKD", family_name).encode("ascii", "ignore").decode("ascii").lower()
        family_key = re.sub(r"[^a-z0-9]", "", ascii_name)
        if family_key:
            citation_key = f"{family_key}{year_match.group(1)}"
            text = re.sub(r"(?is)(@\s*[a-z]+\s*\{)\s*[^,]+", rf"\g<1>{citation_key}", text, count=1)
    return text


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
    return _normalize_doi_bibtex(text) + "\n"


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
