from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scientific_slides.server import STARTER_DECK, _normalize_doi_bibtex, _python_snapshot, _video_conversion_plan, _video_duration, _video_progress, create_server, initialize_deck


class DeckInitializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_doi_bibtex_braces_nonstandard_month_names(self) -> None:
        source = "@article{Wallraff_2004, author={Wallraff, A. and Schuster, D. I.}, month=Sept, year={2004}}"
        self.assertEqual(_normalize_doi_bibtex(source), "@article{wallraff2004, author={Wallraff, A. and Schuster, D. I.}, month={Sept}, year={2004}}")

    def test_doi_bibtex_key_uses_lowercase_family_name_and_full_year(self) -> None:
        source = "@article{provider_key, author={Albert Einstein and Boris Podolsky}, year={1935}}"
        self.assertTrue(_normalize_doi_bibtex(source).startswith("@article{einstein1935,"))
        accented = "@article{provider_key, author={Peñas, Juan}, year={2023}}"
        self.assertTrue(_normalize_doi_bibtex(accented).startswith("@article{penas2023,"))

    def test_missing_markdown_is_created_from_starter(self) -> None:
        deck = self.root / "new-deck.md"
        self.assertEqual(initialize_deck(deck), deck.resolve())
        self.assertEqual(deck.read_text(encoding="utf-8"), STARTER_DECK)
        self.assertIn(".layout-front", deck.read_text(encoding="utf-8"))

    def test_whitespace_only_markdown_is_initialized(self) -> None:
        deck = self.root / "empty.markdown"
        deck.write_text(" \r\n\t", encoding="utf-8")
        initialize_deck(deck)
        self.assertEqual(deck.read_text(encoding="utf-8"), STARTER_DECK)

    def test_nonempty_markdown_is_preserved(self) -> None:
        deck = self.root / "existing.md"
        source = "## Keep me {.layout-1}\n"
        deck.write_text(source, encoding="utf-8")
        initialize_deck(deck)
        self.assertEqual(deck.read_text(encoding="utf-8"), source)

    def test_missing_parent_is_not_created(self) -> None:
        deck = self.root / "missing" / "deck.md"
        with self.assertRaises(FileNotFoundError):
            initialize_deck(deck)
        self.assertFalse(deck.parent.exists())

    def test_non_markdown_path_is_rejected_before_creation(self) -> None:
        deck = self.root / "deck.txt"
        with self.assertRaises(ValueError):
            initialize_deck(deck)
        self.assertFalse(deck.exists())

    def test_python_snapshot_tracks_source_changes(self) -> None:
        package = self.root / "package"
        package.mkdir()
        source = package / "server.py"
        source.write_text("first", encoding="utf-8")
        first = _python_snapshot(package)
        source.write_text("second version", encoding="utf-8")
        self.assertNotEqual(first, _python_snapshot(package))

    def test_unknown_video_duration_is_allowed(self) -> None:
        probe = SimpleNamespace(stdout='{"streams":[{"duration":"N/A"}],"format":{"duration":"N/A"}}')
        with mock.patch("scientific_slides.server.subprocess.run", return_value=probe):
            self.assertIsNone(_video_duration(self.root / "video.mkv"))

    def test_unknown_ffmpeg_progress_is_ignored(self) -> None:
        self.assertIsNone(_video_progress("N/A", 12.0))
        self.assertIsNone(_video_progress("nan", 12.0))
        self.assertEqual(_video_progress("6000000", 12.0), 50.0)

    def test_mp4_plan_reuses_compatible_streams(self) -> None:
        with (
            mock.patch("scientific_slides.server._video_codecs", return_value=("h264", "aac")),
            mock.patch("scientific_slides.server._ffmpeg_encoders", return_value=set()),
        ):
            suffix, command = _video_conversion_plan(self.root / "video.mkv")
        self.assertEqual(suffix, ".mp4")
        self.assertEqual(command.count("copy"), 2)

    def test_mp4_plan_only_encodes_incompatible_stream(self) -> None:
        with (
            mock.patch("scientific_slides.server._video_codecs", return_value=("h264", "opus")),
            mock.patch("scientific_slides.server._ffmpeg_encoders", return_value={"libx264"}),
        ):
            suffix, command = _video_conversion_plan(self.root / "video.mkv")
        self.assertEqual(suffix, ".mp4")
        self.assertEqual(command[0:2], ["-c:v", "copy"])
        self.assertIn("aac", command)


