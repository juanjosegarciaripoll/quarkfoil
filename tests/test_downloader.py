from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scientific_slides import main
from scientific_slides.downloader import (
    DownloadError,
    _safe_folder_name,
    download_published,
    download_talk,
    verify_project_archive,
    write_project_archive,
)
from scientific_slides.exporter import serve_directory
from scientific_slides.publisher import publish_presentation


SOURCE = """---
title: Download test
date: 2026-11-08
bibliography: references.bib
assets:
  include:
    - data
social:
  image: figures/card.png
  alt: Download test card
---

## Figure {.layout-1}

::: core
![](figures/diagram.svg){fit=contain}
:::

::: overlay {#handout type="markdown" x="5" y="80" w="30" h="8"}
[Handout](handout.txt)
:::

::: notes
Recoverable only when published deliberately.
:::
"""


class PublishedTalkCase(unittest.TestCase):
    """A talk published into a local collection and served on a loopback port."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        (self.project / "figures").mkdir(parents=True)
        (self.project / "data").mkdir()
        (self.project / "figures" / "diagram.svg").write_text("<svg>diagram</svg>", encoding="utf-8")
        (self.project / "figures" / "card.png").write_bytes(b"social card")
        (self.project / "data" / "values.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        (self.project / "handout.txt").write_text("reader copy\n", encoding="utf-8")
        (self.project / "references.bib").write_text("@article{test, title={Test}}\n", encoding="utf-8")
        self.deck = self.project / "source-talk.md"
        self.deck.write_text(SOURCE, encoding="utf-8")
        self.site = self.root / "site"
        publish_presentation(
            self.deck, str(self.site), name="published-talk", include_notes=True, index=False,
            site_url="https://example.test/talks/",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @contextlib.contextmanager
    def url(self):
        with serve_directory(self.site) as origin:
            yield f"{origin}/published-talk/"


class DownloadPublishedTests(PublishedTalkCase):
    def test_download_reconstructs_an_editable_project(self) -> None:
        with self.url() as url:
            destination, deck = download_published(url, self.root / "recovered")

        self.assertEqual(deck, destination / "source-talk.md")
        self.assertEqual(deck.read_text(encoding="utf-8"), SOURCE)
        self.assertEqual((destination / "figures/diagram.svg").read_text(encoding="utf-8"), "<svg>diagram</svg>")
        self.assertEqual((destination / "figures/card.png").read_bytes(), b"social card")
        self.assertEqual((destination / "data/values.csv").read_text(encoding="utf-8"), "x,y\n1,2\n")
        self.assertEqual((destination / "references.bib").read_text(encoding="utf-8"),
                         "@article{test, title={Test}}\n")
        self.assertEqual((destination / "handout.txt").read_text(encoding="utf-8"), "reader copy\n")
        self.assertFalse((destination / "index.html").exists())
        self.assertFalse((destination / "meta.json").exists())
        self.assertFalse((destination / "assets").exists())

    def test_an_older_publication_defaults_to_the_talk_slug(self) -> None:
        meta_path = self.site / "published-talk" / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.pop("source")
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        with self.url() as url:
            _, deck = download_published(url, self.root / "recovered")

        self.assertEqual(deck.name, "published-talk.md")

    def test_name_override_and_existing_destination_conflicts(self) -> None:
        with self.url() as url:
            destination, deck = download_published(
                url, self.root / "recovered", name="new-presentation"
            )
            self.assertEqual(deck.name, "new-presentation.md")
            deck.write_text("local edit\n", encoding="utf-8")
            with self.assertRaises(FileExistsError) as error:
                download_published(url, destination, name="new-presentation")
            self.assertIn("--force", str(error.exception))
            self.assertEqual(deck.read_text(encoding="utf-8"), "local edit\n")
            download_published(url, destination, name="new-presentation", force=True)

        self.assertEqual(deck.read_text(encoding="utf-8"), SOURCE)

    def test_unsafe_published_paths_are_rejected_without_output(self) -> None:
        index_path = self.site / "published-talk" / "index.html"
        index = index_path.read_text(encoding="utf-8")
        marker = 'id="quarkfoil-assets">'
        before, remainder = index.split(marker, 1)
        payload, after = remainder.split("</script>", 1)
        mapping = json.loads(payload)
        mapped = next(iter(mapping.values()))
        index_path.write_text(
            before + marker + json.dumps({"../outside.svg": mapped}) + "</script>" + after,
            encoding="utf-8",
        )

        with self.url() as url:
            with self.assertRaises(DownloadError) as error:
                download_published(url, self.root / "recovered")

        self.assertIn("unsafe", str(error.exception))
        self.assertFalse((self.root / "recovered").exists())
        self.assertFalse(any(path.name.startswith(".recovered-") for path in self.root.iterdir()))

    def test_missing_published_asset_leaves_no_partial_project(self) -> None:
        pooled = next((self.site / "assets" / "f").rglob("*diagram.svg"))
        pooled.unlink()

        with self.url() as url:
            with self.assertRaises(DownloadError):
                download_published(url, self.root / "recovered")

        self.assertFalse((self.root / "recovered").exists())

    def test_command_line_downloads_and_reports_errors_without_a_traceback(self) -> None:
        with self.url() as url:
            output = self.root / "cli-copy"
            self.assertEqual(main(["download", url, "--output", str(output)]), 0)
            self.assertTrue((output / "source-talk.md").is_file())

        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = main(["download", "not-a-url", "--output", str(self.root / "bad")])
        self.assertEqual(code, 1)
        self.assertIn("quarkfoil download:", errors.getvalue())



PDF_BYTES = b"%PDF-1.7\n%%EOF\n"


class DownloadBackupTests(PublishedTalkCase):
    """ZIP archives and PDFs of a published talk, alone or beside the project."""

    def setUp(self) -> None:
        super().setUp()
        self.printed: list[tuple[Path, Path]] = []
        browsers = mock.patch("scientific_slides.printer.browser_candidates", return_value=[("chromium", "chromium")])
        browsers.start()
        self.addCleanup(browsers.stop)
        printer = mock.patch("scientific_slides.printer.print_presentation", side_effect=self._print)
        printer.start()
        self.addCleanup(printer.stop)

    def _print(self, deck: Path, output: Path, **options: object) -> tuple[Path, str]:
        # Printed from the recovered deck, with its assets beside it.
        self.assertTrue((deck.parent / "figures" / "diagram.svg").is_file())
        self.printed.append((deck, output))
        output.write_bytes(PDF_BYTES)
        return output, "/usr/bin/chromium"

    def leftovers(self) -> list[str]:
        return sorted(path.name for path in self.root.iterdir() if path.name.startswith("."))

    def test_a_zip_holds_the_editable_project_in_one_folder(self) -> None:
        archive = self.root / "backups" / "talk.zip"
        with self.url() as url:
            result = download_talk(url, archive=archive)
        self.assertIsNone(result.project)
        self.assertEqual(result.archive, archive)
        with zipfile.ZipFile(archive) as opened:
            names = opened.namelist()
            self.assertEqual(names, sorted(names))
            self.assertTrue(all(name.startswith("published-talk/") for name in names))
            # The deck's own bytes: the fixture's write_text gives CRLF on Windows.
            self.assertEqual(opened.read("published-talk/source-talk.md"), self.deck.read_bytes())
            self.assertEqual(opened.read("published-talk/figures/diagram.svg"), b"<svg>diagram</svg>")
            self.assertIn("published-talk/references.bib", names)
            self.assertNotIn("published-talk/index.html", names)
            self.assertNotIn("published-talk/meta.json", names)
            self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in opened.infolist()))
        self.assertEqual(self.printed, [])
        self.assertEqual(self.leftovers(), [])

    def test_an_unchanged_talk_gives_the_same_archive_and_a_changed_one_needs_force(self) -> None:
        archive = self.root / "talk.zip"
        with self.url() as url:
            download_talk(url, archive=archive)
            first = archive.read_bytes()
            again = download_talk(url, archive=archive)
            self.assertTrue(again.archive_unchanged)
            self.assertEqual(archive.read_bytes(), first)

            archive.write_bytes(b"an older backup")
            with self.assertRaises(FileExistsError) as error:
                download_talk(url, archive=archive)
            self.assertIn("--force", str(error.exception))
            self.assertEqual(archive.read_bytes(), b"an older backup")
            download_talk(url, archive=archive, force=True)
        self.assertEqual(archive.read_bytes(), first)
        self.assertEqual(self.leftovers(), [])

    def test_a_pdf_is_printed_from_the_recovered_project(self) -> None:
        pdf = self.root / "talk.pdf"
        with self.url() as url:
            result = download_talk(url, pdf=pdf, browser="firefox")
        self.assertEqual(pdf.read_bytes(), PDF_BYTES)
        self.assertEqual(result.browser, "/usr/bin/chromium")
        deck, output = self.printed[0]
        self.assertEqual(deck.name, "source-talk.md")
        self.assertNotEqual(output, pdf, "the browser writes beside the PDF, not over it")
        self.assertEqual(self.leftovers(), [])

    def test_an_existing_pdf_needs_force_and_is_checked_before_downloading(self) -> None:
        pdf = self.root / "talk.pdf"
        pdf.write_bytes(b"older backup")
        with self.url() as url:
            with self.assertRaises(FileExistsError):
                download_talk(url, pdf=pdf)
            self.assertEqual(self.printed, [])
            self.assertEqual(pdf.read_bytes(), b"older backup")
            download_talk(url, pdf=pdf, force=True)
        self.assertEqual(pdf.read_bytes(), PDF_BYTES)

    def test_a_failed_print_writes_no_project_archive_or_pdf(self) -> None:
        output, archive, pdf = self.root / "recovered", self.root / "talk.zip", self.root / "talk.pdf"
        with mock.patch("scientific_slides.printer.print_presentation", side_effect=RuntimeError("browser crashed")):
            with self.url() as url:
                with self.assertRaises(RuntimeError):
                    download_talk(url, output=output, archive=archive, pdf=pdf)
        self.assertFalse(output.exists())
        self.assertFalse(archive.exists())
        self.assertFalse(pdf.exists())
        self.assertEqual(self.leftovers(), [])

    def test_without_a_browser_nothing_is_downloaded(self) -> None:
        output = self.root / "recovered"
        with mock.patch("scientific_slides.printer.browser_candidates", side_effect=RuntimeError("needs a browser")), \
             mock.patch("scientific_slides.downloader._recover") as recover:
            with self.assertRaises(RuntimeError):
                download_talk("https://example.test/talks/t/", output=output, pdf=self.root / "talk.pdf")
        recover.assert_not_called()
        self.assertFalse(output.exists())

    def test_all_three_outputs_together(self) -> None:
        output, archive, pdf = self.root / "recovered", self.root / "talk.zip", self.root / "talk.pdf"
        with self.url() as url:
            result = download_talk(url, output=output, archive=archive, pdf=pdf)
        self.assertEqual(result.deck, output / "source-talk.md")
        self.assertEqual(result.deck.read_text(encoding="utf-8"), SOURCE)
        with zipfile.ZipFile(archive) as opened:
            files = {name.split("/", 1)[1] for name in opened.namelist()}
        on_disk = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
        self.assertEqual(files, on_disk)
        self.assertEqual(pdf.read_bytes(), PDF_BYTES)

    def test_requests_that_cannot_work_are_refused_before_any_network_access(self) -> None:
        url = "https://example.test/talks/t/"
        with mock.patch("scientific_slides.downloader._recover") as recover:
            with self.assertRaises(DownloadError):
                download_talk(url)
            with self.assertRaises(DownloadError):
                download_talk(url, archive=self.root / "talk.tar")
            with self.assertRaises(DownloadError):
                download_talk(url, pdf=self.root / "talk.png")
            folder = self.root / "folder.zip"
            folder.mkdir()
            with self.assertRaises(IsADirectoryError):
                download_talk(url, archive=folder)
        recover.assert_not_called()

    def test_compressed_media_is_stored_and_text_is_deflated(self) -> None:
        archive = self.root / "talk.zip"
        with self.url() as url:
            download_talk(url, archive=archive)
        with zipfile.ZipFile(archive) as opened:
            methods = {info.filename.split("/", 1)[1]: info.compress_type for info in opened.infolist()}
        self.assertEqual(methods["figures/card.png"], zipfile.ZIP_STORED)
        self.assertEqual(methods["figures/diagram.svg"], zipfile.ZIP_DEFLATED)
        self.assertEqual(methods["source-talk.md"], zipfile.ZIP_DEFLATED)

    def test_verification_rejects_a_damaged_or_incomplete_archive(self) -> None:
        project = self.root / "verify"
        (project / "figures").mkdir(parents=True)
        (project / "talk.md").write_text("## Slide\n" * 200, encoding="utf-8")
        (project / "figures" / "photo.jpg").write_bytes(bytes(range(256)) * 64)
        archive = self.root / "verify.zip"
        write_project_archive(project, "talk", archive)
        verify_project_archive(archive, project, "talk")

        data = bytearray(archive.read_bytes())
        offset = data.index(bytes(range(256)))  # inside the stored photo
        data[offset:offset + 8] = b"\xff" * 8
        damaged = self.root / "damaged.zip"
        damaged.write_bytes(bytes(data))
        with self.assertRaises(DownloadError) as error:
            verify_project_archive(damaged, project, "talk")
        self.assertIn("talk/figures/photo.jpg", str(error.exception))

        (project / "extra.txt").write_text("added after archiving\n", encoding="utf-8")
        with self.assertRaises(DownloadError) as error:
            verify_project_archive(archive, project, "talk")
        self.assertIn("missing talk/extra.txt", str(error.exception))

    def test_a_failed_verification_writes_nothing(self) -> None:
        output, archive = self.root / "recovered", self.root / "talk.zip"
        with mock.patch("scientific_slides.downloader.verify_project_archive", side_effect=DownloadError("verification failed")):
            with self.url() as url:
                with self.assertRaises(DownloadError):
                    download_talk(url, output=output, archive=archive)
        self.assertFalse(output.exists())
        self.assertFalse(archive.exists())
        self.assertEqual(self.leftovers(), [])

    def test_sha256_files_check_with_sha256sum_and_follow_the_conflict_rules(self) -> None:
        archive, pdf = self.root / "talk.zip", self.root / "talk.pdf"
        with self.url() as url:
            result = download_talk(url, archive=archive, pdf=pdf, checksums=True)
            for backup in (archive, pdf):
                line = (backup.parent / f"{backup.name}.sha256").read_text(encoding="utf-8")
                self.assertEqual(line, f"{hashlib.sha256(backup.read_bytes()).hexdigest()}  {backup.name}\n")
            self.assertEqual(result.checksums, [self.root / "talk.zip.sha256", self.root / "talk.pdf.sha256"])

            # An unchanged archive keeps a matching checksum without --force...
            download_talk(url, archive=archive, checksums=True)
            # ...but a checksum that disagrees is a conflict, never silently replaced.
            (self.root / "talk.zip.sha256").write_text("0" * 64 + "  talk.zip\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                download_talk(url, archive=archive, checksums=True)
            download_talk(url, archive=archive, checksums=True, force=True)
            self.assertIn(hashlib.sha256(archive.read_bytes()).hexdigest(),
                          (self.root / "talk.zip.sha256").read_text(encoding="utf-8"))
            with self.assertRaises(DownloadError):
                download_talk(url, output=self.root / "project-only", checksums=True)
        self.assertEqual(self.leftovers(), [])

    def test_archive_folder_names_are_single_portable_components(self) -> None:
        self.assertEqual(_safe_folder_name("quantum-simulation"), "quantum-simulation")
        self.assertEqual(_safe_folder_name('a:b/c\\d*e?'), "a-b-c-d-e-")
        self.assertEqual(_safe_folder_name(".."), "")

    def test_command_line_writes_backups_and_needs_one_output(self) -> None:
        archive, pdf = self.root / "talk.zip", self.root / "talk.pdf"
        output = io.StringIO()
        with self.url() as url, contextlib.redirect_stdout(output):
            self.assertEqual(main(["download", url, "--zip", str(archive), "--pdf", str(pdf)]), 0)
        self.assertIn(f"ZIP archive of the editable project written: {archive}", output.getvalue())
        self.assertIn(f"Printed the talk to {pdf}", output.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as exit_:
                main(["download", "https://example.test/talks/t/"])
        self.assertEqual(exit_.exception.code, 2)
        self.assertIn("--output, --zip, or --pdf", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
