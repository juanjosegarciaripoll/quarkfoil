from __future__ import annotations

import math
import json
from pathlib import Path
import unittest

from scientific_slides.parser import parse_attributes, parse_deck


ROOT = Path(__file__).resolve().parents[1]


class ParserTests(unittest.TestCase):
    def assert_fixture_subset(self, actual: object, expected: object) -> None:
        if isinstance(expected, dict):
            self.assertIsInstance(actual, dict)
            for key, value in expected.items():
                self.assertIn(key, actual)
                self.assert_fixture_subset(actual[key], value)
        elif isinstance(expected, list):
            self.assertIsInstance(actual, list)
            self.assertEqual(len(actual), len(expected))
            for actual_item, expected_item in zip(actual, expected, strict=True):
                self.assert_fixture_subset(actual_item, expected_item)
        elif isinstance(expected, float):
            self.assertAlmostEqual(actual, expected)
        else:
            self.assertEqual(actual, expected)

    def test_shared_parser_corpus(self) -> None:
        fixtures = json.loads((ROOT / "app/parser-fixtures.json").read_text(encoding="utf-8"))
        for fixture in fixtures:
            with self.subTest(fixture=fixture["name"]):
                deck = parse_deck(fixture["source"])
                actual = {
                    "metadata": deck.metadata,
                    "slides": [
                        {
                            "title": slide.title,
                            "layout": slide.layout,
                            "cells": [cell.id for cell in slide.cells],
                            "overlays": [overlay.id for overlay in slide.overlays],
                            "trashed": slide.trashed,
                            "titleSource": slide.title_source,
                            "columns": list(slide.columns),
                            "rows": list(slide.rows),
                            "notes": slide.notes,
                            "footer": slide.footer[0] if slide.footer else None,
                            "section": None if slide.section is None else {"title": slide.section.title, "id": slide.section.id},
                        }
                        for slide in deck.slides
                    ],
                    "sections": [
                        {
                            "title": section.title,
                            "id": section.id,
                            "slideCount": section.slide_count,
                            "isTrash": section.is_trash,
                        }
                        for section in deck.sections
                    ],
                    "diagnostics": [item.message for item in deck.diagnostics],
                    "diagnosticCodes": [item.code for item in deck.diagnostics],
                }
                self.assert_fixture_subset(actual, fixture["expected"])
                messages = actual["diagnostics"]
                for prefix in fixture.get("diagnosticPrefixes", []):
                    self.assertTrue(any(message.startswith(prefix) for message in messages), prefix)

    def test_attributes_match_presentation_syntax(self) -> None:
        attrs = parse_attributes("#plot .wide enabled caption='Phase space' color=\"#123456\"")
        self.assertEqual(attrs.id, "plot")
        self.assertEqual(attrs.classes, ["wide"])
        self.assertEqual(
            attrs.values,
            {"enabled": "true", "caption": "Phase space", "color": "#123456"},
        )

    def test_parses_example_deck(self) -> None:
        source = (ROOT / "example/deck.md").read_text(encoding="utf-8")
        deck = parse_deck(source)
        self.assertGreater(len(deck.slides), 1)
        self.assertEqual(deck.source, source)
        self.assertEqual(deck.front_matter_range.start, 0)
        self.assertEqual(source[deck.slides[0].range.start:deck.slides[0].range.end], deck.slides[0].raw)
        self.assertFalse([item for item in deck.diagnostics if item.level == "error"])

    def test_ranges_preserve_crlf_and_ordinary_markdown(self) -> None:
        source = "---\r\ntitle: Test\r\n---\r\n\r\n## One {.layout-1}\r\n\r\nBefore\r\n\r\n::: notes\r\nSpeak\r\n:::\r\n\r\nAfter\r\n"
        deck = parse_deck(source)
        slide = deck.slides[0]
        self.assertEqual(slide.title, "One")
        self.assertEqual(slide.notes, "Speak")
        self.assertEqual(slide.cells[0].source, "Before\r\n\r\n\r\nAfter")
        self.assertEqual([source[item.start:item.end] for item in slide.cells[0].source_ranges], ["Before", "After"])

    def test_parses_sections_images_video_and_overlay_geometry(self) -> None:
        source = """# Part {#part .section}

---

## Media {.layout-1-1 columns=1:2}

::: left
![Plot](figures/plot.svg "Plot")
:::

::: right {type=video src=movie.mp4 autoplay=true}
:::

::: overlay {#arrow type=arrow x1=5 y1=10 x2=80 y2=90 heads=both}
:::
"""
        deck = parse_deck(source)
        self.assertEqual(deck.sections[0].slide_count, 1)
        slide = deck.slides[0]
        self.assertEqual(slide.columns, (100 / 3, 200 / 3))
        self.assertEqual(slide.cells[0].image.source, "figures/plot.svg")
        self.assertEqual(slide.cells[1].video.source, "movie.mp4")
        self.assertTrue(slide.cells[1].video.autoplay)
        self.assertEqual(slide.overlays[0].arrow["heads"], "both")
        self.assertTrue(all(math.isfinite(value) for value in slide.overlays[0].geometry.values()))

    def test_reports_structural_diagnostics(self) -> None:
        source = """## Broken {.layout-unknown background=red}

::: overlay {#same font-size=nope}
:::

::: overlay {#same}
:::

::: mystery
"""
        messages = [item.message for item in parse_deck(source).diagnostics]
        self.assertIn("Unknown layout 'unknown', using 1", messages)
        self.assertIn("Duplicate overlay ID 'same'", messages)
        self.assertIn("Overlay 'same' has invalid font size", messages)
        self.assertIn("Unclosed ::: mystery block", messages)
        self.assertIn("Invalid background color 'red', using the theme color", messages)

    def test_front_matter_must_be_a_mapping(self) -> None:
        deck = parse_deck("---\n- item\n---\n\n## Slide\n")
        self.assertEqual(deck.metadata, {})
        self.assertTrue(any(item.message == "YAML: Front matter must be a mapping" for item in deck.diagnostics))


if __name__ == "__main__":
    unittest.main()
