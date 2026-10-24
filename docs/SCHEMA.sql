-- Sloth Ledger — Tiger Cloud / TimescaleDB schema.
--
-- The app applies this on startup (sloth/db.py: PG_SCHEMA) and tolerates the
-- statements a least-privilege role cannot run, then probes that the tables
-- are usable. This file is the readable copy, including the continuous
-- aggregate that the dashboard's top-automations panel reads.

CREATE SCHEMA IF NOT EXISTS ledger;

-- One row per chore a person described, with the verdict and the evidence
-- that produced its minutes.
CREATE TABLE IF NOT EXISTS ledger.chore (
    id             bigserial PRIMARY KEY,
    occurred_at    timestamptz NOT NULL,
    description    text        NOT NULL,
    manual_minutes numeric     NOT NULL CHECK (manual_minutes >= 0),
    verdict        text        NOT NULL CHECK (verdict IN ('automate', 'delegate', 'ignore')),
    reason         text,
    automation     text,
    model_lane     text        NOT NULL,
    evidence       text        NOT NULL DEFAULT '',
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- One row per automation run that actually gave time back. This is the
-- hypertable: reclaimed time is a time series, queried by week and by day.
CREATE TABLE IF NOT EXISTS ledger.reclaimed (
    reclaimed_at timestamptz NOT NULL,
    chore_id     bigint      REFERENCES ledger.chore (id) ON DELETE CASCADE,
    automation   text        NOT NULL,
    minutes      numeric     NOT NULL CHECK (minutes >= 0),
    source       text        NOT NULL DEFAULT 'run'
);

SELECT create_hypertable(
    'ledger.reclaimed',
    'reclaimed_at',
    if_not_exists => TRUE,
    migrate_data  => TRUE
);

CREATE INDEX IF NOT EXISTS reclaimed_automation_idx
    ON ledger.reclaimed (automation, reclaimed_at DESC);

-- The rollup the dashboard reads instead of scanning the hypertable.
CREATE MATERIALIZED VIEW IF NOT EXISTS ledger.reclaimed_daily
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', reclaimed_at) AS day,
       automation,
       sum(minutes) AS minutes,
       count(*)     AS runs
FROM ledger.reclaimed
GROUP BY day, automation
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'ledger.reclaimed_daily',
    start_offset      => INTERVAL '120 days',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists     => TRUE
);

-- Compression is the slow-and-steady tax: old rows stop costing full price.
ALTER TABLE ledger.reclaimed
    SET (timescaledb.compress, timescaledb.compress_segmentby = 'automation');

SELECT add_compression_policy('ledger.reclaimed', INTERVAL '30 days', if_not_exists => TRUE);

-- Least-privilege application role. Created once by an admin, never used to
-- administer the database.
--   CREATE ROLE sloth_app LOGIN PASSWORD '<generated>';
--   GRANT USAGE ON SCHEMA ledger TO sloth_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ledger TO sloth_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ledger TO sloth_app;
GRANT SELECT ON ledger.reclaimed_daily TO sloth_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA ledger
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sloth_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA ledger
    GRANT USAGE, SELECT ON SEQUENCES TO sloth_app;
