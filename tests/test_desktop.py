from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scientific_slides.desktop import parse_args, run_smoke_test, validate_deck_path
from scientific_slides.server import ServerLifecycle


class DesktopPathTests(unittest.TestCase):
    def test_zero_or_one_document_argument(self) -> None:
        self.assertIsNone(parse_args([]))
        self.assertEqual(parse_args(["talk.md"]), Path("talk.md"))
        with self.assertRaises(SystemExit):
            parse_args(["one.md", "two.md"])

    def test_validate_deck_accepts_existing_and_new_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / "démo deck.markdown"
            existing.write_text("# Test\n", encoding="utf-8")
            self.assertEqual(validate_deck_path(existing), existing.resolve())
            self.assertEqual(validate_deck_path(root / "new.md"), (root / "new.md").resolve())

    def test_validate_deck_rejects_other_suffixes(self) -> None:
        with self.assertRaisesRegex(ValueError, "ending in"):
            validate_deck_path("deck.txt")


class ServerLifecycleTests(unittest.TestCase):
    def test_headless_packaging_smoke_mode_starts_and_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deck = root / "deck.md"
            deck.write_text("# Test\n", encoding="utf-8")
            ready = root / "ready"
            stop = root / "stop"
            stop.touch()
            self.assertEqual(run_smoke_test(deck, ready, stop), 0)
            self.assertRegex(ready.read_text(encoding="utf-8"), r"^http://127\.0\.0\.1:\d+/$")

    def test_ephemeral_port_and_programmatic_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            deck = Path(temporary) / "deck.md"
            deck.write_text("# Test\n", encoding="utf-8")
            lifecycle = ServerLifecycle(deck, port=0, reload=False)
            self.assertNotEqual(lifecycle.server.server_port, 0)
            lifecycle.start()
            thread = lifecycle._server_thread
            lifecycle.stop()
            self.assertIsNotNone(thread)
            self.assertFalse(thread.is_alive())

    def test_browser_policy_opens_resolved_url_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            deck = Path(temporary) / "deck.md"
            deck.write_text("# Test\n", encoding="utf-8")
            with mock.patch("scientific_slides.server.threading.Timer") as timer:
                lifecycle = ServerLifecycle(deck, port=0, reload=False, open_browser=True)
                lifecycle.start()
                lifecycle.stop()
            timer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
