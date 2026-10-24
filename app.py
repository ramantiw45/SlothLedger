#!/usr/bin/env python3
"""Sloth Ledger -- a local-first ledger of time you got back.

Run it:      python app.py
Open:        http://127.0.0.1:8787
No dependencies. Standard library only, on purpose.
"""
from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from sloth import config, ledger
from sloth.db import open_store

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
PORT = int(config.setting("PORT", "8787") or 8787)

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "SlothLedger/1.0"

    def log_message(self, fmt: str, *args) -> None:  # keep the console quiet
        if "healthz" not in (args[0] if args else ""):
            super().log_message(fmt, *args)

    # -- helpers ---------------------------------------------------------
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if "json" in content_type else "max-age=60")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("body is not valid JSON")

    def _store(self):
        return open_store()

    def _snapshot(self) -> dict:
        store = self._store()
        try:
            return ledger.snapshot(store)
        finally:
            store.close()

    # -- routes ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path == "/healthz":
            store = self._store()
            try:
                lane = getattr(store, "lane", "unknown")
            finally:
                store.close()
            return self._json(200, {"ok": True, "store": lane, "lanes": ledger.model.lanes_available()})
        if path == "/api/summary":
            return self._json(200, self._snapshot())
        if path.startswith("/static/"):
            return self._static(path.removeprefix("/static/"))
        self._json(404, {"error": "not found"})

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self._body()
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})

        if path == "/api/log":
            description = (payload.get("description") or "").strip()
            if len(description) < 3:
                return self._json(400, {"error": "describe the chore in a few words"})
            minutes = payload.get("minutes")
            try:
                minutes = int(minutes) if minutes not in (None, "") else None
            except (TypeError, ValueError):
                minutes = None
            store = self._store()
            try:
                chore = ledger.log_chore(store, description, minutes)
                snapshot = ledger.snapshot(store)
            finally:
                store.close()
            return self._json(200, {"chore": chore, "ledger": snapshot})

        if path == "/api/run":
            try:
                chore_id = int(payload.get("id"))
            except (TypeError, ValueError):
                return self._json(400, {"error": "id is required"})
            store = self._store()
            try:
                result = ledger.run_automation(store, chore_id)
                snapshot = ledger.snapshot(store)
            except KeyError:
                return self._json(404, {"error": "no such chore"})
            except ValueError as exc:
                return self._json(409, {"error": str(exc)})
            finally:
                store.close()
            return self._json(200, {"ran": result, "ledger": snapshot})

        self._json(404, {"error": "not found"})

    def _static(self, name: str) -> None:
        target = (STATIC / name).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            return self._json(404, {"error": "not found"})
        self._send(200, target.read_bytes(), CONTENT_TYPES.get(target.suffix, "application/octet-stream"))


def main() -> None:
    config.load_env()
    store = open_store()
    lane = getattr(store, "lane", "unknown")
    store.close()
    print(f"Sloth Ledger on http://127.0.0.1:{PORT}  (store: {lane})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
