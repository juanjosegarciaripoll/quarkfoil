from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path


ICONIFY_API = "https://api.iconify.design"
ICON_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ICON_COLLECTIONS = {
    "material-symbols": {
        "collection": "Material Symbols",
        "author": "Google LLC",
        "source": "https://github.com/google/material-design-icons",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
    },
    "tabler": {
        "collection": "Tabler Icons",
        "author": "Pawel Kuna and Tabler Icons contributors",
        "source": "https://github.com/tabler/tabler-icons",
        "license": "MIT",
        "license_url": "https://github.com/tabler/tabler-icons/blob/main/LICENSE",
    },
    "icon-park-outline": {
        "collection": "IconPark Outline",
        "author": "ByteDance IconPark contributors",
        "source": "https://github.com/bytedance/IconPark",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
    },
    "icon-park-solid": {
        "collection": "IconPark Solid",
        "author": "ByteDance IconPark contributors",
        "source": "https://github.com/bytedance/IconPark",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
    },
    "icon-park-twotone": {
        "collection": "IconPark Two-tone",
        "author": "ByteDance IconPark contributors",
        "source": "https://github.com/bytedance/IconPark",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
    },
}


def _read_url(url: str, *, maximum: int = 2 * 1024 * 1024) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Quarkfoil icon importer"})
    with urllib.request.urlopen(request, timeout=12) as response:
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("Icon service response is too large")
    return data


def search_icons(query: str, *, limit: int = 60) -> list[dict[str, str]]:
    query = query.strip()
    if len(query) < 2 or len(query) > 80:
        raise ValueError("Enter between 2 and 80 characters")
    parameters = urllib.parse.urlencode({
        "query": query,
        "prefixes": ",".join(ICON_COLLECTIONS),
        "limit": max(1, min(limit, 96)),
    })
    payload = json.loads(_read_url(f"{ICONIFY_API}/search?{parameters}").decode("utf-8"))
    results = []
    for value in payload.get("icons", []):
        prefix, separator, name = str(value).partition(":")
        if separator and prefix in ICON_COLLECTIONS and ICON_NAME.fullmatch(name):
            results.append({"id": value, "prefix": prefix, "name": name, "collection": ICON_COLLECTIONS[prefix]["collection"]})
    return results


def fetch_icon_svg(prefix: str, name: str) -> bytes:
    if prefix not in ICON_COLLECTIONS or not ICON_NAME.fullmatch(name):
        raise ValueError("Unknown icon")
    data = _read_url(f"{ICONIFY_API}/{prefix}/{name}.svg", maximum=512 * 1024)
    text = data.decode("utf-8")
    if not re.match(r"^\s*<svg\b", text, re.IGNORECASE) or re.search(
        r"<(?:script|foreignObject)\b|\bon[a-z]+\s*=|(?:href|src)\s*=\s*['\"]\s*(?:https?:|//|javascript:|data:)",
        text,
        re.IGNORECASE,
    ):
        raise ValueError("Icon service returned an unsafe SVG")
    return data


def import_icon(project_root: Path, figure_folder: Path, prefix: str, name: str) -> str:
    if prefix not in ICON_COLLECTIONS or not ICON_NAME.fullmatch(name):
        raise ValueError("Unknown icon")
    icon_folder = figure_folder / "icons"
    icon_folder.mkdir(parents=True, exist_ok=True)
    target = icon_folder / f"{prefix}--{name}.svg"
    relative = target.relative_to(project_root).as_posix()
    if not target.is_file():
        data = fetch_icon_svg(prefix, name)
        _atomic_write(target, data)
    metadata_path = icon_folder / ".quarkfoil-icons.json"
    metadata = {"version": 1, "icons": {}}
    if metadata_path.is_file():
        loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("icons"), dict):
            metadata = loaded
    metadata["icons"][relative] = {"prefix": prefix, "name": name, **ICON_COLLECTIONS[prefix]}
    _atomic_write(metadata_path, (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return relative


def _atomic_write(path: Path, data: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".quarkfoil-icon-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def icon_notices(project: Path, references: set[str]) -> list[dict[str, str]]:
    notices = []
    for metadata_path in project.rglob(".quarkfoil-icons.json"):
        try:
            icons = json.loads(metadata_path.read_text(encoding="utf-8")).get("icons", {})
        except (OSError, ValueError, AttributeError):
            continue
        for path, record in icons.items():
            if path not in references or not isinstance(record, dict):
                continue
            notices.append({**record, "path": path})
    return notices
