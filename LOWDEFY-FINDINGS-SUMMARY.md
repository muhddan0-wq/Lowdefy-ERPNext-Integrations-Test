# Lowdefy: summary of findings, best uses, and who uses it

Prepared for SHRDC. Based on:
- building and testing the ERP Copilot app (Lowdefy 7.1.0 + ERPNext v16);
- Lowdefy's official 7.1.0 documentation, bundled in this project;
- public web sources (listed at the end).

Full detail: [LOWDEFY-EVALUATION.md](LOWDEFY-EVALUATION.md).

---

## Part 1: Summary of all findings

### 1.1 What Lowdefy is

- An open-source framework (**Apache-2.0**, checked in the installed 7.1.0 packages) for building **internal business web apps from YAML configuration** instead of code.
- It's made by the Lowdefy team, who also run **Resonancy**, a consultancy that builds client apps on it.
- Version 7 compiles the YAML into a **Node.js (Hono) server plus a React (Vite) client**.
  - Older versions (v4–v6) were built on Next.js and Auth.js.
  - Many articles online describe those older versions.
- Apps are made from four building blocks:
  - **blocks:** screens; 114 ready components such as tables, forms, charts and cards;
  - **operators:** logic; about 70 functions such as `_if`, `_sum` and date maths;
  - **events and actions:** what happens on clicks and page loads;
  - **requests and connections:** data, always fetched on the server.

### 1.2 What it does well (and why)

| # | Finding | Why (the feature inside Lowdefy) |
|---|---|---|
| S1 | Very fast to build multi-page business screens | 114 prebuilt components configured in YAML; no front-end code or build setup to maintain |
| S2 | Secure data access by default | Every data request runs on the server, and keys stay in server-side `LOWDEFY_SECRET_*` variables. In this app, the ERPNext token never reached the browser |
| S3 | Connects to most business systems | Official connections: REST (AxiosHttp), PostgreSQL, MySQL/MariaDB, MSSQL, SQLite, MongoDB, Redis, Elasticsearch, Google Sheets, S3/Azure/GCS, Stripe, SMTP/SendGrid, OpenAI/Anthropic, MCP |
| S4 | Server-side workflows without writing a backend | API endpoints with routines: if/switch/loops, parallel steps, try/catch, input validation, webhooks, background jobs |
| S5 | Full login system | BetterAuth: email+password, magic link, one-time codes, passkeys, 2FA, ~35 OAuth providers (incl. generic OAuth); role-protected pages and APIs |
| S6 | Live updates with no extra server | Built-in websocket channels with publish/subscribe |
| S7 | AI features in config | AI agents (Claude, OpenAI, Google) with an `AgentChat` block; agents can call the app's own APIs as tools; MCP support |
| S8 | Testable | Official Playwright e2e toolkit with Lowdefy-aware helpers and request mocking |
| S9 | Low overhead | Measured: a 250 KB ERPNext request took **32 ms direct vs 44 ms through Lowdefy**, and every page request was 12–190 ms |
| S10 | Extensible | Custom blocks, connections, actions and operators can be written as npm plugins (JS/React) |

### 1.3 What it can't do, or does poorly (and why)

| # | Finding | Why |
|---|---|---|
| L1 | **Login needs MongoDB** | Auth must store sessions in a database, and the only adapter provided is for MongoDB. There's no MySQL/MariaDB adapter, so ERPNext's database can't be used |
| L2 | **No scheduled jobs when self-hosted** | Scheduled API endpoints only work on Vercel. On a local Node or Docker server, something else (Node-RED, ERPNext scheduler, OS cron) must trigger them |
| L3 | **Complex logic doesn't fit** | Logic must be YAML operators and routine steps. Real calculations (rules engines, forecasting, optimisation) need a separate service or a plugin. That's why ERP Copilot has a 3,066-line Node helper |
| L4 | **30-second request cap** | The server stops any request at 30 s by default (`config.requestTimeout`), even if a connection allows longer. **Proven in testing:** requests failed at exactly 30.0 s although the connection allowed 120 s |
| L5 | **Raw error messages on timeout** | **Proven:** the user saw `Unexpected token 'G', "Gateway Timeout" is not valid JSON` |
| L6 | **No offline mode** | No service worker or offline sync; every action needs the server |
| L7 | **No camera, 3D or graphics components** | The component library is business UI only. The scanner and 3D floor had to be separate pages in iframes |
| L8 | **No automatic forms from ERPNext** | Every field and child table must be written in YAML by hand. ERPNext's own validation only runs on save |
| L9 | **Not a BI tool** | Fixed ECharts dashboards only, no ad-hoc exploration (use Metabase) |
| L10 | **Error handling is left to the developer** | A failed action stops the rest of that event's actions, and errors appear as a generic "Something went wrong" |
| L11 | **YAML learning curve** | Browser state isn't visible to server requests (values must go through `payload`); hidden blocks lose their values; typos show up as empty data rather than errors |

