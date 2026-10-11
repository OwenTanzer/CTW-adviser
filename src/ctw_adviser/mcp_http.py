"""Stateless MCP Streamable HTTP endpoint over the existing read-only dispatcher.

Run ``python -m ctw_adviser.mcp_http --db PATH``. TLS termination belongs to
the hosting platform; the local listener defaults to loopback.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading

from .mcp import PROTOCOL_VERSION, SERVER_VERSION, _response, dispatch_method
from .queries import Queries

MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_CONNECTIONS = 16


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = MAX_CONNECTIONS

    def __init__(self, *args, **kwargs):
        self._connections = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._connections.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(15)
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()

    def handle_error(self, request, client_address):
        # A client can leave during a response; it is not a server failure.
        if isinstance(sys.exc_info()[1], (ConnectionError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def make_handler(db_path: str, allowed_origins: frozenset[str]):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "CTW-MCP/" + SERVER_VERSION

        def log_message(self, format, *args):
            # Never log request bodies, tool arguments, or private conversations.
            pass

        def _send(self, status: int, payload=None, *, headers=None):
            body = (json.dumps(payload, ensure_ascii=False, allow_nan=False,
                               separators=(",", ":")).encode("utf-8") if payload is not None else b"")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8" if body else "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _origin_ok(self):
            origins = self.headers.get_all("Origin", [])
            if len(origins) > 1 or (origins and origins[0] not in allowed_origins):
                self._send(403, {"error": "origin not allowed"})
                return False
            return True

        def do_GET(self):
            if not self._origin_ok():
                return
            if self.path == "/healthz":
                self._send(200, {"status": "ok", "transport": "streamable-http",
                                 "protocol_version": PROTOCOL_VERSION})
            elif self.path == "/mcp":
                # This server never sends unsolicited messages or SSE streams.
                self._send(405, {"error": "SSE GET not supported"}, headers={"Allow": "POST"})
            else:
                self._send(404, {"error": "not found"})

        def do_DELETE(self):
            if not self._origin_ok():
                return
            self._send(405, {"error": "stateless server has no sessions"}, headers={"Allow": "POST, GET"})

        def do_OPTIONS(self):
            if self._origin_ok():
                self._send(405, {"error": "method not allowed"}, headers={"Allow": "POST, GET"})

        do_HEAD = do_OPTIONS
        do_PUT = do_OPTIONS
        do_PATCH = do_OPTIONS

        def do_POST(self):
            if not self._origin_ok():
                return
            if self.path != "/mcp":
                self._send(404, {"error": "not found"})
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            accept = self.headers.get("Accept", "").lower()
            if content_type != "application/json" or "application/json" not in accept or "text/event-stream" not in accept:
                self._send(406, {"error": "MCP requires JSON Content-Type and JSON plus event-stream Accept"})
                return
            version = self.headers.get("MCP-Protocol-Version")
            if version is not None and version != PROTOCOL_VERSION:
                self._send(400, {"error": "unsupported MCP protocol version"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = -1
            if length < 0:
                self._send(411, {"error": "Content-Length required"})
                return
            if length > MAX_REQUEST_BYTES:
                if length <= 2 * MAX_REQUEST_BYTES:
                    self.rfile.read(length)
                self.close_connection = True
                self._send(413, {"error": "request exceeds 64 KiB"})
                return
            try:
                request = json.loads(self.rfile.read(length).decode("utf-8", errors="strict"))
            except (UnicodeError, json.JSONDecodeError):
                self._send(400, _response(None, error={"code": -32700, "message": "invalid UTF-8 JSON"}))
                return
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
                self._send(400, _response(None, error={"code": -32600, "message": "invalid JSON-RPC request"}))
                return
            if "id" not in request:
                # Stateless notifications need no remembered initialized flag.
                if request["method"] != "notifications/initialized":
                    self._send(400, _response(None, error={"code": -32600, "message": "unsupported notification"}))
                else:
                    self._send(202)
                return
            message_id = request["id"]
            if isinstance(message_id, bool) or not isinstance(message_id, (str, int)):
                self._send(400, _response(None, error={"code": -32600, "message": "invalid id"}))
                return
            if request["method"] == "initialize":
                params = request.get("params")
                if not isinstance(params, dict) or not isinstance(params.get("protocolVersion"), str):
                    result = _response(message_id, error={"code": -32602, "message": "invalid initialize params"})
                else:
                    result = _response(message_id, result={"protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "ctw-adviser", "version": SERVER_VERSION}})
            else:
                # Queries opens the verified artifact read-only for each request.
                with Queries(db_path) as queries:
                    result = dispatch_method(queries, request["method"], request.get("params"), message_id)
            encoded = json.dumps(result, ensure_ascii=False, allow_nan=False,
                                 separators=(",", ":")).encode("utf-8")
            if len(encoded) > MAX_RESPONSE_BYTES:
                result = _response(message_id, error={"code": -32001,
                    "message": "response exceeds 1 MiB; use a smaller limit, section or detail cursor"})
            self._send(200, result)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="already built and verified SQLite snapshot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument("--allow-public", action="store_true", help="allow binding beyond loopback")
    parser.add_argument("--allowed-origin", action="append", default=[], help="exact Origin value; repeatable")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "::1", "localhost") and not args.allow_public:
        parser.error("non-loopback binding requires --allow-public")
    db_path = str(Path(args.db).resolve(strict=True))
    with Queries(db_path):
        pass
    configured = [item.strip() for item in os.environ.get("CTW_ALLOWED_ORIGINS", "").split(",") if item.strip()]
    server = BoundedHTTPServer((args.host, args.port), make_handler(db_path, frozenset(args.allowed_origin + configured)))
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
