# Lowdefy evaluation: what it's for, what it can't do, and whether to deploy it

Version evaluated: **Lowdefy 7.1.0**, as used by the ERP Copilot app against ERPNext v16.

Sources:
- Lowdefy's own 7.1.0 documentation, shipped inside the project at `.lowdefy/dev/node_modules/@lowdefy/docs-content/content/`.
- The installed build (`.lowdefy/dev/build/`).
- Tests run on this app on 2026-11-23 (section 8).

Doc paths are given so every claim can be checked.

---

## 1. Verdict in one paragraph

Lowdefy is a **config-driven framework for internal business apps**: admin panels, dashboards, CRUD screens, approval flows and operational tools sitting on top of existing databases and APIs.

**Where it's strong:**
- A small team (or a trainee) can deliver a secure, good-looking, multi-page tool very quickly.
- The screens come from a large ready-made component library.
- Data access, secrets and the rules for who may call what are all handled on the server by the framework.

**Where it's weak:**
- It isn't a general-purpose programming environment. Heavy business logic, custom device or graphics features, offline use and very custom UX all push you outside YAML, into plugins or a separate service.
- Login needs MongoDB.
- Scheduled jobs only work on Vercel.

**Is it deployable?** Yes. It builds to a standard Node.js server, with an official Docker recipe and an official Vercel path.

**Recommended for:** internal tools for known users (staff, trainees, supervisors).

**Not recommended for:**
- Public, high-traffic customer-facing apps.
- Offline shop-floor devices.
- Anything where the main value is complex computation rather than screens over data.

---

## 2. What Lowdefy actually is (and why that shapes everything)

```
lowdefy.yaml + pages/*.yaml  ──lowdefy build──▶  Hono (Node) server  +  Vite/React client
   blocks, requests,                                │                      │
   events/actions, operators,                       │ runs requests,       │ renders blocks,
   connections, api, auth                           │ API routines, auth,  │ holds page state,
                                                    │ websockets, agents   │ runs actions
```

- You don't write React or server code. You write **YAML built from four primitives**:
  - **blocks** (UI; 114 components),
  - **operators** (logic; ~70 functions such as `_if`, `_sum`, `_date`),
  - **events/actions** (behaviour),
  - **requests/connections** (data, always server-side).

  Source: `learn/introduction.md`, `concepts/four-primitives.md`.
- `lowdefy build` compiles the YAML into a ready-to-run web server. The 7.x server is **Hono** with a **Vite** React client (`deployment/vercel.md`, `.lowdefy/dev/src/app.js`).
- **Every data call runs on the server.** The browser only sends a `payload`. That single design choice explains most of Lowdefy's strengths (security, no CORS) and most of its friction (`_state` doesn't exist in request properties; `hazards.json → state-in-request-properties`).

---

## 3. What Lowdefy is good at, and the feature that makes it so

