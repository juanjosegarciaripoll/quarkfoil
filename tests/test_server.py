from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from scientific_slides.server import create_server


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.deck = self.root / "deck.md"
        self.deck.write_text("---\ntitle: Test\n---\n\n# Slide\n", encoding="utf-8")
        self.server = create_server(self.deck, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request(self, path: str, *, method: str = "GET", body: bytes | None = None, headers=None):
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=headers or {})
        with urllib.request.urlopen(request, timeout=4) as response:
            return response.status, response.headers, response.read()

    def test_config_and_deck(self) -> None:
        status, _, payload = self.request("/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["deck"], "deck.md")
        _, headers, payload = self.request("/api/deck")
        self.assertIn("text/markdown", headers["Content-Type"])
        self.assertEqual(payload, self.deck.read_bytes())

    def test_atomic_save_and_conflict(self) -> None:
        previous = self.deck.read_bytes()
        digest = hashlib.sha256(previous).hexdigest()
        next_source = b"---\ntitle: Changed\n---\n\n# Slide\n"
        status, _, payload = self.request(
            "/api/deck",
            method="PUT",
            body=next_source,
            headers={"Content-Type": "text/markdown", "If-Match": f'"{digest}"'},
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(payload)["ok"])
        self.assertEqual(self.deck.read_bytes(), next_source)
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request(
                "/api/deck",
                method="PUT",
                body=b"stale",
                headers={"If-Match": f'"{digest}"'},
            )
        self.assertEqual(context.exception.code, 409)
        self.assertEqual(self.deck.read_bytes(), next_source)

    def test_project_boundary(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/project/../outside.txt")
        self.assertIn(context.exception.code, {403, 404})

    def test_asset_import(self) -> None:
        status, _, payload = self.request(
            "/api/asset?name=diagram.svg",
            method="POST",
            body=b"<svg xmlns='http://www.w3.org/2000/svg'/>",
            headers={"Content-Type": "image/svg+xml"},
        )
        self.assertEqual(status, 201)
        result = json.loads(payload)
        self.assertEqual(result["path"], "figures/diagram.svg")
        self.assertTrue((self.root / result["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
