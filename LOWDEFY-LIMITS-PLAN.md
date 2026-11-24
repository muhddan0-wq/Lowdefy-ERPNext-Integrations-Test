# Lowdefy: max potential, hard limits, and a stress-test plan

> **Superseded by [LOWDEFY-EVALUATION.md](LOWDEFY-EVALUATION.md).** Two corrections from Lowdefy's own docs:
> - **L2:** only AxiosHttp and MongoDB are *installed* here. Lowdefy officially ships Knex (PostgreSQL, MySQL/MariaDB, MSSQL, SQLite), Redis, Elasticsearch, S3, SMTP and other connections.
> - **L4:** API endpoints can be scheduled, but only on Vercel deployments.

Scope: ERP Copilot (Lowdefy 7.1.0) against the ERPNext v16 sandbox, as API user `copilot-api@copilot.local`.
Written 2026-11-23. Nothing in this plan has been run yet. Every test that writes to ERPNext or changes code needs approval first.

---

## 0. The honest starting point (why the boss isn't convinced yet)

Evidence from the repo:

- The 9 pages are ~5,900 lines of YAML, but the real logic (aggregation, rules, writes, audit, 3D, scanner) is in **one 3,066-line Node file**, `server/copilot-api.mjs`.
- 28 of the requests go through the `copilot` helper connection. Only 3 call ERPNext directly: `orders.yaml` (Sales Order, Work Order) and `settings.yaml` (Error Log).
- Block usage is basic: Box ×102, Card ×77, Statistic ×53, Table ×26, EChart ×4. The app uses 4 action types (`SetState`, `Request`, `CallMethod`, `Link`) and about 20 operators.

**So today the demo shows "Lowdefy as a thin screen layer over a custom Node backend".** It doesn't yet show what Lowdefy can do by itself. The installed 7.1.0 build (`.lowdefy/dev/build/plugins/availableTypes.json`) includes features this app never touches:

| Available in this install, unused by the app | Why it matters |
|---|---|
| `CallAPI` action + API endpoints (`auth.api.roles` in `build/auth.json`) | Server-side routines in YAML. Could replace parts of the Node helper |
| `mcp.json` (MCP endpoints, `configured: false`) | Lowdefy can expose its API endpoints as MCP tools for AI agents |
| `AgentChat`, `AgentConversations`, `IntentInput` blocks | Built-in AI chat UI |
| Websockets: `Channel`, `Interval`, `MongoDBChangeStream`; actions `Publish` / `Subscribe` | Live updates and multi-user push. An `Interval` "tick" is declared in `lowdefy.yaml` but nothing subscribes to it |
| `AgGrid*` (8 variants), `TableInput`, `AgGridInput*`, `ControlledList` | Editable grids: the natural fit for ERPNext child tables |
| `TiptapInput`, `TiptapMentionInput`, `Calendar`, `Steps`, `Tour`, `Splitter`, `Masonry`, `Watermark` | Rich forms, schedulers, guided training tours |
| `PollingTimer` block, `Fetch`, `SetLocalStorage` / `GetLocalStorage`, `GeolocationCurrentPosition` | Auto-refresh, client caching, offline drafts, shop-floor location |
| Auth: `GenericOAuth` + 35 providers, strategies `apiKey` / `jwt`, adapter `MongoDBAuthAdapter` only | Login through **ERPNext itself as the OAuth server** (Frappe supports OAuth 2) |
| `MongoDB*` requests (19 types incl. `MongoDBChangeStream`, `VersionedUpdateOne`) | Real app database: auth, audit log, drafts |
| Operators: `dayjs`, `nunjucks`, `mql`, `diff`, `cron`, `uuid`, `yaml`, `change-case`, `js` (66 client / 59 server) | Templating (print formats), diffs (audit "before/after"), date maths in YAML |
| `@lowdefy/e2e-utils` (Playwright 1.59.1) | Automated UI tests, which the repo currently lacks |

The strongest story for the boss is **"how far can we go with Lowdefy alone, and where exactly does it run out"**, with evidence for both halves.

---

## 1. What Lowdefy can't do (hard limits)

Status key:
- **Confirmed**: seen in this repo or its built Lowdefy config.
- **Likely**: from how Lowdefy works; needs one experiment to prove.
- **To verify**: check Lowdefy docs or a probe before telling the boss.

