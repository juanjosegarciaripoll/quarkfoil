from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scientific_slides import main
from scientific_slides.publisher import (
    PublishError,
    publish_presentations,
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
        self.root = Path(self.temporary.name).resolve()
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

    def test_site_url_is_remembered_and_the_first_slide_is_the_default_card(self) -> None:
        calls = []

        def preview(root: Path, relative: str, page: str, size: tuple[int, int]) -> None:
            calls.append(page)
            self.assertEqual(size, (1200, 630))
            output = root / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"generated png")

        with mock.patch("scientific_slides.publisher._create_preview", side_effect=preview):
            meta = publish_presentation(
                self.deck, str(self.site), site_url="https://example.test/talks"
            )

        self.assertEqual(calls, ["/lecture/?preview&preview-slide=slide-1"])
        self.assertEqual(meta["url"], "https://example.test/talks/lecture/")
        self.assertRegex(str(meta["social_image"]), r"^https://example\.test/talks/assets/f/")
        settings = json.loads((self.site / "collection.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["url"], "https://example.test/talks/")
        page = (self.published() / "index.html").read_text(encoding="utf-8")
        self.assertIn('rel="canonical" href="https://example.test/talks/lecture/"', page)
        self.assertIn('property="og:image:width" content="1200"', page)
        self.assertIn('property="og:image:height" content="630"', page)
        self.assertIn('name="twitter:card" content="summary_large_image"', page)
        self.assertIn('property="og:image:alt" content="Superconducting circuits"', page)

    def test_a_social_figure_is_pooled_without_rendering_a_slide(self) -> None:
        (self.project / "figures" / "card.png").write_bytes(b"chosen card")
        self.deck.write_text(
            self.deck.read_text(encoding="utf-8").replace(
                "date: 2026-09-07", "date: 2026-09-07\nsocial:\n  image: figures/card.png\n  alt: Diagram of a circuit"
            ),
            encoding="utf-8",
        )

        with mock.patch("scientific_slides.publisher._create_preview") as preview:
            meta = publish_presentation(
                self.deck, str(self.site), site_url="https://example.test/talks/"
            )

        preview.assert_not_called()
        image = str(meta["social_image"])
        self.assertRegex(image, r"/assets/f/[0-9a-f]{2}/[0-9a-f]{16}-card\.png$")
        pooled = list((self.site / "assets" / "f").rglob("*card.png"))
        self.assertEqual([path.read_bytes() for path in pooled], [b"chosen card"])
        page = (self.published() / "index.html").read_text(encoding="utf-8")
        self.assertIn('property="og:image:type" content="image/png"', page)
        self.assertIn('name="twitter:image:alt" content="Diagram of a circuit"', page)

    def test_a_social_slide_uses_its_stable_id(self) -> None:
        self.deck.write_text(
            self.deck.read_text(encoding="utf-8")
            .replace("date: 2026-09-07", "date: 2026-09-07\nsocial:\n  slide: result")
            .replace("## Diagram {.layout-1}", "## Diagram {#result .layout-1}"),
            encoding="utf-8",
        )

        def preview(root: Path, relative: str, page: str, size: tuple[int, int]) -> None:
            self.assertEqual(page, "/lecture/?preview&preview-slide=result")
            self.assertEqual(size, (1200, 630))
            output = root / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"result slide")

        with mock.patch("scientific_slides.publisher._create_preview", side_effect=preview):
            publish_presentation(self.deck, str(self.site), site_url="https://example.test/talks/")

    def test_the_front_page_layout_is_preferred_for_the_default_card(self) -> None:
        self.deck.write_text(
            self.deck.read_text(encoding="utf-8")
            + "\n---\n\n## Opening {#opening .layout-front}\n\n::: core\nFront page.\n:::\n",
            encoding="utf-8",
        )

        def preview(root: Path, relative: str, page: str, size: tuple[int, int]) -> None:
            self.assertEqual(page, "/lecture/?preview&preview-slide=opening")
            output = root / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"front page")

        with mock.patch("scientific_slides.publisher._create_preview", side_effect=preview):
            publish_presentation(self.deck, str(self.site), site_url="https://example.test/talks/")

    def test_an_explicit_social_card_requires_a_public_collection_url(self) -> None:
        self.deck.write_text(
            self.deck.read_text(encoding="utf-8").replace(
                "date: 2026-09-07", "date: 2026-09-07\nsocial:\n  slide: slide-1"
            ),
            encoding="utf-8",
        )
        with self.assertRaises(PublishError) as error:
            publish_presentation(self.deck, str(self.site))
        self.assertIn("--site-url", str(error.exception))


