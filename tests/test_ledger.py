#!/usr/bin/env python3
"""Tests for the estimation rules and the ledger. No test framework required."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Tests pin the deterministic floor so a running local model cannot change the
# expected verdicts halfway through a suite.
os.environ["SLOTH_FORCE_RULES"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sloth import ledger, model  # noqa: E402
from sloth.db import SqliteStore  # noqa: E402


class EstimateTests(unittest.TestCase):
    def test_count_beats_model_for_minutes(self):
        est = model.estimate("renamed 40 receipts from the shoebox")
        # 40 x 20s = 800s = 13.3 min -> 13. The number comes from the count.
        self.assertEqual(est["minutes"], 13)
        self.assertIn("40 x 20s", est["evidence"])

    def test_stated_minutes_win(self):
        est = model.estimate("sorted 40 receipts", stated_minutes=45)
        self.assertEqual(est["minutes"], 45)
        self.assertIn("measured", est["evidence"])

    def test_tiny_chore_is_ignored(self):
        est = model.estimate("watered one plant")
        self.assertEqual(est["verdict"], "ignore")
        self.assertIsNone(est["automation"])

    def test_recurring_chore_is_automated(self):
        est = model.estimate("every night I re-type the till totals into a sheet")
        self.assertEqual(est["verdict"], "automate")
        self.assertTrue(est["automation"])

    def test_human_chore_is_delegated(self):
        est = model.estimate("call the landlord about the leaking tap")
        self.assertEqual(est["verdict"], "delegate")

    def test_minutes_are_clamped(self):
        est = model.estimate("filed 5000 documents")
        self.assertLessEqual(est["minutes"], 480)

    def test_empty_description_is_rejected(self):
        with self.assertRaises(ValueError):
            model.estimate("   ")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SqliteStore(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_run_books_minutes_once(self):
        chore = ledger.log_chore(self.store, "renamed 40 receipts")
        self.assertEqual(chore["verdict"], "automate")
        before = self.store.summary()
        self.assertEqual(before["week_minutes"], 0)

        result = ledger.run_automation(self.store, chore["id"])
        self.assertEqual(result["minutes"], 13)

        after = self.store.summary()
        self.assertEqual(after["week_minutes"], 13)
        self.assertEqual(after["week_runs"], 1)

        with self.assertRaises(ValueError):
            ledger.run_automation(self.store, chore["id"])
        self.assertEqual(self.store.summary()["week_minutes"], 13)

    def test_ignore_verdict_cannot_run(self):
        chore = ledger.log_chore(self.store, "replied to one message")
        with self.assertRaises(ValueError):
            ledger.run_automation(self.store, chore["id"])

    def test_payoff_line_reads_from_totals(self):
        chore = ledger.log_chore(self.store, "every night re-typed 60 entries")
        ledger.run_automation(self.store, chore["id"])
        summary = self.store.summary()
        self.assertIn("reclaimed this week", ledger.payoff_line(summary).lower())

    def test_still_manual_excludes_reclaimed(self):
        chore = ledger.log_chore(self.store, "renamed 40 receipts")
        self.assertGreater(self.store.summary()["still_manual_minutes"], 0)
        ledger.run_automation(self.store, chore["id"])
        self.assertEqual(self.store.summary()["still_manual_minutes"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