| Strength | Why: the mechanism inside Lowdefy | Seen in this project |
|---|---|---|
| **Building screens fast** | 114 ready blocks (Ant Design tables, forms, cards, tabs, drawers, charts) configured in YAML. No front-end build pipeline to maintain | 9 pages, ~5,900 lines of YAML, no React code |
| **Secure by default for data access** | Connections and requests execute only on the server. Credentials come from `_secret` (env vars `LOWDEFY_SECRET_*`) and never reach the browser (`concepts/secrets.md`) | The ERPNext token never appears in the browser. No CORS problems |
| **Connecting to many systems** | Official connections: AxiosHttp (any REST), PostgreSQL, MySQL/MariaDB (Knex), MSSQL, SQLite, MongoDB, Redis, Elasticsearch, Google Sheets, S3/Azure/GCS storage, Stripe, SMTP/SendGrid, OpenAI/Anthropic, MCP (`content/connections/`) | Uses AxiosHttp to call ERPNext's REST API |
| **Server-side workflows without a separate backend** | **API endpoints with routines**: `:if`, `:switch`, `:for`, `:parallel`, `:parallel_for`, `:try/:catch`, `:reject`, `:return`, `CallApi` between endpoints, JSON-schema payload validation, async endpoints, webhook receivers (`concepts/lowdefy-api.md`) | Not used yet. The app uses a custom Node helper instead |
| **Login, roles, organisations** | Built on BetterAuth: email+password, magic link, email OTP, passkeys, 2FA, ~35 OAuth providers incl. GenericOAuth. Pages, APIs and websockets are protected by role (`user-authentication/`) | Deferred (needs MongoDB; see §4) |
| **Live updates without extra infrastructure** | Websocket channels (`Interval`, `Channel`, `MongoDBChangeStream`) with `Publish`/`Subscribe`, served by the same Lowdefy server. Authorised with the same roles (`websockets/websockets-introduction.md`) | An `Interval` channel is declared but unused |
| **AI features in config** | `agents` + `AgentChat` block + Anthropic/OpenAI/Google connections. Agents call your API endpoints as tools. MCP endpoints expose those APIs to external AI clients (`agents/`, `connections/mcp.md`) | Available, unused |
| **Consistent look** | App-wide theme tokens (`theme.antd`) plus a global `public/styles.css` and Tailwind classes | Dark theme, KPI design system |
| **Testability** | `@lowdefy/e2e-utils`: Playwright with Lowdefy-aware locators, request mocking from YAML, test-user sessions (`testing/e2e-introduction.md`) | Installed, unused |
| **Deployment** | One build output: Node server, Docker image (with health check), or Vercel. Multiple environments in config (`deployment/`) | Runs locally in dev mode only |
| **Extensibility** | Any block, connection, action, operator or auth adapter can be added as an **npm plugin** written in JS/React (`plugins/plugins-introduction.md`) | Not used. The 3D floor and scanner are iframes instead |

**Why it excels at internal tools specifically:** most internal tools are lists, forms and dashboards over data you already have, plus access control and an audit trail. Each of those is a built-in primitive in Lowdefy. You configure them instead of coding them, and the framework keeps the server/client split safe.

---

## 4. What Lowdefy can't do, or does badly, and why

| Limit | Why it exists: the mechanism | Impact | Workaround |
|---|---|---|---|
| **Login requires MongoDB** | Auth must have a `database`, and the only adapter shipped is `MongoDBAuthAdapter` (`user-authentication/auth-configuration.md`, `adapter-reference/`). There's no SQL/MariaDB adapter | You can't add login to an ERPNext-only stack without running MongoDB as well | Run MongoDB (one container), or write a custom adapter plugin |
| **Scheduled jobs only on Vercel** | API `schedules` are "currently supported on Vercel deployments", where they become Vercel cron jobs (`concepts/lowdefy-api.md`). There's no built-in scheduler on a self-hosted Node/Docker server | Nightly scans, reminders and syncs don't run by themselves on-premise | An external timer (Node-RED, ERPNext scheduler, OS cron) calls a Lowdefy webhook endpoint |
| **Logic must fit operators and routines** | Logic is expressed as YAML operators and routine steps. There's no place for an arbitrary program | Heavy calculations (forecasting, multi-doctype rule engines, optimisation) become unreadable YAML | Keep a separate service (as this app does) or write a custom operator/connection plugin |
| **30-second request cap by default** | The server wraps every request in a timeout (`config.requestTimeout`, default 30000 ms). A connection's own `timeout` can't exceed it (`.lowdefy/dev/src/middleware/requestTimeout.js`; `lowdefySchema.js`) | Slow reports fail at 30 s even when the connection allows 120 s (proven in §8) | Set `config.requestTimeout`, or use async endpoints for long jobs |
| **No offline mode** | The docs have no service worker, PWA or offline-sync feature. All requests go to the server | Not suitable for devices on unreliable Wi-Fi | Local-storage drafts (`SetLocalStorage`) plus manual resubmit, or a native app |
| **No device, graphics or 3D blocks** | The block library is business UI (114 blocks). Camera scanning, WebGL/3D and canvas drawing aren't included | The scanner and 3D floor had to be separate HTML pages in iframes | Custom block plugin (React), or iframe |
| **No automatic forms from a data model** | Every field, column and child table is declared by hand in YAML. Lowdefy doesn't read ERPNext doctype metadata | A big ERPNext form (Sales Order + items) is a lot of YAML. ERPNext's own validation still runs only on save | Generate YAML from doctype metadata, or keep complex forms in ERPNext Desk |
| **Not a BI tool** | One chart library (ECharts) with fixed chart configs. No drag-and-drop or ad-hoc queries | Fine for fixed dashboards, poor for analysts exploring data | Metabase (already in the sandbox) for exploration |
| **Errors show as generic messages by default** | A failed action stops the rest of that event's action list, and request errors appear as a generic "Something went wrong" unless you handle them (observed in §8) | Screens can show "0" or "no rows" when data actually failed to load | Explicit `onError` handling and loading/empty-state design |
| **YAML pitfalls** | State is browser-side and request properties are server-side; `visible: false` deletes state; `_ref` to `.njk` renders at build time (`hazards.json`) | A learning curve, and typos fail silently as empty data | e2e tests and the hazard list |
| **Customer-facing scale and SEO** | It's an app framework for logged-in use, rendered by a React client, and each request goes through the one Node server | Not ideal for public, high-traffic or SEO-driven sites | A normal web stack or a CMS for public sites |