### Platform and architecture

| # | Limit | Status | Evidence / where it bites | Workaround |
|---|---|---|---|---|
| L1 | **Login needs MongoDB.** The only auth adapter in 7.1.0 is `MongoDBAuthAdapter`. There's no SQL/MariaDB adapter, so you can't reuse ERPNext's database | Confirmed (`availableTypes.json → auth.adapters`) | README "Authentication (deferred)" | Run a Mongo container; or test whether the `jwt` strategy works without an adapter (experiment E5) |
| L2 | **Only two connection types installed: `AxiosHttp` and `MongoDBCollection`.** There's no native Frappe/ERPNext, MariaDB/SQL or file connection | Confirmed for this install. To verify whether a SQL connection exists for v7 on npm | Every ERPNext call is hand-built REST | Use AxiosHttp to `/api/resource` + `/api/method`, or write a custom connection plugin |
| L3 | **No general-purpose backend code.** Logic is YAML operators, `_js` / `_function` snippets, or API routines. There's nowhere to write 300 lines of joining and rules | Confirmed by design: that's why the Node helper exists | Exceptions (10+ queries plus rules) and Purchasing formula live in the helper | API routines for medium logic (to measure in S7). Keep a sidecar service for heavy logic |
| L4 | **No background jobs or scheduler.** Lowdefy only runs when a page or API is called. `operators-cron` parses cron expressions; it doesn't schedule anything | Likely | Exception detection only runs when someone clicks "Run detection scan" | Node-RED, ERPNext Scheduler, or the helper run on a timer and call a Lowdefy API endpoint |
| L5 | **No raw browser/device access** beyond the built-in actions. There's no camera/barcode block and no WebGL/3D block | Confirmed | Scanner and 3D floor are both pages served by the helper and embedded with iframe or new tab | iframe via `DangerousHtml` (needs `ADD_TAGS: [iframe]`), or a custom block plugin (S6) |
| L6 | **Browser state never reaches the server automatically.** `properties` run on the server; browser values must be sent through `payload` | Confirmed (docs/02 §4) | The most common source of bugs here | Discipline: every request has an explicit `payload` |
| L7 | **Only one chart library (ECharts).** There's no pivot table, and no BI-style drag-and-drop or ad-hoc querying | Confirmed for this install | Reports page is fixed charts | ECharts covers almost every chart type. Metabase (already on :3005) for ad-hoc BI, embedded by iframe |
| L8 | **Not a document editor for ERPNext.** There's no automatic form generated from a doctype's metadata. Every field and child table must be declared in YAML | Likely | A Sales Order form = hand-mapping ~30 fields + items table | Generate the YAML from `/api/method/frappe.desk.form.load.getdoctype` (S2 measures the cost) |
| L9 | **Offline mode isn't built in.** There's no service worker or sync queue | To verify | Shop-floor Wi-Fi drops | `SetLocalStorage` drafts + manual resubmit (S8) |
| L10 | **Config is YAML.** There's no type-checking of field names against ERPNext. A typo in `_request: x.data.rows` fails silently as empty data | Likely | Hard-to-see bugs | Playwright e2e checks (S9) |
| L11 | **Dev server port quirk:** `lowdefy dev --port 3010` serves the app on 3011 | Confirmed (`start.ps1`, `launch.json`) | Docs and slides that say 3010 are wrong | Document 3011 |
| L12 | **YAML gotchas:** an unquoted ` #` truncates CSS colours, and `class:` hits the wrapper unless you use `.element` | Confirmed (docs/02 §8) | Styling time sink | Already documented |

### Security / roles (current app, not Lowdefy itself)

| # | Limit | Status | Evidence |
|---|---|---|---|
| R1 | **The "role" is chosen in the browser and trusted by the helper.** The Settings page has an "Acting role" selector, and `roleAllowed(body.role, …)` checks what the client sent. Anyone can claim `administrator` | Confirmed (`server/copilot-api.mjs:753`, `pages/settings.yaml:207`) | Fixing it needs real auth (L1) |
| R2 | **Audit `actor` is client-supplied** (`body.actor`), and is a fixed name today | Confirmed (`copilot-api.mjs:760,1527,2069`) | Same fix |
| R3 | **Every user gets the API user's ERPNext permissions.** ERPNext sees only `copilot-api@copilot.local`, so ERPNext's per-user permissions and row-level rules are bypassed | Confirmed by architecture | OAuth with the user's own ERPNext token (S5) |

