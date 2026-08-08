from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path

from scientific_slides.server import create_server


ROOT = Path(__file__).resolve().parents[1]


def find_edge() -> Path:
    candidates = []
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(variable)
        if base:
            candidates.append(Path(base) / "Microsoft/Edge/Application/msedge.exe")
    candidates.append(Path.home() / "AppData/Local/Microsoft/Edge/Application/msedge.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Microsoft Edge is required for the browser self-test")


def main() -> int:
    server = create_server(ROOT / "example/deck.md", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="quarkfoil-edge-") as profile:
            result = subprocess.run(
                [
                    str(find_edge()),
                    "--headless",
                    "--disable-gpu",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=5000",
                    f"--user-data-dir={profile}",
                    "--dump-dom",
                    f"http://127.0.0.1:{server.server_port}/selftest.html",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=True,
            )
        if 'data-status="passed"' not in result.stdout or "checks passed" not in result.stdout:
            excerpt = result.stdout[-4000:]
            raise RuntimeError(f"Browser self-test did not pass:\n{excerpt}\n{result.stderr}")
        print("Quarkfoil browser self-test passed in Microsoft Edge.")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
