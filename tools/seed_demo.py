#!/usr/bin/env python3
"""Seed the ledger with demo entries.

DEMO CORPUS — synthetic. These are illustrative entries for a fictional
freelance designer, not measurements of a real person's week. Replace them
with your own chores before publishing anything that claims savings.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sloth import config, ledger  # noqa: E402
from sloth.db import open_store  # noqa: E402

# (description, days-ago the automation ran) - order sets the history.
DEMO = [
    ("every night re-typed 60 invoice lines into the accounts sheet", 12),
    ("reconciled 25 bank statement lines against invoices", 10),
    ("sorted 35 receipts into the expense folder", None),
    ("logged 20 expenses into the sheet every Friday", 5),
    ("renamed 40 client files from the WhatsApp downloads folder", 3),
    ("replied to 12 client messages that only needed a thumbs up", None),
    ("call the landlord about the studio deposit", None),
    ("watered the two plants on the windowsill", None),
]


def days_ago(days: int, hour: int = 19) -> str:
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return moment.replace(hour=hour, minute=30, second=0, microsecond=0).isoformat(timespec="seconds")


def main() -> None:
    config.load_env()
    store = open_store()
    print(f"[seed] store lane: {store.lane}")
    try:
        for description, ran_days_ago in DEMO:
            chore = ledger.log_chore(store, description)
            status = f"{chore['verdict']:<9} {chore['manual_minutes']:>3}m"
            print(f"[seed] {status}  {description[:58]}")
            if ran_days_ago is not None and chore["verdict"] == "automate":
                store.add_reclaimed(
                    chore["id"],
                    chore["automation"] or "Chore runner",
                    float(chore["manual_minutes"]),
                    source="backfill",
                    when=days_ago(ran_days_ago),
                )
        summary = store.summary()
        print(f"[seed] week {summary['week_minutes']}m · all time {summary['all_minutes']}m "
              f"· {summary['chores_counted']} chores judged")
    finally:
        store.close()


if __name__ == "__main__":
    main()
