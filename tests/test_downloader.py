from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scientific_slides import main
from scientific_slides.downloader import DownloadError, download_published
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


class DownloadPublishedTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