### Data volume (helper limits that look like Lowdefy limits)

| # | Limit | Status | Evidence |
|---|---|---|---|
| D1 | **Silent truncation.** Helper `getList` caps are hard-coded (`limit: 200 / 500 / 2000 / 5000`), and Orders requests ERPNext with `limit_page_length: 200`. Above those counts, rows just disappear and KPIs are wrong, with no warning | Confirmed in code (e.g. `copilot-api.mjs:1709` Bin limit 5000; `orders.yaml` 200) | S1 proves it |
| D2 | **Client-side tables.** Lowdefy `Table` pages data already loaded in the browser. There's no server-side paging in the current pages | Confirmed (`pagination: true, pageSize: 25` on full arrays) | S1 measures where the browser slows down |

---

## 2. Max potential (what Lowdefy can plausibly do that the app doesn't show yet)

Each item is a claim to **prove with a prototype page**, not to assert:

1. **ERPNext login for every user** (GenericOAuth against Frappe's OAuth 2 server). Real roles, a real audit actor, ERPNext permissions respected. Fixes R1–R3.
2. **ERPNext forms with child tables in YAML** (`TableInput` / `AgGridInput` for Sales Order items, BOM items, Stock Entry details), with validation, and draft save only.
3. **Logic moved from the Node helper into Lowdefy API routines** (`CallAPI`). Shows how much of the 3,066 lines YAML can absorb.
4. **Live multi-user screens:** `Channel` websocket + `Publish` when someone resolves an exception or posts a transfer; other screens update without refresh.
5. **AI assistant inside the app:** `AgentChat` + MCP endpoints, so "what's at risk this week?" calls the same Exceptions/Purchasing endpoints, read-only.
6. **Shop-floor kiosk mode:** large buttons, scanner, offline drafts in localStorage, `Tour` blocks for trainees.
7. **Automated test suite** with `@lowdefy/e2e-utils` (Playwright). It runs every page and catches empty-data bugs (L10).

---

## 3. Stress-test plan (prioritised, quick wins first)

Legend:
- **R** = read-only.
- **W** = writes to ERPNext (needs approval).
- **C** = changes app code (needs approval; work on a branch).
- Effort: S < 2 h, M ≈ half a day, L ≥ 1 day.

Pre-req for all: the sandbox is up (`docker compose … up -d` in `F:\ERPNEXT\erpnextcomp_demo`), and `.\start.ps1` is running. **Docker was not running when this plan was written.** Also confirm the ERPNext port: `.env` says `localhost:8000`, the team notes say 8080.

### Tier 1: quick wins (read-only, results in hours)

**S1. Large lists and silent truncation** (R, S)
- *Run:* Count rows directly in ERPNext (`/api/method/frappe.client.get_count?doctype=Bin`, `Sales Order`, `Stock Ledger Entry`) and compare with the row counts each page shows (Inventory, Movements, Orders). In the browser pane, time each page load and record table render time with DevTools Performance. Repeat with 1k / 5k / 20k rows later (data comes from S1b, which writes, so it needs approval).
- *Finding if:* page count < ERPNext count (D1 truncation, a bug); or the browser freezes above N rows (D2 limit). Workaround to test: AG Grid or server-side paging via `limit_start`.
- *Evidence:* a table of doctype / ERPNext count / page count / load ms; a screenshot of the mismatch; the line numbers of the hard-coded limits.

**S2. Auth and role-boundary probe on the current app** (R + one denied write, S)
- *Run:* (a) Set the Settings "Acting role" to viewer and try Save: expect 403. (b) Send the same request with `role: administrator` in the body via `curl` to the helper. The helper requires `x-copilot-key`, so test both with and without the key. (c) Read the audit log rows produced.
- *Finding if:* the role can be self-declared (R1); the actor is spoofable (R2); `copilot-api` can read doctypes a viewer shouldn't.
- *Evidence:* the curl commands and HTTP codes, the audit rows, and a "who can do what" matrix.
- Note: (b) only sends a settings PUT to SQLite, not to ERPNext, but it still changes app state. Approval needed.

**S3. Error and degraded-mode matrix** (R, S)
- *Run:* For each page, record behaviour with (1) ERPNext stopped, (2) a wrong token, (3) the helper stopped, (4) slow ERPNext (add 10 s latency with a toxiproxy or `tc` container, or simply pause the backend container), (5) the browser offline (DevTools → Offline).
- *Finding if:* stack traces, blank pages, stale data shown as fresh, or spinners that never end. Lowdefy's own request error UI versus the helper's friendly messages.
- *Evidence:* a 9 pages × 5 conditions grid with a screenshot per failure.

**S4. Build and deploy time** (R, S)
- *Run:* `npx lowdefy@7.1.0 build`, timed 3×, cold and warm. Measure: dev-server hot-reload time after editing one page; bundle size of `.lowdefy/server` output; `lowdefy start` (production) memory. Then synthesise 50 and 200 copies of `inventory.yaml` in a scratch copy of the repo and rebuild.
- *Finding if:* build time grows super-linearly with page count, or reload gets above ~5 s (developer-experience limit).
- *Evidence:* a chart of pages vs build seconds; the RAM figure.

### Tier 2: high-value prototypes (code changes on a branch)

**S5. ERPNext OAuth login + real roles** (C, M–L). The single biggest finding either way.
- *Run:* Register an OAuth Client in ERPNext (Desk → OAuth Client; a sandbox config write). Start `mongo` in Docker. Configure `auth` with `GenericOAuth` (issuer = ERPNext, `/api/method/frappe.integrations.oauth2.*`). Map ERPNext roles to Lowdefy roles, and protect pages and API endpoints. Separately, try the `jwt` strategy without Mongo.
- *Finding if:* it works (fixes R1–R3, a headline); Mongo is unavoidable (confirms L1); or the user's token can't be forwarded to ERPNext (only page-level roles possible).
- *Evidence:* the login screen recording, a viewer vs manager screenshot, ERPNext's own permission error when a viewer tries a write.

**S6. Heavy form with child tables** (C + W drafts only, M)
- *Run:* A new page "New Sales Order (draft)": header fields plus an items child table using `TableInput`, then `AgGridInput` as a comparison. Item code autocomplete from `/api/resource/Item`, rate lookup, live totals via operators, `Validate` action, POST as **draft** (`docstatus: 0`). Then scale to 100 / 500 lines.
- *Finding if:* the editable grid lags above N rows; validation can't express ERPNext rules (e.g. UOM conversion); ERPNext rejects it and the error isn't surfaced clearly.
- *Evidence:* YAML line count versus fields mapped (cost per doctype, for L8); typing lag in ms at 100 / 500 rows; a draft link in Desk (deleted afterwards with approval).

**S7. Logic migration: helper → Lowdefy API routines** (C, M)
- *Run:* Re-implement two helper endpoints as Lowdefy API endpoints: `/overview` (simple) and `/purchasing` (formula). Compare output JSON byte-for-byte, response time, and lines of code.
- *Finding if:* YAML can express it (shrinks the helper), or it becomes unreadable or slow. That gives the boss a measured line for where Lowdefy stops.
- *Evidence:* side-by-side LOC, a diff of outputs, latency of p50/p95 over 50 calls.

**S8. Concurrency** (W, M)
- *Run:* (a) Read: 20 / 50 / 100 parallel page-request loads with `autocannon` or k6 against the Lowdefy `/api/request/...` routes, which hit the helper and then ERPNext. (b) Write race: two browser tabs create a stock transfer for the same item and qty at once; two users resolve the same exception at once. (c) Live: add a `Channel` websocket so tab B sees tab A's change.
- *Finding if:* the helper cache causes stale reads; ERPNext `TimestampMismatchError` isn't handled; the exception is "resolved twice" in the audit; or the Lowdefy server's throughput ceiling.
- *Evidence:* k6 summary (rps, p95, errors), audit rows of the race, a GIF of live push.

### Tier 3: frontier features (shows max potential)

**S9. Playwright e2e suite** (C, M): a smoke test per page using `@lowdefy/e2e-utils`. *Finding:* catches L10-type silent empty tables. *Evidence:* the HTML test report.

**S10. Charts and dashboard stress** (C, S–M): an ECharts page with 10 charts × 10k points, plus a 20-tile live dashboard on `Interval` / `PollingTimer`. *Finding:* the FPS and memory ceiling, ERPNext load from polling. *Evidence:* DevTools perf trace, helper request log per minute.

**S11. Custom block plugin** (C, L): wrap the scanner (jsQR) or the three.js floor as a real Lowdefy block instead of an iframe. *Finding:* how hard the plugin API is (hours spent, build issues); whether events like `onScan` flow into state. *Evidence:* plugin source LOC, a working page.

**S12. AI assistant (AgentChat + MCP)** (C, L): expose read-only API endpoints (exceptions, purchasing, stock) as MCP tools, and add `AgentChat`. *Finding:* whether the agent framework works with a non-Mongo setup, and how it handles permissions. *Evidence:* a recorded Q&A answering from live data.

**S13. Offline drafts** (C, M): the Stock transfer form saves to localStorage while offline and replays on reconnect. *Finding:* confirms L9 and what the workaround costs. *Evidence:* a GIF offline → online.

---

## 4. New use cases for a manufacturing / ERPNext training audience

Each one exercises a limit above:

| Use case | Lowdefy features | Tests |
|---|---|---|
| **Shop-floor Job Card kiosk:** scan a job card, Start / Pause / Complete, log time and scrap | Scanner, big Buttons, `Steps`, localStorage | S6, S13 |
| **Material Request from the floor:** an operator scans an item, enters qty, creates a draft Material Request | Form + child table | S6 |
| **Quality Inspection checklist** linked to Purchase Receipt (pass/fail per parameter) | `TableInput`, `Validate` | S6 |
| **Production planning board:** Work Orders on a `Calendar` / drag lanes by workstation | Calendar, AG Grid | S1, S10 |
| **Live Andon board:** workstation status, downtime, OEE tiles on a TV, pushed via websocket | `Channel` / `Interval`, EChart | S8, S10 |
| **BOM explorer and cost roll-up** (tree of sub-assemblies) | `TreeSelector`, nested requests | S1 |
| **Trainee mode:** guided `Tour` over each ERPNext flow (PO → PR → Invoice), with a checkpoint verifying the doc status via REST | `Tour`, `Steps`, REST verify | ties to the training deck gaps (DECK-AUDIT §3 "Expected outcome checkpoints") |
| **Role-play sandbox:** each trainee logs in as Buyer / Storekeeper / Planner and sees only their actions | OAuth + roles | S5 |
| **Ask-the-ERP assistant:** "which orders are at risk?" over the read-only APIs | AgentChat, MCP | S12 |
| **Printable labels and print formats** (QR labels, pick lists) from nunjucks templates | `_nunjucks`, QRCode | S4 |

---

## 5. Evidence pack for the boss (one folder per test)

For every test, capture:

1. The command or steps exactly as run.
2. The raw output (k6 JSON, curl, timings).
3. A screenshot or GIF.
4. A one-line verdict: **Limit / Bug / Workaround / Works**.
5. The Lowdefy version, the ERPNext version and the row counts.

Keep the evidence under `evidence/<test-id>/` (gitignored if it contains tokens).

Summary table to fill in:

| Test | Verdict | Number that matters | Evidence link |
|---|---|---|---|
| S1 | | rows shown vs rows in ERPNext | |
| … | | | |

---

## 6. Run these first (top 5)

1. **S1: silent truncation and the large-list ceiling** (read-only; likely an immediate, concrete bug finding from D1).
2. **S3: error / degraded-mode matrix** (read-only; produces 45 screenshots of real behaviour).
3. **S4: build and deploy time** (read-only; clean numbers, done in a scratch copy).
4. **S2: role-spoof probe** (one SQLite settings write; proves R1/R2 and motivates S5).
5. **S5: ERPNext OAuth login** (code plus an ERPNext OAuth Client; the headline "max potential" result, which either removes the Mongo blocker or proves it).

S1, S3 and S4 need only the sandbox running. S2 and S5 need approval: S2 writes app settings, S5 changes code and ERPNext config.
