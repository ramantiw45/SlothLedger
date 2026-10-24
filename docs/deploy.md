# Deploying Sloth Ledger on Render

Two steps, about ten minutes, no card anywhere:

1. create the Render blueprint from this repo;
2. paste two secrets when it asks.

The result is a public URL that runs the whole flow: log a chore, get a verdict
from the open-weight lane, run the automation, watch the total restamp against
the Tiger Cloud ledger.

Nothing here is required for local use. `python app.py` still runs with no key
and a SQLite file.

---

## 1. Blueprint

1. Open <https://dashboard.render.com/blueprints> and click **New Blueprint Instance**.
2. Connect GitHub if it is not connected yet, and pick `ramantiw45/SlothLedger`.
   The repo already contains `render.yaml`, so Render reads the service name,
   the start command, the health check, and the free plan from it.
3. Render prompts for the two `sync: false` values:

   | Variable | Where to get it |
   |---|---|
   | `MODEL_API_KEY` | Groq console → API Keys. The lane calls `qwen/qwen3.8-27b`. |
   | `DATABASE_URL` | Tiger Cloud → the `sloth-ledger` service → connection string for the `sloth_app` role. Keep `?sslmode=require`. |

   `DATABASE_URL` is the value already in your local `.env`; it is not committed
   and it is not printed by the app.

4. Click **Apply**. The first build takes a couple of minutes.

## 2. Verify

```bash
curl https://sloth-ledger.onrender.com/healthz
# {"ok": true, "store": "postgres", "lanes": ["rules", "api:qwen/qwen3.8-27b"]}
```

Then open the URL, log one chore, and confirm the new card appears with an
evidence line. If `store` says `sqlite`, the database secret did not reach the
service; fix it under **Environment** and redeploy.

## What the free plan means

- The service sleeps after fifteen minutes of inactivity. The first request
  after a sleep takes a few seconds; the ledger data does not disappear,
  because it lives in Tiger Cloud, not on Render's disk.
- Writes are rate-limited per visitor (`DEMO_MODE=1`, eight writes per ten
  minutes) because every visitor shares one ledger.
- The page labels itself `public demo · shared ledger` so nobody mistakes the
  seeded entries for their own.

## Local check before deploying

```bash
python tools/smoke_http.py --base http://127.0.0.1:8787
```

Fifteen checks, no framework. If those pass locally against the Tiger lane, the
only thing the deploy adds is the host binding and the proxy.
