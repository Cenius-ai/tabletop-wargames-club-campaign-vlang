# Install and run

## Prerequisites

- **Python 3.11** (the app is tested on 3.11; no other system packages needed)
- `pip` available as `python3 -m pip`
- No database server, message broker, cache or external service is required —
  SQLite ships with Python
- No environment variables are required; every setting has a working default

## One-command setup

```bash
bash install.sh
```

It upgrades pip/setuptools/wheel, installs `requirements.txt`, creates the SQLite
schema, seeds the demo club, verifies the app imports, and then **exits** (it
never starts the server).

## Manual steps (same thing, one at a time)

1. **Install dependencies**

   ```bash
   python3 -m pip install --upgrade pip setuptools wheel
   python3 -m pip install -r requirements.txt
   ```

2. **Create the schema and seed the demo data** (its own step; safe to re-run —
   it skips itself when the club already has accounts)

   ```bash
   python3 -m app.seed
   ```

   Expected output: `seeded demo data` on the first run, then
   `demo data already present — nothing to do`.

3. **Start the server** (foreground)

   ```bash
   python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
   ```

4. **Open the app** at <http://localhost:8000>, sign in as
   `cenius@cenius.ai` / `cenius`, and you are on the organiser dashboard.

> The app also creates and seeds `campaign.db` itself on the normal boot path, so
> step 2 is optional if you start the server on a fresh checkout.

## Configuration

`cp .env.example .env` is optional — the defaults are already correct.

| Variable | Default | Notes |
| --- | --- | --- |
| `PORT` | `8000` | Uvicorn bind port; the server always binds `0.0.0.0` |
| `CAMPAIGN_DB` | `campaign.db` | SQLite file; relative paths resolve against the project root |
| `COOKIE_SECURE` | `0` | `1` behind HTTPS only — leaving it `1` on plain http drops the session cookie |

There are no secrets to provision.

## Tests

```bash
python3 -m pytest
```

The suite uses a temporary SQLite file per test (no network, no fixtures to
install). For a live walkthrough against a running server:

```bash
python3 scripts/smoke_test.py http://127.0.0.1:8000
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'starlette'` | Dependencies are not installed — run step 1. |
| `Address already in use` | Another server holds the port; stop it or start with `PORT=8001 python3 -m uvicorn app.main:app --port 8001`. |
| Login form reloads with no message | Cookies are blocked; the session cookie is `HttpOnly; SameSite=Lax` and needs cookies enabled. |
| `Secure` cookie not stored | You set `COOKIE_SECURE=1` while serving plain http — set it back to `0`. |
| Pages render with no data | The database was deleted while the server ran; restart the server and the seed runs again. |

## Reset the demo data

```bash
rm -f campaign.db campaign.db-wal campaign.db-shm
python3 -m app.seed
```