### 1.4 Deployability

- **Deployable: yes.**
  - Official options: plain Node.js server, Docker (generated Dockerfile with health check, non-root user, Node 24), or Vercel (serverless).
  - Supports separate dev, staging and prod environments, with guards against pointing at the wrong database.
- **Recommended for SHRDC:** Docker, in the same docker-compose as ERPNext, Metabase and Node-RED.
- **Extra pieces production needs:**
  - MongoDB, if login is used;
  - an external scheduler, if timed jobs are needed;
  - a sensible `requestTimeout`.
- **ERP Copilot today is not production-ready:**
  - it runs only in dev mode;
  - it has no login: the acting role is chosen in the browser and trusted by the helper;
  - it depends on a second service, the Node helper.

### 1.5 Findings specific to the ERP Copilot app (from testing)

| # | Finding | Evidence |
|---|---|---|
| A1 | When data fails to load, KPIs show **0** and tables say "No inventory rows match these filters", which looks like real data | `evidence/S3/A-*.jpg`, `C-*.jpg` |
| A2 | When ERPNext hangs, the Inventory page shows "0 rows" with **no loading indicator** for 30 s | `evidence/S3/B-erpnext-hung-inventory-says-no-rows.jpg` |
| A3 | One failed request blocks the rest: on Orders, the Production and Purchasing data never loaded | browser request log |
| A4 | The helper's helpful message ("Cannot reach ERPNext at …") is replaced by a generic "Something went wrong" | curl vs screenshot |
| A5 | The Error Log shows **100 of 1,520** errors with no "showing latest 100" note | `evidence/S1/error-log-shows-100-of-1520.jpg` |
| A6 | Roles and audit "actor" are sent by the browser and trusted by the helper, so anyone can claim administrator | `server/copilot-api.mjs:753` |
| A7 | Most Lowdefy features are unused (API routines, login, websockets, AI agents, e2e tests); the logic lives in the Node helper | build plugin inventory |
| A8 | ERPNext returns only **20 rows** when a list request has no `limit_page_length`. The app always sets it, but it's a trap for new pages | API test |
| A9 | ERPNext runs on port **8000**, not 8080 | ping test |

---

## Part 2: Best uses for Lowdefy

### Rule of thumb

Use Lowdefy when the job is **"show the right data to the right person, let them take a controlled action, and record it."** Avoid it when the job is **"compute something hard", "work offline"** or **"build a public, custom-designed product."**

### Best uses (ranked by fit)

| Rank | Use | Why Lowdefy fits | Manufacturing / SHRDC example |
|---|---|---|---|
| 1 | **ERP companion portals** | Simple role-focused screens over a complex ERP, with server-side API access | ERP Copilot: exceptions inbox, reorder suggestions, stock lookup for staff who don't use ERPNext Desk |
| 2 | **Operational dashboards** | Tables, KPIs and charts, with live updates over websockets | Production status board, OEE/downtime tiles on a TV, integration health |
| 3 | **Approval and request workflows** | Forms + roles + audit + email | Purchase requests, maintenance requests, quality sign-off, leave approval |
| 4 | **Admin back-offices / CRUD apps** | Direct SQL/MongoDB connections, role protection | Master-data maintenance, supplier lists, asset registers |
| 5 | **Training and lab apps** | Guided `Steps` and `Tour` blocks; API checks of ERPNext document status | Trainee mode: "create a Purchase Receipt", then verify it was submitted |
| 6 | **Customer or supplier portals (logged-in)** | OAuth/email login, organisations, role-limited views | Supplier portal to view open POs and confirm delivery dates |
| 7 | **Internal AI assistants** | AI agents calling the app's APIs as tools, with role control | "Which orders are at risk this week?" over read-only endpoints |
| 8 | **Inventory and asset tracking** | Tables, forms, QR codes, scanner via an embedded page | Stock movements, serial-number lookup, label printing |
| 9 | **Integration consoles** | REST/webhook endpoints, plus monitoring screens | Node-RED / Shopify / ngrok health and error investigation |

