from __future__ import annotations

import tempfile
import unittest
import subprocess
import sys
from pathlib import Path

from scientific_slides import main
from scientific_slides.exporter import _asset_references, export_presentation


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

    def test_local_export_is_complete(self) -> None:
        output = export_presentation(self.deck, self.root / "local-site")
        index = (output / "index.html").read_text(encoding="utf-8")
        self.assertIn("quarkfoil/vendor/reveal/reveal.js", index)
        self.assertNotIn("cdn.jsdelivr.net", index)
        self.assertEqual((output / "presentation.md").read_text(encoding="utf-8"), self.deck.read_text(encoding="utf-8"))
        self.assertTrue((output / "figures/diagram.svg").is_file())
        self.assertTrue((output / "quarkfoil/player.js").is_file())
        self.assertTrue((output / "quarkfoil/shapes.js").is_file())
        self.assertTrue((output / "quarkfoil/layout.css").is_file())
        self.assertTrue((output / "quarkfoil/themes.css").is_file())
        self.assertTrue((output / "quarkfoil/quarkfoil-mark.svg").is_file())
        self.assertIn('rel="icon" href="quarkfoil/quarkfoil-mark.svg"', index)
        self.assertTrue((output / "quarkfoil/vendor/katex/fonts/KaTeX_Main-Regular.woff2").is_file())
        self.assertIn("Reveal.js", (output / "THIRD_PARTY_LICENSES.txt").read_text(encoding="utf-8"))
        player = (output / "quarkfoil/player.js").read_text(encoding="utf-8")
        self.assertNotIn("/api/", player)

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

    def test_configured_asset_folders_are_exported(self) -> None:
        artwork = self.project / "artwork"
        resources = self.project / "resources"
        artwork.mkdir()
        resources.mkdir()
        (artwork / "unused.svg").write_text("<svg/>", encoding="utf-8")
        (resources / "notes.pdf").write_bytes(b"%PDF-test")
        self.deck.write_text(
            "---\ntitle: Assets\nassets:\n  figures: artwork\n  include:\n    - resources\n---\n\n"
            "## Files {.layout-1}\n\n[Notes](resources/notes.pdf)\n",
            encoding="utf-8",
        )
        output = export_presentation(self.deck, self.root / "asset-site")
        self.assertTrue((output / "artwork/unused.svg").is_file())

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
