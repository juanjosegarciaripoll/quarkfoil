from __future__ import annotations

import base64
import contextlib
import hashlib
import html
import http.server
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import yaml

from .icons import icon_notices
from .bibliography import citation_keys, trim_bibliography as _trim_bibliography
from .paths import APP_ROOT, inside as _inside
from .parser import canonical_source


EXPORT_FILES = {
    "assets/quarkfoil-mark.svg": "quarkfoil/quarkfoil-mark.svg",
    "styles/layout.css": "quarkfoil/layout.css",
    "styles/themes.css": "quarkfoil/themes.css",
    "styles/player.css": "quarkfoil/player.css",
}

LOCAL_FILES = {
    "vendor/bibtex/bibtexParse.js": "quarkfoil/vendor/bibtex/bibtexParse.js",
    "vendor/bibtex/LICENSE": "quarkfoil/vendor/bibtex/LICENSE",
    "vendor/reveal/reveal.js": "quarkfoil/vendor/reveal/reveal.js",
    "vendor/reveal/reveal.css": "quarkfoil/vendor/reveal/reveal.css",
    "vendor/reveal/notes.js": "quarkfoil/vendor/reveal/notes.js",
    "vendor/reveal/LICENSE": "quarkfoil/vendor/reveal/LICENSE",
    "vendor/katex/katex.min.js": "quarkfoil/vendor/katex/katex.min.js",
    "vendor/katex/katex.min.css": "quarkfoil/vendor/katex/katex.min.css",
    "vendor/katex/fonts": "quarkfoil/vendor/katex/fonts",
    "vendor/katex/LICENSE": "quarkfoil/vendor/katex/LICENSE",
    "vendor/marked/marked.min.js": "quarkfoil/vendor/marked/marked.min.js",
    "vendor/marked/LICENSE.md": "quarkfoil/vendor/marked/LICENSE.md",
    "vendor/yaml/js-yaml.min.js": "quarkfoil/vendor/yaml/js-yaml.min.js",
    "vendor/yaml/LICENSE": "quarkfoil/vendor/yaml/LICENSE",
}

CDN_FILES = {
    "reveal_css": (
        "vendor/reveal/reveal.css",
        "https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/dist/reveal.css",
    ),
    "katex_css": (
        "vendor/katex/katex.min.css",
        "https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css",
    ),
    "reveal_js": (
        "vendor/reveal/reveal.js",
        "https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/dist/reveal.js",
    ),
    "notes_js": (
        "vendor/reveal/notes.js",
        "https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/plugin/notes/notes.js",
    ),
    "marked_js": (
        "vendor/marked/marked.min.js",
        "https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js",
    ),
    "yaml_js": (
        "vendor/yaml/js-yaml.min.js",
        "https://cdn.jsdelivr.net/npm/js-yaml@4.1.0/dist/js-yaml.min.js",
    ),
    "katex_js": (
        "vendor/katex/katex.min.js",
        "https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.js",
    ),
    "bibtex_js": (
        "vendor/bibtex/bibtexParse.js",
        "https://cdn.jsdelivr.net/npm/bibtex-parse-js@0.0.24/bibtexParse.js",
    ),
}

PLAYER_MODULE = "player"
PLAYER_BUNDLE = "quarkfoil/player.js"

