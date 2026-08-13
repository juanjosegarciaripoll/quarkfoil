"""Build a native, unsigned Quarkfoil desktop bundle on the current OS."""

from __future__ import annotations

import struct
import subprocess
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRANDING = ROOT / "build" / "desktop-branding"


def _png(size: int = 256) -> bytes:
    rows = []
    center = (size - 1) / 2
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            radius = ((x - center) ** 2 + (y - center) ** 2) ** 0.5
            ring = size * 0.27 < radius < size * 0.38
            tail = x > center and y > center and abs(x - y) < size * 0.055 and radius < size * 0.48
            if ring or tail:
                row.extend((31, 94, 113, 255))
            else:
                row.extend((245, 249, 250, 255))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def create_icons() -> None:
    BRANDING.mkdir(parents=True, exist_ok=True)
    png = _png()
    (BRANDING / "quarkfoil.png").write_bytes(png)
    ico_header = struct.pack("<HHHBBBBHHII", 0, 1, 1, 0, 0, 0, 0, 1, 32, len(png), 22)
    (BRANDING / "quarkfoil.ico").write_bytes(ico_header + png)
    icns_entry = b"ic08" + struct.pack(">I", len(png) + 8) + png
    (BRANDING / "quarkfoil.icns").write_bytes(b"icns" + struct.pack(">I", len(icns_entry) + 8) + icns_entry)


def main() -> int:
    if sys.platform not in {"win32", "darwin", "linux"}:
        raise SystemExit("Desktop bundles must be built natively on Windows, macOS, or Linux")
    create_icons()
    return subprocess.call([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "packaging" / "quarkfoil.spec")], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
