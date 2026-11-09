from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from scientific_slides.browser import (
    BrowserError,
    ChromiumPage,
    FirefoxPage,
    WebSocket,
    browser_kind,
    find_browser,
    launch_command,
    open_page,
    read_endpoint,
    wait_for,
)

WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class BrowserDiscoveryTests(unittest.TestCase):
    def test_chromium_is_preferred_and_firefox_is_the_fallback(self) -> None:
        with mock.patch("scientific_slides.browser.find_executable", side_effect=["/usr/bin/chromium"]):
            self.assertEqual(find_browser(), ("chromium", "/usr/bin/chromium"))
        with mock.patch("scientific_slides.browser.find_executable", side_effect=[None, "/usr/bin/firefox"]):
            self.assertEqual(find_browser(), ("firefox", "/usr/bin/firefox"))

    def test_missing_browser_names_the_purpose_and_the_ones_that_would_work(self) -> None:
        with mock.patch("scientific_slides.browser.find_executable", return_value=None):
            with self.assertRaises(RuntimeError) as error:
                find_browser(purpose="Rendering slides")
        self.assertIn("Rendering slides needs Chrome, Chromium, Edge, or Firefox", str(error.exception))

    def test_named_browser_is_used_and_classified_by_its_program_name(self) -> None:
        with mock.patch("scientific_slides.browser.find_executable", return_value="/opt/firefox-esr/firefox-esr"):
            self.assertEqual(find_browser("firefox-esr"), ("firefox", "/opt/firefox-esr/firefox-esr"))
        with mock.patch("scientific_slides.browser.find_executable", return_value=None):
            with self.assertRaises(FileNotFoundError):
                find_browser("no-such-browser")

    def test_edge_and_brave_are_driven_the_way_chromium_is(self) -> None:
        self.assertEqual(browser_kind("/usr/bin/msedge"), "chromium")
        self.assertEqual(browser_kind(r"C:\Program Files\BraveSoftware\brave.exe"), "chromium")
        self.assertEqual(browser_kind(r"C:\Program Files\Mozilla Firefox\firefox.exe"), "firefox")


class LaunchTests(unittest.TestCase):
    def test_chromium_runs_headless_in_its_own_profile_on_a_free_loopback_port(self) -> None:
        command = launch_command("chromium", "/usr/bin/chromium", Path("/tmp/p"))
        self.assertIn("--headless=new", command)
        self.assertIn(f"--user-data-dir={Path('/tmp/p')}", command)
        self.assertIn("--remote-debugging-port=0", command)
        self.assertIn("--remote-debugging-address=127.0.0.1", command)

    def test_firefox_runs_headless_in_its_own_instance_and_profile(self) -> None:
        command = launch_command("firefox", "/usr/bin/firefox", Path("/tmp/p"))
        self.assertIn("--headless", command)
        self.assertIn("--no-remote", command)
        self.assertEqual(command[command.index("--profile") + 1], str(Path("/tmp/p")))
        self.assertEqual(command[command.index("--remote-debugging-port") + 1], "0")

    def test_the_endpoint_is_read_from_the_file_each_browser_writes_in_its_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            self.assertIsNone(read_endpoint("chromium", profile))
            self.assertIsNone(read_endpoint("firefox", profile))
            (profile / "DevToolsActivePort").write_text("41234\n/devtools/browser/abc\n", encoding="utf-8")
            self.assertEqual(read_endpoint("chromium", profile), ("127.0.0.1", 41234, "/devtools/browser/abc"))
            (profile / "WebDriverBiDiServer.json").write_text('{"ws_host": "127.0.0.1", "ws_port": 39', encoding="utf-8")
            self.assertIsNone(read_endpoint("firefox", profile), "a half-written file is not an endpoint")
            (profile / "WebDriverBiDiServer.json").write_text('{"ws_host": "127.0.0.1", "ws_port": 39793}', encoding="utf-8")
            self.assertEqual(read_endpoint("firefox", profile), ("127.0.0.1", 39793, "/session"))

    def test_the_console_announcement_is_the_fallback_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            profile, log = Path(directory), Path(directory) / "browser.log"
            self.assertIsNone(read_endpoint("firefox", profile, log), "a missing log is not an endpoint")
            log.write_text("starting\nWebDriver BiDi listening on ws://127.0.0.1:4444\n", encoding="utf-8")
            self.assertEqual(read_endpoint("firefox", profile, log), ("127.0.0.1", 4444, "/session"))
            log.write_text("DevTools listening on ws://127.0.0.1:9222/devtools/browser/x-y\n", encoding="utf-8")
            self.assertEqual(read_endpoint("chromium", profile, log), ("127.0.0.1", 9222, "/devtools/browser/x-y"))

    def _fake_browser(self, script: str):
        return mock.patch(
            "scientific_slides.browser.launch_command",
            side_effect=lambda kind, program, profile: [sys.executable, "-c", script, str(profile)],
        )

    def test_a_browser_that_stops_before_it_listens_reports_what_it_said(self) -> None:
        with self._fake_browser("import sys; print('cannot open display'); sys.exit(1)"):
            with self.assertRaises(BrowserError) as error:
                with open_page("chromium", "chromium", startup_timeout=30):
                    pass
        self.assertIn("stopped before it was ready", str(error.exception))
        self.assertIn("cannot open display", str(error.exception))

    def test_a_browser_that_never_listens_is_timed_out_and_stopped(self) -> None:
        with self._fake_browser("import time; time.sleep(60)"):
            with self.assertRaises(BrowserError) as error:
                with open_page("firefox", "firefox", startup_timeout=1):
                    pass
        self.assertIn("Timed out waiting for the browser to start", str(error.exception))


