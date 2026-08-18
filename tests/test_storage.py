import os
from pathlib import Path
import stat
import tempfile
import unittest

from scientific_slides.storage import atomic_write


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
