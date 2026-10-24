"""Two storage lanes behind one interface: Tiger Cloud (Postgres/TimescaleDB)
and a single local SQLite file for when there is no database configured.

The Postgres lane is the point of the project. Reclaimed minutes go into a
TimescaleDB hypertable, and the daily rollup is a continuous aggregate the
database maintains itself, so the dashboard query stays small however much
history piles up.
"""
from __future__ import annotations

import ssl
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import config

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS chore (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    description TEXT NOT NULL,
    manual_minutes REAL NOT NULL,
    verdict TEXT NOT NULL,
    reason TEXT NOT NULL,
    automation TEXT,
    model_lane TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS reclaimed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reclaimed_at TEXT NOT NULL,
    chore_id INTEGER REFERENCES chore(id) ON DELETE CASCADE,
    automation TEXT NOT NULL,
    minutes REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'run'
);
CREATE INDEX IF NOT EXISTS reclaimed_automation_idx ON reclaimed (automation, reclaimed_at DESC);
"""

PG_SCHEMA = [
    "CREATE SCHEMA IF NOT EXISTS ledger",
    """CREATE TABLE IF NOT EXISTS ledger.chore (
        id bigserial PRIMARY KEY,
        occurred_at timestamptz NOT NULL,
        description text NOT NULL,
        manual_minutes numeric NOT NULL,
        verdict text NOT NULL,
        reason text,
        automation text,
        model_lane text NOT NULL,
        evidence text NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS ledger.reclaimed (
        reclaimed_at timestamptz NOT NULL,
        chore_id bigint REFERENCES ledger.chore(id) ON DELETE CASCADE,
        automation text NOT NULL,
        minutes numeric NOT NULL,
        source text NOT NULL DEFAULT 'run'
    )""",
    "CREATE INDEX IF NOT EXISTS reclaimed_automation_idx ON ledger.reclaimed (automation, reclaimed_at DESC)",
    "SELECT create_hypertable('ledger.reclaimed', 'reclaimed_at', if_not_exists => TRUE, migrate_data => TRUE)",
    """CREATE MATERIALIZED VIEW IF NOT EXISTS ledger.reclaimed_daily
       WITH (timescaledb.continuous) AS
       SELECT time_bucket('1 day', reclaimed_at) AS day,
              automation,
              sum(minutes) AS minutes,
              count(*) AS runs
       FROM ledger.reclaimed
       GROUP BY day, automation
       WITH NO DATA""",
    """SELECT add_continuous_aggregate_policy('ledger.reclaimed_daily',
         start_offset => INTERVAL '120 days',
         end_offset   => INTERVAL '1 hour',
         schedule_interval => INTERVAL '1 hour',
         if_not_exists => TRUE)""",
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_dict(row, columns: list[str]) -> dict:
    return {name: row[i] for i, name in enumerate(columns)}


class SqliteStore:
    lane = "sqlite"

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or config.setting("LEDGER_DB", "ledger.db"))
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SQLITE_SCHEMA)
        self.conn.commit()

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self.conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def add_chore(self, chore: dict) -> int:
        cur = self.conn.execute(
            """INSERT INTO chore (occurred_at, description, manual_minutes, verdict,
                                  reason, automation, model_lane, evidence)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                chore.get("occurred_at") or utcnow(),
                chore["description"],
                chore["minutes"],
                chore["verdict"],
                chore["reason"],
                chore.get("automation"),
                chore["lane"],
                chore.get("evidence", ""),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_chore(self, chore_id: int) -> dict | None:
        rows = self._rows("SELECT * FROM chore WHERE id = ?", (chore_id,))
        return rows[0] if rows else None

    def add_reclaimed(
        self, chore_id: int, automation: str, minutes: float, source: str = "run", when: str | None = None
    ) -> None:
        self.conn.execute(
            "INSERT INTO reclaimed (reclaimed_at, chore_id, automation, minutes, source) VALUES (?,?,?,?,?)",
            (when or utcnow(), chore_id, automation, minutes, source),
        )
        self.conn.commit()

    def already_reclaimed(self, chore_id: int) -> bool:
        rows = self._rows("SELECT 1 AS hit FROM reclaimed WHERE chore_id = ? LIMIT 1", (chore_id,))
        return bool(rows)

    def recent(self, limit: int = 12) -> list[dict]:
        return self._rows(
            """SELECT c.*, EXISTS (SELECT 1 FROM reclaimed r WHERE r.chore_id = c.id) AS reclaimed
               FROM chore c ORDER BY c.id DESC LIMIT ?""",
            (limit,),
        )

    def summary(self) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
        week = self._rows("SELECT coalesce(sum(minutes),0) AS m, count(*) AS n FROM reclaimed WHERE reclaimed_at >= ?", (cutoff,))[0]
        all_time = self._rows("SELECT coalesce(sum(minutes),0) AS m, count(*) AS n FROM reclaimed")[0]
        counted = self._rows("SELECT count(*) AS n, coalesce(sum(manual_minutes),0) AS m FROM chore")[0]
        top = self._rows(
            """SELECT automation, sum(minutes) AS minutes, count(*) AS runs
               FROM reclaimed GROUP BY automation ORDER BY minutes DESC LIMIT 5"""
        )
        daily = self._rows(
            """SELECT substr(reclaimed_at,1,10) AS day, sum(minutes) AS minutes
               FROM reclaimed WHERE reclaimed_at >= ? GROUP BY day ORDER BY day""",
            ((datetime.now(timezone.utc) - timedelta(days=13)).isoformat(timespec="seconds"),),
        )
        ignored = self._rows(
            """SELECT description, count(*) AS times FROM chore WHERE verdict = 'ignore'
               GROUP BY description ORDER BY times DESC LIMIT 5"""
        )
        still_manual = self._rows(
            """SELECT coalesce(sum(manual_minutes),0) AS m FROM chore c
               WHERE c.verdict = 'automate'
                 AND NOT EXISTS (SELECT 1 FROM reclaimed r WHERE r.chore_id = c.id)"""
        )[0]
        return {
            "week_minutes": round(float(week["m"] or 0), 1),
            "week_runs": int(week["n"] or 0),
            "all_minutes": round(float(all_time["m"] or 0), 1),
            "all_runs": int(all_time["n"] or 0),
            "chores_counted": int(counted["n"] or 0),
            "chores_minutes": round(float(counted["m"] or 0), 1),
            "still_manual_minutes": round(float(still_manual["m"] or 0), 1),
            "top": top,
            "daily": daily,
            "ignored": ignored,
        }

    def close(self) -> None:
        self.conn.close()


def _ssl_context(dsn: str) -> ssl.SSLContext:
    """Tiger Cloud's direct endpoint presents a self-signed chain, so the
    default is libpq's `sslmode=require`: the wire is encrypted, the host is
    not verified. Opt into `sslmode=verify-full` in DATABASE_URL to verify."""
    query = urlparse(dsn).query or ""
    if "sslmode=verify-full" in query or "sslmode=verify-ca" in query:
        return ssl.create_default_context()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


class PostgresStore:
    """Tiger Cloud lane. pg8000 is pure Python, so no compiler and no wheels."""
    lane = "postgres"

    def __init__(self, dsn: str):
        import pg8000.dbapi

        url = urlparse(dsn)
        database = (url.path or "/tsdb").lstrip("/") or "tsdb"
        self.conn = pg8000.dbapi.connect(
            user=unquote(url.username or "tsdbadmin"),
            password=unquote(url.password or ""),
            host=url.hostname,
            port=url.port or 5432,
            database=database,
            ssl_context=_ssl_context(dsn),
            timeout=20,
        )
        self.conn.autocommit = True
        cur = self.conn.cursor()
        for statement in PG_SCHEMA:
            try:
                cur.execute(statement)
            except Exception:
                # Timescale helpers and objects an app role does not own fail
                # harmlessly here; the probe below proves the tables are usable.
                continue
        try:
            cur.execute("SELECT 1 FROM ledger.chore LIMIT 1")
            cur.fetchall()
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller
            raise RuntimeError(f"ledger schema not usable: {exc}") from exc
        cur.close()

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(sql, params)
        # INSERT/DDL statements have no result set; pg8000 raises if you call
        # fetchall() on them, so stop here when there are no columns.
        if cur.description is None:
            cur.close()
            return []
        columns = [d[0] for d in cur.description]
        rows = [
            {
                key: (
                    value.isoformat()
                    if isinstance(value, (datetime, date))
                    else float(value) if isinstance(value, Decimal) else value
                )
                for key, value in zip(columns, row)
            }
            for row in cur.fetchall()
        ]
        cur.close()
        return rows

    def add_chore(self, chore: dict) -> int:
        rows = self._rows(
            """INSERT INTO ledger.chore (occurred_at, description, manual_minutes, verdict,
                                         reason, automation, model_lane, evidence)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (
                chore.get("occurred_at") or utcnow(),
                chore["description"],
                chore["minutes"],
                chore["verdict"],
                chore["reason"],
                chore.get("automation"),
                chore["lane"],
                chore.get("evidence", ""),
            ),
        )
        return int(rows[0]["id"])

    def get_chore(self, chore_id: int) -> dict | None:
        rows = self._rows("SELECT * FROM ledger.chore WHERE id = %s", (chore_id,))
        return rows[0] if rows else None

    def add_reclaimed(
        self, chore_id: int, automation: str, minutes: float, source: str = "run", when: str | None = None
    ) -> None:
        self._rows(
            "INSERT INTO ledger.reclaimed (reclaimed_at, chore_id, automation, minutes, source) VALUES (%s,%s,%s,%s,%s)",
            (when or utcnow(), chore_id, automation, minutes, source),
        )

    def already_reclaimed(self, chore_id: int) -> bool:
        return bool(self._rows("SELECT 1 AS hit FROM ledger.reclaimed WHERE chore_id = %s LIMIT 1", (chore_id,)))

    def recent(self, limit: int = 12) -> list[dict]:
        return self._rows(
            """SELECT c.id, c.occurred_at, c.description, c.manual_minutes, c.verdict, c.reason,
                      c.automation, c.model_lane, c.evidence,
                      EXISTS (SELECT 1 FROM ledger.reclaimed r WHERE r.chore_id = c.id) AS reclaimed
               FROM ledger.chore c ORDER BY c.id DESC LIMIT %s""",
            (limit,),
        )

    def summary(self) -> dict:
        week = self._rows(
            """SELECT coalesce(sum(minutes),0) AS m, count(*) AS n FROM ledger.reclaimed
               WHERE reclaimed_at >= now() - interval '7 days'"""
        )[0]
        all_time = self._rows("SELECT coalesce(sum(minutes),0) AS m, count(*) AS n FROM ledger.reclaimed")[0]
        counted = self._rows("SELECT count(*) AS n, coalesce(sum(manual_minutes),0) AS m FROM ledger.chore")[0]
        top = self._rows(
            """SELECT automation, sum(minutes) AS minutes, sum(runs) AS runs
               FROM ledger.reclaimed_daily GROUP BY automation ORDER BY minutes DESC LIMIT 5"""
        )
        daily = self._rows(
            """SELECT time_bucket('1 day', reclaimed_at)::date::text AS day, sum(minutes) AS minutes
               FROM ledger.reclaimed WHERE reclaimed_at >= now() - interval '14 days'
               GROUP BY 1 ORDER BY 1"""
        )
        ignored = self._rows(
            """SELECT description, count(*) AS times FROM ledger.chore WHERE verdict = 'ignore'
               GROUP BY description ORDER BY times DESC LIMIT 5"""
        )
        still_manual = self._rows(
            """SELECT coalesce(sum(c.manual_minutes),0) AS m FROM ledger.chore c
               WHERE c.verdict = 'automate'
                 AND NOT EXISTS (SELECT 1 FROM ledger.reclaimed r WHERE r.chore_id = c.id)"""
        )[0]
        return {
            "week_minutes": round(float(week["m"] or 0), 1),
            "week_runs": int(week["n"] or 0),
            "all_minutes": round(float(all_time["m"] or 0), 1),
            "all_runs": int(all_time["n"] or 0),
            "chores_counted": int(counted["n"] or 0),
            "chores_minutes": round(float(counted["m"] or 0), 1),
            "still_manual_minutes": round(float(still_manual["m"] or 0), 1),
            "top": top,
            "daily": daily,
            "ignored": ignored,
        }

    def close(self) -> None:
        self.conn.close()


def open_store() -> SqliteStore | PostgresStore:
    """Postgres when DATABASE_URL is set, SQLite otherwise. Never raises for a
    missing database: a ledger that cannot start is a ledger nobody uses."""
    dsn = config.setting("DATABASE_URL")
    if dsn:
        try:
            return PostgresStore(dsn)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, then fall back
            print(f"[sloth] postgres lane unavailable ({exc.__class__.__name__}); using sqlite")
    return SqliteStore()