class TargetTests(unittest.TestCase):
    def test_local_and_remote_targets_are_told_apart(self) -> None:
        for value in ("/srv/talks", "./talks", "talks", "C:/decks", r"C:\decks"):
            self.assertFalse(Target.parse(value).remote, value)
        for value in ("homepage:talks/", "user@host:/var/www/talks", "rsync://host/module/talks", "host::module/talks"):
            self.assertTrue(Target.parse(value).remote, value)


class RemotePublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
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

        self.assertEqual(len(calls), 5)
        settings_read, root, assets, deck, settings_write = calls
        self.assertIn("--ignore-missing-args", settings_read)
        self.assertTrue(root[-1].endswith("homepage:talks/"))
        self.assertNotIn("--delete", root)
        self.assertIn("--ignore-existing", assets)
        self.assertNotIn("--delete", assets)
        self.assertTrue(assets[-1].endswith("homepage:talks/assets/"))
        self.assertIn("--delete", deck)
        self.assertIn("--delay-updates", deck)
        self.assertTrue(deck[-1].endswith("homepage:talks/lecture/"))
        self.assertIn("-rltpL", deck)
        # a web server has to be able to read what was published
        for command in calls[1:]:
            self.assertIn("--chmod=D755,F644", command)
        self.assertTrue(settings_write[-1].endswith("homepage:talks/collection.json"))

    def test_a_missing_rsync_is_reported_clearly(self) -> None:
        with mock.patch("scientific_slides.publisher.shutil.which", return_value=None):
            with self.assertRaises(PublishError) as error:
                publish_presentation(self.deck, "homepage:talks/", index=False)
        self.assertIn("rsync", str(error.exception))


class PublishCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
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

    def test_index_only_can_initialize_the_public_url(self) -> None:
        site = self.root / "talks"
        self.assertEqual(main([
            "publish", "--site", str(site), "--index-only",
            "--site-url", "https://example.test/talks",
        ]), 0)
        settings = json.loads((site / "collection.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["url"], "https://example.test/talks/")
        page = (site / "index.html").read_text(encoding="utf-8")
        self.assertIn('rel="canonical" href="https://example.test/talks/"', page)


if __name__ == "__main__":
    unittest.main()


class CollectionSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
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


class FirstPublishTests(unittest.TestCase):
    """A collection that does not exist yet reads as empty, not as a failure."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "figures").mkdir()
        (self.root / "figures" / "diagram.svg").write_text("<svg/>", encoding="utf-8")
        self.deck = self.root / "lecture.md"
        self.deck.write_text(
            DECK.format(title="First", description="d", event="e", date="2026-01-02"), encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _rsync(self, missing: bool):
        def run(command, capture_output=False, text=False):
            reading = "--list-only" in command or "--include=meta.json" in command or "--ignore-missing-args" in command
            code = 23 if reading and missing else 0
            return mock.Mock(returncode=code, stdout="", stderr="No such file or directory")
        return run

    def test_a_dry_run_against_a_new_collection_succeeds(self) -> None:
        with mock.patch("scientific_slides.publisher.shutil.which", return_value="/usr/bin/rsync"), \
             mock.patch("scientific_slides.publisher.subprocess.run", side_effect=self._rsync(missing=True)):
            meta = publish_presentation(self.deck, "homepage:talks/", dry_run=True)
        self.assertEqual(meta["slug"], "lecture")

    def test_an_unreadable_collection_never_blanks_its_listing(self) -> None:
        calls = []

        def run(command, capture_output=False, text=False):
            calls.append(command)
            reading = "--include=meta.json" in command or "--ignore-missing-args" in command
            listing = "--list-only" in command
            if reading:
                return mock.Mock(returncode=23, stdout="", stderr="connection dropped")
            if listing:  # the collection does have an index.html already
                return mock.Mock(returncode=0, stdout="index.html", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch("scientific_slides.publisher.shutil.which", return_value="/usr/bin/rsync"), \
             mock.patch("scientific_slides.publisher.subprocess.run", side_effect=run):
            self.assertEqual(publish_index("homepage:talks/"), 0)

        self.assertFalse(any(str(command[-1]).endswith("talks/index.html") and "--list-only" not in command
                             for command in calls))


class PublishedNotesTests(unittest.TestCase):
    """A published deck's Markdown is public, so its notes are opt-in."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "figures").mkdir()
        (self.root / "figures" / "diagram.svg").write_text("<svg/>", encoding="utf-8")
        self.deck = self.root / "lecture.md"
        self.deck.write_text(
            DECK.format(title="Noted", description="d", event="e", date="2026-03-04")
            + "\n::: notes\nRemember the derivation.\n:::\n",
            encoding="utf-8",
        )
        self.site = self.root / "talks"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def published(self) -> str:
        return (self.site / "lecture" / "presentation.md").read_text(encoding="utf-8")

    def test_notes_are_left_out_by_default(self) -> None:
        publish_presentation(self.deck, str(self.site))

        self.assertNotIn("Remember the derivation", self.published())
        self.assertIn("Remember the derivation", self.deck.read_text(encoding="utf-8"))

    def test_notes_are_published_when_asked_for(self) -> None:
        publish_presentation(self.deck, str(self.site), include_notes=True)

        self.assertIn("Remember the derivation", self.published())

    def test_the_command_line_keeps_them_out_unless_notes_is_given(self) -> None:
        self.assertEqual(main(["publish", str(self.deck), "--site", str(self.site)]), 0)
        self.assertNotIn("Remember the derivation", self.published())

        self.assertEqual(main(["publish", str(self.deck), "--site", str(self.site), "--notes"]), 0)
        self.assertIn("Remember the derivation", self.published())


SERIES_DECK = """---
title: {title}
description: {description}
event: {event}
date: {date}
series: {series}
part: {part}
series-description: {series_description}
---

## Slide {{.layout-1}}

::: core
![](figures/diagram.svg){{fit=contain}}
:::
"""


class SeriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "figures").mkdir()
        (self.root / "figures" / "diagram.svg").write_text("<svg/>", encoding="utf-8")
        self.site = self.root / "talks"
        self.decks = []
        for number, (day, title) in enumerate(((8, "Why quantum simulation"), (12, "Cold atoms")), start=1):
            deck = self.root / f"0{number}-lecture.md"
            deck.write_text(
                SERIES_DECK.format(
                    title=title, description=f"Lecture {number}.", event="CERN, Geneva",
                    date=f"2026-06-{day:02d}", series="Quantum Simulation Platforms", part=number,
                    series_description="Nine lectures on simulating matter.",
                ),
                encoding="utf-8",
            )
            self.decks.append(deck)
        self.single = self.root / "seminar.md"
        self.single.write_text(
            DECK.format(title="A single seminar", description="One off.", event="Madrid", date="2026-09-07"),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_several_decks_publish_together(self) -> None:
        published = publish_presentations(self.decks, str(self.site))

        self.assertEqual([meta["slug"] for meta in published], ["01-lecture", "02-lecture"])
        for slug in ("01-lecture", "02-lecture"):
            self.assertTrue((self.site / slug / "index.html").is_file())
        # the shared figure is stored once for the whole series
        self.assertEqual(len(sorted((self.site / "assets" / "f").rglob("*.svg"))), 1)

    def test_a_series_is_one_card_linking_to_its_own_page(self) -> None:
        publish_presentations(self.decks + [self.single], str(self.site))

        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="series/quantum-simulation-platforms/"', page)
        self.assertIn("Quantum Simulation Platforms", page)
        self.assertIn("2 talks · 8–12 June", page)
        self.assertIn("Nine lectures on simulating matter.", page)
        self.assertIn("A single seminar", page)
        # the members are not also listed at the top level
        self.assertNotIn('href="01-lecture/"', page)
        self.assertNotIn("<script", page)

    def test_the_series_page_lists_its_talks_in_order(self) -> None:
        publish_presentations(self.decks, str(self.site))

        page = (self.site / "series" / "quantum-simulation-platforms" / "index.html").read_text(encoding="utf-8")
        self.assertLess(page.index("Why quantum simulation"), page.index("Cold atoms"))
        self.assertIn('href="../../01-lecture/"', page)
        self.assertIn("CERN, Geneva · 8–12 June", page)
        self.assertNotIn("<script", page)

    def test_the_series_is_filed_under_its_latest_year(self) -> None:
        older = self.root / "00-older.md"
        older.write_text(
            SERIES_DECK.format(title="Older", description="d", event="CERN, Geneva", date="2025-11-30",
                               series="Quantum Simulation Platforms", part=0,
                               series_description="Nine lectures on simulating matter."),
            encoding="utf-8",
        )
        publish_presentations(self.decks + [older], str(self.site))

        page = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("<h2>2026</h2>", page)
        self.assertNotIn("<h2>2025</h2>", page)

    def test_series_pages_of_removed_series_do_not_survive(self) -> None:
        publish_presentations(self.decks, str(self.site))
        self.assertTrue((self.site / "series" / "quantum-simulation-platforms").is_dir())

        for slug in ("01-lecture", "02-lecture"):
            shutil.rmtree(self.site / slug)
        publish_index(str(self.site))

        self.assertFalse((self.site / "series" / "quantum-simulation-platforms").exists())

    def test_a_deck_may_not_be_named_series(self) -> None:
        with self.assertRaises(PublishError):
            publish_presentations([self.single], str(self.site), names=["series"])
