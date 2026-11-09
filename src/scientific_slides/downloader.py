"""Recover an editable Quarkfoil project from a published talk."""

from __future__ import annotations

import contextlib
import filecmp
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .exporter import _asset_references, _front_matter, _pack_conflicts, _publish
from .paths import inside as _inside


MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
USER_AGENT = "Quarkfoil published-talk downloader"


class DownloadError(RuntimeError):
    """A published talk could not be reconstructed safely."""


class _AssetMapParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.collecting = False
        self.chunks: list[str] = []
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.lower() == "script" and values.get("id") == "quarkfoil-assets":
            self.collecting = True
            self.found = True

    def handle_data(self, data: str) -> None:
        if self.collecting:
            self.chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.collecting:
            self.collecting = False


def _talk_url(value: str) -> str:
    parsed = urlsplit(str(value).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DownloadError("Talk URL must be an absolute http(s) URL")
    if parsed.query or parsed.fragment:
        raise DownloadError("Talk URL must not contain a query or fragment")
    path = parsed.path or "/"
    if path.endswith(("/index.html", "/presentation.md", "/meta.json")):
        path = path.rsplit("/", 1)[0] + "/"
    elif not path.endswith("/"):
        path += "/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _read_url(url: str, timeout: float, *, optional: bool = False) -> tuple[bytes, str] | None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_DOCUMENT_BYTES + 1)
            if len(data) > MAX_DOCUMENT_BYTES:
                raise DownloadError(f"Published document is too large: {url}")
            return data, response.geturl()
    except HTTPError as error:
        if optional and error.code == 404:
            return None
        raise DownloadError(f"Could not download {url}: HTTP {error.code}") from error
    except URLError as error:
        raise DownloadError(f"Could not download {url}: {error.reason}") from error
    except (TimeoutError, OSError) as error:
        raise DownloadError(f"Could not download {url}: {error}") from error


def _same_origin(url: str, origin: str) -> bool:
    candidate = urlsplit(url)
    expected = urlsplit(origin)
    try:
        candidate_port = candidate.port or (443 if candidate.scheme.lower() == "https" else 80)
        expected_port = expected.port or (443 if expected.scheme.lower() == "https" else 80)
    except ValueError:
        return False
    return (
        candidate.scheme.lower(), candidate.hostname or "", candidate_port
    ) == (
        expected.scheme.lower(), expected.hostname or "", expected_port
    )


def _download_file(url: str, destination: Path, timeout: float, origin: str) -> None:
    if not _same_origin(url, origin):
        raise DownloadError(f"Published asset points outside its collection: {url}")
    request = Request(url, headers={"User-Agent": USER_AGENT})
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=timeout) as response:
            if not _same_origin(response.geturl(), origin):
                raise DownloadError(f"Published asset redirects outside its collection: {url}")
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)
    except HTTPError as error:
        raise DownloadError(f"Could not download published asset {url}: HTTP {error.code}") from error
    except URLError as error:
        raise DownloadError(f"Could not download published asset {url}: {error.reason}") from error
    except (TimeoutError, OSError) as error:
        raise DownloadError(f"Could not download published asset {url}: {error}") from error


def _asset_map(index: str) -> dict[str, str]:
    parser = _AssetMapParser()
    parser.feed(index)
    if not parser.found:
        return {}
    try:
        value = json.loads("".join(parser.chunks))
    except json.JSONDecodeError as error:
        raise DownloadError("Published page has an unreadable asset map") from error
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(mapped, str) for key, mapped in value.items()
    ):
        raise DownloadError("Published page has an invalid asset map")
    return value


def _relative_asset(root: Path, value: str) -> tuple[Path, Path]:
    parsed = urlsplit(value.replace("\\", "/"))
    relative_text = unquote(parsed.path)
    if (
        parsed.scheme
        or parsed.netloc
        or relative_text.startswith("/")
        or re.match(r"^[A-Za-z]:", relative_text)
    ):
        raise DownloadError(f"Published asset path is not project-relative: {value}")
    relative = Path(relative_text)
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise DownloadError(f"Published asset path is unsafe: {value}")
    destination = (root / relative).resolve()
    if not _inside(root, destination):
        raise DownloadError(f"Published asset leaves the recovered project: {value}")
    return relative, destination


