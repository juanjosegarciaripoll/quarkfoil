from __future__ import annotations

import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
from unittest import mock

from scientific_slides import main
from scientific_slides.exporter import _asset_references, _preview_command, export_presentation


class ExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        figures = self.project / "figures"
        figures.mkdir(parents=True)
        (figures / "diagram.svg").write_text(
            "<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8"
        )
        self.deck = self.project / "lecture.md"
        self.deck.write_text(
            "---\ntitle: Export test\n---\n\n"
            "## Diagram {.layout-1}\n\n"
            "::: core\n![](figures/diagram.svg){fit=contain}\n:::\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_video_and_poster_assets_are_exported(self) -> None:
        source = '::: overlay {type="video" src="media/demo.webm" poster="posters/demo.jpg"}\n:::\n'
        self.assertEqual(_asset_references(source), {"media/demo.webm", "posters/demo.jpg"})
        media = self.project / "media"
        posters = self.project / "posters"
        media.mkdir()
        posters.mkdir()
        (media / "demo.webm").write_bytes(b"webm-video")
        (posters / "demo.jpg").write_bytes(b"jpeg-poster")
        self.deck.write_text("## Video {.layout-free}\n\n" + source, encoding="utf-8")
        output = export_presentation(self.deck, self.root / "video-site")
        self.assertEqual((output / "media/demo.webm").read_bytes(), b"webm-video")
        self.assertEqual((output / "posters/demo.jpg").read_bytes(), b"jpeg-poster")

    def test_asset_references_decode_paths_and_ignore_nonlocal_urls(self) -> None:
        source = (
            "![encoded](figures/a%20b.svg?raw=1#view)\n"
            "[remote](https://example.test/file.pdf) [root](/private.pdf) [fragment](#slide)\n"
        )
        self.assertEqual(_asset_references(source), {"figures/a b.svg"})

    def test_local_export_is_complete(self) -> None:
        output = export_presentation(self.deck, self.root / "local-site")
        index = (output / "index.html").read_text(encoding="utf-8")
        self.assertIn("quarkfoil/vendor/reveal/reveal.js", index)
        self.assertNotIn("cdn.jsdelivr.net", index)
        self.assertEqual((output / "presentation.md").read_text(encoding="utf-8"), self.deck.read_text(encoding="utf-8"))
        self.assertTrue((output / "figures/diagram.svg").is_file())
        self.assertTrue((output / "quarkfoil/player.js").is_file())
        self.assertTrue((output / "quarkfoil/print.js").is_file())
        self.assertTrue((output / "quarkfoil/shapes.js").is_file())
        self.assertTrue((output / "quarkfoil/layout.css").is_file())
        self.assertTrue((output / "quarkfoil/themes.css").is_file())
        self.assertTrue((output / "quarkfoil/quarkfoil-mark.svg").is_file())
        self.assertIn('rel="icon" href="quarkfoil/quarkfoil-mark.svg"', index)
        self.assertIn('id="print-button"', index)
        self.assertTrue((output / "quarkfoil/vendor/katex/fonts/KaTeX_Main-Regular.woff2").is_file())
        self.assertIn("Reveal.js", (output / "THIRD_PARTY_LICENSES.txt").read_text(encoding="utf-8"))
        player = (output / "quarkfoil/player.js").read_text(encoding="utf-8")
        self.assertIn('document.body.dataset.playerSource === "local"', player)
        self.assertNotIn('data-player-source="local"', index)

    def test_export_can_remove_speaker_notes(self) -> None:
        self.deck.write_text(
            "## First {.layout-1}\n\nVisible content.\n\n"
            "::: notes\nPrivate speaker note.\n\nSecond paragraph.\n:::\n\n"
            "---\n\n## Second {.layout-1}\n\nStill visible.\n\n"
            "::: notes {audience=private}\nAnother private note.\n:::\n",
            encoding="utf-8",
        )
        output = export_presentation(self.deck, self.root / "no-notes-site", include_notes=False)
        exported = (output / "presentation.md").read_text(encoding="utf-8")
        self.assertIn("Visible content.", exported)
        self.assertIn("Still visible.", exported)
        self.assertNotIn("::: notes", exported)
        self.assertNotIn("Private speaker note", exported)
        self.assertNotIn("Another private note", exported)

    def test_cli_no_notes_removes_speaker_notes(self) -> None:
        self.deck.write_text(
            "## Slide {.layout-1}\n\nContent.\n\n::: notes\nDo not publish.\n:::\n",
            encoding="utf-8",
        )
        output = self.root / "cli-no-notes-site"
        result = main(["export", str(self.deck), "--output", str(output), "--no-notes"])
        self.assertEqual(result, 0)
        self.assertNotIn("Do not publish", (output / "presentation.md").read_text(encoding="utf-8"))

    def test_deck_metadata_is_written_into_exported_html(self) -> None:
        self.deck.write_text(
            "---\ntitle: Quantum & light\nauthor:\n  - Ada Lovelace\n  - Emmy Noether\n"
            "subtitle: A <shared> deck\n---\n\n## Slide\n",
            encoding="utf-8",
        )
        output = export_presentation(self.deck, self.root / "metadata-site")
        index = (output / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>Quantum &amp; light</title>", index)
        self.assertIn('name="author" content="Ada Lovelace, Emmy Noether"', index)
        self.assertIn('property="og:description" content="A &lt;shared&gt; deck"', index)
        self.assertNotIn('property="og:image"', index)

    def test_preview_uses_deck_name_and_configured_figures_folder(self) -> None:
        self.deck.write_text(
            "---\ntitle: Preview\nassets:\n  figures: artwork\n---\n\n## Slide\n",
            encoding="utf-8",
        )

        def create_preview(root: Path, relative: str) -> None:
            self.assertEqual(relative, "artwork/lecture-preview.png")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"png")

        with mock.patch("scientific_slides.exporter._create_preview", side_effect=create_preview):
            output = export_presentation(self.deck, self.root / "preview-site", preview=True)
        index = (output / "index.html").read_text(encoding="utf-8")
        self.assertTrue((output / "artwork/lecture-preview.png").is_file())
        self.assertIn('property="og:image" content="artwork/lecture-preview.png"', index)
        self.assertIn('name="twitter:image" content="artwork/lecture-preview.png"', index)

    def test_preview_browser_command_captures_a_1280_by_720_viewport(self) -> None:
        output = self.root / "preview.png"
        url = "http://127.0.0.1:8000/?preview"
        chromium = _preview_command("/usr/bin/chromium", output, url)
        self.assertIn("--window-size=1280,720", chromium)
        self.assertIn(f"--screenshot={output}", chromium)
        self.assertNotIn("--print-to-pdf", " ".join(chromium))

    def test_imported_icon_license_is_folded_into_export_notice(self) -> None:
        icon = self.project / "figures/icons/tabler--car.svg"
        icon.parent.mkdir()
        icon.write_text("<svg/>", encoding="utf-8")
        metadata = {
            "version": 1,
            "icons": {
                "figures/icons/tabler--car.svg": {
                    "prefix": "tabler", "name": "car", "collection": "Tabler Icons", "author": "Paweł Kuna",
                    "source": "https://github.com/tabler/tabler-icons", "license": "MIT",
                    "license_url": "https://github.com/tabler/tabler-icons/blob/main/LICENSE",
                },
                "figures/icons/tabler--unused.svg": {
                    "prefix": "tabler", "name": "unused", "collection": "Tabler Icons", "author": "Paweł Kuna",
                    "source": "https://github.com/tabler/tabler-icons", "license": "MIT",
                    "license_url": "https://github.com/tabler/tabler-icons/blob/main/LICENSE",
                },
            },
        }
        (icon.parent / ".quarkfoil-icons.json").write_text(__import__("json").dumps(metadata), encoding="utf-8")
        self.deck.write_text("## Icon\n\n![](figures/icons/tabler--car.svg)\n", encoding="utf-8")
        output = export_presentation(self.deck, self.root / "icon-site")
        notice = (output / "THIRD_PARTY_LICENSES.txt").read_text(encoding="utf-8")
        self.assertIn("Imported icon collection: Tabler Icons", notice)
        self.assertIn("figures/icons/tabler--car.svg", notice)
        self.assertIn("Copyright (c) 2020-2026 Paweł Kuna", notice)
        self.assertNotIn("unused", notice)
        self.assertFalse((output / "figures/icons/tabler--unused.svg").exists())
        self.assertFalse((output / "figures/icons/.quarkfoil-icons.json").exists())

    def test_cdn_export_uses_pinned_integrity_checked_urls(self) -> None:
        output = export_presentation(self.deck, self.root / "cdn-site", assets="cdn")
        index = (output / "index.html").read_text(encoding="utf-8")
        self.assertIn("https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/dist/reveal.js", index)
        self.assertIn("https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css", index)
        self.assertIn('integrity="sha384-', index)
        self.assertIn('crossorigin="anonymous"', index)
        self.assertFalse((output / "quarkfoil/vendor").exists())
        self.assertTrue((output / "THIRD_PARTY_LICENSES.txt").is_file())

    def test_existing_destination_is_never_overwritten(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            export_presentation(self.deck, output)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_missing_referenced_figure_leaves_no_export(self) -> None:
        self.deck.write_text("## Missing\n\n![](figures/missing.svg)\n", encoding="utf-8")
        output = self.root / "missing-figure-site"
        with self.assertRaises(FileNotFoundError):
            export_presentation(self.deck, output)
        self.assertFalse(output.exists())

    def test_configured_asset_folders_are_exported(self) -> None:
        artwork = self.project / "artwork"
        resources = self.project / "resources"
        artwork.mkdir()
        resources.mkdir()
        nested = artwork / "nested"
        nested.mkdir()
        (nested / "used.svg").write_text("<svg id='used'/>", encoding="utf-8")
        (artwork / "unused.svg").write_text("<svg id='unused'/>", encoding="utf-8")
        (resources / "notes.pdf").write_bytes(b"%PDF-test")
        (resources / "unreferenced.csv").write_text("data", encoding="utf-8")
        self.deck.write_text(
            "---\ntitle: Assets\nassets:\n  figures: artwork\n  include:\n    - resources\n---\n\n"
            "## Files {.layout-1}\n\n![](artwork/nested/used.svg)\n\n[Notes](resources/notes.pdf)\n",
            encoding="utf-8",
        )
        output = export_presentation(self.deck, self.root / "asset-site")
        self.assertTrue((output / "artwork/nested/used.svg").is_file())
        self.assertFalse((output / "artwork/unused.svg").exists())
        self.assertTrue((output / "resources/notes.pdf").is_file())
        self.assertTrue((output / "resources/unreferenced.csv").is_file())

    def test_no_notes_omits_assets_referenced_only_by_speaker_notes(self) -> None:
        private = self.project / "private.pdf"
        private.write_bytes(b"private")
        self.deck.write_text(
            "## Slide {.layout-1}\n\nVisible.\n\n::: notes\n[Private](private.pdf)\n:::\n",
            encoding="utf-8",
        )
        output = export_presentation(self.deck, self.root / "note-assets-site", include_notes=False)
        self.assertFalse((output / "private.pdf").exists())

    def test_configured_figures_must_be_a_directory(self) -> None:
        (self.project / "artwork").write_text("not a directory", encoding="utf-8")
        self.deck.write_text("---\nassets:\n  figures: artwork\n---\n\n## Slide\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            export_presentation(self.deck, self.root / "invalid-figures-site")
        self.assertFalse((self.root / "invalid-figures-site").exists())

    def test_bibliography_is_exported(self) -> None:
        bibliography = self.project / "references.bib"
        bibliography.write_text("@article{test, title={Test}}\n", encoding="utf-8")
        self.deck.write_text("---\nbibliography: references.bib\n---\n\n## Cited\n\n[@test]\n", encoding="utf-8")
        output = export_presentation(self.deck, self.root / "bibliography-site")
        self.assertEqual((output / "references.bib").read_text(encoding="utf-8"), bibliography.read_text(encoding="utf-8"))
        self.assertTrue((output / "quarkfoil/bibliography.js").is_file())
        self.assertTrue((output / "quarkfoil/vendor/bibtex/bibtexParse.js").is_file())

    def test_configured_asset_folder_cannot_leave_project(self) -> None:
        self.deck.write_text(
            "---\nassets:\n  include:\n    - ../outside\n---\n\n## Unsafe\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            export_presentation(self.deck, self.root / "unsafe-folder-site")
        self.assertFalse((self.root / "unsafe-folder-site").exists())

    def test_asset_cannot_leave_project(self) -> None:
        outside = self.root / "outside.svg"
        outside.write_text("<svg/>", encoding="utf-8")
        self.deck.write_text("## Escape\n\n![](../outside.svg)\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            export_presentation(self.deck, self.root / "unsafe-site")
        self.assertFalse((self.root / "unsafe-site").exists())

    def test_cli_export_alias(self) -> None:
        output = self.root / "cli-site"
        result = main(["export", str(self.deck), "--output", str(output), "--cdn"])
        self.assertEqual(result, 0)
        self.assertTrue((output / "index.html").is_file())

    def test_cli_export_does_not_load_server_or_reload_monitor(self) -> None:
        output = self.root / "isolated-cli-site"
        script = (
            "import sys; from scientific_slides import main; "
            f"result=main(['export',{str(self.deck)!r},'--output',{str(output)!r}]); "
            "assert result == 0; assert 'scientific_slides.server' not in sys.modules"
        )
        subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
        self.assertTrue((output / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