---

## 5. Where to use Lowdefy in real life (and where not)

### Good fits

- **ERP companion portals**, like ERP Copilot: role-specific screens over ERPNext such as exceptions inboxes, reorder suggestions, approvals and stock lookups. These are simpler than ERPNext Desk for non-ERP staff.
- **Operational dashboards:** KPIs, production status, integration health, live with websockets.
- **Approval and request workflows:** purchase requests, leave, maintenance requests, quality sign-off. These need forms, roles, an audit trail and email (SMTP connection).
- **Admin back-offices over a database:** CRUD on PostgreSQL/MySQL/MongoDB tables with access control.
- **Training and lab apps:** guided steps (`Steps`, `Tour` blocks) and checkpoints that verify an ERPNext document status through the API. This matches SHRDC's training use.
- **Internal AI assistants:** chat over company data through the agent tools, with role-based access.

### Poor fits

- **Offline or edge devices** (shop-floor terminals with bad Wi-Fi, handheld scanners without a network).
- **Heavy computation:** MRP runs, scheduling optimisation, forecasting. Do these in ERPNext or a service, and use Lowdefy to show the results.
- **Rich custom interfaces:** 3D, CAD, drag-and-drop planners, real-time machine HMIs.
- **Public consumer websites and e-commerce storefronts.**
- **Replacing ERPNext Desk:** ERPNext already generates forms, validation and workflows from doctypes. Re-creating them in YAML is duplicate work.

### Rule of thumb

Use Lowdefy when the job is **"show the right data to the right person, let them take a controlled action, and record it."** Don't use it when the job is **"compute something hard", "work without a network"** or **"look like a bespoke product"**.

---

## 6. Deployability

| Option | How (official) | Good for |
|---|---|---|
| **Node server** | `lowdefy build` → `.lowdefy/server` → `node src/index.js` (port `PORT`, default 3000) (`deployment/node-server.md`) | One on-premise machine next to ERPNext |
| **Docker** | `lowdefy init-docker` generates a multi-stage Dockerfile (Node 24, non-root user, `/api/lowdefy-health` health check) (`deployment/docker.md`) | **Recommended for SHRDC:** sits in the same docker-compose as ERPNext, Metabase and Node-RED |
| **Vercel** | `lowdefy init-vercel`: static CDN plus one serverless function. Cron supported, `maxDuration` default 60 s (`deployment/vercel.md`) | Cloud demos. Needs ERPNext reachable from the internet |