def _deck_name(requested: str | None, metadata: dict[str, object], talk_url: str) -> str:
    slug = unquote(urlsplit(talk_url).path.rstrip("/").rsplit("/", 1)[-1]) or "presentation"
    value = requested or (metadata.get("source") if isinstance(metadata.get("source"), str) else None)
    name = str(value or f"{slug}.md").strip()
    if not Path(name).suffix:
        name += ".md"
    if Path(name).name != name or Path(name).suffix.lower() not in {".md", ".markdown"}:
        raise DownloadError("Recovered deck name must be a Markdown file name without a directory")
    return name


def _recover(url: str, root: Path, *, name: str | None, timeout: float) -> tuple[str, str]:
    """Reconstruct the editable project of *url* inside the empty directory *root*.

    Returns the recovered deck's file name and the talk's slug.
    """
    talk_url = _talk_url(url)
    index_result = _read_url(urljoin(talk_url, "index.html"), timeout)
    source_result = _read_url(urljoin(talk_url, "presentation.md"), timeout)
    if index_result is None or source_result is None:  # Non-optional reads never return None.
        raise DownloadError("Published talk is incomplete")
    index_bytes, index_url = index_result
    source_bytes, source_url = source_result
    if not _same_origin(source_url, index_url):
        raise DownloadError("Published presentation redirects outside its collection")
    try:
        index = index_bytes.decode("utf-8")
        source = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DownloadError("Published page or presentation is not valid UTF-8") from error

    final_talk_url = urljoin(index_url, "./")
    origin = urlunsplit((*urlsplit(index_url)[:2], "", "", ""))
    mappings = _asset_map(index)
    try:
        metadata_result = _read_url(urljoin(final_talk_url, "meta.json"), timeout, optional=True)
    except DownloadError:
        metadata_result = None
    metadata: dict[str, object] = {}
    if metadata_result is not None:
        try:
            loaded = json.loads(metadata_result[0].decode("utf-8"))
            if isinstance(loaded, dict):
                metadata = loaded
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass  # Older or hand-edited metadata is not needed to recover the project.
    social = _front_matter(source).get("social")
    social_image = social.get("image") if isinstance(social, dict) else None
    published_social_image = metadata.get("social_image")
    normalized_social_image = (
        social_image.replace("\\", "/") if isinstance(social_image, str) else None
    )
    if (
        normalized_social_image
        and normalized_social_image not in mappings
        and isinstance(published_social_image, str)
        and published_social_image
    ):
        # Social images published before they joined the ordinary asset map can
        # still be recovered from the resolved URL recorded in meta.json.
        mappings[normalized_social_image] = published_social_image

    deck_name = _deck_name(name, metadata, final_talk_url)
    (root / deck_name).write_bytes(source_bytes)
    restored: set[Path] = set()
    for original, mapped in sorted(mappings.items()):
        relative, target = _relative_asset(root, original)
        if relative in restored or target.exists():
            raise DownloadError(f"Published asset paths collide after decoding: {original}")
        asset_url = urljoin(index_url, mapped)
        _download_file(asset_url, target, timeout, origin)
        restored.add(relative)

    references = _asset_references(source)
    if normalized_social_image:
        references.add(normalized_social_image)
    bibliography = _front_matter(source).get("bibliography")
    if isinstance(bibliography, str) and bibliography:
        references.add(bibliography)
    for reference in sorted(references):
        relative, target = _relative_asset(root, reference)
        if relative in restored:
            continue
        if target.exists():
            raise DownloadError(f"Published asset conflicts with the recovered deck: {reference}")
        asset_url = urljoin(final_talk_url, quote(relative.as_posix(), safe="/"))
        _download_file(asset_url, target, timeout, origin)
        restored.add(relative)
    slug = unquote(urlsplit(final_talk_url).path.rstrip("/").rsplit("/", 1)[-1])
    return deck_name, _safe_folder_name(slug) or Path(deck_name).stem


