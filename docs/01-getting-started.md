# 1. Getting started

This guide takes you from a fresh clone to the app running in your browser.

## What you are running

There are three programs. You start two of them; ERPNext is already running somewhere.

| Program | Port | What it is |
|---|---|---|
| **ERPNext** | 8000 (or 8080) | The ERP system. It holds the real data: items, stock, orders, job cards. |
| **Copilot helper** (`server/copilot-api.mjs`) | 4010 | A small Node.js server. It talks to ERPNext, does the maths, stores the audit log, and serves the scanner and 3D floor pages. |
| **Lowdefy app** | 3011 (dev: whatever Lowdefy prints) | The web UI. Pages are written in YAML, not React code. |

The browser only talks to Lowdefy. Lowdefy talks to the helper. The helper talks to ERPNext. The ERPNext API key never reaches the browser.

## Prerequisites

- **Node.js 22.13 or newer** (this machine uses Node 24). The helper uses Node's built-in SQLite module (`node:sqlite`), which older Node versions don't have or hide behind a flag.
- **A running ERPNext** (v15 or v16) that you can reach from this machine.
- **An ERPNext API key and secret** for a user that can read stock, buying, selling and manufacturing documents. Use a dedicated user (this project uses `copilot-api@copilot.local`), **not Administrator**. If other tools regenerate Administrator's keys, the app breaks with 401 errors.
- **PowerShell** for the start scripts (Windows). On macOS/Linux, run the same commands by hand.
- Optional: **Python 3** for the demo-data scripts in `scripts/`.

## Step 1: get an API key from ERPNext

1. In ERPNext, open the user you want the app to use (User list → `copilot-api@copilot.local`).
2. Under **Settings → API Access**, click **Generate Keys**. Copy the API key and the secret (the secret is shown only once).
3. Give that user the roles it needs: Stock User/Manager, Purchase User, Sales User, Accounts User, Manufacturing User, Item Manager. This project also adds a custom role, "Copilot Integration", that can read **Error Log**.

## Step 2: create `.env`

```powershell
copy .env.example .env
```

Fill in `.env`:

| Variable | Example | Meaning |
|---|---|---|
| `ERPNEXT_URL` | `http://localhost:8000` | ERPNext base URL, no trailing slash |
| `ERPNEXT_SITE` | `frontend` | Frappe site name |
| `ERPNEXT_AUTH_HEADER` | `token abc123:def456` | `token <api_key>:<api_secret>`; the helper sends it |
| `COPILOT_DB_PATH` | `C:/…/erpnext-copilot/data/copilot.sqlite` | Where the SQLite file goes (absolute path) |
| `COPILOT_API_URL` / `COPILOT_API_PORT` | `http://127.0.0.1:4010` / `4010` | Where the helper listens |
| `COPILOT_APP_URL` | `http://localhost:3011` | The Lowdefy app's URL (the scanner sends codes back here) |
| `LOWDEFY_SECRET_COPILOT_API_URL` | `http://127.0.0.1:4010` | The same helper URL, exposed to Lowdefy as a secret |
| `LOWDEFY_SECRET_ERP_TOKEN` | `abc123:def456` | `key:secret` used by the Orders/Monitoring pages that call ERPNext directly from the Lowdefy server |
| `LOWDEFY_SECRET_SHOPIFY_*` | | Only for the Shopify status card; leave as is if unused |

`setup-env.ps1` can write `.env` for you from another project's `.env`. Its default source path (`F:\ERPNEXT\erpnextcomp_demo\.env`) is specific to the original machine, so pass `-SourceEnv <path>` or just edit `.env` by hand. Running it with `-Force` overwrites your token, so be careful.

**Never commit `.env`.** `.gitignore` already excludes it.

## Step 3: install and start

```powershell
pnpm install          # or: npm install
.\start.ps1
```

`start.ps1` does three things:

1. `node scripts\init-db.mjs` creates `data/copilot.sqlite` with the `audit_log` and `settings` tables and default settings.
2. It starts the helper (`node server\copilot-api.mjs`) in the background and waits for `http://127.0.0.1:4010/health` to say `ok`. Logs go to `data\api.log` and `data\api.err.log`.
3. It runs `npx lowdefy@7.1.0 dev --port 3010`. Lowdefy builds the YAML and serves the app. **Read the terminal for the real URL.** It can be 3011, 3110, 3111 and so on. On this machine it ran on `http://127.0.0.1:3111`.

## Step 4: check it works

- `http://127.0.0.1:4010/health` should return JSON with `"ok": true` and the ERPNext version.
- Open the Lowdefy URL. The Dashboard should show live numbers, not errors.
- `http://127.0.0.1:4010/floor` opens the 3D floor on its own (the **3D Floor** page shows the same thing in an iframe).

## Optional: demo data

`scripts/seed_demo_company.py`, `scripts/top_up_recent_sales.py` and `scripts/settle_demo_invoices.py` create a demo company, recent sales and paid invoices, so the Exceptions, Purchasing and Reports pages have something to show. Read each script's header before running it: they write to ERPNext.

## Restarting after code changes

| You changed | What to do |
|---|---|
| A page or `lowdefy.yaml` | Nothing. Lowdefy dev reloads automatically. |
| `server/copilot-api.mjs` or `server/vendor/*.html` | Restart the helper. It reads the HTML files once at startup. |
| `.env` | Restart both. |

Restart the helper from PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 4010 -State Listen | % { Stop-Process -Id $_.OwningProcess -Force }
Start-Process node -ArgumentList 'server\copilot-api.mjs' -WindowStyle Hidden -RedirectStandardOutput data\api.log -RedirectStandardError data\api.err.log
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Every card says "Cannot reach ERPNext" | ERPNext is down or `ERPNEXT_URL` is wrong |
| 401 / AuthenticationError | API key regenerated. Generate new keys for the API user and update `.env` |
| 403 / "Insufficient Permission for X" | The API user is missing a role for doctype X |
| Page loads, data never arrives | The helper is not running. Check `data\api.err.log` |
| 3D floor says "Showing sample data" | The helper could not reach ERPNext, or no stock is in the configured warehouses |
| Lowdefy says the port is in use | A dev server is already running. Check node processes before starting another |
