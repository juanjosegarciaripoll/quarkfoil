from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scientific_slides import main
from scientific_slides.publisher import (
    PublishError,
    Target,
    index_page,
    publish_index,
    publish_presentation,
)

DECK = """---
title: {title}
description: {description}
event: {event}
date: {date}
---

## Diagram {{.layout-1}}

::: core
![](figures/diagram.svg){{fit=contain}}
:::
"""


class PublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.site = self.root / "talks"
        self.project = self.root / "project"
        (self.project / "figures").mkdir(parents=True)
        (self.project / "figures" / "diagram.svg").write_text("<svg/>", encoding="utf-8")
        self.deck = self.project / "lecture.md"
        self.deck.write_text(
            DECK.format(title="Superconducting circuits", description="A biased introduction.",
                        event="INC School", date="2026-09-07"),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def published(self, name: str = "lecture") -> Path:
        return self.site / name

    def test_layout_shares_the_runtime_and_pools_the_assets(self) -> None:
        meta = publish_presentation(self.deck, str(self.site))

        folder = self.published()
        self.assertEqual(sorted(path.name for path in folder.iterdir()),
                         ["index.html", "meta.json", "presentation.md"])
        runtime = self.site / "assets" / "quarkfoil" / str(meta["runtime"])
        self.assertTrue((runtime / "player.js").is_file())
        self.assertTrue((runtime / "vendor" / "katex" / "katex.min.js").is_file())
        self.assertTrue((runtime / "THIRD_PARTY_LICENSES.txt").is_file())
        pooled = sorted((self.site / "assets" / "f").rglob("*.svg"))
        self.assertEqual(len(pooled), 1)
        self.assertEqual(pooled[0].read_text(encoding="utf-8"), "<svg/>")

    def test_the_page_maps_deck_paths_onto_the_pool(self) -> None:
        publish_presentation(self.deck, str(self.site))

        page = (self.published() / "index.html").read_text(encoding="utf-8")
        block = re.search(r'id="quarkfoil-assets">(.*?)</script>', page, re.S).group(1)
        mapping = json.loads(block)
        self.assertRegex(mapping["figures/diagram.svg"], r"^\.\./assets/f/[0-9a-f]{2}/[0-9a-f]{16}-diagram\.svg$")
        self.assertIn('<script src="../assets/quarkfoil/', page)
        self.assertIn('href="../assets/quarkfoil/', page)
        # the deck's own Markdown is published untouched
        self.assertIn("![](figures/diagram.svg)", (self.published() / "presentation.md").read_text(encoding="utf-8"))

    def test_identical_assets_are_stored_once_and_collisions_are_not(self) -> None:
        second = self.root / "other"
        (second / "figures").mkdir(parents=True)
        (second / "figures" / "diagram.svg").write_text("<svg/>", encoding="utf-8")  # same bytes
        (second / "figures" / "shared.png").write_text("first", encoding="utf-8")
        deck = second / "talk.md"
        deck.write_text(
            DECK.format(title="Second", description="", event="", date="2025-03-01"), encoding="utf-8",
        )
        publish_presentation(self.deck, str(self.site))
        publish_presentation(deck, str(self.site))

        self.assertEqual(len(sorted((self.site / "assets" / "f").rglob("*.svg"))), 1)

        # same name, different bytes: two pool entries, both reachable
        (second / "figures" / "diagram.svg").write_text("<svg data-v='2'/>", encoding="utf-8")
        publish_presentation(deck, str(self.site), name="talk-v2")
        self.assertEqual(len(sorted((self.site / "assets" / "f").rglob("*.svg"))), 2)
        for folder in ("talk", "talk-v2"):
            page = (self.site / folder / "index.html").read_text(encoding="utf-8")
            pooled = json.loads(re.search(r'id="quarkfoil-assets">(.*?)</script>', page, re.S).group(1))
            target = self.site / pooled["figures/diagram.svg"].replace("../", "")
            self.assertTrue(target.is_file())

    def test_a_talk_must_carry_a_date(self) -> None:
        self.deck.write_text("---\ntitle: No date\n---\n\n## Slide {.layout-1}\n\n::: core\nx\n:::\n", encoding="utf-8")
        with self.assertRaises(PublishError) as error:
            publish_presentation(self.deck, str(self.site))
        self.assertIn("date", str(error.exception))

        self.deck.write_text("---\ntitle: Bad\ndate: last tuesday\n---\n\n## S {.layout-1}\n\n::: core\nx\n:::\n", encoding="utf-8")
        with self.assertRaises(PublishError):
            publish_presentation(self.deck, str(self.site))

    def test_index_is_static_html_grouped_by_year_newest_first(self) -> None:
        publish_presentation(self.deck, str(self.site))
        older = self.root / "older.md"
        older.write_text(
            DECK.format(title="Cold atoms", description="Older talk.", event="CERN", date="2024-06-12"),
            encoding="utf-8",
        )
        (self.project / "older.md").write_text(older.read_text(encoding="utf-8"), encoding="utf-8")
        publish_presentation(self.project / "older.md", str(self.site))

        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertLess(page.index("2026"), page.index("2024"))
        self.assertLess(page.index("Superconducting circuits"), page.index("Cold atoms"))
        self.assertIn("A biased introduction.", page)
        self.assertIn("INC School · 7 September", page)
        self.assertIn('href="lecture/"', page)
        self.assertNotIn("<script", page)

    def test_unlisted_talks_are_published_but_not_listed(self) -> None:
        self.deck.write_text(
            self.deck.read_text(encoding="utf-8").replace("date: 2026-09-07", "date: 2026-09-07\nunlisted: true"),
            encoding="utf-8",
        )
        publish_presentation(self.deck, str(self.site))

        self.assertTrue((self.published() / "index.html").is_file())
        self.assertNotIn("Superconducting circuits", (self.site / "index.html").read_text(encoding="utf-8"))

    def test_republishing_replaces_the_deck_but_keeps_the_pool(self) -> None:
        publish_presentation(self.deck, str(self.site))
        (self.published() / "stale.txt").write_text("old", encoding="utf-8")
        pooled = sorted((self.site / "assets" / "f").rglob("*.svg"))[0]
        pooled_bytes = pooled.read_bytes()

        publish_presentation(self.deck, str(self.site))

        self.assertFalse((self.published() / "stale.txt").exists())
        self.assertEqual(pooled.read_bytes(), pooled_bytes)

    def test_dry_run_changes_nothing(self) -> None:
        publish_presentation(self.deck, str(self.site), dry_run=True)
        self.assertFalse(self.site.exists())

    def test_index_only_rebuilds_the_listing(self) -> None:
        publish_presentation(self.deck, str(self.site), index=False)
        self.assertFalse((self.site / "index.html").exists())

        self.assertEqual(publish_index(str(self.site), title="Talks"), 1)
        self.assertIn("Superconducting circuits", (self.site / "index.html").read_text(encoding="utf-8"))

    def test_an_inline_image_keeps_a_private_copy(self) -> None:
        self.deck.write_text(
            "---\ntitle: Inline\ndate: 2026-01-02\n---\n\n"
            "## Slide {.layout-1}\n\n::: core\nText with ![d](figures/diagram.svg) inside.\n:::\n",
            encoding="utf-8",
        )
        publish_presentation(self.deck, str(self.site))

        self.assertTrue((self.published() / "figures" / "diagram.svg").is_file())
        page = (self.published() / "index.html").read_text(encoding="utf-8")
        mapping = json.loads(re.search(r'id="quarkfoil-assets">(.*?)</script>', page, re.S).group(1))
        self.assertNotIn("figures/diagram.svg", mapping)


class TargetTests(unittest.TestCase):
    def test_local_and_remote_targets_are_told_apart(self) -> None:
        for value in ("/srv/talks", "./talks", "talks", "C:/decks", r"C:\decks"):
            self.assertFalse(Target.parse(value).remote, value)
        for value in ("homepage:talks/", "user@host:/var/www/talks", "rsync://host/module/talks", "host::module/talks"):
            self.assertTrue(Target.parse(value).remote, value)


class RemotePublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "figures").mkdir()
        (self.root / "figures" / "diagram.svg").write_text("<svg/>", encoding="utf-8")
        self.deck = self.root / "lecture.md"
        self.deck.write_text(
            DECK.format(title="Remote", description="d", event="e", date="2026-02-03"), encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_the_pool_is_pushed_append_only_and_the_deck_mirrored(self) -> None:
        calls = []

        def fake_run(command, capture_output=False, text=False):
            calls.append(command)
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch("scientific_slides.publisher.shutil.which", return_value="/usr/bin/rsync"), \
             mock.patch("scientific_slides.publisher.subprocess.run", side_effect=fake_run):
            publish_presentation(self.deck, "homepage:talks/", index=False)

        self.assertEqual(len(calls), 2)
        assets, deck = calls
        self.assertIn("--ignore-existing", assets)
        self.assertNotIn("--delete", assets)
        self.assertTrue(assets[-1].endswith("homepage:talks/assets/"))
        self.assertIn("--delete", deck)
        self.assertIn("--delay-updates", deck)
        self.assertTrue(deck[-1].endswith("homepage:talks/lecture/"))
        self.assertIn("-rltL", deck)

    def test_a_missing_rsync_is_reported_clearly(self) -> None:
        with mock.patch("scientific_slides.publisher.shutil.which", return_value=None):
            with self.assertRaises(PublishError) as error:
                publish_presentation(self.deck, "homepage:talks/", index=False)
        self.assertIn("rsync", str(error.exception))


class PublishCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "figures").mkdir()
        (self.root / "figures" / "diagram.svg").write_text("<svg/>", encoding="utf-8")
        self.deck = self.root / "lecture.md"
        self.deck.write_text(
            DECK.format(title="CLI", description="d", event="e", date="2026-04-05"), encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_command_line_publishes_and_lists(self) -> None:
        site = self.root / "talks"
        self.assertEqual(main(["publish", str(self.deck), "--site", str(site)]), 0)
        self.assertTrue((site / "lecture" / "index.html").is_file())
        self.assertIn("CLI", (site / "index.html").read_text(encoding="utf-8"))

    def test_missing_date_exits_with_a_message(self) -> None:
        self.deck.write_text("---\ntitle: x\n---\n\n## S {.layout-1}\n\n::: core\ny\n:::\n", encoding="utf-8")
        self.assertEqual(main(["publish", str(self.deck), "--site", str(self.root / "talks")]), 1)


if __name__ == "__main__":
    unittest.main()


class CollectionSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "figures").mkdir()
        (self.root / "figures" / "diagram.svg").write_text("<svg/>", encoding="utf-8")
        self.deck = self.root / "lecture.md"
        self.deck.write_text(
            DECK.format(title="First", description="d", event="e", date="2026-05-06"), encoding="utf-8",
        )
        self.site = self.root / "talks"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_the_heading_survives_later_publishes(self) -> None:
        publish_presentation(self.deck, str(self.site), index_title="Seminars", index_lede="Selected talks.")
        second = self.root / "second.md"
        second.write_text(
            DECK.format(title="Second", description="d", event="e", date="2026-07-08"), encoding="utf-8",
        )

        publish_presentation(second, str(self.site))

        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("<h1>Seminars</h1>", page)
        self.assertIn("Selected talks.", page)
        self.assertEqual(
            json.loads((self.site / "collection.json").read_text(encoding="utf-8"))["title"], "Seminars"
        )
