from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scientific_slides import main
from scientific_slides.printer import (
    SLIDE_HEIGHT_INCHES,
    SLIDE_WIDTH_INCHES,
    _chromium_command,
    _firefox_command,
    browser_kind,
    find_browser,
    firefox_preferences,
    print_presentation,
    print_url,
    run_browser,
)

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

WRITE_PDF = (
    "import sys\n"
    "open(sys.argv[1], 'wb').write(sys.argv[2].encode('latin-1'))\n"
)


def _fake_browser(script: str, *arguments: str) -> list[str]:
    return [sys.executable, "-c", script, *arguments]


class BrowserDiscoveryTests(unittest.TestCase):
    def test_chromium_is_preferred_and_firefox_is_the_fallback(self) -> None:
        with mock.patch("scientific_slides.printer.find_executable", side_effect=["/usr/bin/chromium"]):
            self.assertEqual(find_browser(), ("chromium", "/usr/bin/chromium"))
        with mock.patch("scientific_slides.printer.find_executable", side_effect=[None, "/usr/bin/firefox"]):
            self.assertEqual(find_browser(), ("firefox", "/usr/bin/firefox"))

    def test_missing_browser_names_the_ones_that_would_work(self) -> None:
        with mock.patch("scientific_slides.printer.find_executable", return_value=None):
            with self.assertRaises(RuntimeError) as error:
                find_browser()
        self.assertIn("Chrome, Chromium, Edge, or Firefox", str(error.exception))

    def test_named_browser_is_used_and_classified_by_its_program_name(self) -> None:
        with mock.patch("scientific_slides.printer.find_executable", return_value="/opt/firefox-esr/firefox-esr"):
            self.assertEqual(find_browser("firefox-esr"), ("firefox", "/opt/firefox-esr/firefox-esr"))
        with mock.patch("scientific_slides.printer.find_executable", return_value=None):
            with self.assertRaises(FileNotFoundError):
                find_browser("no-such-browser")

    def test_edge_and_brave_print_the_way_chromium_does(self) -> None:
        self.assertEqual(browser_kind("/usr/bin/msedge"), "chromium")
        self.assertEqual(browser_kind(r"C:\Program Files\BraveSoftware\brave.exe"), "chromium")
        self.assertEqual(browser_kind(r"C:\Program Files\Mozilla Firefox\firefox.exe"), "firefox")


class BrowserCommandTests(unittest.TestCase):
    def test_chromium_prints_the_reveal_print_view_without_page_furniture(self) -> None:
        command = _chromium_command("/usr/bin/chromium", Path("/tmp/out.pdf"), "http://127.0.0.1:9/?print-pdf", Path("/tmp/p"))
        self.assertIn("--headless=new", command)
        self.assertIn("--print-to-pdf=/tmp/out.pdf", command)
        self.assertIn("--no-pdf-header-footer", command)
        self.assertIn("--user-data-dir=/tmp/p", command)
        self.assertEqual(command[-1], "http://127.0.0.1:9/?print-pdf")

    def test_firefox_runs_headless_in_its_own_instance_and_profile(self) -> None:
        command = _firefox_command("/usr/bin/firefox", "http://127.0.0.1:9/?print-pdf&print-dialog", Path("/tmp/p"))
        self.assertIn("--headless", command)
        self.assertIn("--no-remote", command)
        self.assertIn("--profile", command)
        self.assertIn("/tmp/p", command)

    def test_only_firefox_needs_the_page_to_open_the_print_dialog(self) -> None:
        self.assertEqual(print_url("http://127.0.0.1:9", "chromium"), "http://127.0.0.1:9/?print-pdf")
        self.assertEqual(print_url("http://127.0.0.1:9", "firefox"), "http://127.0.0.1:9/?print-pdf&print-dialog")


