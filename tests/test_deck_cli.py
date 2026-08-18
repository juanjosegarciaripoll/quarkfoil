from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from io import StringIO
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

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
        self.assertEqual(payload["slides"][0]["slide_revision"], revision(parse_deck(SOURCE).slides[0].raw.encode("utf-8")))
        self.assertIn("Private first note", payload["source"])
        self.assertIn("Private first note", payload["slides"][0]["source"])

    def test_guide_is_concise_and_complete(self) -> None:
        result, output, errors = self.invoke(["deck", "guide"])
        self.assertEqual((result, errors), (0, ""))
        self.assertLess(len(output.split()), 150)
        self.assertIn("Quarkfoil agent protocol v1", output)
        self.assertIn('"operation":"replace"', output)
        self.assertIn("Exit 3 means the deck changed", output)
        self.assertIn("--no-notes hides returned notes", output)

    def test_protocol_advertises_machine_readable_contract(self) -> None:
        result, output, errors = self.invoke(["deck", "protocol"])
        self.assertEqual((result, errors), (0, ""))
        payload = json.loads(output)
        self.assertEqual(payload["protocol_version"], 1)
        self.assertIn("dry_run", payload["capabilities"])
        self.assertEqual(payload["exit_codes"]["3"], "revision conflict")
        self.assertNotIn("schema_dialect", payload)
        self.assertIn("changed_slides", payload["response_shapes"]["apply"]["required"])

    def test_apply_help_describes_quiet_result(self) -> None:
        output = StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as stopped:
            main(["deck", "apply", "--help"])
        self.assertEqual(stopped.exception.code, 0)
        self.assertIn("Omit the complete deck snapshot; return revision", output.getvalue())
        self.assertIn("changed slides, operation results, and diagnostics", output.getvalue())

    def test_inspect_projection_and_compact_output(self) -> None:
        result, output, errors = self.invoke([
            "deck", "inspect", str(self.deck), "--no-source", "--slides", "2", "--compact",
        ])
        self.assertEqual((result, errors), (0, ""))
        self.assertNotIn("\n ", output)
        payload = json.loads(output)
        self.assertNotIn("source", payload)
        self.assertEqual([slide["number"] for slide in payload["slides"]], [2])

    def test_projection_rejects_missing_slides_and_uses_deck_order(self) -> None:
        result, output, errors = self.invoke(["deck", "inspect", str(self.deck), "--slides", "999"])
        self.assertEqual((result, output), (2, ""))
        self.assertEqual(json.loads(errors)["error"], "unknown_slide")
        result, output, errors = self.invoke(["deck", "inspect", str(self.deck), "--slides", "3,1"])
        self.assertEqual((result, errors), (0, ""))
        self.assertEqual([slide["number"] for slide in json.loads(output)["slides"]], [1, 3])

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

    def test_replace_preserves_all_source_outside_target_range(self) -> None:
        source = "---\r\ntitle: Exact\r\n---\r\n\r\n## First\r\n\r\nKeep  trailing spaces.  \r\n\r\n  ---  \r\n\r\n\r\n## Second\r\n\r\nOld.\r\n\r\n---\r\n\r\n## Third\r\n\r\nKeep third.\r\n"
        target = parse_deck(source).slides[1].range
        updated = apply_transaction(source, [{
            "operation": "replace", "slide": 2, "source": "## Replacement\r\n\r\nNew.\r\n",
        }])
        self.assertEqual(updated[:target.start], source[:target.start])
        self.assertEqual(updated[-len(source[target.end:]):], source[target.end:])
        self.assertNotIn("\n", updated.replace("\r\n", ""))

    def test_insert_preserves_source_on_both_sides_of_insertion(self) -> None:
        deck = parse_deck(SOURCE)
        insertion = deck.slides[1].range.end
        updated = apply_transaction(SOURCE, [{
            "operation": "insert", "after": 2, "source": "## Inserted\n\nNew.\n",
        }])
        self.assertEqual(updated[:insertion], SOURCE[:insertion])
        self.assertTrue(updated.endswith(SOURCE[insertion:]))

    def test_delete_removes_only_slide_and_following_separator(self) -> None:
        deck = parse_deck(SOURCE)
        target = deck.slides[1]
        following = deck.slides[2]
        updated = apply_transaction(SOURCE, [{"operation": "delete", "slide": 2}])
        self.assertEqual(updated, SOURCE[:target.range.start] + SOURCE[following.range.start:])

    def test_move_preserves_every_slide_body(self) -> None:
        original = parse_deck(SOURCE)
        updated = parse_deck(apply_transaction(SOURCE, [{"operation": "move", "slide": 3, "after": 1}]))
        self.assertEqual([slide.title for slide in updated.slides], ["First", "Third", "Second"])
        original_bodies = {slide.title: slide.raw.strip() for slide in original.slides}
        self.assertEqual({slide.title: slide.raw.strip() for slide in updated.slides}, original_bodies)

    def test_apply_commits_once_and_returns_new_revision_without_notes(self) -> None:
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": revision(SOURCE.encode("utf-8")),
            "operations": [{
                "operation": "replace",
                "slide": 2,
                "source": "## Updated {.layout-1}\n\nVisible.\n\n::: notes\nNew private note.\n:::\n",
                "notes": "replace",
            }],
        }), encoding="utf-8")
        result, output, errors = self.invoke(["deck", "apply", str(self.deck), str(transaction), "--no-notes"])
        self.assertEqual((result, errors), (0, ""))
        payload = json.loads(output)
        stored = self.deck.read_text(encoding="utf-8")
        self.assertIn("New private note", stored)
        self.assertNotIn("New private note", payload["source"])
        self.assertEqual(payload["revision"], revision(stored.encode("utf-8")))

    def test_no_notes_preserves_hidden_notes_when_replacing_slide(self) -> None:
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": revision(SOURCE.encode("utf-8")),
            "operations": [{
                "operation": "replace",
                "slide": 1,
                "source": "## Revised {.layout-1}\n\nVisible replacement.\n",
            }],
        }), encoding="utf-8")
        result, output, errors = self.invoke(["deck", "apply", str(self.deck), str(transaction), "--no-notes"])
        self.assertEqual((result, errors), (0, ""))
        self.assertIn("Private first note", self.deck.read_text(encoding="utf-8"))
        self.assertNotIn("Private first note", json.loads(output)["source"])

    def test_replace_notes_policy_is_independent_of_output_filter(self) -> None:
        preserved = apply_transaction(SOURCE, [{
            "operation": "replace", "slide": 1,
            "source": "## Preserved\n\nNew.\n\n::: notes\nIgnored.\n:::\n",
        }])
        self.assertIn("Private first note", preserved)
        self.assertNotIn("Ignored", preserved)
        replaced = apply_transaction(SOURCE, [{
            "operation": "replace", "slide": 1, "notes": "replace",
            "source": "## Replaced\n\nNew.\n\n::: notes\nReplacement note.\n:::\n",
        }])
        self.assertIn("Replacement note", replaced)
        removed = apply_transaction(SOURCE, [{
            "operation": "replace", "slide": 1, "notes": "remove", "source": "## Removed\n",
        }])
        self.assertNotIn("Private first note", removed)

    def test_dry_run_validates_without_writing(self) -> None:
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": revision(SOURCE.encode("utf-8")),
            "operations": [{"operation": "delete", "slide": 2}],
        }), encoding="utf-8")
        result, output, errors = self.invoke([
            "deck", "apply", str(self.deck), str(transaction), "--dry-run", "--quiet", "--compact",
        ])
        self.assertEqual((result, errors), (0, ""))
        self.assertTrue(json.loads(output)["dry_run"])
        self.assertEqual(self.deck.read_text(encoding="utf-8"), SOURCE)

    def test_quiet_apply_returns_changed_slides_and_operation_mapping(self) -> None:
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": revision(SOURCE.encode("utf-8")),
            "operations": [
                {"operation": "replace", "slide": 2, "source": "## Replaced\n"},
                {"operation": "insert", "after": 2, "source": "## Inserted\n"},
                {"operation": "move", "slide": 4, "after": 1},
                {"operation": "delete", "slide": 3},
            ],
        }), encoding="utf-8")
        result, output, errors = self.invoke([
            "deck", "apply", str(self.deck), str(transaction), "--quiet", "--compact",
        ])
        self.assertEqual((result, errors), (0, ""))
        payload = json.loads(output)
        self.assertEqual([slide["title"] for slide in payload["changed_slides"]], ["Third", "Inserted"])
        self.assertEqual(
            [item["result_slide"] for item in payload["operation_results"]],
            [None, 3, 2, None],
        )
        self.assertEqual([slide.title for slide in parse_deck(self.deck.read_text(encoding="utf-8")).slides],
                         ["First", "Third", "Inserted"])

    def test_source_file_is_relative_to_transaction_and_revision_guarded(self) -> None:
        fragments = Path(self.temporary.name) / "fragments"
        fragments.mkdir()
        fragment = fragments / "equation.md"
        fragment.write_text("## Equation\n\n\\[H=\\sum_i n_i\\]\n", encoding="utf-8")
        transaction = fragments / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": revision(SOURCE.encode("utf-8")),
            "operations": [{
                "operation": "replace", "slide": 2, "source_file": "equation.md",
                "source_revision": revision(fragment.read_bytes()),
            }],
        }), encoding="utf-8")

        result, output, errors = self.invoke([
            "deck", "apply", str(self.deck), str(transaction), "--quiet", "--compact",
        ])

        self.assertEqual((result, errors), (0, ""))
        self.assertIn("\\sum_i", json.loads(output)["changed_slides"][0]["source"])
        self.assertIn("\\sum_i", self.deck.read_text(encoding="utf-8"))
        self.assertTrue(fragment.is_file())

    def test_source_file_errors_are_structured_and_leave_deck_unchanged(self) -> None:
        fragment = Path(self.temporary.name) / "slide.md"
        fragment.write_text("## External\n", encoding="utf-8")
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": revision(SOURCE.encode("utf-8")),
            "operations": [{
                "operation": "replace", "slide": 2, "source_file": "slide.md",
                "source_revision": "sha256:" + "0" * 64,
            }],
        }), encoding="utf-8")

        result, output, errors = self.invoke(["deck", "apply", str(self.deck), str(transaction)])

        self.assertEqual((result, output), (2, ""))
        payload = json.loads(errors)
        self.assertEqual(payload["error"], "source_revision_mismatch")
        self.assertEqual(payload["path"], "operations[0].source_file")
        self.assertEqual(payload["resolved_source_path"], str(fragment.resolve()))
        self.assertEqual(self.deck.read_text(encoding="utf-8"), SOURCE)

    def test_source_and_source_file_are_mutually_exclusive(self) -> None:
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": revision(SOURCE.encode("utf-8")),
            "operations": [{"operation": "insert", "after": 1, "source": "## Inline\n", "source_file": "x.md"}],
        }), encoding="utf-8")
        result, _, errors = self.invoke(["deck", "apply", str(self.deck), str(transaction)])
        self.assertEqual(result, 2)
        self.assertIn("exactly one", json.loads(errors)["message"])
        self.assertEqual(self.deck.read_text(encoding="utf-8"), SOURCE)

    def test_stdin_source_file_is_relative_to_current_directory(self) -> None:
        fragment = Path(self.temporary.name) / "stdin-slide.md"
        fragment.write_text("## From stdin\n", encoding="utf-8")
        transaction = json.dumps({
            "revision": revision(SOURCE.encode("utf-8")),
            "operations": [{"operation": "replace", "slide": 2, "source_file": fragment.name}],
        })
        previous = Path.cwd()
        output, errors = StringIO(), StringIO()
        try:
            os.chdir(self.temporary.name)
            with mock.patch.object(sys, "stdin", StringIO(transaction)), \
                    redirect_stdout(output), redirect_stderr(errors):
                result = main(["deck", "apply", str(self.deck), "-", "--quiet"])
        finally:
            os.chdir(previous)
        self.assertEqual((result, errors.getvalue()), (0, ""))
        self.assertEqual(json.loads(output.getvalue())["changed_slides"][0]["title"], "From stdin")

    def test_errors_are_structured_and_operation_indexed(self) -> None:
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": revision(SOURCE.encode("utf-8")),
            "operations": [{"operation": "delete", "slide": 9}],
        }), encoding="utf-8")
        result, output, errors = self.invoke(["deck", "apply", str(self.deck), str(transaction)])
        self.assertEqual((result, output), (2, ""))
        payload = json.loads(errors)
        self.assertEqual(payload["error"], "invalid_request")
        self.assertEqual(payload["operation"], 0)
        self.assertEqual(payload["path"], "operations[0]")

    def test_conflicts_are_structured(self) -> None:
        transaction = Path(self.temporary.name) / "transaction.json"
        transaction.write_text(json.dumps({
            "revision": "sha256:" + "0" * 64,
            "operations": [{"operation": "delete", "slide": 2}],
        }), encoding="utf-8")
        result, output, errors = self.invoke(["deck", "apply", str(self.deck), str(transaction)])
        self.assertEqual((result, output), (3, ""))
        payload = json.loads(errors)
        self.assertEqual(payload["error"], "revision_mismatch")
        self.assertIn("actual_revision", payload)

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
