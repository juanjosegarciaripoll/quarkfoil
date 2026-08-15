from __future__ import annotations

import base64
import hashlib
import html
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .server import APP_ROOT, _inside
from .icons import icon_notices


EXPORT_FILES = {
    "modules/parser.js": "quarkfoil/parser.js",
    "modules/render.js": "quarkfoil/render.js",
    "modules/shapes.js": "quarkfoil/shapes.js",
    "modules/bibliography.js": "quarkfoil/bibliography.js",
    "modules/player.js": "quarkfoil/player.js",
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

ASSET_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)")
ATTRIBUTE_ASSET_PATTERN = re.compile(r"\b(?:src|poster)=(?:\"([^\"]+)\"|'([^']+)'|([^\s}]+))")


def _integrity(path: Path) -> str:
    digest = hashlib.sha384(path.read_bytes()).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def _copy_entry(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def _asset_references(source: str) -> set[str]:
    references = set()
    values = [match.group(1) for match in ASSET_PATTERN.finditer(source)]
    values.extend(next(group for group in match.groups() if group is not None) for match in ATTRIBUTE_ASSET_PATTERN.finditer(source))
    for raw_value in values:
        value = unquote(raw_value).replace("\\", "/")
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or value.startswith(("/", "#")):
            continue
        references.add(parsed.path)
    return references


def _yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value.strip()


def _configured_asset_folders(source: str) -> set[str]:
    if not source.startswith("---"):
        return {"figures"}
    lines = source.splitlines()
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {"figures"}

    folders = {"figures"}
    in_assets = False
    in_include = False
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0:
            in_assets = stripped == "assets:"
            in_include = False
            continue
        if not in_assets:
            continue
        if indent == 2 and stripped.startswith("figures:"):
            value = _yaml_scalar(stripped.split(":", 1)[1])
            if value:
                folders.discard("figures")
                folders.add(value)
            in_include = False
        elif indent == 2 and stripped == "include:":
            in_include = True
        elif in_include and indent >= 4 and stripped.startswith("-"):
            value = _yaml_scalar(stripped[1:])
            if value:
                folders.add(value)
        elif indent <= 2:
            in_include = False
    return folders


def _folder_files(project: Path, relative: str) -> set[str]:
    normalized = unquote(relative).replace("\\", "/")
    folder = (project / normalized).resolve()
    if not normalized or folder == project or not _inside(project, folder):
        raise ValueError(f"Asset folder leaves the presentation directory: {relative}")
    if not folder.exists():
        return set()
    if not folder.is_dir():
        raise ValueError(f"Configured asset folder is not a directory: {relative}")
    return {
        path.relative_to(project).as_posix()
        for path in folder.rglob("*")
        if path.is_file() and _inside(project, path)
    }


def _copy_project_assets(deck: Path, source: str, destination: Path) -> None:
    project = deck.parent.resolve()
    references = _asset_references(source)
    match = re.search(r"(?m)^bibliography:\s*[\"']?([^\s\"']+)", source.split("---", 2)[1] if source.startswith("---") else "")
    if match:
        references.add(match.group(1))
    for folder in _configured_asset_folders(source):
        references.update(_folder_files(project, folder))
    for relative in sorted(references):
        asset = (project / relative).resolve()
        if not _inside(project, asset):
            raise ValueError(f"Asset leaves the presentation directory: {relative}")
        if not asset.is_file():
            raise FileNotFoundError(f"Referenced asset not found: {relative}")
        target = destination / Path(relative)
        _copy_entry(asset, target)


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


def _resource_tags(assets: str) -> tuple[str, str, str]:
    if assets == "local":
        styles = "\n".join(
            (
                '  <link rel="stylesheet" href="quarkfoil/vendor/reveal/reveal.css">',
                '  <link rel="stylesheet" href="quarkfoil/vendor/katex/katex.min.css">',
            )
        )
        scripts = "\n".join(
            f'  <script src="quarkfoil/vendor/{path}"></script>'
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


def _index_html(assets: str) -> str:
    styles, scripts, external = _resource_tags(assets)
    policy = (
        "default-src 'self'; "
        f"script-src {external}; style-src {external} 'unsafe-inline'; "
        f"font-src {external}; img-src 'self' data:; connect-src 'self'; "
        "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <meta http-equiv="Content-Security-Policy" content="{html.escape(policy, quote=True)}">
  <title>Quarkfoil presentation</title>
{styles}
  <link rel="stylesheet" href="quarkfoil/layout.css">
  <link rel="stylesheet" href="quarkfoil/themes.css">
  <link rel="stylesheet" href="quarkfoil/player.css">
</head>
<body>
  <main class="reveal" aria-label="Presentation">
    <div id="slides" class="slides"></div>
  </main>
  <div id="loading" role="status">Loading presentation…</div>
{scripts}
  <script type="module" src="quarkfoil/player.js"></script>
</body>
</html>
"""


def export_presentation(deck: Path, output: Path, *, assets: str = "local") -> Path:
    resolved = deck.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Presentation not found: {resolved}")
    if resolved.suffix.lower() not in {".md", ".markdown"}:
        raise ValueError("Presentation source must be Markdown")
    if assets not in {"local", "cdn"}:
        raise ValueError(f"Unknown asset strategy: {assets}")

    destination = output.resolve()
    if destination.exists():
        raise FileExistsError(f"Export destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = resolved.read_text(encoding="utf-8")

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        (temporary / "presentation.md").write_text(source, encoding="utf-8")
        _copy_project_assets(resolved, source, temporary)
        for source_name, target_name in EXPORT_FILES.items():
            _copy_entry(APP_ROOT / source_name, temporary / target_name)
        if assets == "local":
            for source_name, target_name in LOCAL_FILES.items():
                _copy_entry(APP_ROOT / source_name, temporary / target_name)
        (temporary / "THIRD_PARTY_LICENSES.txt").write_text(
            _third_party_notice(resolved.parent, _asset_references(source)), encoding="utf-8"
        )
        (temporary / "index.html").write_text(_index_html(assets), encoding="utf-8")
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination
