"""Launch and cleanly stop a frozen Quarkfoil bundle in native CI."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def executable() -> Path:
    if sys.platform == "win32":
        return ROOT / "dist" / "Quarkfoil" / "Quarkfoil.exe"
    if sys.platform == "darwin":
        return ROOT / "dist" / "Quarkfoil.app" / "Contents" / "MacOS" / "Quarkfoil"
    if sys.platform == "linux":
        return ROOT / "dist" / "Quarkfoil" / "Quarkfoil"
    raise SystemExit("Frozen desktop smoke tests run only on Windows, macOS, or Linux")


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        deck = root / "frozen smoke.md"
        deck.write_text("# Frozen smoke test\n", encoding="utf-8")
        ready = root / "ready.txt"
        stop = root / "stop"
        environment = os.environ.copy()
        environment["QUARKFOIL_DESKTOP_SMOKE_READY"] = str(ready)
        environment["QUARKFOIL_DESKTOP_SMOKE_STOP"] = str(stop)
        process = subprocess.Popen([str(executable()), str(deck)], env=environment)
        try:
            deadline = time.monotonic() + 30
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            if not ready.exists():
                raise RuntimeError(f"Frozen launcher did not become ready (exit={process.poll()})")
            url = ready.read_text(encoding="utf-8")
            with urllib.request.urlopen(url, timeout=5) as response:
                body = response.read()
            if response.status != 200 or b"Quarkfoil" not in body:
                raise RuntimeError("Frozen launcher did not serve the application shell")
            port = urllib.parse.urlsplit(url).port
            stop.touch()
            if process.wait(timeout=10) != 0:
                raise RuntimeError("Frozen launcher exited unsuccessfully")
            assert port is not None
            with socket.socket() as probe:
                probe.settimeout(1)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError("Frozen launcher left its loopback port open")
            print(f"Frozen desktop smoke test passed at {url}")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
