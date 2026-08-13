"""Native launcher for frozen Quarkfoil desktop bundles."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import webbrowser
from pathlib import Path

from .server import PRESENTATION_SUFFIXES, ServerLifecycle


APP_NAME = "Quarkfoil"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def log_directory() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_NAME / "Logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP_NAME
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / APP_NAME.lower()


def configure_logging() -> Path:
    directory = log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "quarkfoil.log"
    logging.basicConfig(
        filename=destination,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return destination


def validate_deck_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.suffix.lower() not in PRESENTATION_SUFFIXES:
        raise ValueError("Choose a Markdown presentation ending in .md or .markdown")
    if path.exists() and not path.is_file():
        raise ValueError("The selected presentation is not a file")
    if not path.parent.resolve().is_dir():
        raise ValueError("The presentation directory does not exist")
    return path.resolve()


def parse_args(argv: list[str] | None = None) -> Path | None:
    parser = argparse.ArgumentParser(description="Launch the Quarkfoil desktop application")
    parser.add_argument("deck", nargs="?", type=Path, help="Markdown presentation to open")
    return parser.parse_args(argv).deck


def choose_deck(root: object) -> Path | None:
    from tkinter import filedialog, messagebox

    selected = filedialog.askopenfilename(
        parent=root,
        title="Open a Quarkfoil presentation",
        filetypes=(("Markdown presentations", "*.md *.markdown"), ("All files", "*.*")),
    )
    if selected:
        return validate_deck_path(selected)
    if not messagebox.askyesno(APP_NAME, "Create a new presentation instead?", parent=root):
        return None
    selected = filedialog.asksaveasfilename(
        parent=root,
        title="Create a Quarkfoil presentation",
        defaultextension=".md",
        filetypes=(("Markdown presentation", "*.md"), ("Markdown presentation", "*.markdown")),
    )
    return validate_deck_path(selected) if selected else None


def run_desktop(deck: Path | None = None) -> int:
    import tkinter as tk
    from tkinter import messagebox

    log_path = configure_logging()
    root = tk.Tk()
    root.withdraw()
    lifecycle: ServerLifecycle | None = None
    try:
        selected = validate_deck_path(deck) if deck is not None else choose_deck(root)
        if selected is None:
            return 0
        lifecycle = ServerLifecycle(selected, host="127.0.0.1", port=0, reload=False)
        lifecycle.start()
        logging.info("Opened %s at %s (frozen=%s)", selected, lifecycle.url, is_frozen())
        if not webbrowser.open(lifecycle.url):
            messagebox.showwarning(APP_NAME, f"Could not open a browser.\n\nOpen {lifecycle.url}", parent=root)

        root.deiconify()
        root.title(APP_NAME)
        root.resizable(False, False)
        tk.Label(root, text=f"Serving {selected.name}", padx=28, pady=14).pack()
        tk.Button(root, text="Open editor", width=22, command=lambda: webbrowser.open(lifecycle.url)).pack(pady=4)
        tk.Button(root, text="Quit", width=22, command=root.destroy).pack(pady=(4, 16))
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
        return 0
    except Exception as error:
        logging.exception("Desktop startup failed")
        messagebox.showerror(APP_NAME, f"Quarkfoil could not start:\n\n{error}\n\nLog: {log_path}", parent=root)
        return 1
    finally:
        if lifecycle is not None:
            lifecycle.stop()
        try:
            root.destroy()
        except tk.TclError:
            pass


def run_smoke_test(deck: Path, ready_file: Path, stop_file: Path) -> int:
    """Exercise a frozen server without GUI interaction in packaging CI."""
    import tkinter

    interpreter = tkinter.Tcl()
    if not interpreter.eval("info patchlevel"):
        raise RuntimeError("Tcl/Tk runtime did not initialize")
    lifecycle = ServerLifecycle(validate_deck_path(deck), host="127.0.0.1", port=0, reload=False)
    try:
        lifecycle.start()
        ready_file.write_text(lifecycle.url, encoding="utf-8")
        deadline = time.monotonic() + 60
        while not stop_file.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for desktop smoke-test shutdown")
            time.sleep(0.05)
        return 0
    finally:
        lifecycle.stop()


def main(argv: list[str] | None = None) -> int:
    try:
        deck = parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    ready = os.environ.get("QUARKFOIL_DESKTOP_SMOKE_READY")
    stop = os.environ.get("QUARKFOIL_DESKTOP_SMOKE_STOP")
    if ready and stop:
        if deck is None:
            return 2
        return run_smoke_test(deck, Path(ready), Path(stop))
    return run_desktop(deck)


if __name__ == "__main__":
    raise SystemExit(main())
