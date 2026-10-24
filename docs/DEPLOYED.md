# Deployment record

The public demo is a Render web service. This file is the receipt: what is
deployed, what it is configured with, and how to check that it is still telling
the truth.

Live: <https://sloth-ledger.onrender.com>

## Service

| | |
|---|---|
| Render service | `srv-dbee9h0n74is73eev8hg` (`sloth-ledger`) |
| Type | Web service, Python 3.12.6 |
| Plan | Free |
| Region | Singapore |
| Branch | `main`, auto-deploy on push |
| Build | `pip install -r requirements.txt` (only `pg8000`) |
| Start | `python app.py` |
| Health check | `/healthz` |
| Blueprint | `render.yaml` |

Render injects `PORT`; the app binds `HOST=0.0.0.0` from the blueprint and keeps
`127.0.0.1` as its local default, so `python app.py` on a laptop still works
exactly as it did before the deploy.

## Environment

| Variable | Source | Why |
|---|---|---|
| `HOST` | blueprint | `0.0.0.0` so Render can route to the process |
| `DEMO_MODE` | blueprint | shared ledger: per-visitor write limit and a demo label |
| `PYTHON_VERSION` | blueprint | `3.12.6` |
| `MODEL_BASE_URL` | blueprint | `https://api.groq.com/openai/v1` |
| `MODEL_NAME` | blueprint | `qwen/qwen3.8-27b` |
| `MODEL_API_KEY` | dashboard secret | Groq key; `sync: false`, never committed |
| `DATABASE_URL` | dashboard secret | Tiger Cloud connection string; `sync: false`, never committed |

`render.yaml` is the source of truth for everything that is not a secret. Both
secrets are prompted once at blueprint creation and stored encrypted by Render;
rotating one means changing it in the dashboard and redeploying.

## Verified

Checked after the deploy on 24 Oct 2026:

```text
GET /healthz
{"ok": true, "store": "postgres", "lanes": ["rules", "api:qwen/qwen3.8-27b"]}

GET /api/summary
chores 8 · runs 4 · week 15m · all time 43m · demo true
```

A live write (`POST /api/log`) was judged by `compatible:qwen/qwen3.8-27b`, not
by the rules floor, and the test row was deleted afterwards. The page labels
itself `public demo · shared ledger`.

## Free plan, honestly

- The service sleeps after fifteen minutes without traffic; the first request
  after a sleep takes a few seconds. The ledger does not sleep: the minutes live
  in Tiger Cloud, so a restart costs a cold start and nothing else.
- Visitors share one ledger. `DEMO_MODE=1` caps writes at eight per visitor per
  ten minutes, and the header says so.
- Render's disk is ephemeral. Nothing durable is written there.

## Redeploy and logs

Push to `main` (auto-deploy is on), or use **Manual Deploy** in the dashboard.
Saving an environment variable triggers a redeploy automatically.

When the model lane falls back, the process writes one line to stderr:

```text
[lane] _ask_compatible HTTP 403: ...
[lane] _ask_compatible unavailable: URLError: ...
```

That line names the failure without printing the key. It exists because the first
request after the first deploy silently used the rules floor; the cause was never
proven, so the fallback is logged rather than trusted.

## Why Render and Tiger are separate

Render runs a disposable web process. Tiger Cloud holds the hypertable, the
continuous aggregate, and the compression policy. That split is the reason the
free plan is acceptable here: losing the instance loses nothing, and the ledger
still answers with the same totals when the service wakes up.
