from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scientific_slides import main
from scientific_slides.exporter import pack_presentation


class PackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        figures = self.project / "figures"
        figures.mkdir(parents=True)
        (figures / "diagram.svg").write_text(
            "<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8"
        )
        (figures / "unused.svg").write_text(
            "<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8"
        )
        self.deck = self.project / "lecture.md"
        self.deck.write_text(
            "---\ntitle: Pack test\n---\n\n"
            "## Diagram {.layout-1}\n\n"
            "::: core\n![](figures/diagram.svg){fit=contain}\n:::\n\n"
            "::: notes\nRemember the derivation.\n:::\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_pack_copies_the_deck_under_its_own_name_with_its_assets(self) -> None:
        destination = pack_presentation(self.deck, self.root / "packed")

        self.assertEqual(destination, (self.root / "packed").resolve())
        packed = destination / "lecture.md"
        self.assertEqual(packed.read_text(encoding="utf-8"), self.deck.read_text(encoding="utf-8"))
        self.assertTrue((destination / "figures/diagram.svg").is_file())
        self.assertFalse((destination / "figures/unused.svg").exists())

    def test_pack_copies_the_deck_bytes_whatever_their_line_endings(self) -> None:
        # Path.write_text would write CRLF on Windows; read_text folds CRLF to LF.
        source = self.deck.read_bytes().replace(b"\r\n", b"\n")
        for name, data in (("lf", source), ("crlf", source.replace(b"\n", b"\r\n"))):
            with self.subTest(name):
                self.deck.write_bytes(data)
                destination = pack_presentation(self.deck, self.root / f"packed-{name}")
                self.assertEqual((destination / "lecture.md").read_bytes(), data)
        crlf = source.replace(b"\n", b"\r\n")
        self.deck.write_bytes(crlf)
        destination = pack_presentation(self.deck, self.root / "packed-no-notes", include_notes=False)
        packed = (destination / "lecture.md").read_bytes()
        self.assertNotIn(b"Remember the derivation", packed)
        self.assertNotIn(b"\n", packed.replace(b"\r\n", b""))

    def test_pack_writes_no_website_files(self) -> None:
        destination = pack_presentation(self.deck, self.root / "packed")

        self.assertFalse((destination / "index.html").exists())
        self.assertFalse((destination / "quarkfoil").exists())
        self.assertFalse((destination / "presentation.md").exists())
        self.assertFalse((destination / "THIRD_PARTY_LICENSES.txt").exists())
        self.assertEqual(
            sorted(path.name for path in destination.iterdir()), ["figures", "lecture.md"]
        )

    def test_included_folders_and_the_bibliography_are_packed(self) -> None:
        (self.project / "data").mkdir()
        (self.project / "data" / "series.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        (self.project / "refs.bib").write_text(
            "@article{cited,\n  title = {Cited},\n}\n\n@article{other,\n  title = {Other},\n}\n",
            encoding="utf-8",
        )
        self.deck.write_text(
            "---\ntitle: Pack test\nbibliography: refs.bib\nassets:\n  include:\n    - data\n---\n\n"
            "## Slide {.layout-1}\n\n::: core\nSee [@cited].\n:::\n",
            encoding="utf-8",
        )

        destination = pack_presentation(self.deck, self.root / "packed")

        self.assertTrue((destination / "data/series.csv").is_file())
        self.assertIn("@article{other", (destination / "refs.bib").read_text(encoding="utf-8"))

    def test_options_trim_the_packed_notes_and_bibliography(self) -> None:
        (self.project / "refs.bib").write_text(
            "@article{cited,\n  title = {Cited},\n}\n\n@article{other,\n  title = {Other},\n}\n",
            encoding="utf-8",
        )
        self.deck.write_text(
            "---\ntitle: Pack test\nbibliography: refs.bib\n---\n\n"
            "## Slide {.layout-1}\n\n::: core\nSee [@cited].\n:::\n\n"
            "::: notes\nRemember the derivation.\n:::\n",
            encoding="utf-8",
        )

        destination = pack_presentation(
            self.deck, self.root / "packed", include_notes=False, trim_bibliography=True
        )

        packed = (destination / "lecture.md").read_text(encoding="utf-8")
        self.assertNotIn("Remember the derivation", packed)
        bibliography = (destination / "refs.bib").read_text(encoding="utf-8")
        self.assertIn("@article{cited", bibliography)
        self.assertNotIn("@article{other", bibliography)
        self.assertIn("Remember the derivation", self.deck.read_text(encoding="utf-8"))
        self.assertIn("@article{other", (self.project / "refs.bib").read_text(encoding="utf-8"))

    def test_repacking_an_unchanged_project_keeps_unrelated_files(self) -> None:
        destination = pack_presentation(self.deck, self.root / "packed")
        (destination / "notes.txt").write_text("my own notes\n", encoding="utf-8")

        pack_presentation(self.deck, self.root / "packed")

        self.assertEqual((destination / "notes.txt").read_text(encoding="utf-8"), "my own notes\n")
        self.assertTrue((destination / "figures/diagram.svg").is_file())

    def test_pack_refuses_to_replace_differing_files(self) -> None:
        destination = pack_presentation(self.deck, self.root / "packed")
        edited = "---\ntitle: Edited in place\n---\n\n## Slide {.layout-1}\n\n::: core\nText\n:::\n"
        (destination / "lecture.md").write_text(edited, encoding="utf-8")

        with self.assertRaises(FileExistsError) as error:
            pack_presentation(self.deck, self.root / "packed")

        self.assertIn("lecture.md", str(error.exception))
        self.assertIn("--force", str(error.exception))
        self.assertEqual((destination / "lecture.md").read_text(encoding="utf-8"), edited)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["packed", "project"])

    def test_force_replaces_differing_files(self) -> None:
        destination = pack_presentation(self.deck, self.root / "packed")
        (destination / "lecture.md").write_text("stale\n", encoding="utf-8")

        pack_presentation(self.deck, self.root / "packed", force=True)

        self.assertEqual(
            (destination / "lecture.md").read_text(encoding="utf-8"),
            self.deck.read_text(encoding="utf-8"),
        )

    def test_an_entry_of_a_different_kind_is_a_conflict(self) -> None:
        destination = self.root / "packed"
        (destination / "figures").mkdir(parents=True)
        (destination / "figures" / "diagram.svg").mkdir()

        with self.assertRaises(FileExistsError) as error:
            pack_presentation(self.deck, destination)

        self.assertIn("figures/diagram.svg", str(error.exception))
        self.assertTrue((destination / "figures" / "diagram.svg").is_dir())

    def test_destination_file_and_project_directory_are_rejected(self) -> None:
        occupied = self.root / "packed"
        occupied.write_text("not a directory\n", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            pack_presentation(self.deck, occupied)
        self.assertEqual(occupied.read_text(encoding="utf-8"), "not a directory\n")

        with self.assertRaises(ValueError):
            pack_presentation(self.deck, self.project)

    def test_a_failed_pack_leaves_no_temporary_directory(self) -> None:
        self.deck.write_text(
            "---\ntitle: Pack test\n---\n\n"
            "## Slide {.layout-1}\n\n::: core\n![](figures/missing.svg)\n:::\n",
            encoding="utf-8",
        )

        with self.assertRaises(FileNotFoundError):
            pack_presentation(self.deck, self.root / "packed")

        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["project"])

    def test_command_line_packs_a_project(self) -> None:
        code = main(["pack", str(self.deck), "--output", str(self.root / "packed")])

        self.assertEqual(code, 0)
        self.assertTrue((self.root / "packed" / "lecture.md").is_file())

    def test_command_line_reports_a_conflict_without_a_traceback(self) -> None:
        self.assertEqual(main(["pack", str(self.deck), "--output", str(self.root / "packed")]), 0)
        (self.root / "packed" / "lecture.md").write_text("edited\n", encoding="utf-8")

        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = main(["pack", str(self.deck), "--output", str(self.root / "packed")])

        self.assertEqual(code, 1)
        self.assertIn("lecture.md", errors.getvalue())
        self.assertIn("--force", errors.getvalue())
        self.assertEqual(
            (self.root / "packed" / "lecture.md").read_text(encoding="utf-8"), "edited\n"
        )

        self.assertEqual(
            main(["pack", str(self.deck), "--output", str(self.root / "packed"), "--force"]), 0
        )
        self.assertEqual(
            (self.root / "packed" / "lecture.md").read_text(encoding="utf-8"),
            self.deck.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
