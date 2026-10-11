"""HTTP transport contract; set CTW_ADVISER_DB to a pinned built snapshot."""

import http.client
from contextlib import closing
import json
import os
import shutil
import socket
import sqlite3
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ctw_adviser.mcp_http import make_handler, BoundedHTTPServer, SlidingWindowLimiter


DB = Path(os.environ.get("CTW_ADVISER_DB", "work/adviser.sqlite"))
ACCEPT = "application/json, text/event-stream"


class RateLimitTests(unittest.TestCase):
    def test_rolling_window_and_retry_delay(self):
        now = [100.0]
        limiter = SlidingWindowLimiter(capacity=2, window_seconds=60, clock=lambda: now[0])
        self.assertEqual(limiter.admit(), (True, 0))
        self.assertEqual(limiter.admit(), (True, 0))
        now[0] += 2.2
        self.assertEqual(limiter.admit(), (False, 58))
        now[0] += 57.8
        self.assertEqual(limiter.admit(), (True, 0))


@unittest.skipUnless(DB.is_file(), "build work/adviser.sqlite first")
class HTTPTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = BoundedHTTPServer(("127.0.0.1", 0), make_handler(str(DB), frozenset({"https://allowed.example"})))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        self.server.rate_limiter = SlidingWindowLimiter()

    def request(self, method, path="/mcp", payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = json.dumps(payload).encode() if payload is not None else None
        all_headers = {"Content-Type": "application/json", "Accept": ACCEPT,
                       "MCP-Protocol-Version": "2025-06-18"}
        all_headers.update(headers or {})
        connection.request(method, path, body=body, headers=all_headers)
        response = connection.getresponse()
        data = response.read()
        status = response.status
        connection.close()
        return status, json.loads(data) if data else None

    def rpc(self, method, params=None, message_id=1):
        return self.request("POST", payload={"jsonrpc": "2.0", "id": message_id,
                                             "method": method, "params": params or {}})

    def test_lifecycle_discovery_and_calls(self):
        status, data = self.rpc("initialize", {"protocolVersion": "2025-06-18",
            "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
        self.assertEqual(status, 200)
        self.assertEqual(data["result"]["protocolVersion"], "2025-06-18")
        self.assertNotIn("Mcp-Session-Id", data)
        status, _ = self.request("POST", payload={"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(status, 202)
        status, listed = self.rpc("tools/list")
        self.assertEqual(status, 200)
        self.assertEqual(len(listed["result"]["tools"]), 8)
        for tool in listed["result"]["tools"]:
            self.assertIn("inputSchema", tool)
            self.assertIn("outputSchema", tool)
            self.assertTrue(tool["annotations"]["readOnlyHint"])
        status, resolved = self.rpc("tools/call", {"name": "resolve_unit",
            "arguments": {"name_or_key": "Lothern Sea Guard"}})
        self.assertEqual(status, 200)
        self.assertEqual(resolved["result"]["structuredContent"]["status"], "ok")
        self.assertEqual(resolved["result"]["structuredContent"]["snapshot"]["source_commit"],
                         "595e22764b22e748afdbafafcb0a6258973e2451")
        self.assertEqual(json.loads(resolved["result"]["content"][0]["text"]),
                         resolved["result"]["structuredContent"])

    def test_ambiguity_paging_detail_and_errors(self):
        _, ambiguous = self.rpc("tools/call", {"name": "resolve_unit",
            "arguments": {"name_or_key": "Feral Manticore"}})
        self.assertEqual(ambiguous["result"]["structuredContent"]["data"]["status"], "ambiguous")
        _, missing = self.rpc("tools/call", {"name": "resolve_unit",
            "arguments": {"name_or_key": "Bloodletters"}})
        self.assertEqual(missing["result"]["structuredContent"]["data"]["status"], "not_found")
        _, first = self.rpc("tools/call", {"name": "get_unit_combat_profile",
            "arguments": {"unit_key": "Lothern Sea Guard", "section": "weapons", "limit": 1}})
        packet = first["result"]["structuredContent"]["data"]["units"][0]
        section = next(s for s in packet["coverage"]["sections"] if s["name"] == "weapons")
        self.assertEqual(section["state"], "partial")
        _, second = self.rpc("tools/call", {"name": "get_unit_combat_profile",
            "arguments": {"unit_key": "Lothern Sea Guard", "section": "weapons",
                          "limit": 1, "cursor": section["cursor"]}})
        self.assertEqual(next(s for s in second["result"]["structuredContent"]["data"]["units"][0]
                              ["coverage"]["sections"] if s["name"] == "weapons")["offset"], 1)
        ref = packet["provenance_refs"][0]
        _, detail = self.rpc("tools/call", {"name": "get_detail",
            "arguments": {"ref": "record:" + ref, "limit": 1}})
        self.assertEqual(detail["result"]["structuredContent"]["status"], "ok")
        _, invalid = self.rpc("tools/call", {"name": "resolve_unit",
            "arguments": {"name_or_key": "Teclis", "limit": 2}})
        self.assertEqual(invalid["error"]["code"], -32602)
        _, unknown = self.rpc("tools/call", {"name": "absent", "arguments": {}})
        self.assertEqual(unknown["error"]["code"], -32602)

    def test_transport_rejections_and_disconnect(self):
        self.assertEqual(self.request("GET")[0], 405)
        self.assertEqual(self.request("DELETE")[0], 405)
        self.assertEqual(self.request("GET", "/healthz")[0], 200)
        self.assertEqual(self.request("POST", payload={"jsonrpc": "2.0", "id": 1,
            "method": "ping"}, headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request("POST", payload={"jsonrpc": "2.0", "id": 1,
            "method": "ping"}, headers={"MCP-Protocol-Version": "invalid"})[0], 400)
        self.assertEqual(self.request("POST", payload={"jsonrpc": "2.0", "id": 1,
            "method": "ping"}, headers={"Accept": "application/json"})[0], 406)
        self.assertEqual(self.request("POST", payload={"jsonrpc": "2.0", "id": 1,
            "method": "ping"}, headers={"Origin": "https://allowed.example"})[0], 200)
        self.assertEqual(self.request("POST", payload={"jsonrpc": "2.0", "id": 1,
            "method": "ping", "padding": "x" * 65536})[0], 413)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request("POST", "/mcp", body=b"\xff", headers={"Content-Type": "application/json", "Accept": ACCEPT})
        self.assertEqual(connection.getresponse().status, 400)
        connection.close()
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2) as sock:
            sock.sendall(b"POST /mcp HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nAccept: application/json, text/event-stream\r\nContent-Length: 999\r\n\r\n{")
            # Disconnect before the declared body is complete.
        # A disconnected client leaves no server-side session or lock.
        self.assertEqual(self.rpc("ping")[1]["result"], {})

    def test_rate_limit_includes_health(self):
        previous = self.server.rate_limiter
        self.server.rate_limiter = SlidingWindowLimiter(capacity=2)
        try:
            self.assertEqual(self.request("GET", "/healthz")[0], 200)
            self.assertEqual(self.request("GET", "/healthz")[0], 200)
            self.assertEqual(self.request("GET", "/healthz")[0], 429)
            self.assertEqual(self.rpc("ping")[0], 429)
        finally:
            self.server.rate_limiter = previous

    def test_completed_requests_release_all_connection_slots(self):
        held = []
        try:
            for _ in range(16):
                connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
                connection.request("GET", "/healthz")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Connection"), "close")
                response.read()
                held.append(connection)
            time.sleep(0.05)
            self.assertEqual(self.rpc("ping")[0], 200)
        finally:
            for connection in held:
                connection.close()

    def test_slow_body_has_absolute_deadline(self):
        with patch("ctw_adviser.mcp_http.BODY_READ_SECONDS", 0.25):
            with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2) as sock:
                sock.settimeout(2)
                sock.sendall(b"POST /mcp HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
                             b"Accept: application/json, text/event-stream\r\nContent-Length: 20\r\n\r\n{")
                time.sleep(0.12)
                sock.sendall(b" ")
                time.sleep(0.3)
                self.assertIn(b"408 Request Timeout", sock.recv(4096))

    def test_hosted_startup_rejects_forged_source_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            forged = Path(folder) / "forged.sqlite"
            shutil.copyfile(DB, forged)
            with closing(sqlite3.connect(forged)) as db, db:
                db.execute("UPDATE snapshot SET source_commit=?", ("0" * 40,))
            with self.assertRaisesRegex(ValueError, "pinned CTW-data snapshot"):
                make_handler(str(forged), frozenset())
            with closing(sqlite3.connect(forged)) as db, db:
                db.execute("UPDATE snapshot SET source_commit=?, id=?",
                           ("595e22764b22e748afdbafafcb0a6258973e2451", "forged-store4"))
            with self.assertRaisesRegex(ValueError, "pinned CTW-data snapshot"):
                make_handler(str(forged), frozenset())


if __name__ == "__main__":
    unittest.main()