class FirefoxPreferenceTests(unittest.TestCase):
    def test_paper_is_one_slide_rather_than_the_configured_stationery(self) -> None:
        preferences = firefox_preferences(Path("/tmp/slides.pdf"))
        self.assertIn('user_pref("print.printer_Mozilla_Save_to_PDF.print_paper_width", "13.33333");', preferences)
        self.assertIn('user_pref("print.printer_Mozilla_Save_to_PDF.print_paper_height", "7.50000");', preferences)
        self.assertIn('user_pref("print.printer_Mozilla_Save_to_PDF.print_paper_size_unit", 0);', preferences)
        self.assertIn('user_pref("print.printer_Mozilla_Save_to_PDF.print_shrink_to_fit", false);', preferences)
        self.assertAlmostEqual(SLIDE_WIDTH_INCHES / SLIDE_HEIGHT_INCHES, 16 / 9)

    def test_printing_is_silent_edge_to_edge_and_unstamped(self) -> None:
        preferences = firefox_preferences(Path("/tmp/slides.pdf"))
        self.assertIn('user_pref("print.always_print_silent", true);', preferences)
        self.assertIn('user_pref("print_printer", "Mozilla Save to PDF");', preferences)
        self.assertIn('user_pref("print.printer_Mozilla_Save_to_PDF.print_to_filename", "/tmp/slides.pdf");', preferences)
        self.assertIn('user_pref("print.printer_Mozilla_Save_to_PDF.print_bgcolor", true);', preferences)
        for margin in ("top", "bottom", "left", "right"):
            self.assertIn(f'user_pref("print.printer_Mozilla_Save_to_PDF.print_margin_{margin}", "0");', preferences)
        for edge in ("left", "center", "right"):
            self.assertIn(f'user_pref("print.printer_Mozilla_Save_to_PDF.print_header{edge}", "");', preferences)
            self.assertIn(f'user_pref("print.printer_Mozilla_Save_to_PDF.print_footer{edge}", "");', preferences)

    def test_windows_paths_stay_readable_as_javascript_strings(self) -> None:
        preferences = firefox_preferences(Path(r"C:\Users\ada\talk.pdf"))
        self.assertIn(r'"C:\\Users\\ada\\talk.pdf"', preferences)


class BrowserRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)
        self.output = self.root / "out.pdf"
        self.log = self.root / "browser.log"

    def test_a_browser_that_writes_a_complete_pdf_finishes(self) -> None:
        run_browser(_fake_browser(WRITE_PDF, str(self.output), PDF_BYTES.decode("latin-1")), self.output, self.log, 30.0)
        self.assertEqual(self.output.read_bytes(), PDF_BYTES)

    def test_a_browser_that_stops_without_a_pdf_reports_what_it_said(self) -> None:
        script = "import sys; print('cannot open display'); sys.exit(1)"
        with self.assertRaises(RuntimeError) as error:
            run_browser(_fake_browser(script), self.output, self.log, 30.0)
        self.assertIn("without writing the PDF", str(error.exception))
        self.assertIn("cannot open display", str(error.exception))

    def test_a_browser_that_never_finishes_is_timed_out_and_stopped(self) -> None:
        script = "import time; time.sleep(60)"
        with self.assertRaises(RuntimeError) as error:
            run_browser(_fake_browser(script), self.output, self.log, 1.0)
        self.assertIn("Timed out", str(error.exception))

    def test_a_half_written_pdf_is_not_mistaken_for_a_finished_one(self) -> None:
        script = (
            "import sys, time\n"
            "path = sys.argv[1]\n"
            "open(path, 'wb').write(b'%PDF-1.7\\n')\n"
            "time.sleep(60)\n"
        )
        with self.assertRaises(RuntimeError) as error:
            run_browser(_fake_browser(script, str(self.output)), self.output, self.log, 1.5)
        self.assertIn("Timed out", str(error.exception))


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
        self.commands: list[list[str]] = []
        browser = mock.patch("scientific_slides.printer.find_browser", return_value=("chromium", "/usr/bin/chromium"))
        browser.start()
        self.addCleanup(browser.stop)
        printer = mock.patch("scientific_slides.printer.run_browser", side_effect=self._render)
        printer.start()
        self.addCleanup(printer.stop)

    def _render(self, command: list[str], output: Path, log: Path, timeout: float) -> None:
        self.commands.append(command)
        output.write_bytes(PDF_BYTES)

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
        url = self.commands[0][-1]
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        self.assertTrue(url.endswith("/?print-pdf"))

    def test_nothing_is_left_beside_the_pdf_when_the_browser_fails(self) -> None:
        with mock.patch("scientific_slides.printer.run_browser", side_effect=RuntimeError("browser exploded")):
            with self.assertRaises(RuntimeError):
                print_presentation(self.deck)
        self.assertEqual(sorted(item.name for item in self.project.iterdir()), ["lecture.md"])

    def test_a_replaced_pdf_is_never_seen_half_written(self) -> None:
        destination = self.project / "lecture.pdf"
        destination.write_bytes(b"%PDF-1.7\nold\n%%EOF\n")

        def check(command: list[str], output: Path, log: Path, timeout: float) -> None:
            self.assertNotEqual(output, destination)
            self.assertEqual(destination.read_bytes(), b"%PDF-1.7\nold\n%%EOF\n")
            output.write_bytes(PDF_BYTES)

        with mock.patch("scientific_slides.printer.run_browser", side_effect=check):
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