class FakeServer:
    """A one-connection WebSocket server that runs a scripted conversation."""

    def __init__(self, script, accept: bool = True) -> None:
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.script = script
        self.accept = accept
        self.received: list[tuple[int, bytes]] = []
        self.request = b""
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _read(self, connection: socket.socket, count: int) -> bytes:
        data = b""
        while len(data) < count:
            chunk = connection.recv(count - len(data))
            if not chunk:
                raise ConnectionError
            data += chunk
        return data

    def read_frame(self, connection: socket.socket) -> tuple[int, bytes]:
        first, second = self._read(connection, 2)
        assert second & 0x80, "client frames must be masked"
        length = second & 0x7F
        if length == 126:
            (length,) = struct.unpack("!H", self._read(connection, 2))
        elif length == 127:
            (length,) = struct.unpack("!Q", self._read(connection, 8))
        mask = self._read(connection, 4)
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(self._read(connection, length)))
        self.received.append((first & 0x0F, payload))
        return first & 0x0F, payload

    @staticmethod
    def frame(opcode: int, payload: bytes, final: bool = True) -> bytes:
        header = bytearray([(0x80 if final else 0) | opcode])
        if len(payload) < 126:
            header.append(len(payload))
        elif len(payload) < 1 << 16:
            header.append(126)
            header += struct.pack("!H", len(payload))
        else:
            header.append(127)
            header += struct.pack("!Q", len(payload))
        return bytes(header) + payload

    def _run(self) -> None:
        with self.listener:
            connection, _ = self.listener.accept()
        with connection:
            while b"\r\n\r\n" not in self.request:
                self.request += connection.recv(4096)
            if not self.accept:
                connection.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            key = [line.split(b":", 1)[1].strip() for line in self.request.split(b"\r\n") if line.lower().startswith(b"sec-websocket-key")][0]
            accept = base64.b64encode(hashlib.sha1(key + WEBSOCKET_GUID.encode()).digest())
            connection.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                               b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n")
            try:
                self.script(self, connection)
            except ConnectionError:
                pass


