"""Publish presentations into one collection that shares its runtime and assets."""

from __future__ import annotations

import datetime as _datetime
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import unicodedata
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit

from .exporter import (
    ASSET_PATTERN,
    ATTRIBUTE_ASSET_PATTERN,
    EXPORT_FILES,
    LOCAL_FILES,
    _configured_assets,
    _create_preview,
    _folder_files,
    _front_matter,
    _index_html,
    _metadata_text,
    _player_bundle,
    _third_party_notice,
    _without_speaker_notes,
)
from .bibliography import citation_keys, trim_bibliography as _trim_bibliography
from .parser import parse_deck
from .paths import APP_ROOT, inside as _inside

ASSETS_DIR = "assets"
RUNTIME_DIR = f"{ASSETS_DIR}/quarkfoil"
POOL_DIR = f"{ASSETS_DIR}/f"
MARK_FILE = f"{ASSETS_DIR}/quarkfoil-mark.svg"
SERIES_DIR = "series"
META_NAME = "meta.json"
INDEX_NAME = "index.html"
SETTINGS_NAME = "collection.json"

# A target is remote when rsync would read it as remote: an rsync:// URL, a
# daemon `host::module`, or `host:path` with at least two characters before the
# colon, which keeps a Windows drive letter local.
REMOTE_PATTERN = re.compile(r"^(?:rsync://|[^/:]+::|[^/:]{2,}:)")

