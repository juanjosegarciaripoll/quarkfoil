from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from io import StringIO
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from scientific_slides import main
from scientific_slides.deck_cli import apply_transaction, revision, without_notes
from scientific_slides.parser import parse_deck
from scientific_slides.storage import deck_file_lock


SOURCE = """---
title: Agent test
---

## First {.layout-1}

First body.

::: notes
Private first note.
:::

---

## Second {.layout-1}

Second body.

---

## Third {.layout-free}
"""


def wait_for_deck_lock(path: str, waiting: multiprocessing.synchronize.Event, acquired: multiprocessing.synchronize.Event) -> None:
    waiting.set()
    with deck_file_lock(Path(path)):
        acquired.set()


class DeckCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.deck = Path(self.temporary.name) / "deck.md"
        self.deck.write_text(SOURCE, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def invoke(self, arguments: list[str]) -> tuple[int, str, str]:
        output = StringIO()
        errors = StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            result = main(arguments)
        return result, output.getvalue(), errors.getvalue()

    def test_inspect_returns_revision_and_slide_source(self) -> None:
        result, output, errors = self.invoke(["deck", "inspect", str(self.deck)])
        self.assertEqual((result, errors), (0, ""))
        payload = json.loads(output)
        self.assertEqual(payload["revision"], revision(SOURCE.encode("utf-8")))
        self.assertEqual([slide["number"] for slide in payload["slides"]], [1, 2, 3])
        self.assertIn("Private first note", payload["source"])
        self.assertIn("Private first note", payload["slides"][0]["source"])

    def test_guide_is_concise_and_complete(self) -> None:
        result, output, errors = self.invoke(["deck", "guide"])
        self.assertEqual((result, errors), (0, ""))
        self.assertLess(len(output.split()), 150)
        self.assertIn("Quarkfoil agent protocol v1", output)
        self.assertIn('"operation":"replace"', output)
        self.assertIn("Exit 3 means the deck changed", output)
        self.assertIn("--no-notes filters returned JSON only", output)

    def test_no_notes_only_filters_returned_output(self) -> None:
        result, output, _ = self.invoke(["deck", "inspect", str(self.deck), "--no-notes"])
        self.assertEqual(result, 0)
        payload = json.loads(output)
        self.assertNotIn("::: notes", payload["source"])
        self.assertNotIn("Private first note", payload["slides"][0]["source"])
        self.assertEqual(self.deck.read_text(encoding="utf-8"), SOURCE)
        self.assertEqual(payload["revision"], revision(SOURCE.encode("utf-8")))

    def test_apply_transaction_supports_structural_operations(self) -> None:
        updated = apply_transaction(SOURCE, [
            {"operation": "replace", "slide": 2, "source": "## Replacement {.layout-0}\n"},
            {"operation": "insert", "after": 2, "source": "## Inserted {.layout-1}\n\nNew body.\n"},
            {"operation": "move", "slide": 4, "after": 1},
            {"operation": "delete", "slide": 3},
        ])
        deck = parse_deck(updated)
        self.assertEqual([slide.title for slide in deck.slides], ["First", "Third", "Inserted"])
        self.assertFalse([item for item in deck.diagnostics if item.level == "error"])

    def test_apply_commits_once_and_returns_new_revision_without_notes(self) -> None:
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": revision(SOURCE.encode("utf-8")),
            "operations": [{
                "operation": "replace",
                "slide": 2,
                "source": "## Updated {.layout-1}\n\nVisible.\n\n::: notes\nNew private note.\n:::\n",
            }],
        }), encoding="utf-8")
        result, output, errors = self.invoke(["deck", "apply", str(self.deck), str(transaction), "--no-notes"])
        self.assertEqual((result, errors), (0, ""))
        payload = json.loads(output)
        stored = self.deck.read_text(encoding="utf-8")
        self.assertIn("New private note", stored)
        self.assertNotIn("New private note", payload["source"])
        self.assertEqual(payload["revision"], revision(stored.encode("utf-8")))

    def test_stale_revision_rejects_without_writing(self) -> None:
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": "sha256:" + "0" * 64,
            "operations": [{"operation": "delete", "slide": 2}],
        }), encoding="utf-8")
        result, output, errors = self.invoke(["deck", "apply", str(self.deck), str(transaction)])
        self.assertEqual(result, 3)
        self.assertEqual(output, "")
        self.assertIn("presentation changed", errors)
        self.assertEqual(self.deck.read_text(encoding="utf-8"), SOURCE)

    def test_invalid_transaction_rejects_without_writing(self) -> None:
        digest = hashlib.sha256(SOURCE.encode("utf-8")).hexdigest()
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps([
            {"operation": "replace", "slide": 9, "source": "## Missing\n"},
        ]), encoding="utf-8")
        result, _, errors = self.invoke([
            "deck", "apply", str(self.deck), str(transaction), "--if-revision", digest,
        ])
        self.assertEqual(result, 2)
        self.assertIn("unknown slide 9", errors)
        self.assertEqual(self.deck.read_text(encoding="utf-8"), SOURCE)

    def test_final_slide_cannot_be_deleted(self) -> None:
        with self.assertRaisesRegex(Exception, "at least one slide"):
            apply_transaction("## Only\n", [{"operation": "delete", "slide": 1}])

    def test_note_filter_uses_structural_directives(self) -> None:
        source = "## Slide\n\nA literal `::: notes` remains.\n\n::: notes\nRemove me.\n:::\n"
        filtered = without_notes(source)
        self.assertIn("A literal `::: notes` remains", filtered)
        self.assertNotIn("Remove me", filtered)

    def test_deck_lock_serializes_separate_processes(self) -> None:
        context = multiprocessing.get_context("spawn")
        waiting = context.Event()
        acquired = context.Event()
        process = context.Process(target=wait_for_deck_lock, args=(str(self.deck), waiting, acquired))
        with deck_file_lock(self.deck):
            process.start()
            self.assertTrue(waiting.wait(2))
            self.assertFalse(acquired.wait(0.2))
        self.assertTrue(acquired.wait(2))
        process.join(timeout=2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
        self.assertEqual(process.exitcode, 0)


if __name__ == "__main__":
    unittest.main()