class WebSocketTests(unittest.TestCase):
    def test_messages_of_every_length_encoding_round_trip(self) -> None:
        large = "x" * 70000

        def script(server: FakeServer, connection: socket.socket) -> None:
            for _ in range(3):
                _, payload = server.read_frame(connection)
                connection.sendall(server.frame(0x1, payload))

        server = FakeServer(script)
        client = WebSocket("127.0.0.1", server.port, "/session")
        for message in ("hi", "y" * 300, large):
            client.send(message)
            self.assertEqual(client.receive(), message)
        client.close()
        self.assertIn(b"GET /session HTTP/1.1", server.request)
        self.assertNotIn(b"origin:", server.request.lower(), "automation endpoints refuse page origins")

    def test_fragments_are_joined_and_pings_are_answered(self) -> None:
        def script(server: FakeServer, connection: socket.socket) -> None:
            connection.sendall(server.frame(0x9, b"are you there"))
            connection.sendall(server.frame(0x1, b'{"id": ', final=False))
            connection.sendall(server.frame(0x0, b"1}"))
            server.read_frame(connection)

        server = FakeServer(script)
        client = WebSocket("127.0.0.1", server.port, "/")
        self.assertEqual(client.receive(), '{"id": 1}')
        client.close()
        server.thread.join(5)
        self.assertEqual(server.received[0], (0xA, b"are you there"))

    def test_a_closed_connection_is_a_browser_error(self) -> None:
        def script(server: FakeServer, connection: socket.socket) -> None:
            connection.sendall(server.frame(0x8, b""))

        server = FakeServer(script)
        client = WebSocket("127.0.0.1", server.port, "/")
        with self.assertRaises(BrowserError):
            client.receive()
        client.close()

    def test_a_refused_handshake_is_a_browser_error(self) -> None:
        server = FakeServer(lambda *_: None, accept=False)
        with self.assertRaises(BrowserError) as error:
            WebSocket("127.0.0.1", server.port, "/")
        self.assertIn("403", str(error.exception))


class ScriptedConnection:
    """Stands in for a WebSocket: answers each request from a table of replies."""

    def __init__(self, replies) -> None:
        self.replies = replies
        self.sent: list[dict] = []
        self.queue: list[str] = []

    def settimeout(self, timeout: float | None) -> None:
        pass

    def send(self, text: str) -> None:
        message = json.loads(text)
        self.sent.append(message)
        reply = self.replies(message)
        # An unrelated event arrives first; the adapter must skip it.
        self.queue.append(json.dumps({"method": "some.event", "params": {}}))
        self.queue.append(json.dumps({"id": message["id"], **reply}))

    def receive(self) -> str:
        return self.queue.pop(0)


class ChromiumPageTests(unittest.TestCase):
    def replies(self, message: dict) -> dict:
        method = message["method"]
        if method == "Browser.getVersion":
            return {"result": {"protocolVersion": "1.3", "product": "HeadlessChrome/156.0", "userAgent": "UA"}}
        if method == "Target.createTarget":
            return {"result": {"targetId": "T"}}
        if method == "Target.attachToTarget":
            return {"result": {"sessionId": "S"}}
        if method == "Runtime.evaluate":
            if message["params"]["expression"] == "broken":
                return {"result": {"exceptionDetails": {"text": "Uncaught"}}}
            return {"result": {"result": {"type": "boolean", "value": True}}}
        if method == "Page.captureScreenshot":
            return {"result": {"data": base64.b64encode(b"PNG").decode()}}
        if method == "Page.printToPDF":
            return {"result": {"data": base64.b64encode(b"%PDF").decode()}}
        if method == "Page.navigate" and message["params"]["url"] == "http://bad/":
            return {"result": {"errorText": "net::ERR_CONNECTION_REFUSED"}}
        if method == "Missing.method":
            return {"error": {"message": "not found"}}
        return {"result": {}}

    def test_page_commands_go_to_the_attached_session_with_the_requested_viewport(self) -> None:
        connection = ScriptedConnection(self.replies)
        page = ChromiumPage(connection, 640, 360)
        page.navigate("http://127.0.0.1:9/?preview")
        self.assertIs(page.evaluate("1"), True)
        self.assertEqual(page.screenshot(), b"PNG")
        self.assertEqual(page.print_pdf(13.3, 7.5, 30), b"%PDF")
        self.assertEqual(page.details["product"], "HeadlessChrome/156.0")
        self.assertEqual(page.details["protocol"], "CDP 1.3")
        by_method = {message["method"]: message for message in connection.sent}
        self.assertNotIn("sessionId", by_method["Target.createTarget"])
        self.assertEqual(by_method["Page.navigate"]["sessionId"], "S")
        metrics = by_method["Emulation.setDeviceMetricsOverride"]["params"]
        self.assertEqual((metrics["width"], metrics["height"], metrics["deviceScaleFactor"]), (640, 360, 1))
        pdf = by_method["Page.printToPDF"]["params"]
        self.assertTrue(pdf["printBackground"])
        self.assertTrue(pdf["preferCSSPageSize"])
        self.assertEqual((pdf["paperWidth"], pdf["paperHeight"], pdf["marginTop"]), (13.3, 7.5, 0))

    def test_failures_are_browser_errors(self) -> None:
        page = ChromiumPage(ScriptedConnection(self.replies), 1280, 720)
        with self.assertRaises(BrowserError):
            page.evaluate("broken")
        with self.assertRaises(BrowserError):
            page.navigate("http://bad/")
        with self.assertRaises(BrowserError):
            page.command("Missing.method")


