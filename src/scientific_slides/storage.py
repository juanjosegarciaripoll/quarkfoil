"""Cross-process locking and atomic presentation writes."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile
from typing import BinaryIO, Iterator


def _lock_path(path: Path) -> Path:
    directory = Path(tempfile.gettempdir()) / "quarkfoil-locks"
    directory.mkdir(mode=0o700, exist_ok=True)
    identity = os.path.normcase(str(path.resolve())).encode("utf-8")
    return directory / f"{hashlib.sha256(identity).hexdigest()}.lock"


def _lock(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        if not stream.read(1):
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _unlock(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def deck_file_lock(path: Path) -> Iterator[None]:
    """Serialize writers of *path* across Quarkfoil processes."""
    with _lock_path(path).open("a+b") as stream:
        _lock(stream)
        try:
            yield
        finally:
            _unlock(stream)


def _replace_existing_windows(temporary: Path, path: Path) -> None:
    """Replace an existing Windows file while retaining its ACLs and attributes."""
    import ctypes
    from ctypes import wintypes

    replace_file = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    replace_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    )
    replace_file.restype = wintypes.BOOL
    if not replace_file(str(path.resolve()), str(temporary.resolve()), None, 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def atomic_write(path: Path, data: bytes) -> None:
    """Durably replace *path* with *data* without exposing a partial file."""
    original_mode = None
    if os.name != "nt" and path.exists():
        import stat

        original_mode = stat.S_IMODE(path.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".quarkfoil-deck-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if original_mode is not None:
            os.chmod(temporary, original_mode)
        if os.name == "nt" and path.exists():
            _replace_existing_windows(temporary, path)
        else:
            os.replace(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["atomic_write", "deck_file_lock"]