def _safe_folder_name(value: str) -> str:
    """A single portable path component for the folder inside a ZIP archive."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value).strip(" .")
    return cleaned if cleaned not in {"", ".", ".."} else ""


# Reproducible archives: the same project always gives the same bytes, so a
# repeated backup of an unchanged talk is recognised as identical.
ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


# Formats that are already compressed are stored as they are. Deflating them
# saves almost nothing, and a damaged byte in a stored file spoils only that
# byte, where in a deflated one it spoils the rest of the file.
STORED_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".heic", ".jxl",
    ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi",
    ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac",
    ".woff", ".woff2", ".pdf",
    ".zip", ".gz", ".tgz", ".bz2", ".xz", ".zst", ".7z", ".rar",
})


def _project_files(root: Path) -> list[tuple[str, Path]]:
    return sorted((path.relative_to(root).as_posix(), path) for path in root.rglob("*") if path.is_file())


def write_project_archive(root: Path, folder: str, target: Path) -> None:
    """Write every file under *root* to a ZIP at *target*, inside *folder*/."""
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, path in _project_files(root):
            info = zipfile.ZipInfo(f"{folder}/{relative}", date_time=ARCHIVE_TIMESTAMP)
            stored = path.suffix.lower() in STORED_SUFFIXES
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            info.create_system = 3  # Unix, so the permission bits below mean the same everywhere.
            info.external_attr = 0o100644 << 16
            info.file_size = path.stat().st_size  # Lets zipfile switch to ZIP64 for large videos.
            with path.open("rb") as source, archive.open(info, "w") as output:
                shutil.copyfileobj(source, output)


def verify_project_archive(archive_path: Path, root: Path, folder: str) -> None:
    """Read the archive back and check it holds exactly the files under *root*, undamaged.

    Catches a write that a disk, network share, or sync client corrupted before
    the archive is trusted as a backup.
    """
    expected = {f"{folder}/{relative}": path.stat().st_size for relative, path in _project_files(root)}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            found = {info.filename: info.file_size for info in archive.infolist()}
            if found != expected:
                missing = sorted(set(expected) - set(found))
                extra = sorted(set(found) - set(expected))
                raise DownloadError(
                    "ZIP archive does not match the recovered project"
                    + (f"; missing {', '.join(missing[:3])}" if missing else "")
                    + (f"; unexpected {', '.join(extra[:3])}" if extra else "")
                )
            damaged = archive.testzip()  # Reads every entry and checks its CRC-32.
            if damaged is not None:
                raise DownloadError(f"ZIP archive failed verification at {damaged}")
    except (zipfile.BadZipFile, OSError) as error:
        raise DownloadError(f"ZIP archive failed verification: {error}") from error


def checksum_line(path: Path, name: str | None = None) -> str:
    """A ``sha256sum``-compatible line for *path*, under *name* (default: its own file name)."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{digest.hexdigest()}  {name or path.name}\n"


def _file_destination(path: Path | None, suffix: str, label: str) -> Path | None:
    if path is None:
        return None
    destination = path.resolve()
    if destination.suffix.lower() != suffix:
        raise DownloadError(f"{label} must be a {suffix} file: {destination}")
    if destination.is_dir():
        raise IsADirectoryError(f"{label} destination is a directory: {destination}")
    return destination