class FirefoxPageTests(unittest.TestCase):
    def replies(self, message: dict) -> dict:
        method = message["method"]
        if method == "session.new":
            return {"type": "success", "result": {"capabilities": {
                "browserName": "firefox", "browserVersion": "153.6", "platformName": "linux", "userAgent": "UA"}}}
        if method == "browsingContext.getTree":
            return {"type": "success", "result": {"contexts": [{"context": "C"}]}}
        if method == "script.evaluate":
            if message["params"]["expression"] == "broken":
                return {"type": "success", "result": {"type": "exception", "exceptionDetails": {"text": "Uncaught"}}}
            return {"type": "success", "result": {"type": "success", "result": {"type": "string", "value": "ok"}}}
        if method == "browsingContext.captureScreenshot":
            return {"type": "success", "result": {"data": base64.b64encode(b"PNG").decode()}}
        if method == "browsingContext.print":
            return {"type": "success", "result": {"data": base64.b64encode(b"%PDF").decode()}}
        if method == "Missing.method":
            return {"type": "error", "error": "unknown command", "message": "nope"}
        return {"type": "success", "result": {}}

    def test_a_session_drives_the_first_context_and_prints_at_the_slide_size(self) -> None:
        connection = ScriptedConnection(self.replies)
        page = FirefoxPage(connection, 1280, 720)
        page.navigate("http://127.0.0.1:9/?print-pdf")
        self.assertEqual(page.evaluate("1"), "ok")
        self.assertEqual(page.screenshot(), b"PNG")
        self.assertEqual(page.print_pdf(1280 / 96, 720 / 96, 30), b"%PDF")
        self.assertEqual(connection.sent[0]["method"], "session.new")
        self.assertEqual(page.details["product"], "firefox/153.6")
        self.assertEqual(page.details["platform"], "linux")
        by_method = {message["method"]: message["params"] for message in connection.sent}
        self.assertEqual(by_method["browsingContext.setViewport"]["viewport"], {"width": 1280, "height": 720})
        self.assertEqual(by_method["browsingContext.navigate"]["context"], "C")
        printed = by_method["browsingContext.print"]
        self.assertAlmostEqual(printed["page"]["width"], 33.8667, places=3)
        self.assertAlmostEqual(printed["page"]["height"], 19.05, places=3)
        self.assertEqual(printed["margin"], {"top": 0, "bottom": 0, "left": 0, "right": 0})
        self.assertFalse(printed["shrinkToFit"])
        self.assertTrue(printed["background"])

    def test_failures_are_browser_errors(self) -> None:
        page = FirefoxPage(ScriptedConnection(self.replies), 1280, 720)
        with self.assertRaises(BrowserError):
            page.evaluate("broken")
        with self.assertRaises(BrowserError):
            page.command("Missing.method")


class WaitTests(unittest.TestCase):
    def test_evaluation_errors_while_loading_are_retried(self) -> None:
        page = mock.Mock()
        page.evaluate.side_effect = [BrowserError("context destroyed"), "", 0, 37]
        self.assertEqual(wait_for(page, "ready", 30), 37)

    def test_a_reported_player_error_stops_waiting(self) -> None:
        page = mock.Mock()
        page.evaluate.return_value = "error:Cannot open presentation: bad YAML"
        with self.assertRaises(BrowserError) as error:
            wait_for(page, "ready", 30)
        self.assertEqual(str(error.exception), "Cannot open presentation: bad YAML")

    def test_a_page_that_never_becomes_ready_times_out(self) -> None:
        page = mock.Mock()
        page.evaluate.return_value = False
        with self.assertRaises(BrowserError) as error:
            wait_for(page, "ready", 0.3)
        self.assertIn("Timed out", str(error.exception))


if __name__ == "__main__":
    unittest.main()
