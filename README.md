# ERPNext Copilot

One merged Lowdefy application for ERPNext operations: live **inventory** and
**stock movements**, a **QR / barcode scanner**, a prioritised **Exceptions**
queue, a **Purchasing Assistant** (sales-velocity reorder suggestions grouped by
supplier, with one-click draft Purchase Order creation), plus the **monitoring**
pages (integration status, orders, production, errors, analytics) and an
**Audit Log**.

Built with **Lowdefy 7.1.0** (UI) and a small local **Node helper service**
(`server/copilot-api.mjs`) that owns SQLite and does all ERPNext aggregation and
writes server-side. It also serves the camera scanner page.

## Learning guides

New to this project or to Lowdefy? Read these in order:

1. [Getting started](docs/01-getting-started.md): install, configure `.env`, run, troubleshoot
2. [Lowdefy basics](docs/02-lowdefy-basics.md): blocks, state, requests, events, operators, styling, with examples from this app
3. [How it works](docs/03-how-it-works.md): architecture, the helper's functions, business rules, the 3D floor
4. [What was built](docs/04-what-was-built.md): session-by-session history, decisions and known limitations

## Architecture

```
Browser (Lowdefy UI, port 3011)
   ├─ AxiosHttp (server-side) ──► Copilot helper (port 4010)
   │                                ├─ SQLite: exceptions + audit_log + settings
   │                                ├─ Camera scanner page (/scanner + jsQR)
   │                                └─ ERPNext REST (server-side, token from .env)
   └─ link opens http://127.0.0.1:4010/scanner?app=<origin> in a new tab
```

- **No secrets reach the browser.** The ERPNext API token lives only in `.env`
  and is used by the helper service, never by the browser.
- **No CORS issues.** The browser talks only to Lowdefy's own server, which talks
  to the helper on `127.0.0.1`.
- **Every write is confirmed and audited.** Stock transfers, exception lifecycle
  changes, settings changes, PO creation, document submit/cancel and comments
  each write an audit-log row (who / what / when / docname / result) to SQLite.

## Pages

| Page | Purpose |
|------|---------|
| **Control Centre** | Integration health for ERPNext, Node-RED, ngrok, Shopify and the planner, with recent orders. |
| **Inventory** | Live stock by warehouse and item group, item detail drawer, reorder levels and stock value. |
| **QR / Barcode Scanner** | Camera scanner (BarcodeDetector with bundled jsQR fallback) plus manual code entry. Serial numbers resolve to a unit, item codes resolve to the item master, and QR labels can be printed. |
| **Stock Movements** | Every Stock Entry line including drafts, with transaction detail and a stock-transfer form. |
| **Exceptions** | Inventory and sales/finance findings with rule, evidence and a tracked investigate/assign/resolve lifecycle, plus submit-draft-order and log-reminder document actions. |
| **Purchasing** | Reorder suggestions from sales velocity, grouped by supplier. "Create draft PO" makes a draft Purchase Order (never auto-submitted). |
| **Reports** | Rolling-window stock, movement, purchasing and exception aggregates. |
| **Monitoring** | Integration Monitor, Orders, Production, Error Investigation and Analytics pages absorbed from the monitoring app. |
| **Audit Log** | Read-only view of every write, with actor, role, action, document, result and message. |
| **Settings** | Inventory detection thresholds, sales/purchasing defaults, role selector and helper health — stored in SQLite, not hardcoded. |

## Prerequisites

- Node.js ≥ 20 (uses the built-in `node:sqlite` module).
- A running ERPNext instance with an API key/secret for a user that can read and
  create the relevant doctypes.

## Setup

```powershell
.\setup-env.ps1   # reads ERPNEXT_API_TOKEN/SITE_NAME/ERPNEXT_PORT from F:\ERPNEXT\erpnextcomp_demo\.env, writes .env
.\start.ps1       # initialises SQLite, starts the helper on :4010, then Lowdefy on :3011
```

Then open http://localhost:3011. `start.ps1` pins `lowdefy@7.1.0`
(`--port 3010` is Lowdefy's internal docs/MCP port; the app itself is served one
port up at 3011). The camera scanner is served by the helper at
`http://127.0.0.1:4010/scanner`; the Scan page passes the app origin so a scanned
code returns to `/scan?code=...`. Browsers require a secure origin for camera
access — `http://localhost` and `http://127.0.0.1` qualify.

## Configuration

Settings live in SQLite (`data/copilot.sqlite`, table `settings`), seeded with
defaults by `scripts/init-db.mjs` and editable on the Settings page.

## Authentication (deferred)

Lowdefy 7 role-based auth requires BetterAuth with a database adapter, and the
only adapter currently available is MongoDB (`@lowdefy/connection-mongodb` →
`MongoDBAuthAdapter`). No MongoDB is running in this environment, so auth has been
**deferred**. The plan is to:

1. Run a MongoDB container (e.g. `docker run -p 27017:27017 mongo`).
2. Configure `auth` in `lowdefy.yaml` with two roles — `manager` (write) and
   `viewer` (read-only).
3. Hide/disable write buttons for `viewer` and pass the authenticated user as the
   audit `actor` (currently a fixed `copilot-user`).

## Verification

- `/exceptions` and `/purchasing` are aggregated by the helper; hand-check any
  three items against ERPNext Desk.
- Write path: a draft PO is created and can be reviewed (and deleted) in Desk.
- Degraded states: a missing/wrong token and an ERPNext-down situation return a
  friendly error rather than a stack trace.