IMAGE_BLOCK_PATTERN = re.compile(r"^:{3,}[ \t]*(\S+)[^\n]*\n(.*?)^:{3,}[ \t]*$", re.S | re.M)
IMAGE_ONLY_PATTERN = re.compile(
    r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+["\'][^"\']*["\'])?\)\s*(?:\{[^}]*\})?\s*$'
)

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


class PublishError(RuntimeError):
    """A publish that must not proceed, reported without a traceback."""


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("quarkfoil")
    except PackageNotFoundError:
        return "dev"


@dataclass(frozen=True)
class Target:
    """Where a collection lives: a local directory or an rsync destination."""

    raw: str
    remote: bool

    @classmethod
    def parse(cls, value: str) -> "Target":
        text = str(value)
        remote = bool(REMOTE_PATTERN.match(text))
        return cls(text.rstrip("/") if remote else str(Path(text).expanduser()), remote)

    @property
    def description(self) -> str:
        return f"{self.raw} (remote, rsync)" if self.remote else f"{self.raw} (local directory)"

    def child(self, name: str) -> str:
        return f"{self.raw}/{name}" if self.remote else str(Path(self.raw) / name)

    @property
    def path(self) -> Path:
        if self.remote:
            raise PublishError(f"{self.raw} is a remote target")
        return Path(self.raw)


def _slugify(value: str, fallback: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w.-]+", "-", ascii_value.strip().lower()).strip("-.")
    return cleaned or fallback


def _slug(deck: Path, name: str | None) -> str:
    candidate = name or deck.stem
    cleaned = re.sub(r"[^\w.-]+", "-", candidate.strip()).strip("-.")
    if not cleaned:
        raise PublishError(f"Cannot derive a folder name from {candidate!r}; pass --name")
    if cleaned == SERIES_DIR:
        raise PublishError(f"{SERIES_DIR!r} is reserved for series pages; pass a different --name")
    return cleaned


def _date(value: object, deck: Path) -> str:
    if isinstance(value, _datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, _datetime.date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        raise PublishError(
            f"{deck.name} has no `date` in its front matter, and a published talk is "
            "listed by year. Add for example `date: 2026-09-07`."
        )
    try:
        return _datetime.date.fromisoformat(text[:10]).isoformat()
    except ValueError as error:
        raise PublishError(f"{deck.name} has an unreadable date {text!r}: use YYYY-MM-DD") from error


def _raw_references(source: str) -> list[str]:
    """Asset references exactly as the deck writes them, which is what the player resolves."""
    values = [match.group(1) for match in ASSET_PATTERN.finditer(source)]
    values.extend(
        next(group for group in match.groups() if group is not None)
        for match in ATTRIBUTE_ASSET_PATTERN.finditer(source)
    )
    references = []
    for value in values:
        if value.startswith(("http://", "https://", "//", "/", "#", "data:", "mailto:")):
            continue
        if value not in references:
            references.append(value)
    return references


def _resolvable_references(source: str) -> set[str]:
    """References the player resolves through its asset map.

    The renderer routes an image only when the whole block is that image, plus
    videos and posters, which are attributes. Anything else reaches the page as
    Markdown the resolver never sees.
    """
    resolvable = set()
    for match in IMAGE_BLOCK_PATTERN.finditer(source):
        single = IMAGE_ONLY_PATTERN.match(match.group(2).strip())
        if single:
            resolvable.add(single.group(2))
    for match in ATTRIBUTE_ASSET_PATTERN.finditer(source):
        resolvable.add(next(group for group in match.groups() if group is not None))
    return resolvable


def _project_file(project: Path, reference: str) -> Path:
    relative = unquote(reference).replace("\\", "/")
    asset = (project / relative).resolve()
    if not _inside(project, asset):
        raise PublishError(f"Asset leaves the presentation directory: {reference}")
    if not asset.is_file():
        raise PublishError(f"Referenced asset not found: {reference}")
    return asset


def _pool_name(asset: Path, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    safe = re.sub(r"[^\w.-]+", "-", asset.name).strip("-") or "asset"
    return f"{digest[:2]}/{digest[:16]}-{safe}"


def _public_url(value: object) -> str:
    """Validate and normalize the public URL stored with a collection."""
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlsplit(text)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise PublishError("--site-url must be an absolute http(s) URL without a query or fragment")
    return text.rstrip("/") + "/"


def _resolved_settings(
    existing: dict[str, object],
    *,
    title: str | None = None,
    lede: str | None = None,
    site_url: str | None = None,
) -> dict[str, str]:
    return {
        "title": title or str(existing.get("title") or "Talks"),
        "lede": lede if lede is not None else str(existing.get("lede") or ""),
        "url": _public_url(site_url if site_url is not None else existing.get("url")),
    }


def _pool_asset(root: Path, asset: Path, data: bytes) -> tuple[str, Path]:
    pool_name = _pool_name(asset, data)
    target = root / POOL_DIR / pool_name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        if asset.is_file() and data == asset.read_bytes():
            _link(asset, target)
        else:
            target.write_bytes(data)
    return pool_name, target


def _link(source: Path, destination: Path) -> None:
    """Stage a file without copying its bytes; rsync -L and copy2 both follow it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        return
    destination.symlink_to(source.resolve())


@dataclass
class Staged:
    """A collection tree holding one deck, its pooled assets and the runtime."""

    root: Path
    slug: str
    meta: dict[str, object]
    warnings: list[str] = field(default_factory=list)


def _stage_runtime(root: Path, version: str) -> str:
    runtime = f"{RUNTIME_DIR}/{version}"
    for source_name, target_name in {**EXPORT_FILES, **LOCAL_FILES}.items():
        source = APP_ROOT / source_name
        target = root / runtime / Path(target_name).relative_to("quarkfoil")
        if source.is_dir():
            for entry in sorted(source.rglob("*")):
                if entry.is_file():
                    _link(entry, target / entry.relative_to(source))
        else:
            _link(source, target)
    bundle = root / runtime / "player.js"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    if not bundle.exists():
        bundle.write_text(_player_bundle(), encoding="utf-8")
    notice = root / runtime / "THIRD_PARTY_LICENSES.txt"
    if not notice.exists():
        notice.write_text(_third_party_notice(), encoding="utf-8")
    _link(APP_ROOT / "assets/quarkfoil-mark.svg", root / MARK_FILE)
    return runtime


def _stage_deck(
    deck: Path,
    root: Path,
    *,
    name: str | None,
    include_notes: bool,
    trim_bibliography: bool,
    collection_url: str = "",
) -> Staged:
    resolved = deck.resolve()
    if not resolved.is_file():
        raise PublishError(f"Presentation not found: {resolved}")
    if resolved.suffix.lower() not in {".md", ".markdown"}:
        raise PublishError("Presentation source must be Markdown")
    project = resolved.parent
    source = resolved.read_text(encoding="utf-8")
    if not include_notes:
        source = _without_speaker_notes(source)

    front = _front_matter(source)
    slug = _slug(resolved, name)
    version = _version()
    runtime = _stage_runtime(root, version)
    folder = root / slug
    folder.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    resolvable = _resolvable_references(source)
    asset_map: dict[str, str] = {}
    pooled: list[str] = []
    references = list(_raw_references(source))
    bibliography = front.get("bibliography")
    if isinstance(bibliography, str) and bibliography:
        references.append(bibliography)
        resolvable.add(bibliography)
    figures, included = _configured_assets(source)
    for entry in sorted(included):
        for relative in sorted(_folder_files(project, entry)):
            if relative not in references:
                references.append(relative)
                resolvable.add(relative)

    for reference in references:
        asset = _project_file(project, reference)
        data = asset.read_bytes()
        if reference == bibliography and trim_bibliography:
            trimmed = _trim_bibliography(data.decode("utf-8"), citation_keys(source))
            data = trimmed.encode("utf-8")
        pool_name = _pool_name(asset, data)
        if reference in resolvable:
            _pool_asset(root, asset, data)
            asset_map[reference.replace("\\", "/")] = f"../{POOL_DIR}/{quote(pool_name, safe='/')}"
            pooled.append(f"{POOL_DIR}/{pool_name}")
        else:
            # The renderer never routes this one through the asset map, so the
            # deck keeps its own copy and its written path stays correct.
            private = folder / unquote(reference).replace("\\", "/")
            private.parent.mkdir(parents=True, exist_ok=True)
            if data == asset.read_bytes():
                _link(asset, private)
            else:
                private.write_bytes(data)
            warnings.append(f"{reference} is not a standalone image block; kept a private copy")

    (folder / "presentation.md").write_text(source, encoding="utf-8")
    metadata = {
        "title": _metadata_text(front.get("title")) or resolved.stem,
        "author": _metadata_text(front.get("author")),
        "description": _metadata_text(front.get("description")) or _metadata_text(front.get("subtitle")),
    }
    date = _date(front.get("date"), resolved)
    social = front.get("social")
    if social is None:
        social = {}
    if not isinstance(social, dict):
        raise PublishError(f"{resolved.name} has invalid `social` metadata: expected a mapping")
    has_social_image = "image" in social
    has_social_slide = "slide" in social
    social_image = social.get("image")
    social_slide = social.get("slide")
    if has_social_image and has_social_slide:
        raise PublishError(f"{resolved.name} sets both `social.image` and `social.slide`; choose one")
    if (has_social_image or has_social_slide) and not collection_url:
        raise PublishError(
            f"{resolved.name} selects a social card but the collection has no public URL; "
            "publish once with --site-url"
        )
    talk_url = urljoin(collection_url, f"{quote(slug, safe='')}/") if collection_url else ""
    card_url = ""
    card_alt = _metadata_text(social.get("alt")) or metadata["title"]
    card_type = ""
    card_size: tuple[int, int] | None = None

    if collection_url and has_social_image:
        if not isinstance(social_image, str) or not social_image.strip():
            raise PublishError(f"{resolved.name} has invalid `social.image`: expected a project-relative path")
        card_asset = _project_file(project, social_image)
        card_data = card_asset.read_bytes()
        card_pool, _ = _pool_asset(root, card_asset, card_data)
        pooled.append(f"{POOL_DIR}/{card_pool}")
        card_url = urljoin(collection_url, f"{POOL_DIR}/{quote(card_pool, safe='/')}")
        asset_map[social_image.replace("\\", "/")] = f"../{POOL_DIR}/{quote(card_pool, safe='/')}"
        card_type = mimetypes.guess_type(card_asset.name)[0] or "application/octet-stream"
        if not card_type.startswith("image/"):
            raise PublishError(f"{resolved.name} social.image is not a recognized image: {social_image}")

    asset_json = (
        json.dumps(asset_map, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    if collection_url and not has_social_image:
        parsed = parse_deck(source)
        visible = [slide for slide in parsed.slides if not slide.trashed]
        if not visible:
            raise PublishError(f"{resolved.name} has no visible slide to use as its social card")
        if not has_social_slide:
            selected = next((slide for slide in visible if slide.layout == "front"), visible[0])
        elif isinstance(social_slide, int) and not isinstance(social_slide, bool):
            if social_slide < 1 or social_slide > len(parsed.slides):
                raise PublishError(f"{resolved.name} social.slide {social_slide} is outside the deck")
            selected = parsed.slides[social_slide - 1]
        elif isinstance(social_slide, str) and social_slide.strip():
            matches = [slide for slide in parsed.slides if slide.id == social_slide.strip()]
            if not matches:
                raise PublishError(f"{resolved.name} has no slide with ID {social_slide!r}")
            if len(matches) > 1:
                raise PublishError(f"{resolved.name} has more than one slide with ID {social_slide!r}")
            selected = matches[0]
        else:
            raise PublishError(f"{resolved.name} has invalid `social.slide`: use a stable slide ID or page number")
        if selected.trashed:
            raise PublishError(f"{resolved.name} selects trashed slide {selected.id!r} as its social card")
        # The player must exist before Chromium can capture the selected slide.
        (folder / INDEX_NAME).write_text(
            _index_html(
                "local", metadata, None, None, runtime=f"../{runtime}", asset_map=asset_json,
                canonical_url=talk_url,
            ),
            encoding="utf-8",
        )
        preview = root / ".quarkfoil-previews" / f"{slug}-card.png"
        preview_relative = preview.relative_to(root).as_posix()
        page = f"/{quote(slug, safe='')}/?preview&preview-slide={quote(selected.id, safe='')}"
        try:
            _create_preview(root, preview_relative, page, (1200, 630))
        except (FileNotFoundError, RuntimeError) as error:
            raise PublishError(f"Could not render the social card for {resolved.name}: {error}") from error
        card_pool, _ = _pool_asset(root, Path(f"{slug}-card.png"), preview.read_bytes())
        pooled.append(f"{POOL_DIR}/{card_pool}")
        card_url = urljoin(collection_url, f"{POOL_DIR}/{quote(card_pool, safe='/')}")
        card_type = "image/png"
        card_size = (1200, 630)

    event = _metadata_text(front.get("event"))
    series = _metadata_text(front.get("series"))
    part = front.get("part")
    (folder / INDEX_NAME).write_text(
        _index_html(
            "local",
            metadata,
            card_url or None,
            None,
            runtime=f"../{runtime}",
            asset_map=asset_json,
            canonical_url=talk_url or None,
            preview_alt=card_alt if card_url else None,
            preview_type=card_type or None,
            preview_size=card_size,
        ),
        encoding="utf-8",
    )
    meta = {
        "slug": slug,
        "source": resolved.name,
        "title": metadata["title"],
        "description": metadata["description"],
        "author": metadata["author"],
        "event": event,
        "date": date,
        "series": series,
        "series_slug": _slugify(series, "series") if series else "",
        "series_description": _metadata_text(front.get("series-description")),
        "part": int(part) if isinstance(part, int) or (isinstance(part, str) and part.isdigit()) else None,
        "unlisted": bool(front.get("unlisted")),
        "runtime": version,
        "published": _datetime.datetime.now(_datetime.timezone.utc).date().isoformat(),
        "assets": sorted(set(pooled)),
        "url": talk_url,
        "social_image": card_url,
        "social_alt": card_alt if card_url else "",
    }
    (folder / META_NAME).write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return Staged(root=root, slug=slug, meta=meta, warnings=warnings)


# ---------------------------------------------------------------- publishing


def _copy_tree(source: Path, destination: Path, *, replace: bool) -> None:
    """Copy a staged tree, following the symlinks that stand in for its files."""
    if replace and destination.exists():
        shutil.rmtree(destination)
    for entry in sorted(source.rglob("*")):
        if entry.is_dir() and not entry.is_symlink():
            continue
        target = destination / entry.relative_to(source)
        if target.exists() and not replace:
            continue  # the pool is append-only: an equal name means equal bytes
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry, target)  # follows the staged symlink


# rsync reports a missing source with 23, which is what reading a collection
# that does not exist yet looks like.
RSYNC_PARTIAL = 23

# A published collection is served by a web server, so its modes must not
# depend on the umask of whoever publishes, nor on a staging directory's.
RSYNC_MODES = ("-rltpL", "--chmod=D755,F644")


# Local operands are always relative POSIX paths resolved from `cwd`. rsync
# reads `HOST:path` as a remote operand, so an absolute Windows path such as
# D:\staging\talk would name a host called "D"; Windows builds (cwRsync,
# MSYS2, Cygwin) also disagree on how to spell a drive. A relative path means
# the same thing to all of them.
def _rsync(
    command: list[str],
    dry_run: bool,
    *,
    cwd: Path | None = None,
    tolerate: tuple[int, ...] = (),
    quiet: bool = False,
) -> int:
    if shutil.which(command[0]) is None:
        raise PublishError(
            f"{command[0]} is required to publish to a remote target; install it or use a local --site"
        )
    if not quiet:
        print(f"  {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0 and result.returncode not in tolerate:
        raise PublishError(f"rsync failed ({result.returncode}): {result.stderr.strip()}")
    if dry_run and result.stdout.strip():
        for line in result.stdout.splitlines()[:20]:
            print(f"    {line}")
    return result.returncode


def _push(
    staging: Path,
    target: Target,
    names: list[str],
    dry_run: bool,
    rsync: str,
    *,
    root_exists: bool,
) -> None:
    """Send the pool once and every collection-owned path in one other transfer."""
    base = [rsync, *RSYNC_MODES, "--human-readable"]
    if dry_run:
        base += ["--dry-run", "--itemize-changes"]
    assets = staging / ASSETS_DIR
    owned = [Path(name).as_posix() for name in names if (staging / name).exists()]

    def push_assets() -> None:
        if assets.is_dir():
            _rsync(
                base + ["--ignore-existing", f"{ASSETS_DIR}/", f"{target.child(ASSETS_DIR)}/"],
                dry_run,
                cwd=staging,
            )

    def push_owned() -> None:
        if owned:
            # Passing each named directory without a trailing slash scopes
            # --delete to those directories. Unnamed talks, assets, and other
            # root entries are outside the transfer and cannot be deleted.
            _rsync(
                base + ["--delete", "--delay-updates", *owned, f"{target.raw}/"],
                dry_run,
                cwd=staging,
            )

    if root_exists:
        push_assets()
        push_owned()
    else:
        # A named directory/file transfer creates the collection root. On a
        # real first publish it must precede the nested assets destination.
        push_owned()
        if dry_run and assets.is_dir():
            print(f"  would append shared assets to {target.child(ASSETS_DIR)}/")
        else:
            push_assets()


def _install(
    staging: Path,
    target: Target,
    names: list[str],
    dry_run: bool,
    rsync: str,
    *,
    root_exists: bool = True,
) -> None:
    if target.remote:
        _push(staging, target, names, dry_run, rsync, root_exists=root_exists)
        return
    root = target.path
    if dry_run:
        for name in [ASSETS_DIR] + names:
            if (staging / name).exists():
                print(f"  would write {root / name}")
        return
    root.mkdir(parents=True, exist_ok=True)
    if (staging / ASSETS_DIR).is_dir():
        _copy_tree(staging / ASSETS_DIR, root / ASSETS_DIR, replace=False)
    for name in names:
        entry = staging / name
        if entry.is_dir():
            _copy_tree(entry, root / name, replace=True)
        elif entry.is_file():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, root / name)


def publish_presentations(
    decks: list[Path],
    site: str,
    *,
    names: list[str] | None = None,
    include_notes: bool = False,
    trim_bibliography: bool = False,
    index: bool = True,
    index_title: str | None = None,
    index_lede: str | None = None,
    site_url: str | None = None,
    dry_run: bool = False,
    rsync: str = "rsync",
) -> list[dict[str, object]]:
    """Publish several decks as one collection update.

    They are staged together, so a course of lectures sends its shared assets
    once and rebuilds the listing once, however many decks it holds.
    """
    if not decks:
        raise PublishError("No presentation to publish")
    target = Target.parse(site)
    state = _collection_state(target, rsync)
    settings = _resolved_settings(
        state.settings, title=index_title, lede=index_lede, site_url=site_url
    )
    print(f"Publishing to {target.description}")
    staging = Path(tempfile.mkdtemp(prefix=".quarkfoil-publish-"))
    published: list[dict[str, object]] = []
    try:
        for position, deck in enumerate(decks):
            staged = _stage_deck(
                deck,
                staging,
                name=names[position] if names else None,
                include_notes=include_notes,
                trim_bibliography=trim_bibliography,
                collection_url=settings["url"],
            )
            for warning in staged.warnings:
                print(f"  warning: {staged.slug}: {warning}")
            published.append(staged.meta)
        entries = _updated_entries(state.entries, published)
        names = [str(meta["slug"]) for meta in published]
        rebuild_index = index
        if index and not _listed_entries(entries) and not state.complete and _has(target, INDEX_NAME, rsync):
            print("  warning: the collection could not be read; its listing is left unchanged")
            rebuild_index = False
            state.exists = True
        if rebuild_index:
            count = _stage_index(staging, entries, settings)
            names += [INDEX_NAME, SETTINGS_NAME, SERIES_DIR]
        else:
            (staging / SETTINGS_NAME).write_text(
                json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            names.append(SETTINGS_NAME)
        _install(staging, target, names, dry_run, rsync, root_exists=state.exists)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if rebuild_index:
        print(f"  listed {count} talk{'' if count == 1 else 's'}")
    return published


def publish_presentation(
    deck: Path,
    site: str,
    *,
    name: str | None = None,
    include_notes: bool = False,
    trim_bibliography: bool = False,
    index: bool = True,
    index_title: str | None = None,
    index_lede: str | None = None,
    site_url: str | None = None,
    dry_run: bool = False,
    rsync: str = "rsync",
) -> dict[str, object]:
    """Publish *deck* into the collection at *site*, sharing its runtime and assets.

    Speaker notes are left out unless asked for: a published deck's Markdown is
    a public file, and its notes are written for the presenter.
    """
    return publish_presentations(
        [deck],
        site,
        names=[name] if name else None,
        include_notes=include_notes,
        trim_bibliography=trim_bibliography,
        index=index,
        index_title=index_title,
        index_lede=index_lede,
        site_url=site_url,
        dry_run=dry_run,
        rsync=rsync,
    )[0]


# --------------------------------------------------------------------- index


@dataclass
class CollectionState:
    settings: dict[str, object]
    entries: list[dict[str, object]]
    complete: bool
    exists: bool


def _read_settings(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _collection_state(target: Target, rsync: str) -> CollectionState:
    """Read collection settings and every deck metadata file in one operation."""
    if not target.remote:
        entries = []
        if target.path.is_dir():
            entries = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(target.path.glob(f"*/{META_NAME}"))
            ]
        return CollectionState(
            _read_settings(target.path / SETTINGS_NAME), entries, True, target.path.is_dir()
        )

    temporary = Path(tempfile.mkdtemp(prefix=".quarkfoil-state-"))
    try:
        code = _rsync(
            [
                rsync,
                "-rm",
                "--include=*/",
                f"--include={META_NAME}",
                f"--include={SETTINGS_NAME}",
                "--exclude=*",
                f"{target.raw}/",
                "./",
            ],
            False,
            cwd=temporary,
            tolerate=(RSYNC_PARTIAL,),
            quiet=True,
        )
        entries = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(temporary.rglob(META_NAME))
        ]
        complete = code == 0
        return CollectionState(
            _read_settings(temporary / SETTINGS_NAME), entries, complete, complete
        )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _updated_entries(
    existing: list[dict[str, object]], updates: list[dict[str, object]]
) -> list[dict[str, object]]:
    by_slug = {str(entry.get("slug", "")): entry for entry in existing if entry.get("slug")}
    for entry in updates:
        by_slug[str(entry["slug"])] = entry
    return list(by_slug.values())


def _listed_entries(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    return [entry for entry in entries if not entry.get("unlisted")]


def _has(target: Target, name: str, rsync: str) -> bool:
    """Whether the collection already holds *name*, without fetching it."""
    if not target.remote:
        return (target.path / name).exists()
    return _rsync(
        [rsync, "--list-only", f"{target.raw}/{name}"], False, tolerate=(RSYNC_PARTIAL,), quiet=True
    ) == 0


def _human_date(value: str) -> str:
    try:
        date = _datetime.date.fromisoformat(value)
    except ValueError:
        return value
    return f"{date.day} {MONTHS[date.month - 1]}"


INDEX_STYLE = """
:root {
  color-scheme: light dark;
  --page: #fbfbfd;
  --ink: #14202b;
  --muted: #5b6b7a;
  --rule: #dde3ea;
  --accent: #0f6f74;
  --card: #ffffff;
}
@media (prefers-color-scheme: dark) {
  :root {
    --page: #10161c;
    --ink: #e8eef4;
    --muted: #9aabb9;
    --rule: #26313c;
    --accent: #5ecfd4;
    --card: #161e26;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: clamp(2rem, 6vw, 5rem) clamp(1.2rem, 6vw, 4rem) 6rem;
  background: var(--page);
  color: var(--ink);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.page { max-width: 54rem; margin: 0 auto; }
header { margin-bottom: clamp(2rem, 5vw, 3.5rem); }
h1 { margin: 0 0 .4rem; font-size: clamp(1.9rem, 5vw, 2.6rem); letter-spacing: -.02em; }
.lede { margin: 0; color: var(--muted); font-size: 1.05rem; max-width: 40rem; }
.year { margin: 0 0 2.6rem; }
.year > h2 {
  display: flex; align-items: center; gap: 1rem;
  margin: 0 0 1.1rem; font-size: .95rem; font-weight: 600;
  letter-spacing: .16em; text-transform: uppercase; color: var(--muted);
}
.year > h2::after { content: ""; flex: 1; height: 1px; background: var(--rule); }
ul { list-style: none; margin: 0; padding: 0; display: grid; gap: .75rem; }
.talk {
  display: block; padding: 1.15rem 1.3rem;
  background: var(--card); border: 1px solid var(--rule); border-radius: 12px;
  color: inherit; text-decoration: none;
  transition: border-color .15s ease, transform .15s ease, box-shadow .15s ease;
}
.talk:hover, .talk:focus-visible {
  border-color: var(--accent);
  transform: translateY(-1px);
  box-shadow: 0 6px 20px -12px rgba(15, 111, 116, .55);
}
.talk.series { border-left: 3px solid var(--accent); }
.talk-title { display: block; font-size: 1.16rem; font-weight: 600; letter-spacing: -.01em; }
.back { margin: 0 0 .9rem; font-size: .9rem; }
.back a { color: var(--muted); text-decoration: none; }
.back a:hover { color: var(--accent); }
.talk-meta { display: block; margin-top: .2rem; font-size: .88rem; color: var(--accent); }
.talk-description { display: block; margin-top: .5rem; color: var(--muted); }
footer { margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid var(--rule); color: var(--muted); font-size: .85rem; }
footer a { color: inherit; }
"""



def _entry_date(entry: dict[str, object]) -> str:
    return str(entry.get("date", ""))


def _date_range(dates: list[str]) -> str:
    """A series spans days; say so without repeating the year in every card."""
    parsed = sorted(_datetime.date.fromisoformat(value) for value in dates if value)
    if not parsed:
        return ""
    first, last = parsed[0], parsed[-1]
    if first == last:
        return f"{first.day} {MONTHS[first.month - 1]}"
    if (first.year, first.month) == (last.year, last.month):
        return f"{first.day}–{last.day} {MONTHS[first.month - 1]}"
    if first.year == last.year:
        return f"{first.day} {MONTHS[first.month - 1]} – {last.day} {MONTHS[last.month - 1]}"
    return (f"{first.day} {MONTHS[first.month - 1]} {first.year} – "
            f"{last.day} {MONTHS[last.month - 1]} {last.year}")


def _order_talks(talks: list[dict[str, object]]) -> list[dict[str, object]]:
    """Lectures read forwards: by `part` when given, otherwise by date."""
    numbered = [talk for talk in talks if talk.get("part") is not None]
    if len(numbered) == len(talks):
        return sorted(talks, key=lambda talk: int(talk["part"]))
    return sorted(talks, key=lambda talk: (_entry_date(talk), str(talk.get("title", ""))))


def _cards(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    """One card per single talk, and one per series however many talks it holds."""
    cards: list[dict[str, object]] = []
    series: dict[str, dict[str, object]] = {}
    for entry in entries:
        name = str(entry.get("series") or "")
        if not name:
            cards.append({"kind": "talk", "date": _entry_date(entry), "talk": entry})
            continue
        card = series.setdefault(name, {
            "kind": "series",
            "name": name,
            "slug": str(entry.get("series_slug") or _slugify(name, "series")),
            "description": "",
            "talks": [],
        })
        card["talks"].append(entry)
        if not card["description"]:
            card["description"] = str(entry.get("series_description") or "")
    for card in series.values():
        talks = card["talks"]
        card["date"] = max(_entry_date(talk) for talk in talks)
        events = {str(talk.get("event") or "") for talk in talks}
        card["event"] = events.pop() if len(events) == 1 else ""
        card["talks"] = _order_talks(talks)
        cards.append(card)
    return sorted(cards, key=lambda card: (str(card["date"]), str(card.get("name", ""))), reverse=True)


def _talk_item(talk: dict[str, object], prefix: str = "") -> str:
    slug = quote(str(talk.get("slug", "")), safe="")
    name = html.escape(str(talk.get("title", slug)))
    description = html.escape(str(talk.get("description", "")))
    event = html.escape(str(talk.get("event", "")))
    meta = " · ".join(part for part in (event, _human_date(_entry_date(talk))) if part)
    return (
        f'        <li><a class="talk" href="{prefix}{slug}/">\n'
        f'          <span class="talk-title">{name}</span>\n'
        + (f'          <span class="talk-meta">{meta}</span>\n' if meta else "")
        + (f'          <span class="talk-description">{description}</span>\n' if description else "")
        + "        </a></li>"
    )


def _series_item(card: dict[str, object]) -> str:
    talks = card["talks"]
    name = html.escape(str(card["name"]))
    description = html.escape(str(card.get("description", "")))
    count = f"{len(talks)} talk{'' if len(talks) == 1 else 's'}"
    meta = " · ".join(part for part in (
        html.escape(str(card.get("event", ""))), count, _date_range([_entry_date(t) for t in talks]),
    ) if part)
    slug = quote(str(card["slug"]), safe="")
    return (
        f'        <li><a class="talk series" href="{SERIES_DIR}/{slug}/">\n'
        f'          <span class="talk-title">{name}</span>\n'
        f'          <span class="talk-meta">{meta}</span>\n'
        + (f'          <span class="talk-description">{description}</span>\n' if description else "")
        + "        </a></li>"
    )


def _sections(cards: list[dict[str, object]]) -> str:
    years: dict[str, list[str]] = {}
    for card in cards:
        year = str(card["date"])[:4] or "Undated"
        item = _series_item(card) if card["kind"] == "series" else _talk_item(card["talk"])
        years.setdefault(year, []).append(item)
    return "\n".join(
        f'      <section class="year">\n        <h2>{html.escape(year)}</h2>\n'
        f"        <ul>\n" + "\n".join(items) + "\n        </ul>\n      </section>"
        for year, items in years.items()
    )


def _page(
    heading: str,
    lede: str,
    body: str,
    *,
    depth: int = 0,
    back: str = "",
    canonical_url: str = "",
) -> str:
    policy = (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'"
    )
    up = "../" * depth
    title = html.escape(heading)
    description = html.escape(lede) if lede else title
    canonical = html.escape(quote(canonical_url, safe="/:%"), quote=True) if canonical_url else ""
    canonical_tags = (
        f'  <meta property="og:url" content="{canonical}">\n'
        f'  <link rel="canonical" href="{canonical}">\n'
        if canonical else ""
    )
    back_link = f'      <p class="back"><a href="{up}">← {html.escape(back)}</a></p>\n' if back else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="{html.escape(policy, quote=True)}">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
{canonical_tags}  <link rel="icon" href="{up}{MARK_FILE}" type="image/svg+xml">
  <style>{INDEX_STYLE}</style>
</head>
<body>
  <div class="page">
    <header>
{back_link}      <h1>{title}</h1>
{f'      <p class="lede">{html.escape(lede)}</p>' if lede else ""}
    </header>
    <main>
{body}
    </main>
  </div>
</body>
</html>
"""


def index_page(
    entries: list[dict[str, object]], title: str = "Talks", lede: str = "", url: str = ""
) -> str:
    """One static page: years descending, a series folded into a single card."""
    cards = _cards(entries)
    body = _sections(cards) if cards else '      <p class="lede">No talks published yet.</p>'
    return _page(title, lede, body, canonical_url=url)


def series_page(card: dict[str, object], collection: str = "Talks", url: str = "") -> str:
    """A series reads forwards: its talks in the order they were given."""
    items = "\n".join(_talk_item(talk, prefix="../../") for talk in card["talks"])
    meta = " · ".join(part for part in (
        html.escape(str(card.get("event", ""))),
        _date_range([_entry_date(talk) for talk in card["talks"]]),
    ) if part)
    body = (
        f'      <section class="year">\n        <h2>{meta}</h2>\n'
        f"        <ul>\n{items}\n        </ul>\n      </section>"
    )
    canonical = urljoin(url, f"{SERIES_DIR}/{quote(str(card['slug']), safe='')}/") if url else ""
    return _page(
        str(card["name"]), str(card.get("description", "")), body,
        depth=2, back=collection, canonical_url=canonical,
    )


def index_pages(
    entries: list[dict[str, object]], title: str = "Talks", lede: str = "", url: str = ""
) -> dict[str, str]:
    """The listing and one page per series, all of them plain HTML."""
    pages = {INDEX_NAME: index_page(entries, title, lede, url)}
    for card in _cards(entries):
        if card["kind"] == "series":
            pages[f"{SERIES_DIR}/{card['slug']}/{INDEX_NAME}"] = series_page(card, title, url)
    return pages

def _stage_index(
    staging: Path, entries: list[dict[str, object]], settings: dict[str, str]
) -> int:
    listed = _listed_entries(entries)
    pages = index_pages(listed, settings["title"], settings["lede"], settings["url"])
    for relative, page in pages.items():
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(page, encoding="utf-8")
    # Always present, even with no series left, so mirroring removes the pages
    # of a series whose talks are gone.
    (staging / SERIES_DIR).mkdir(exist_ok=True)
    (staging / SETTINGS_NAME).write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return len(listed)


def publish_index(
    site: str,
    *,
    title: str | None = None,
    lede: str | None = None,
    site_url: str | None = None,
    dry_run: bool = False,
    rsync: str = "rsync",
) -> int:
    """Rebuild the collection's listing from the metadata each deck carries."""
    target = Target.parse(site)
    state = _collection_state(target, rsync)
    # Given once, kept from then on: a later publish must not reset the heading.
    resolved = _resolved_settings(state.settings, title=title, lede=lede, site_url=site_url)
    entries = _listed_entries(state.entries)
    if not entries and not state.complete and _has(target, INDEX_NAME, rsync):
        print("  warning: the collection could not be read; its listing is left unchanged")
        return 0
    staging = Path(tempfile.mkdtemp(prefix=".quarkfoil-index-"))
    try:
        count = _stage_index(staging, state.entries, resolved)
        _install(
            staging,
            target,
            [INDEX_NAME, SETTINGS_NAME, SERIES_DIR],
            dry_run,
            rsync,
            root_exists=state.exists,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"  listed {count} talk{'' if count == 1 else 's'}")
    return count


__all__ = [
    "PublishError",
    "Target",
    "index_page",
    "index_pages",
    "publish_index",
    "publish_presentation",
    "publish_presentations",
    "series_page",
]