**Production checklist (from the docs):**
- `LOWDEFY_SECRET_*` env vars for every secret.
- `config.environments` + `LOWDEFY_ENVIRONMENT` for dev, staging and prod.
- `BETTER_AUTH_URL` (or the environment `url`) when auth is on.
- `config.trustedProxies` behind a reverse proxy.
- MongoDB if login is on.
- `config.requestTimeout` sized to your slowest request.
- Always rebuild before restarting.

**Is it production-ready?** For internal apps, yes:
- reproducible builds pinned to the `lowdefy:` version;
- a container image with a health check;
- role-protected pages and APIs;
- environment guards that stop a staging build from pointing at the production database.

The main operational costs are:
1. running MongoDB for auth;
2. no built-in scheduler on-premise;
3. the Node helper, which in this app is a second service to deploy and monitor.

**Today's ERP Copilot is not deployable as-is:**
- It runs only in dev mode (`lowdefy dev`).
- It has no login. The acting role is picked in the browser and trusted by the helper (`server/copilot-api.mjs:753`).
- It depends on a separate Node helper on port 4010.
- Getting it there needs auth + MongoDB, a Docker build, and a decision on the helper (§7).

---

## 7. What this means for the ERP Copilot app

1. **Show more Lowdefy, less helper.** Today almost all logic sits in a 3,066-line Node file, so the demo shows Lowdefy only as a screen layer. Moving simple endpoints (overview, settings, audit) into **Lowdefy API routines** would show its server side. Keep the heavy ones (exceptions rules, purchasing formula) in the helper and say why (§4: logic must fit operators and routines).
2. **Add login via ERPNext** (GenericOAuth against ERPNext's OAuth server, with MongoDB for sessions). That gives real roles and a real audit actor.
3. **Use the unused built-ins**: websocket live updates, an `AgentChat` "ask the ERP" assistant over read-only endpoints, and e2e tests.
4. **Fix the error UX found in §8**: show "unavailable" instead of 0, set `config.requestTimeout`, and handle errors per request so one failure doesn't blank other tabs.
5. **Deploy with Docker** inside the existing ERPNext compose stack.

---

## 8. Evidence from this project (tested 2026-11-23, read-only)

| Observation | Number / result | Evidence |
|---|---|---|
| Lowdefy's overhead is small | Error Log request: 32 ms direct from ERPNext vs 44 ms through Lowdefy (250 KB). Every page request was 12–190 ms | Browser timings |
| 30 s request cap overrides connection timeouts | ERPNext frozen → every request failed at **30.0 s** with `504 Gateway Timeout`, although the `copilot` connection sets `timeout: 120000` | `evidence/S3/B-erpnext-hung-*.jpg`, `src/middleware/requestTimeout.js` |
| The timeout reaches the user as a raw parse error | Screen showed `Unexpected token 'G', "Gateway Timeout" is not valid JSON` | `evidence/S3/B-erpnext-hung-orders-gateway-timeout.jpg` |
| One failed request stops the rest | Orders page: `orders_req` failed, so `wo_req` and `purchasing_req` never ran | Browser request log |
| Failures look like real zeros | Helper or ERPNext down → Dashboard shows 0 items, 0 stock value; Inventory says "No inventory rows match these filters" | `evidence/S3/A-*.jpg`, `C-*.jpg` |
| The helper's friendly error text is lost | The helper returns "Cannot reach ERPNext at … Is the sandbox running?" but the screen shows a generic "Something went wrong" | curl vs screenshot |
| Partial lists aren't labelled | Error Log tab shows "100 loaded"; ERPNext has 1,520. Nothing says these are only the latest 100 | `evidence/S1/error-log-shows-100-of-1520.jpg` |
| ERPNext's default list size is a trap | `/api/resource` returns only **20** rows when `limit_page_length` is missing. This app always sets it, but new pages may not | API test |

Some of these are app bugs, not Lowdefy limits. The 30 s cap and the raw timeout message are Lowdefy behaviour. The zeros, the lost messages and the unlabelled partial list are this app's error handling, which Lowdefy leaves to the developer.
