"""Recover an editable Quarkfoil project from a published talk."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
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


def download_published(
    url: str,
    output: Path,
    *,
    name: str | None = None,
    force: bool = False,
    timeout: float = 30,
) -> tuple[Path, Path]:
    """Download *url* into an editable project, restoring original asset paths."""
    if timeout <= 0:
        raise DownloadError("Download timeout must be greater than zero")
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

    destination = output.resolve()
    if destination.exists() and not destination.is_dir():
        raise FileExistsError(f"Download destination is not a directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    deck_name = _deck_name(name, metadata, final_talk_url)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        (temporary / deck_name).write_bytes(source_bytes)
        restored: set[Path] = set()
        for original, mapped in sorted(mappings.items()):
            relative, target = _relative_asset(temporary, original)
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
            relative, target = _relative_asset(temporary, reference)
            if relative in restored:
                continue
            if target.exists():
                raise DownloadError(f"Published asset conflicts with the recovered deck: {reference}")
            asset_url = urljoin(final_talk_url, quote(relative.as_posix(), safe="/"))
            _download_file(asset_url, target, timeout, origin)
            restored.add(relative)

        if destination.exists() and not force:
            conflicts = _pack_conflicts(temporary, destination)
            if conflicts:
                listing = ", ".join(conflicts[:5]) + (", ..." if len(conflicts) > 5 else "")
                raise FileExistsError(
                    "Destination already holds different files; pass --force to replace them: " + listing
                )
        _publish(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination, destination / deck_name


__all__ = ["DownloadError", "download_published"]
