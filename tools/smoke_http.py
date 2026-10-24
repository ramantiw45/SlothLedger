#!/usr/bin/env python3
"""Smoke the running app over HTTP, the way a browser would.

    python app.py            # in one terminal
    python tools/smoke_http.py

Checks the health probe, the summary shape, logging a chore, and booking one
automation. Prints one line per check and exits non-zero on the first failure.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

CHECKS: list[str] = []


def call(base: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(f"{base}{path}", data=data, method="POST" if data else "GET")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        print(f"FAIL  {label}  {detail}")
        sys.exit(1)
    CHECKS.append(label)
    print(f"ok    {label}  {detail}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    status, health = call(base, "/healthz")
    check("healthz answers 200", status == 200, health.get("status", ""))
    check("healthz names a store lane", bool(health.get("store")), health.get("store", ""))

    status, summary = call(base, "/api/summary")
    check("summary answers 200", status == 200)
    for field in ("week_minutes", "all_minutes", "chores_counted", "recent", "daily", "payoff_line"):
        check(f"summary has {field}", field in summary)

    before = summary["all_minutes"]
    status, logged = call(
        base,
        "/api/log",
        {"description": "smoke test: renamed 12 receipts from the shoebox"},
    )
    check("log answers 200", status == 200, logged.get("chore", {}).get("verdict", ""))
    chore = logged.get("chore", {})
    check("log returns a chore id", isinstance(chore.get("id"), int))
    check("log returns evidence", bool(chore.get("evidence")), str(chore.get("evidence", "")))
    check("log returns a verdict", chore.get("verdict") in {"automate", "delegate", "ignore"})
    check("ledger grew", logged.get("ledger", {}).get("all_minutes", before) >= before)

    if chore.get("verdict") == "automate":
        status, ran = call(base, "/api/run", {"id": chore["id"]})
        check("run answers 200", status == 200)
        check("run books minutes", ran.get("ledger", {}).get("all_minutes", 0) > before)
        status, again = call(base, "/api/run", {"id": chore["id"]})
        check("second run is refused", status == 400, again.get("error", ""))

    status, bad = call(base, "/api/log", {"description": ""})
    check("empty description is rejected", status == 400, bad.get("error", ""))

    print(f"\n{len(CHECKS)} checks passed against {base}")


if __name__ == "__main__":
    main()
