import os
from io import BytesIO
from pathlib import Path
import stat
import tempfile
import unittest

from scientific_slides.storage import _ensure_lock_byte, atomic_write


class UnreadableBytesIO(BytesIO):
    def read(self, *args, **kwargs):
        raise PermissionError("locked byte cannot be read")


class DeckLockTests(unittest.TestCase):
    def test_lock_byte_initialization_does_not_read_locked_region(self):
        existing = UnreadableBytesIO(b"\0")
        _ensure_lock_byte(existing)
        self.assertEqual(existing.tell(), 0)
        self.assertEqual(existing.getvalue(), b"\0")

        empty = UnreadableBytesIO()
        _ensure_lock_byte(empty)
        self.assertEqual(empty.tell(), 0)
        self.assertEqual(empty.getvalue(), b"\0")


class AtomicWriteTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX mode bits do not model Windows ACLs")
    def test_atomic_write_preserves_existing_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deck.md"
            path.write_bytes(b"old")
            path.chmod(0o640)

            atomic_write(path, b"new")

            self.assertEqual(path.read_bytes(), b"new")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)


if __name__ == "__main__":
    unittest.main()
