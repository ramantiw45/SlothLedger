"""Domain rules for the ledger.

The model is asked for a judgement. The database is asked for the arithmetic.
Nothing here adds up minutes by hand.
"""
from __future__ import annotations

from . import model
from .db import open_store

VERDICT_LABELS = {
    "automate": "Automate",
    "delegate": "Delegate",
    "ignore": "Ignore forever",
}


def log_chore(store, description: str, stated_minutes: int | None = None) -> dict:
    """Estimate a chore, store it, and return the stored row plus the estimate."""
    result = model.estimate(description, stated_minutes)
    chore_id = store.add_chore(result)
    row = store.get_chore(chore_id)
    return {**(row or {}), "id": chore_id, "estimate": result}


def run_automation(store, chore_id: int) -> dict:
    """Claim back the minutes a chore used to cost. Idempotent per chore."""
    chore = store.get_chore(chore_id)
    if not chore:
        raise KeyError("no such chore")
    if chore["verdict"] != "automate":
        raise ValueError("only automate verdicts have an automation to run")
    if store.already_reclaimed(chore_id):
        raise ValueError("this chore has already been reclaimed")
    automation = chore.get("automation") or "Chore runner"
    store.add_reclaimed(chore_id, automation, float(chore["manual_minutes"]))
    return {"chore_id": chore_id, "automation": automation, "minutes": float(chore["manual_minutes"])}


def payoff_line(summary: dict) -> str:
    """One sentence a human can check, from numbers the database produced."""
    minutes = summary["week_minutes"]
    if minutes <= 0:
        return "No reclaimed minutes yet this week. Log a chore, then run its automation."
    hours, mins = divmod(int(round(minutes)), 60)
    span = f"{hours}h {mins:02d}m" if hours else f"{mins}m"
    runs = summary["week_runs"]
    return f"{span} reclaimed this week across {runs} automation run{'s' if runs != 1 else ''}."


def snapshot(store) -> dict:
    summary = store.summary()
    return {
        **summary,
        "payoff_line": payoff_line(summary),
        "recent": store.recent(10),
        "lanes": model.lanes_available(),
        "store_lane": getattr(store, "lane", "unknown"),
        "verdict_labels": VERDICT_LABELS,
    }