### Poor fits

- Offline shop-floor terminals and handheld scanners without a network.
- Heavy calculation: MRP runs, scheduling optimisation, forecasting. Run these in ERPNext or a service and use Lowdefy to show the results.
- Bespoke interfaces: 3D, CAD, drag-and-drop planners, machine HMIs.
- Public, high-traffic or SEO websites and e-commerce storefronts.
- Rebuilding ERPNext Desk. ERPNext already generates its forms and workflows.

---

## Part 3: Existing applications that use Lowdefy

**Honest finding:** there's **no public list of named production deployments or customer case studies**. Lowdefy is mostly used for *internal* tools, which companies rarely publicise. What can be found:

| Source | What it shows | Confidence |
|---|---|---|
| **Lowdefy team / Resonancy (makers)** | Their own client work: CRMs, MRP tools, call-centre systems, reporting dashboards, ticketing, workflow, SOP and QC tools, customer portals, survey apps. They claim **50+ internal tools deployed** | Self-reported by the vendor |
| **Food-processing factory (unnamed)** | A co-founder said on Hacker News (2021) that they were rolling out a full **MRP system** built with Lowdefy for a food-processing factory | Self-reported, client unnamed. This is the closest public example to SHRDC's manufacturing use |
| **Resonancy client logos** | The Resonancy site shows partner logos (BWE, RTT, AVIS, MRM) with no project details | Logos only; what was built isn't stated |
| **Official example apps** (GitHub `lowdefy` org) | Case-management app, customer survey app, CRUD example | Demos, not production apps |
| **lowdefy.com** | Lists target uses: internal tools, customer portals, inventory and asset management, AI apps | Marketing |
| **This project: ERP Copilot** | A working Lowdefy 7 app on ERPNext v16: inventory, scanner, 3D floor, exceptions, purchasing, reports | First-hand, tested |

**What this means for the boss:**
- Lowdefy is a real, maintained framework: v7.1.0, Apache-2.0, about 2.8k GitHub stars per an aggregator snapshot.
- Its proven track record is mainly through its own consultancy's client work.
- That's typical for internal-tool frameworks, but it means **less community support and fewer public references** than Retool, Appsmith or Budibase.
- A fair recommendation: a good choice for SHRDC's internal and training tools, provided SHRDC is comfortable relying on a smaller ecosystem and its own in-house knowledge.

---

## Sources

Lowdefy documentation (bundled, v7.1.0), under `.lowdefy/dev/node_modules/@lowdefy/docs-content/content/`:
- `learn/introduction.md`
- `concepts/lowdefy-api.md`
- `user-authentication/auth-configuration.md`
- `adapter-reference/mongodbauthadapter.md`
- `websockets/websockets-introduction.md`
- `agents/agents-introduction.md`
- `deployment/docker.md`, `node-server.md`, `vercel.md`, `deployment-environments.md`
- `plugins/plugins-introduction.md`
- `testing/e2e-introduction.md`
- `connections/`
- `hazards.json`

Lowdefy server source: `.lowdefy/dev/src/middleware/requestTimeout.js`.

Web:
- [Lowdefy website](https://lowdefy.com/)
- [Lowdefy on GitHub](https://github.com/lowdefy/lowdefy)
- [Lowdefy about page (Resonancy)](https://backiee.wasmer.app/https_lowdefy_com/about)
- [Resonancy](https://apis.emri.workers.dev/https-resonancy.io)
- [OfferZen: Lowdefy company profile](https://www.offerzen.com/companies/lowdefy)
- [Hacker News: Show HN: Lowdefy](https://news.ycombinator.com/item?id=26267891)
- [Hacker News: co-founder comment on client apps (MRP for a food factory)](https://news.ycombinator.com/item?id=27595740)
- [Hacker News: co-founder comment on open-sourcing](https://news.ycombinator.com/item?id=27091866)
- [Example: case-management app](https://github.com/lowdefy/lowdefy-example-case-management)
- [Example: survey app](https://github.com/lowdefy/lowdefy-example-survey)
- [GitHub discussion: pricing and licensing](https://github.com/lowdefy/lowdefy/discussions/1668)
- [awesome.ecosyste.ms: Lowdefy project stats](https://awesome.ecosyste.ms/projects/github.com%2Flowdefy%2Flowdefy)