def _staging_file(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{destination.stem}-", suffix=destination.suffix, dir=destination.parent)
    os.close(handle)
    return Path(name)


@dataclass
class Downloaded:
    """What `download_talk` wrote. Every path is absent unless it was requested."""

    deck_name: str
    project: Path | None = None
    archive: Path | None = None
    archive_unchanged: bool = False
    pdf: Path | None = None
    browser: str | None = None
    checksums: list[Path] = field(default_factory=list)

    @property
    def deck(self) -> Path | None:
        return self.project / self.deck_name if self.project else None


def download_talk(
    url: str,
    *,
    output: Path | None = None,
    archive: Path | None = None,
    pdf: Path | None = None,
    name: str | None = None,
    force: bool = False,
    timeout: float = 30,
    browser: str | None = None,
    checksums: bool = False,
) -> Downloaded:
    """Download a published talk as an editable project, a ZIP of it, a PDF, or any mix.

    Everything is assembled before anything is written: a missing asset, a
    missing browser, or a failed print leaves no project, archive, or PDF.
    """
    if output is None and archive is None and pdf is None:
        raise DownloadError("Choose at least one of --output, --zip, or --pdf")
    if timeout <= 0:
        raise DownloadError("Download timeout must be greater than zero")
    destination = output.resolve() if output is not None else None
    if destination is not None and destination.exists() and not destination.is_dir():
        raise FileExistsError(f"Download destination is not a directory: {destination}")
    archive_path = _file_destination(archive, ".zip", "ZIP archive")
    pdf_path = _file_destination(pdf, ".pdf", "PDF")
    if archive_path is not None and archive_path == pdf_path:
        raise DownloadError("The ZIP archive and the PDF need different file names")
    if checksums and archive_path is None and pdf_path is None:
        raise DownloadError("--sha256 needs --zip or --pdf")
    if pdf_path is not None:
        if pdf_path.exists() and not force:
            # A PDF records when it was made, so a new one never equals the old.
            raise FileExistsError(f"PDF already exists; pass --force to replace it: {pdf_path}")
        from .printer import browser_candidates

        browser_candidates(browser)  # Fail before downloading when nothing can print.

    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    else:
        temporary = Path(tempfile.mkdtemp(prefix="quarkfoil-download-"))
    staged: list[Path] = []
    try:
        deck_name, folder = _recover(url, temporary, name=name, timeout=timeout)
        result = Downloaded(deck_name=deck_name)

        if destination is not None and destination.exists() and not force:
            conflicts = _pack_conflicts(temporary, destination)
            if conflicts:
                listing = ", ".join(conflicts[:5]) + (", ..." if len(conflicts) > 5 else "")
                raise FileExistsError(
                    "Destination already holds different files; pass --force to replace them: " + listing
                )

        staged_archive = None
        if archive_path is not None:
            staged_archive = _staging_file(archive_path)
            staged.append(staged_archive)
            write_project_archive(temporary, folder, staged_archive)
            verify_project_archive(staged_archive, temporary, folder)
            if archive_path.exists():
                if filecmp.cmp(archive_path, staged_archive, shallow=False):
                    result.archive_unchanged = True
                elif not force:
                    raise FileExistsError(f"ZIP archive already exists and differs; pass --force to replace it: {archive_path}")

        staged_pdf = None
        if pdf_path is not None:
            from .printer import print_presentation

            staged_pdf = _staging_file(pdf_path)
            staged.append(staged_pdf)
            _, result.browser = print_presentation(temporary / deck_name, staged_pdf, browser=browser)

        # sha256sum-compatible fingerprints, named after the final files so
        # `sha256sum -c FILE.sha256` works from the folder that holds them.
        fingerprints: list[tuple[Path, Path]] = []
        if checksums:
            for final, built in ((archive_path, staged_archive), (pdf_path, staged_pdf)):
                if final is None or built is None:
                    continue
                line = checksum_line(built, final.name)
                target = final.with_name(final.name + ".sha256")
                if target.exists() and target.read_text(encoding="utf-8") != line and not force:
                    raise FileExistsError(f"Checksum file already exists and differs; pass --force to replace it: {target}")
                staged_checksum = _staging_file(target)
                staged.append(staged_checksum)
                staged_checksum.write_bytes(line.encode("utf-8"))
                fingerprints.append((staged_checksum, target))

        # Everything exists; put it in place.
        if destination is not None:
            _publish(temporary, destination)
            result.project = destination
        if staged_archive is not None:
            if not result.archive_unchanged:
                os.replace(staged_archive, archive_path)
            result.archive = archive_path
        if staged_pdf is not None:
            os.replace(staged_pdf, pdf_path)
            result.pdf = pdf_path
        for staged_checksum, target in fingerprints:
            os.replace(staged_checksum, target)
            result.checksums.append(target)
        return result
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        for path in staged:
            with contextlib.suppress(FileNotFoundError):
                path.unlink()


def download_published(
    url: str,
    output: Path,
    *,
    name: str | None = None,
    force: bool = False,
    timeout: float = 30,
) -> tuple[Path, Path]:
    """Download *url* into an editable project, restoring original asset paths."""
    result = download_talk(url, output=output, name=name, force=force, timeout=timeout)
    assert result.project is not None and result.deck is not None
    return result.project, result.deck


__all__ = [
    "DownloadError", "Downloaded", "checksum_line", "download_published", "download_talk",
    "verify_project_archive", "write_project_archive",
]
