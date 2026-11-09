from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scientific_slides import main
from scientific_slides.browser import BrowserError
from scientific_slides.printer import (
    PRINT_READY,
    SLIDE_HEIGHT_INCHES,
    SLIDE_WIDTH_INCHES,
    browser_candidates,
    print_presentation,
    print_url,
    render_pdf,
)

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class PageSizeTests(unittest.TestCase):
    def test_a_page_is_one_slide_of_the_player_canvas(self) -> None:
        self.assertAlmostEqual(SLIDE_WIDTH_INCHES, 1280 / 96)
        self.assertAlmostEqual(SLIDE_HEIGHT_INCHES, 720 / 96)

    def test_the_browser_opens_the_reveal_print_view(self) -> None:
        self.assertEqual(print_url("http://127.0.0.1:9"), "http://127.0.0.1:9/?print-pdf")

    def test_a_missing_browser_names_printing_and_the_browsers_that_would_work(self) -> None:
        with mock.patch("scientific_slides.browser.find_executable", return_value=None):
            with self.assertRaises(RuntimeError) as error:
                browser_candidates()
        self.assertIn("Printing a PDF needs Chrome, Chromium, Edge, or Firefox", str(error.exception))


class FakePage:
    def __init__(self, pdf: bytes = PDF_BYTES) -> None:
        self.pdf = pdf
        self.calls: list[tuple] = []

    def navigate(self, url: str) -> None:
        self.calls.append(("navigate", url))

    def evaluate(self, expression: str) -> object:
        self.calls.append(("evaluate", expression))
        return True

    def print_pdf(self, width: float, height: float, timeout: float) -> bytes:
        self.calls.append(("print", width, height))
        return self.pdf


candidates_used = [("firefox", "/usr/bin/firefox")]


class RenderPdfTests(unittest.TestCase):
    def _open(self, page: FakePage):
        opened: list[dict] = []

        class Opener:
            def __init__(self, candidates, **options):
                opened.append({"candidates": candidates, **options})

            def __enter__(self):
                return page, candidates_used[0][1]

            def __exit__(self, *exc):
                return False

        return Opener, opened

    def test_the_pdf_is_printed_only_after_the_player_reports_the_layout_ready(self) -> None:
        page = FakePage()
        opener, opened = self._open(page)
        with mock.patch("scientific_slides.printer.open_first_page", opener):
            data, program = render_pdf(candidates_used, "http://127.0.0.1:9/?print-pdf", 30.0)
        self.assertEqual(data, PDF_BYTES)
        self.assertEqual(program, "/usr/bin/firefox")
        self.assertEqual(opened[0]["candidates"], candidates_used)
        self.assertEqual(opened[0]["width"], 1280)
        self.assertEqual(opened[0]["height"], 720)
        kinds = [call[0] for call in page.calls]
        self.assertEqual(kinds, ["navigate", "evaluate", "print"])
        self.assertEqual(page.calls[1][1], PRINT_READY)
        self.assertEqual(page.calls[2][1:], (SLIDE_WIDTH_INCHES, SLIDE_HEIGHT_INCHES))

    def test_the_readiness_check_reports_player_errors(self) -> None:
        self.assertIn("player-error", PRINT_READY)
        self.assertIn("printReady", PRINT_READY)

    def test_anything_but_a_pdf_is_an_error(self) -> None:
        opener, _ = self._open(FakePage(pdf=b"<html>"))
        with mock.patch("scientific_slides.printer.open_first_page", opener):
            with self.assertRaises(BrowserError):
                render_pdf(candidates_used, "http://127.0.0.1:9/?print-pdf", 30.0)


class PrintPresentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)
        self.project = self.root / "project"
        self.project.mkdir()
        self.deck = self.project / "lecture.md"
        self.deck.write_text(
            "---\ntitle: Printable\n---\n\n## Slide {.layout-1}\n\n::: core\nText\n:::\n",
            encoding="utf-8",
        )
        self.urls: list[str] = []
        browser = mock.patch("scientific_slides.printer.browser_candidates", return_value=[("chromium", "/usr/bin/chromium")])
        browser.start()
        self.addCleanup(browser.stop)
        printer = mock.patch("scientific_slides.printer.render_pdf", side_effect=self._render)
        printer.start()
        self.addCleanup(printer.stop)

    def _render(self, candidates: list, url: str, timeout: float) -> tuple[bytes, str]:
        self.urls.append(url)
        return PDF_BYTES, candidates[0][1]

    def test_the_pdf_lands_beside_the_deck_unless_another_name_is_given(self) -> None:
        destination, browser = print_presentation(self.deck)
        self.assertEqual(destination, self.project / "lecture.pdf")
        self.assertEqual(browser, "/usr/bin/chromium")
        self.assertEqual(destination.read_bytes(), PDF_BYTES)

        elsewhere = self.root / "handout.pdf"
        destination, _ = print_presentation(self.deck, elsewhere)
        self.assertEqual(destination, elsewhere)
        self.assertTrue(elsewhere.is_file())

    def test_the_browser_reads_the_presentation_over_http_in_the_print_view(self) -> None:
        print_presentation(self.deck)
        self.assertTrue(self.urls[0].startswith("http://127.0.0.1:"))
        self.assertTrue(self.urls[0].endswith("/?print-pdf"))

    def test_nothing_is_left_beside_the_pdf_when_the_browser_fails(self) -> None:
        with mock.patch("scientific_slides.printer.render_pdf", side_effect=BrowserError("browser exploded")):
            with self.assertRaises(RuntimeError):
                print_presentation(self.deck)
        self.assertEqual(sorted(item.name for item in self.project.iterdir()), ["lecture.md"])

    def test_a_failed_run_leaves_an_existing_pdf_untouched(self) -> None:
        destination = self.project / "lecture.pdf"
        destination.write_bytes(b"%PDF-1.7\nold\n%%EOF\n")
        with mock.patch("scientific_slides.printer.render_pdf", side_effect=BrowserError("timed out")):
            with self.assertRaises(RuntimeError):
                print_presentation(self.deck)
        self.assertEqual(destination.read_bytes(), b"%PDF-1.7\nold\n%%EOF\n")
        print_presentation(self.deck)
        self.assertEqual(destination.read_bytes(), PDF_BYTES)

    def test_only_a_markdown_presentation_that_exists_can_be_printed(self) -> None:
        with self.assertRaises(FileNotFoundError):
            print_presentation(self.project / "missing.md")
        other = self.project / "lecture.txt"
        other.write_text("text", encoding="utf-8")
        with self.assertRaises(ValueError):
            print_presentation(other)

    def test_a_directory_is_rejected_as_the_pdf_destination(self) -> None:
        with self.assertRaises(IsADirectoryError):
            print_presentation(self.deck, self.project)
        with self.assertRaises(FileNotFoundError):
            print_presentation(self.deck, self.root / "absent" / "talk.pdf")

    def test_speaker_notes_stay_out_of_the_printed_pages(self) -> None:
        self.deck.write_text(
            "---\ntitle: Printable\n---\n\n## Slide {.layout-1}\n\n"
            "::: core\nShown\n:::\n\n::: notes\nSecret aside\n:::\n",
            encoding="utf-8",
        )
        sources: list[str] = []

        def record(deck: Path, destination: Path, **options: object) -> Path:
            result = real_export(deck, destination, **options)
            sources.append((result / "presentation.md").read_text(encoding="utf-8"))
            return result

        from scientific_slides.exporter import export_presentation as real_export

        with mock.patch("scientific_slides.printer.export_presentation", side_effect=record):
            print_presentation(self.deck)
        self.assertIn("Shown", sources[0])
        self.assertNotIn("Secret aside", sources[0])


class PrintCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)
        self.deck = self.root / "lecture.md"
        self.deck.write_text("---\ntitle: Printable\n---\n\n## Slide\n", encoding="utf-8")

    def test_the_command_reports_the_file_and_the_page_size(self) -> None:
        output = self.root / "lecture.pdf"
        with mock.patch(
            "scientific_slides.printer.print_presentation", return_value=(output, "/usr/bin/firefox")
        ) as printer:
            with mock.patch("sys.stdout") as stdout:
                self.assertEqual(main(["print", str(self.deck), "-o", str(output), "--browser", "firefox"]), 0)
        printer.assert_called_once()
        self.assertEqual(printer.call_args.kwargs["browser"], "firefox")
        reported = " ".join(str(call.args[0]) for call in stdout.write.call_args_list)
        self.assertIn(str(output), reported)
        self.assertIn("13.33 x 7.50 in", reported)
        self.assertIn("/usr/bin/firefox", reported)

    def test_a_missing_browser_is_reported_without_a_traceback(self) -> None:
        with mock.patch(
            "scientific_slides.printer.print_presentation", side_effect=RuntimeError("Printing a PDF needs a browser")
        ):
            with mock.patch("sys.stderr") as stderr:
                self.assertEqual(main(["print", str(self.deck)]), 1)
        reported = " ".join(str(call.args[0]) for call in stderr.write.call_args_list)
        self.assertIn("quarkfoil print: Printing a PDF needs a browser", reported)


if __name__ == "__main__":
    unittest.main()
