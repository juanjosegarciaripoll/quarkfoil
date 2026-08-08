"""Fetch exact, audited browser dependencies without Node or npm.

Run from the presentation-system directory:
    uv run python tools/fetch_vendor.py
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "app" / "vendor"

# Release archives are pinned. Update versions and hashes together after review.
ARCHIVES = {
    "reveal": {
        "url": "https://github.com/hakimel/reveal.js/archive/refs/tags/5.2.1.zip",
        "sha256": "ad6fe79a57309a80a09a7ea7fa1d8cb260caf045567cb2198d70c0c896336257",
        "prefix": "reveal.js-5.2.1",
        "copies": {
            "dist/reveal.js": "reveal/reveal.js",
            "dist/reveal.css": "reveal/reveal.css",
            "plugin/notes/notes.js": "reveal/notes.js",
            "LICENSE": "reveal/LICENSE",
        },
    },
    "katex": {
        "url": "https://github.com/KaTeX/KaTeX/releases/download/v0.16.22/katex.zip",
        "sha256": "aecf657d52774c7af21bd72da7825ef7844ac38af8a879e9fd200568f38a5cb4",
        "prefix": "",
        "copies": {
            "katex.min.js": "katex/katex.min.js",
            "katex.min.css": "katex/katex.min.css",
            "fonts": "katex/fonts",
        },
    },
}

FILES = {
    "marked/marked.min.js": {
        "url": "https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js",
        "sha256": "3e7e7d7feb3e5d58cb6c804f68ab5c24cc7e5eb6270fd6e5cbb9124739217d0c",
    },
    "yaml/js-yaml.min.js": {
        "url": "https://cdn.jsdelivr.net/npm/js-yaml@4.1.0/dist/js-yaml.min.js",
        "sha256": "45dc3dd03dc07a06705a2c2989b8c7f709013f04bd5386e3279d4e447f07ebd7",
    },
    "katex/LICENSE": {
        "url": "https://raw.githubusercontent.com/KaTeX/KaTeX/v0.16.22/LICENSE",
        "sha256": "766ccc1f306c885aa45542a9846bbd0a505b27a0374f146778171c2254ce18e3",
    },
    "marked/LICENSE.md": {
        "url": "https://raw.githubusercontent.com/markedjs/marked/v15.0.12/LICENSE.md",
        "sha256": "8e3a3f82f59a60958f56ca08f445647c32a4733dc7ca6c2c46f6eb898471ab9c",
    },
    "yaml/LICENSE": {
        "url": "https://raw.githubusercontent.com/nodeca/js-yaml/4.1.0/LICENSE",
        "sha256": "a07bc24468b9654ce76a547d47a2db282d07733b715db4c73a98bd63961f9550",
    },
}


def download(url: str, destination: Path) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "scientific-slides-vendor-fetch/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def copy_entry(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        shutil.copy2(source, destination)


def find_entry(base: Path, relative: str) -> Path:
    direct = base / relative
    if direct.exists():
        return direct
    wanted = Path(relative).as_posix()
    candidates = [path for path in base.rglob(Path(relative).name) if path.as_posix().endswith(wanted)]
    if len(candidates) != 1:
        raise FileNotFoundError(f"Cannot uniquely locate '{relative}' in archive: {candidates}")
    return candidates[0]


def main() -> None:
    VENDOR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="scientific-slides-") as temporary:
        temp = Path(temporary)
        for name, spec in ARCHIVES.items():
            archive = temp / f"{name}.zip"
            digest = download(spec["url"], archive)
            expected = spec["sha256"]
            if expected and digest != expected:
                raise RuntimeError(f"Checksum mismatch for {name}: {digest}")
            print(f"{name}: sha256={digest}")
            extracted = temp / name
            with zipfile.ZipFile(archive) as package:
                package.extractall(extracted)
            base = extracted / spec["prefix"] if spec["prefix"] else extracted
            for source, destination in spec["copies"].items():
                copy_entry(find_entry(base, source), VENDOR / destination)
        for destination, spec in FILES.items():
            target = VENDOR / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = download(spec["url"], target)
            if spec["sha256"] and digest != spec["sha256"]:
                target.unlink(missing_ok=True)
                raise RuntimeError(f"Checksum mismatch for {destination}: {digest}")
            print(f"{destination}: sha256={digest}")


if __name__ == "__main__":
    main()