# Programs tried, in order, when a headless browser has to render the
# presentation itself. Chromium keeps its Windows and macOS builds off PATH,
# so their usual locations are named too.
CHROMIUM_BROWSERS = (
    "chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge", "msedge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)

MODULE_IMPORT_PATTERN = re.compile(
    r'(?m)^import[ \t]*\{(?P<names>[^}]*)\}[ \t]*from[ \t]*"\./(?P<module>[\w.-]+)\.js";[ \t]*$'
)
MODULE_EXPORT_PATTERN = re.compile(
    r'(?m)^export[ \t]+'
    r'(?P<declaration>(?:async[ \t]+)?(?:function|const|let|var|class)[ \t]+(?P<name>[A-Za-z_$][\w$]*)\b)'
)
MODULE_STATEMENT_PATTERN = re.compile(r"(?m)^[ \t]*(?:import|export)\b")

ASSET_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)")
ATTRIBUTE_ASSET_PATTERN = re.compile(r"\b(?:src|poster)=(?:\"([^\"]+)\"|'([^']+)'|([^\s}]+))")
NOTES_BLOCK_PATTERN = re.compile(
    r"(?m)^:::[ \t]*notes(?:[ \t]+\{[^}\r\n]*\})?[ \t]*\r?\n"
    r".*?"
    r"^:::[ \t]*(?:\r?\n|$)",
    re.DOTALL,
)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def _integrity(path: Path) -> str:
    digest = hashlib.sha384(path.read_bytes()).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def _copy_entry(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def _module_chunk(name: str) -> tuple[str, list[str]]:
    source = (APP_ROOT / "modules" / f"{name}.js").read_text(encoding="utf-8")
    dependencies: list[str] = []
    bindings: list[str] = []

    def bind(match: re.Match[str]) -> str:
        dependencies.append(match.group("module"))
        names = ", ".join(
            part.strip().replace(" as ", ": ")
            for part in match.group("names").split(",")
            if part.strip()
        )
        bindings.append(f'const {{ {names} }} = modules["{match.group("module")}"];')
        return ""

    body = MODULE_IMPORT_PATTERN.sub(bind, source)
    exported = [match.group("name") for match in MODULE_EXPORT_PATTERN.finditer(body)]
    body = MODULE_EXPORT_PATTERN.sub(lambda match: match.group("declaration"), body)
    if MODULE_STATEMENT_PATTERN.search(body):
        raise ValueError(f"Unsupported module syntax in {name}.js; the export bundler needs plain imports and exports")
    chunk = "\n".join((
        f'modules["{name}"] = (() => {{',
        *bindings,
        body.strip("\n"),
        f'return {{ {", ".join(exported)} }};',
        "})();",
    ))
    return chunk, dependencies


def _player_bundle(entry: str = PLAYER_MODULE) -> str:
    """Combine the player module graph into one classic script.

    Browsers refuse to load ES modules and to fetch neighbouring files from
    ``file://`` pages, so the exported player is a single ordinary script and
    the deck travels inside ``index.html``.
    """
    chunks: list[str] = []
    done: set[str] = set()

    def visit(name: str, pending: tuple[str, ...]) -> None:
        if name in done:
            return
        if name in pending:
            raise ValueError(f"Cyclic player module import: {' -> '.join((*pending, name))}")
        chunk, dependencies = _module_chunk(name)
        for dependency in dependencies:
            visit(dependency, (*pending, name))
        done.add(name)
        chunks.append(chunk)

    visit(entry, ())
    body = "\n\n".join(chunks)
    return (
        "// Quarkfoil static player: app/modules/*.js combined into one classic\n"
        "// script so the exported presentation also opens from the file system.\n"
        "(() => {\n"
        '"use strict";\n'
        "const modules = {};\n\n"
        f"{body}\n"
        "})();\n"
    )


def _embedded_source(deck: str, bibliography: str | None) -> str:
    payload = json.dumps({"deck": deck, "bibliography": bibliography}, ensure_ascii=False)
    for character, escape in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        payload = payload.replace(character, escape)
    return payload


def _merge_entry(source: Path, destination: Path) -> None:
    if source.is_dir() and destination.is_dir() and not destination.is_symlink():
        for entry in source.iterdir():
            _merge_entry(entry, destination / entry.name)
        source.rmdir()
        return
    if destination.is_dir() and not destination.is_symlink():
        shutil.rmtree(destination)
    elif destination.is_symlink() or destination.exists():
        destination.unlink()
    os.replace(source, destination)


def _publish(temporary: Path, destination: Path) -> None:
    if not destination.exists():
        os.replace(temporary, destination)
        return
    for entry in sorted(temporary.iterdir()):
        _merge_entry(entry, destination / entry.name)
    temporary.rmdir()


def _pack_conflicts(source: Path, destination: Path, relative: Path = Path()) -> list[str]:
    """Return the destination entries a pack would replace with different content."""
    conflicts: list[str] = []
    for entry in sorted(source.iterdir()):
        target = destination / entry.name
        location = relative / entry.name
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_symlink() or entry.is_dir() != target.is_dir():
            conflicts.append(location.as_posix())
        elif entry.is_dir():
            conflicts.extend(_pack_conflicts(entry, target, location))
        elif entry.read_bytes() != target.read_bytes():
            conflicts.append(location.as_posix())
    return conflicts


def _asset_references(source: str) -> set[str]:
    references = set()
    values = [match.group(1) for match in ASSET_PATTERN.finditer(source)]
    values.extend(next(group for group in match.groups() if group is not None) for match in ATTRIBUTE_ASSET_PATTERN.finditer(source))
    for raw_value in values:
        value = raw_value.replace("\\", "/")
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or value.startswith(("/", "#")):
            continue
        references.add(unquote(parsed.path))
    return references


def _without_speaker_notes(source: str) -> str:
    return NOTES_BLOCK_PATTERN.sub("", source)


def _deck_source(deck: Path, *, include_notes: bool) -> tuple[str, str]:
    """Return the deck as written, for copying, and as canonical text, for reading.

    A copy keeps the file's bytes on every platform: export, pack, and publish
    never rewrite the deck. ``read_text`` folds CRLF into LF and ``write_text``
    writes CRLF on Windows, so neither may produce the copied file. The parsers
    read canonical text (no byte-order mark, LF line endings).
    """
    original = deck.read_bytes().decode("utf-8")
    source = canonical_source(original)
    if include_notes:
        return original, source
    source = _without_speaker_notes(source)
    original = _without_speaker_notes(original)
    if canonical_source(original) != source:
        # Line endings the notes pattern cannot see (a lone CR) must not let a
        # note into the copy that the checked reading left out.
        original = source
    return original, source


def _front_matter(source: str) -> dict[str, object]:
    if not source.startswith("---"):
        return {}
    match = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", source, re.DOTALL)
    if not match:
        return {}
    loaded = yaml.safe_load(match.group(1)) or {}
    if not isinstance(loaded, dict):
        raise ValueError("Presentation front matter must be a mapping")
    return loaded


def _metadata_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(filter(None, (_metadata_text(item) for item in value)))
    if isinstance(value, dict):
        if "name" in value:
            return _metadata_text(value["name"])
        return " ".join(filter(None, (_metadata_text(item) for item in value.values())))
    return str(value)


def _page_metadata(source: str, fallback_title: str) -> dict[str, str]:
    front = _front_matter(source)
    title = _metadata_text(front.get("title")) or fallback_title
    author = _metadata_text(front.get("author"))
    description = _metadata_text(front.get("description")) or _metadata_text(front.get("subtitle"))
    return {"title": title, "author": author, "description": description}


def _configured_assets(source: str) -> tuple[str, set[str]]:
    assets = _front_matter(source).get("assets", {})
    if assets is None:
        assets = {}
    if not isinstance(assets, dict):
        raise ValueError("Presentation assets must be a mapping")
    figures = assets.get("figures") or "figures"
    include = assets.get("include") or []
    if not isinstance(figures, str):
        raise ValueError("assets.figures must be a project-relative directory")
    if not isinstance(include, list) or any(not isinstance(folder, str) for folder in include):
        raise ValueError("assets.include must be a list of project-relative directories")
    return figures, set(include)


def _asset_folder(project: Path, relative: str) -> Path | None:
    normalized = unquote(relative).replace("\\", "/")
    folder = (project / normalized).resolve()
    if not normalized or folder == project or not _inside(project, folder):
        raise ValueError(f"Asset folder leaves the presentation directory: {relative}")
    if not folder.exists():
        return None
    if not folder.is_dir():
        raise ValueError(f"Configured asset folder is not a directory: {relative}")
    return folder


def _folder_files(project: Path, relative: str) -> set[str]:
    folder = _asset_folder(project, relative)
    if folder is None:
        return set()
    return {
        path.relative_to(project).as_posix()
        for path in folder.rglob("*")
        if path.is_file() and _inside(project, path)
    }


def _copy_project_assets(deck: Path, source: str, destination: Path, *, trim_bibliography: bool = False) -> None:
    project = deck.parent.resolve()
    references = _asset_references(source)
    front = _front_matter(source)
    bibliography = front.get("bibliography")
    if isinstance(bibliography, str) and bibliography:
        references.add(bibliography)
    figures, included = _configured_assets(source)
    _asset_folder(project, figures)
    for folder in included:
        references.update(_folder_files(project, folder))
    for relative in sorted(references):
        asset = (project / relative).resolve()
        if not _inside(project, asset):
            raise ValueError(f"Asset leaves the presentation directory: {relative}")
        if not asset.is_file():
            raise FileNotFoundError(f"Referenced asset not found: {relative}")
        target = destination / Path(relative)
        _copy_entry(asset, target)
    if trim_bibliography and isinstance(bibliography, str) and bibliography:
        target = destination / bibliography
        trimmed = _trim_bibliography(target.read_bytes().decode("utf-8"), citation_keys(source))
        target.write_bytes(trimmed.encode("utf-8"))


def _exported_bibliography(destination: Path, source: str) -> str | None:
    relative = _front_matter(source).get("bibliography")
    if not isinstance(relative, str) or not relative:
        return None
    exported = destination / Path(unquote(relative).replace("\\", "/"))
    return exported.read_text(encoding="utf-8") if exported.is_file() else None


def _third_party_notice(project: Path | None = None, references: set[str] | None = None) -> str:
    inventory = APP_ROOT.parent / "THIRD_PARTY_LICENSES.md"
    sections = [inventory.read_text(encoding="utf-8").rstrip()] if inventory.is_file() else []
    for label, relative in (
        ("Reveal.js", "vendor/reveal/LICENSE"),
        ("KaTeX", "vendor/katex/LICENSE"),
        ("Marked", "vendor/marked/LICENSE.md"),
        ("js-yaml", "vendor/yaml/LICENSE"),
        ("bibtexParseJs", "vendor/bibtex/LICENSE"),
    ):
        sections.append(f"# {label}\n\n{(APP_ROOT / relative).read_text(encoding='utf-8').rstrip()}")
    if project is not None and references is not None:
        imported = icon_notices(project, references)
        used_licenses = set()
        collections: dict[str, list[dict[str, str]]] = {}
        for notice in imported:
            collections.setdefault(notice.get("prefix", "unknown"), []).append(notice)
        for notices in collections.values():
            notice = notices[0]
            files = "\n".join(f"- {item.get('path', item.get('name', 'Unknown icon'))}" for item in notices)
            sections.append(
                f"# Imported icon collection: {notice.get('collection', notice.get('prefix', 'Unknown'))}\n\n"
                f"Author: {notice.get('author', 'Unknown')}\n\n"
                f"Source: {notice.get('source', '')}\n\n"
                f"License: {notice.get('license', 'Unknown')} ({notice.get('license_url', '')})\n\n"
                f"Referenced imported SVG files:\n\n{files}\n\n"
                "These SVGs are redistributed as unmodified image resources."
            )
            used_licenses.add(notice.get("license"))
        license_root = Path(__file__).resolve().parent / "icon_licenses"
        for identifier, filename in (("Apache-2.0", "Apache-2.0.txt"), ("MIT", "Tabler-MIT.txt")):
            if identifier in used_licenses:
                sections.append(f"# {identifier} license for imported icons\n\n{(license_root / filename).read_text(encoding='utf-8').rstrip()}")
    return "\n\n---\n\n".join(sections) + "\n"


def _resource_tags(assets: str, runtime: str = "quarkfoil") -> tuple[str, str, str]:
    if assets == "local":
        styles = "\n".join(
            (
                f'  <link rel="stylesheet" href="{runtime}/vendor/reveal/reveal.css">',
                f'  <link rel="stylesheet" href="{runtime}/vendor/katex/katex.min.css">',
            )
        )
        scripts = "\n".join(
            f'  <script src="{runtime}/vendor/{path}"></script>'
            for path in (
                "reveal/reveal.js",
                "reveal/notes.js",
                "marked/marked.min.js",
                "yaml/js-yaml.min.js",
                "katex/katex.min.js",
                "bibtex/bibtexParse.js",
            )
        )
        return styles, scripts, "'self'"

    tags: dict[str, str] = {}
    for name, (relative, url) in CDN_FILES.items():
        integrity = _integrity(APP_ROOT / relative)
        if name.endswith("_css"):
            tags[name] = f'  <link rel="stylesheet" href="{url}" integrity="{integrity}" crossorigin="anonymous">'
        else:
            tags[name] = f'  <script src="{url}" integrity="{integrity}" crossorigin="anonymous"></script>'
    styles = "\n".join((tags["reveal_css"], tags["katex_css"]))
    scripts = "\n".join(tags[name] for name in ("reveal_js", "notes_js", "marked_js", "yaml_js", "katex_js", "bibtex_js"))
    return styles, scripts, "'self' https://cdn.jsdelivr.net"


def _index_html(
    assets: str,
    metadata: dict[str, str],
    preview_path: str | None = None,
    embedded: str | None = None,
    *,
    runtime: str = "quarkfoil",
    asset_map: str | None = None,
    canonical_url: str | None = None,
    preview_alt: str | None = None,
    preview_type: str | None = None,
    preview_size: tuple[int, int] | None = None,
) -> str:
    styles, scripts, external = _resource_tags(assets, runtime)
    # Reveal's notes plugin writes this pinned inline speaker-controller script
    # into its popup; the hash avoids enabling arbitrary inline JS.
    policy = (
        "default-src 'self'; "
        f"script-src {external} 'sha256-wfrJpa7dmlxqHmakgJIolYIQ+LOJmVS3HKfvdaO3GDE='; "
        f"style-src {external} 'unsafe-inline'; "
        f"font-src {external}; img-src 'self' data:; connect-src 'self'; "
        "object-src 'none'; frame-src 'self'; base-uri 'none'; form-action 'none'"
    )
    title = html.escape(metadata["title"], quote=True)
    author = html.escape(metadata["author"], quote=True)
    description = html.escape(metadata["description"], quote=True)
    twitter_card = "summary_large_image" if preview_path else "summary"
    meta = [f'  <meta name="author" content="{author}">'] if author else []
    if description:
        meta.append(f'  <meta name="description" content="{description}">')
    meta.extend((
        '  <meta property="og:type" content="website">',
        f'  <meta property="og:title" content="{title}">',
        f'  <meta name="twitter:card" content="{twitter_card}">',
        f'  <meta name="twitter:title" content="{title}">',
    ))
    canonical_tag = ""
    if canonical_url:
        escaped_url = html.escape(quote(canonical_url, safe="/:%"), quote=True)
        meta.append(f'  <meta property="og:url" content="{escaped_url}">')
        canonical_tag = f'  <link rel="canonical" href="{escaped_url}">\n'
    if description:
        meta.extend((
            f'  <meta property="og:description" content="{description}">',
            f'  <meta name="twitter:description" content="{description}">',
        ))
    if preview_path:
        preview_url = html.escape(quote(preview_path, safe="/:%"), quote=True)
        meta.extend((
            f'  <meta property="og:image" content="{preview_url}">',
            f'  <meta name="twitter:image" content="{preview_url}">',
        ))
        if preview_type:
            meta.append(f'  <meta property="og:image:type" content="{html.escape(preview_type, quote=True)}">')
        if preview_size:
            meta.extend((
                f'  <meta property="og:image:width" content="{preview_size[0]}">',
                f'  <meta property="og:image:height" content="{preview_size[1]}">',
            ))
        if preview_alt:
            escaped_alt = html.escape(preview_alt, quote=True)
            meta.extend((
                f'  <meta property="og:image:alt" content="{escaped_alt}">',
                f'  <meta name="twitter:image:alt" content="{escaped_alt}">',
            ))
    metadata_tags = "\n".join(meta)
    # A JSON data block, not a script: it needs no CSP hash because browsers
    # never execute it, and it lets the player start without fetching.
    embedded_tag = (
        f'  <script type="application/json" id="quarkfoil-source">{embedded}</script>\n' if embedded else ""
    )
    # Published decks share one asset pool, so the deck's own paths are mapped
    # to it here instead of being rewritten in the Markdown the player reads.
    asset_tag = (
        f'  <script type="application/json" id="quarkfoil-assets">{asset_map}</script>\n' if asset_map else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <meta http-equiv="Content-Security-Policy" content="{html.escape(policy, quote=True)}">
  <title>{title}</title>
{metadata_tags}
{canonical_tag}  <link rel="icon" href="{runtime}/quarkfoil-mark.svg" type="image/svg+xml">
{styles}
  <link rel="stylesheet" href="{runtime}/layout.css">
  <link rel="stylesheet" href="{runtime}/themes.css">
  <link rel="stylesheet" href="{runtime}/player.css">
</head>
<body>
  <button id="print-button" type="button" title="Print or save as PDF">Print / PDF</button>
  <main class="reveal" aria-label="Presentation">
    <div id="slides" class="slides"></div>
  </main>
  <div id="loading" role="status">Loading presentation…</div>
{embedded_tag}{asset_tag}{scripts}
  <script src="{runtime}/player.js"></script>
</body>
</html>
"""


def find_executable(candidates: tuple[str, ...]) -> str | None:
    """Return the first candidate that is on PATH or is itself a program."""
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
        path = Path(candidate)
        if path.is_file():
            return str(path)
    return None


def _executable(candidates: tuple[str, ...], label: str) -> str:
    found = find_executable(candidates)
    if found:
        return found
    raise RuntimeError(f"{label} is required to create an export preview")


@contextlib.contextmanager
def serve_directory(root: Path) -> Iterator[str]:
    """Serve a directory on a loopback port and yield its origin.

    A headless browser reads the presentation over HTTP rather than from
    ``file://`` so the player takes its ordinary network path.
    """
    handler = lambda *args, **kwargs: _QuietHandler(*args, directory=str(root), **kwargs)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _preview_command(
    browser: str, output: Path, url: str, size: tuple[int, int] = (1280, 720)
) -> list[str]:
    return [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={size[0]},{size[1]}",
        "--virtual-time-budget=30000",
        f"--screenshot={output}",
        url,
    ]


def _create_preview(
    export_root: Path,
    preview_path: str,
    page: str = "/?preview",
    size: tuple[int, int] = (1280, 720),
) -> None:
    browser = _executable(CHROMIUM_BROWSERS, "Chrome, Chromium, or Edge")
    output = export_root / preview_path
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Preview image already exists in the presentation assets: {preview_path}")

    with serve_directory(export_root) as origin:
        try:
            subprocess.run(
                _preview_command(browser, output, f"{origin}{page}", size),
                check=True,
                capture_output=True,
                timeout=60,
            )
            if not output.is_file() or not output.stat().st_size:
                raise RuntimeError("The browser did not create the preview image")
        except subprocess.CalledProcessError as error:
            detail = error.stderr.decode(errors="replace").strip() if isinstance(error.stderr, bytes) else str(error.stderr or "").strip()
            raise RuntimeError(detail or "Could not create the export preview") from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Timed out while creating the export preview") from error


def export_presentation(
    deck: Path,
    output: Path,
    *,
    assets: str = "local",
    preview: bool = False,
    include_notes: bool = True,
    trim_bibliography: bool = False,
) -> Path:
    resolved = deck.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Presentation not found: {resolved}")
    if resolved.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("Presentation source must be Markdown")
    if assets not in {"local", "cdn"}:
        raise ValueError(f"Unknown asset strategy: {assets}")

    destination = output.resolve()
    if destination.exists() and not destination.is_dir():
        raise FileExistsError(f"Export destination is not a directory: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    original, source = _deck_source(resolved, include_notes=include_notes)
    metadata = _page_metadata(source, resolved.stem)
    preview_path = None
    if preview:
        figures = "figures"
        front_assets = _front_matter(source).get("assets", {})
        if isinstance(front_assets, dict) and front_assets.get("figures"):
            figures = str(front_assets["figures"])
        preview_path = (Path(figures) / f"{resolved.stem}-preview.png").as_posix()

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        (temporary / "presentation.md").write_bytes(original.encode("utf-8"))
        _copy_project_assets(resolved, source, temporary, trim_bibliography=trim_bibliography)
        for source_name, target_name in EXPORT_FILES.items():
            _copy_entry(APP_ROOT / source_name, temporary / target_name)
        bundle = temporary / PLAYER_BUNDLE
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_text(_player_bundle(), encoding="utf-8")
        if assets == "local":
            for source_name, target_name in LOCAL_FILES.items():
                _copy_entry(APP_ROOT / source_name, temporary / target_name)
        (temporary / "THIRD_PARTY_LICENSES.txt").write_text(
            _third_party_notice(resolved.parent, _asset_references(source)), encoding="utf-8"
        )
        embedded = _embedded_source(source, _exported_bibliography(temporary, source))
        (temporary / "index.html").write_text(
            _index_html(
                assets,
                metadata,
                preview_path,
                embedded,
                preview_alt=metadata["title"] if preview_path else None,
                preview_type="image/png" if preview_path else None,
                preview_size=(1280, 720) if preview_path else None,
            ),
            encoding="utf-8",
        )
        if preview_path:
            _create_preview(temporary, preview_path)
        _publish(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def pack_presentation(
    deck: Path,
    output: Path,
    *,
    include_notes: bool = True,
    trim_bibliography: bool = False,
    force: bool = False,
) -> Path:
    """Copy *deck* and the assets it uses into a separate editable project folder."""
    resolved = deck.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Presentation not found: {resolved}")
    if resolved.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("Presentation source must be Markdown")

    destination = output.resolve()
    if destination.exists() and not destination.is_dir():
        raise FileExistsError(f"Pack destination is not a directory: {destination}")
    if destination == resolved.parent:
        raise ValueError("Pack destination is the presentation directory; choose another folder")
    destination.parent.mkdir(parents=True, exist_ok=True)
    original, source = _deck_source(resolved, include_notes=include_notes)

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        (temporary / resolved.name).write_bytes(original.encode("utf-8"))
        _copy_project_assets(resolved, source, temporary, trim_bibliography=trim_bibliography)
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
    return destination
