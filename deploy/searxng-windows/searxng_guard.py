"""Token-protected HTTP gateway for the private SearXNG process."""

from __future__ import annotations

import hmac
import hashlib
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8889
UPSTREAM = "http://127.0.0.1:8888"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Handler(BaseHTTPRequestHandler):
    server_version = "GeocodingSearchGateway/1.0"

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return
        if parsed.path != "/search":
            self._send(404, b'{"error":"not found"}', "application/json")
            return

        expected = os.environ.get("SEARXNG_API_TOKEN", "")
        supplied = self.headers.get("X-SearXNG-Token", "")
        if not expected or not hmac.compare_digest(supplied, expected):
            print(
                "auth rejected expected_len=%d expected_fp=%s supplied_len=%d supplied_fp=%s"
                % (
                    len(expected),
                    hashlib.sha256(expected.encode()).hexdigest()[:12],
                    len(supplied),
                    hashlib.sha256(supplied.encode()).hexdigest()[:12],
                ),
                flush=True,
            )
            self._send(403, b'{"error":"forbidden"}', "application/json")
            return

        request = urllib.request.Request(
            UPSTREAM + self.path,
            headers={
                "Accept": "application/json",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0.0.0 Safari/537.36"
                ),
            },
        )
        try:
            with DIRECT_OPENER.open(request, timeout=25) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    self._send(502, b'{"error":"upstream response too large"}', "application/json")
                    return
                self._send(
                    response.status,
                    body,
                    response.headers.get("Content-Type", "application/json"),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read(MAX_RESPONSE_BYTES)
            self._send(exc.code, body, exc.headers.get("Content-Type", "application/json"))
        except Exception:
            self._send(502, b'{"error":"search upstream unavailable"}', "application/json")

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    token = os.environ.get("SEARXNG_API_TOKEN", "")
    if not token:
        raise SystemExit("SEARXNG_API_TOKEN is required")
    print(
        "gateway started token_len=%d token_fp=%s"
        % (len(token), hashlib.sha256(token.encode()).hexdigest()[:12]),
        flush=True,
    )
    ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler).serve_forever()
