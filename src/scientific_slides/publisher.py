"""Publish presentations into one collection that shares its runtime and assets."""

from __future__ import annotations

import datetime as _datetime
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import unicodedata
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

from .exporter import (
    ASSET_PATTERN,
    ATTRIBUTE_ASSET_PATTERN,
    EXPORT_FILES,
    LOCAL_FILES,
    _configured_assets,
    _folder_files,
    _front_matter,
    _index_html,
    _metadata_text,
    _player_bundle,
    _third_party_notice,
    _without_speaker_notes,
)
from .bibliography import citation_keys, trim_bibliography as _trim_bibliography
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
        target = root / POOL_DIR / pool_name
        if reference in resolvable:
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                if data == asset.read_bytes():
                    _link(asset, target)
                else:
                    target.write_bytes(data)
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
    event = _metadata_text(front.get("event"))
    series = _metadata_text(front.get("series"))
    part = front.get("part")
    (folder / INDEX_NAME).write_text(
        _index_html(
            "local",
            metadata,
            None,
            None,
            runtime=f"../{runtime}",
            asset_map=json.dumps(asset_map, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026"),
        ),
        encoding="utf-8",
    )
    meta = {
        "slug": slug,
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
        "assets": sorted(pooled),
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


def _rsync(command: list[str], dry_run: bool, *, tolerate: tuple[int, ...] = (), quiet: bool = False) -> int:
    if shutil.which(command[0]) is None:
        raise PublishError(
            f"{command[0]} is required to publish to a remote target; install it or use a local --site"
        )
    if not quiet:
        print(f"  {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 and result.returncode not in tolerate:
        raise PublishError(f"rsync failed ({result.returncode}): {result.stderr.strip()}")
    if dry_run and result.stdout.strip():
        for line in result.stdout.splitlines()[:20]:
            print(f"    {line}")
    return result.returncode


def _ensure_root(target: Target, rsync: str) -> None:
    """Create the collection folder itself.

    rsync creates the last component of a destination but not the ones above
    it, so the first publish into a new collection would fail on `.../assets`.
    Sending an empty directory to the root first works on every rsync version,
    unlike `--mkpath`, and adds nothing to an existing collection.
    """
    empty = Path(tempfile.mkdtemp(prefix=".quarkfoil-root-"))
    try:
        _rsync([rsync, *RSYNC_MODES, f"{empty}/", f"{target.raw}/"], False, quiet=True)
    finally:
        shutil.rmtree(empty, ignore_errors=True)


def _push(staging: Path, target: Target, names: list[str], dry_run: bool, rsync: str) -> None:
    """Send the staged tree: the shared half append-only, each deck folder mirrored."""
    base = [rsync, *RSYNC_MODES, "--human-readable"]
    if dry_run:
        base += ["--dry-run", "--itemize-changes"]
    else:
        _ensure_root(target, rsync)
    if (staging / ASSETS_DIR).is_dir():
        _rsync(base + ["--ignore-existing", f"{staging / ASSETS_DIR}/", f"{target.child(ASSETS_DIR)}/"], dry_run)
    for name in names:
        entry = staging / name
        if entry.is_dir():
            _rsync(base + ["--delete", "--delay-updates", f"{entry}/", f"{target.child(name)}/"], dry_run)
        elif entry.is_file():
            _rsync(base + [str(entry), target.child(name)], dry_run)


def _install(staging: Path, target: Target, names: list[str], dry_run: bool, rsync: str) -> None:
    if target.remote:
        _push(staging, target, names, dry_run, rsync)
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
            )
            for warning in staged.warnings:
                print(f"  warning: {staged.slug}: {warning}")
            published.append(staged.meta)
        _install(staging, target, [str(meta["slug"]) for meta in published], dry_run, rsync)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if index:
        publish_index(site, title=index_title, lede=index_lede, dry_run=dry_run, rsync=rsync)
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
    dry_run: bool = False,
    rsync: str = "rsync",
) -> dict[str, object]:
    """Publish *deck* into the collection at *site*, sharing its runtime and assets.

    Speaker notes are left out unless asked for: a published deck's Markdown is
    a public file, and its notes are written for the presenter.
    """
    target = Target.parse(site)
    print(f"Publishing to {target.description}")
    staging = Path(tempfile.mkdtemp(prefix=".quarkfoil-publish-"))
    try:
        staged = _stage_deck(
            deck,
            staging,
            name=name,
            include_notes=include_notes,
            trim_bibliography=trim_bibliography,
        )
        for warning in staged.warnings:
            print(f"  warning: {warning}")
        _install(staging, target, [staged.slug], dry_run, rsync)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if index:
        publish_index(site, title=index_title, lede=index_lede, dry_run=dry_run, rsync=rsync)
    return staged.meta


# --------------------------------------------------------------------- index


def _gather(target: Target, rsync: str) -> tuple[list[dict[str, object]], bool]:
    """Read every published deck's own metadata; the collection needs no manifest.

    Returns the entries and whether the collection could be read at all: a
    target that does not exist yet reads as empty, which is not the same as a
    collection whose listing must not be replaced by an empty one.
    """
    entries: list[dict[str, object]] = []
    complete = True
    if target.remote:
        temporary = Path(tempfile.mkdtemp(prefix=".quarkfoil-index-"))
        try:
            code = _rsync(
                [rsync, "-rm", "--include=*/", f"--include={META_NAME}", "--exclude=*",
                 f"{target.raw}/", f"{temporary}/"],
                False,
                tolerate=(RSYNC_PARTIAL,),
                quiet=True,
            )
            complete = code == 0
            files = sorted(temporary.rglob(META_NAME))
            entries = [json.loads(path.read_text(encoding="utf-8")) for path in files]
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
    elif target.path.is_dir():
        for path in sorted(target.path.glob(f"*/{META_NAME}")):
            entries.append(json.loads(path.read_text(encoding="utf-8")))
    return [entry for entry in entries if not entry.get("unlisted")], complete


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


def _page(heading: str, lede: str, body: str, *, depth: int = 0, back: str = "") -> str:
    policy = (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'"
    )
    up = "../" * depth
    title = html.escape(heading)
    description = html.escape(lede) if lede else title
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
  <link rel="icon" href="{up}{MARK_FILE}" type="image/svg+xml">
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


def index_page(entries: list[dict[str, object]], title: str = "Talks", lede: str = "") -> str:
    """One static page: years descending, a series folded into a single card."""
    cards = _cards(entries)
    body = _sections(cards) if cards else '      <p class="lede">No talks published yet.</p>'
    return _page(title, lede, body)


def series_page(card: dict[str, object], collection: str = "Talks") -> str:
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
    return _page(str(card["name"]), str(card.get("description", "")), body, depth=2, back=collection)


def index_pages(entries: list[dict[str, object]], title: str = "Talks", lede: str = "") -> dict[str, str]:
    """The listing and one page per series, all of them plain HTML."""
    pages = {INDEX_NAME: index_page(entries, title, lede)}
    for card in _cards(entries):
        if card["kind"] == "series":
            pages[f"{SERIES_DIR}/{card['slug']}/{INDEX_NAME}"] = series_page(card, title)
    return pages



def _settings(target: Target, rsync: str) -> dict[str, str]:
    """The collection's own heading and standfirst, kept beside its listing."""
    if not target.remote:
        path = target.path / SETTINGS_NAME
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}
    temporary = Path(tempfile.mkdtemp(prefix=".quarkfoil-settings-"))
    try:
        _rsync(
            [rsync, "-q", "--ignore-missing-args", f"{target.raw}/{SETTINGS_NAME}", f"{temporary}/"],
            False,
            tolerate=(RSYNC_PARTIAL,),
            quiet=True,
        )
        path = temporary / SETTINGS_NAME
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (PublishError, json.JSONDecodeError):
        return {}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def publish_index(
    site: str,
    *,
    title: str | None = None,
    lede: str | None = None,
    dry_run: bool = False,
    rsync: str = "rsync",
) -> int:
    """Rebuild the collection's listing from the metadata each deck carries."""
    target = Target.parse(site)
    settings = _settings(target, rsync)
    # Given once, kept from then on: a later publish must not reset the heading.
    resolved = {
        "title": title or str(settings.get("title") or "Talks"),
        "lede": lede if lede is not None else str(settings.get("lede") or ""),
    }
    entries, complete = _gather(target, rsync)
    if not entries and not complete and _has(target, INDEX_NAME, rsync):
        print("  warning: the collection could not be read; its listing is left unchanged")
        return 0
    pages = index_pages(entries, resolved["title"], resolved["lede"])
    staging = Path(tempfile.mkdtemp(prefix=".quarkfoil-index-"))
    try:
        for relative, page in pages.items():
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(page, encoding="utf-8")
        # Always present, even with no series left, so mirroring removes the
        # pages of a series whose talks are gone.
        (staging / SERIES_DIR).mkdir(exist_ok=True)
        (staging / SETTINGS_NAME).write_text(
            json.dumps(resolved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        _install(staging, target, [INDEX_NAME, SETTINGS_NAME, SERIES_DIR], dry_run, rsync)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"  listed {len(entries)} talk{'' if len(entries) == 1 else 's'}")
    return len(entries)


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
