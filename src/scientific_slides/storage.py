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


def atomic_write(path: Path, data: bytes) -> None:
    """Durably replace *path* with *data* without exposing a partial file."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=".quarkfoil-deck-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
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
