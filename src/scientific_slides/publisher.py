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


def _slug(deck: Path, name: str | None) -> str:
    candidate = name or deck.stem
    cleaned = re.sub(r"[^\w.-]+", "-", candidate.strip()).strip("-.")
    if not cleaned:
        raise PublishError(f"Cannot derive a folder name from {candidate!r}; pass --name")
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


def _rsync(command: list[str], dry_run: bool) -> None:
    if shutil.which(command[0]) is None:
        raise PublishError(
            f"{command[0]} is required to publish to a remote target; install it or use a local --site"
        )
    printable = " ".join(command)
    print(f"  {printable}")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise PublishError(f"rsync failed ({result.returncode}): {result.stderr.strip()}")
    if dry_run and result.stdout.strip():
        for line in result.stdout.splitlines()[:20]:
            print(f"    {line}")


def _push(staging: Path, target: Target, names: list[str], dry_run: bool, rsync: str) -> None:
    """Send the staged tree: the shared half append-only, each deck folder mirrored."""
    base = [rsync, "-rltL", "--human-readable"]
    if dry_run:
        base += ["--dry-run", "--itemize-changes"]
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


def publish_presentation(
    deck: Path,
    site: str,
    *,
    name: str | None = None,
    include_notes: bool = True,
    trim_bibliography: bool = False,
    index: bool = True,
    index_title: str | None = None,
    index_lede: str | None = None,
    dry_run: bool = False,
    rsync: str = "rsync",
) -> dict[str, object]:
    """Publish *deck* into the collection at *site*, sharing its runtime and assets."""
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


def _gather(target: Target, rsync: str) -> list[dict[str, object]]:
    """Read every published deck's own metadata; the collection needs no manifest."""
    entries: list[dict[str, object]] = []
    if target.remote:
        temporary = Path(tempfile.mkdtemp(prefix=".quarkfoil-index-"))
        try:
            _rsync(
                [rsync, "-rm", "--include=*/", f"--include={META_NAME}", "--exclude=*",
                 f"{target.raw}/", f"{temporary}/"],
                False,
            )
            files = sorted(temporary.rglob(META_NAME))
            entries = [json.loads(path.read_text(encoding="utf-8")) for path in files]
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
    elif target.path.is_dir():
        for path in sorted(target.path.glob(f"*/{META_NAME}")):
            entries.append(json.loads(path.read_text(encoding="utf-8")))
    return [entry for entry in entries if not entry.get("unlisted")]


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
.talk-title { display: block; font-size: 1.16rem; font-weight: 600; letter-spacing: -.01em; }
.talk-meta { display: block; margin-top: .2rem; font-size: .88rem; color: var(--accent); }
.talk-description { display: block; margin-top: .5rem; color: var(--muted); }
footer { margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid var(--rule); color: var(--muted); font-size: .85rem; }
footer a { color: inherit; }
"""


def index_page(entries: list[dict[str, object]], title: str = "Talks", lede: str = "") -> str:
    """One static page: years descending, talks descending inside each year."""
    ordered = sorted(
        entries,
        key=lambda entry: (str(entry.get("date", "")), str(entry.get("title", ""))),
        reverse=True,
    )
    years: dict[str, list[dict[str, object]]] = {}
    for entry in ordered:
        years.setdefault(str(entry.get("date", ""))[:4] or "Undated", []).append(entry)

    sections = []
    for year, talks in years.items():
        items = []
        for talk in talks:
            slug = quote(str(talk.get("slug", "")), safe="")
            name = html.escape(str(talk.get("title", slug)))
            description = html.escape(str(talk.get("description", "")))
            event = html.escape(str(talk.get("event", "")))
            when = _human_date(str(talk.get("date", "")))
            meta = " · ".join(part for part in (event, when) if part)
            items.append(
                f'        <li><a class="talk" href="{slug}/">\n'
                f'          <span class="talk-title">{name}</span>\n'
                + (f'          <span class="talk-meta">{meta}</span>\n' if meta else "")
                + (f'          <span class="talk-description">{description}</span>\n' if description else "")
                + "        </a></li>"
            )
        sections.append(
            f'      <section class="year">\n        <h2>{html.escape(year)}</h2>\n'
            f"        <ul>\n" + "\n".join(items) + "\n        </ul>\n      </section>"
        )
    body = "\n".join(sections) if sections else '      <p class="lede">No talks published yet.</p>'
    policy = (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'"
    )
    heading = html.escape(title)
    description = html.escape(lede or f"{len(ordered)} presentations")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="{html.escape(policy, quote=True)}">
  <title>{heading}</title>
  <meta name="description" content="{description}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{heading}">
  <link rel="icon" href="{MARK_FILE}" type="image/svg+xml">
  <style>{INDEX_STYLE}</style>
</head>
<body>
  <div class="page">
    <header>
      <h1>{heading}</h1>
{f'      <p class="lede">{html.escape(lede)}</p>' if lede else ""}
    </header>
    <main>
{body}
    </main>
  </div>
</body>
</html>
"""


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
    entries = _gather(target, rsync)
    page = index_page(entries, resolved["title"], resolved["lede"])
    staging = Path(tempfile.mkdtemp(prefix=".quarkfoil-index-"))
    try:
        (staging / INDEX_NAME).write_text(page, encoding="utf-8")
        (staging / SETTINGS_NAME).write_text(
            json.dumps(resolved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        _install(staging, target, [INDEX_NAME, SETTINGS_NAME], dry_run, rsync)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(f"  listed {len(entries)} talk{'' if len(entries) == 1 else 's'}")
    return len(entries)


__all__ = ["PublishError", "Target", "index_page", "publish_index", "publish_presentation"]