class ServerTests(unittest.TestCase):
    def test_packaged_app_is_available(self) -> None:
        from scientific_slides.server import APP_ROOT

        self.assertTrue((APP_ROOT / "index.html").is_file())

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
        self.assertFalse(self.server.verbose)
        status, _, payload = self.request("/api/config")
        self.assertEqual(status, 200)
        config = json.loads(payload)
        self.assertEqual(config["deck"], "deck.md")
        self.assertTrue(config["reload"])
        _, headers, payload = self.request("/api/deck")
        self.assertIn("text/markdown", headers["Content-Type"])
        self.assertEqual(payload, self.deck.read_bytes())
        status, _, payload = self.request("/api/reload")
        self.assertEqual(status, 200)
        self.assertRegex(json.loads(payload)["token"], r"^[0-9a-f]{64}$")

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
            self.request("/api/deck", method="PUT", body=b"stale", headers={"If-Match": f'"{digest}"'})
        self.assertEqual(context.exception.code, 409)
        self.assertEqual(self.deck.read_bytes(), next_source)

    def test_bibliography_load_save_and_conflict(self) -> None:
        status, _, payload = self.request("/api/bibliography?path=references.bib")
        result = json.loads(payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["source"], "")
        source = b"@article{test, title={Test}}\n"
        status, _, payload = self.request("/api/bibliography?path=references.bib", method="PUT", body=source, headers={"If-Match": f'"{result["hash"]}"'})
        saved = json.loads(payload)
        self.assertEqual(status, 200)
        self.assertEqual((self.root / "references.bib").read_bytes(), source)
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/api/bibliography?path=references.bib", method="PUT", body=b"stale", headers={"If-Match": f'"{result["hash"]}"'})
        self.assertEqual(context.exception.code, 409)
        self.assertTrue(saved["hash"])

    def test_bibliography_cannot_leave_project(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/api/bibliography?path=..%2Foutside.bib")
        self.assertEqual(context.exception.code, 400)

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

    def test_video_import_and_listing(self) -> None:
        status, _, payload = self.request(
            "/api/asset?name=experiment.mp4",
            method="POST",
            body=b"video",
            headers={"Content-Type": "video/mp4"},
        )
        self.assertEqual(status, 201)
        result = json.loads(payload)
        self.assertEqual(result["path"], "figures/experiment.mp4")
        status, _, payload = self.request("/api/assets?folder=figures&kind=video")
        self.assertEqual(status, 200)
        self.assertEqual([asset["path"] for asset in json.loads(payload)["assets"]], ["figures/experiment.mp4"])
        status, headers, payload = self.request("/project/figures/experiment.mp4", headers={"Range": "bytes=1-3"})
        self.assertEqual(status, 206)
        self.assertEqual(headers["Content-Range"], "bytes 1-3/5")
        self.assertEqual(payload, b"ide")

    def test_mkv_is_converted_to_mp4_with_preview_and_progress(self) -> None:
        def fake_conversion(job):
            job.output.write_bytes(b"mp4")
            job.poster.write_bytes(b"preview")
            job.source.unlink()
            with job.lock:
                job.status = "complete"
                job.progress = 100

        with (
            mock.patch("scientific_slides.server.shutil.which", return_value="/usr/bin/tool"),
            mock.patch("scientific_slides.server._video_conversion_plan", return_value=(".mp4", ["-c:v", "copy"])),
            mock.patch("scientific_slides.server._run_video_conversion", side_effect=fake_conversion),
        ):
            status, _, payload = self.request(
                "/api/video-conversion?name=experiment.mkv",
                method="POST",
                body=b"matroska",
                headers={"Content-Type": "video/x-matroska"},
            )
        self.assertEqual(status, 202)
        started = json.loads(payload)
        self.assertEqual(started["path"], "figures/experiment.mp4")
        self.assertEqual(started["poster"], "figures/experiment-poster.jpg")
        status, _, payload = self.request(f"/api/video-conversion/{started['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["status"], "complete")
        self.assertEqual((self.root / started["path"]).read_bytes(), b"mp4")
        self.assertEqual((self.root / started["poster"]).read_bytes(), b"preview")

    def test_mkv_conversion_reports_missing_ffmpeg(self) -> None:
        with mock.patch("scientific_slides.server.shutil.which", return_value=None):
            with self.assertRaises(urllib.error.HTTPError) as context:
                self.request("/api/video-conversion?name=experiment.mkv", method="POST", body=b"video")
        self.assertEqual(context.exception.code, 503)
        self.assertIn("requires ffmpeg", context.exception.read().decode("utf-8"))

    def test_asset_import_uses_requested_project_folder(self) -> None:
        status, _, payload = self.request(
            "/api/asset?name=diagram.svg&folder=artwork%2Ffigures",
            method="POST",
            body=b"<svg xmlns='http://www.w3.org/2000/svg'/>",
            headers={"Content-Type": "image/svg+xml"},
        )
        self.assertEqual(status, 201)
        result = json.loads(payload)
        self.assertEqual(result["path"], "artwork/figures/diagram.svg")
        self.assertTrue((self.root / result["path"]).is_file())

    def test_asset_import_folder_cannot_leave_project(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request(
                "/api/asset?name=diagram.svg&folder=..%2Foutside",
                method="POST",
                body=b"<svg/>",
                headers={"Content-Type": "image/svg+xml"},
            )
        self.assertEqual(context.exception.code, 400)
        self.assertFalse((self.root.parent / "outside").exists())

    def test_project_images_are_listed_recursively(self) -> None:
        figures = self.root / "artwork" / "figures"
        (figures / "nested").mkdir(parents=True)
        (figures / "diagram.svg").write_text("<svg/>", encoding="utf-8")
        (figures / "nested" / "photo.PNG").write_bytes(b"png")
        (figures / "notes.txt").write_text("not an image", encoding="utf-8")
        status, _, payload = self.request("/api/assets?folder=artwork%2Ffigures")
        result = json.loads(payload)
        self.assertEqual(status, 200)
        self.assertEqual([asset["path"] for asset in result["assets"]], ["artwork/figures/diagram.svg", "artwork/figures/nested/photo.PNG"])

    def test_project_image_listing_cannot_leave_project(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/api/assets?folder=..%2Foutside")
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
