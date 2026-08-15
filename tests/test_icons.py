from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scientific_slides.icons import fetch_icon_svg, import_icon, search_icons


class IconTests(unittest.TestCase):
    def test_search_filters_results_to_allowlisted_collections(self) -> None:
        payload = json.dumps({"icons": ["tabler:car", "material-symbols:person", "unknown:car", "tabler:Bad Name"]}).encode()
        with patch("scientific_slides.icons._read_url", return_value=payload) as read:
            icons = search_icons("car")
        self.assertEqual([item["id"] for item in icons], ["tabler:car", "material-symbols:person"])
        self.assertIn("prefixes=material-symbols%2Ctabler%2Cicon-park-outline", read.call_args.args[0])

    def test_unsafe_svg_is_rejected(self) -> None:
        with patch("scientific_slides.icons._read_url", return_value=b"<svg><script>alert(1)</script></svg>"):
            with self.assertRaisesRegex(ValueError, "unsafe SVG"):
                fetch_icon_svg("tabler", "car")

    def test_import_writes_local_svg_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("scientific_slides.icons.fetch_icon_svg", return_value=b"<svg xmlns='http://www.w3.org/2000/svg'/>"):
                relative = import_icon(root, root / "artwork", "tabler", "car")
            self.assertEqual(relative, "artwork/icons/tabler--car.svg")
            self.assertTrue((root / relative).is_file())
            metadata = json.loads((root / "artwork/icons/.quarkfoil-icons.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["icons"][relative]["license"], "MIT")

    def test_import_reuses_an_existing_icon_without_downloading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            icon = root / "figures/icons/tabler--car.svg"
            icon.parent.mkdir(parents=True)
            icon.write_text("<svg id='existing'/>", encoding="utf-8")
            with patch("scientific_slides.icons.fetch_icon_svg") as fetch:
                relative = import_icon(root, root / "figures", "tabler", "car")
            self.assertEqual(relative, "figures/icons/tabler--car.svg")
            fetch.assert_not_called()
            self.assertEqual(icon.read_text(encoding="utf-8"), "<svg id='existing'/>")
