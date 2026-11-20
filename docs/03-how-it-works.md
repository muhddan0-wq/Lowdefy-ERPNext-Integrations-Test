# 3. How it works

## The big picture

```
 Browser                Lowdefy server            Copilot helper (Node)          ERPNext
 ───────                ──────────────            ─────────────────────          ───────
 YAML pages   ──req──▶  AxiosHttp connection ──▶  server/copilot-api.mjs  ──▶   /api/resource/...
 (no secrets)           (holds no ERP key for     • reads many doctypes          /api/method/...
                         most pages)              • computes KPIs, rules
                                                  • caches 10–60 s
                                                  • SQLite: settings,
                                                    exceptions, audit log
              ◀──────── iframe ────────────────── /floor  (3D page, three.js)
              ◀──────── new tab ───────────────── /scanner (camera page)
```

**In plain words:** ERPNext is the source of truth. The helper is a translator and calculator: it asks ERPNext many small questions, combines the answers into one tidy result per screen, remembers settings and an audit trail, and hands it to Lowdefy. Lowdefy only draws the screens and sends button clicks back.

### Why a helper service instead of calling ERPNext straight from Lowdefy?

1. **Aggregation.** One screen, such as the Exceptions inbox, needs 10+ ERPNext queries plus logic. That is easier and faster in JavaScript than in YAML.
2. **Security.** The ERPNext API key lives only in the helper's `.env`. The browser never sees it.
3. **No CORS problems.** The browser only talks to its own origin, and server-to-server calls have no CORS.
4. **Memory.** ERPNext has nowhere natural to store "this exception was assigned to Ali" or app settings, so the helper keeps them in SQLite.
5. **Audit.** Every write goes through one function that logs who, what, when and the result.

(The Orders/Monitoring pages are the exception: they call ERPNext directly through the `erpnext` connection in `lowdefy.yaml`, using the `ERP_TOKEN` secret. That still runs on the Lowdefy server, not in the browser.)

## How ERPNext is called

ERPNext (Frappe) exposes every document type (a "doctype") over REST:

| Call | Used for |
|---|---|
| `GET /api/resource/<Doctype>?fields=[...]&filters=[...]&limit_page_length=N` | Lists, e.g. all `Bin` rows for some warehouses |
| `GET /api/method/frappe.client.get?doctype=X&name=Y` | One full document including child tables, e.g. a Routing with its operations |
| `POST /api/resource/<Doctype>` | Create, e.g. a draft Purchase Order or Stock Entry |
| `POST /api/method/frappe.client.submit` / `cancel` | Submit/cancel, only after explicit confirmation in the UI |

Authentication is a header: `Authorization: token <api_key>:<api_secret>`.

Key doctypes this app reads: **Item, Warehouse, Bin** (current qty per item per warehouse), **Stock Ledger Entry** (every stock movement), **Stock Entry**, **Purchase Order / Purchase Receipt**, **Sales Order / Delivery Note / Sales Invoice**, **Workstation, Job Card, Routing, Work Order**, **Putaway Rule** (capacities), **Batch, Serial No, Error Log**.

## The helper service: function reference (`server/copilot-api.mjs`)

Plain Node.js with no framework: the built-in `http` server, `fetch` and `node:sqlite`.

### Plumbing

| Function | What it does |
|---|---|
| `readEnv` | Loads `.env` without any library |
| `migrate` | Creates SQLite tables if missing (`exceptions`, `exception_events`, `audit_log`, `settings`) |
| `getSettings` / `saveSettings` | Read/write tunable rules (lead time, thresholds, 3D floor warehouses, ...) |
| `audit` | Writes one audit row: actor, role, action, doctype, docname, result, message |
| `erp(path, opts)` | The **one** function that calls ERPNext. Adds the token, a 30 s timeout (`AbortController`), and turns Frappe's error format into readable messages ("Cannot reach ERPNext at …", "did not respond in time") |
| `getList(doctype, {fields, filters, limit, orderBy})` | Wrapper for `/api/resource` list calls |
| `fetchDocs(doctype, names)` | Fetches many full documents, 8 at a time in parallel |
| `cacheGet` / `cacheSet` | A tiny in-memory cache with an expiry time, so 30-second auto-refreshes don't hammer ERPNext |
| `num`, `round`, `isoToday`, `shiftDate`, `daysBetween` | Safe number/date helpers |
| `send`, `readBody`, `queryObject` | HTTP response/request helpers |

### Screens (one builder per page)

| Endpoint | Builder | Feeds |
|---|---|---|
| `GET /overview` | `buildOverview` | Dashboard KPIs |
| `GET /inventory`, `/item`, `/warehouses`, `/options` | `buildInventory`, `getItemDetail`, `loadWarehouses`, `loadBins`, `loadReorderLevels` | Inventory page and item drawer |
| `GET /lookup`, `/serial` | `getSerialDetail`, `getItemDetail` | Scanner: a code resolves to a serial number or an item |
| `GET /movements` | `buildMovements`, `buildMovementRows` | Stock Movements |
| `POST /transfer` | `createTransfer` | Stock transfer form (draft, or submit with confirmation) |
| `GET /exceptions`, `POST /exceptions/scan`, `POST /exceptions/action` | `detectExceptions`, `listExceptions`, `exceptionAction` | Exceptions inbox |
| `GET /purchasing`, `POST /purchase-orders` | `buildPurchasing`, `createPurchaseOrders` | Reorder suggestions → draft PO |
| `GET /reports` | `buildReports` | Reports |
| `GET/PUT /settings`, `GET /audit` | `getSettings`, `saveSettings`, `readAudit` | Settings, Audit log |
| `POST /submit-document`, `/cancel-document`, `/comment` | `submitDocument`, `cancelDocument`, `addComment` | Document actions (all audited) |
| `GET /export/purchasing.csv` | `csvEscape` | CSV download |
| `GET /floor`, `/floor/snapshot` | `buildFloorSnapshot` | 3D floor |
| `GET /scanner` | (static page + `jsQR.js`) | Camera scanner |
| `GET /health` | `health` | Start script and Settings page status |

## The interesting logic

### Exceptions inbox: rules that find problems

`detectInventoryFindings` and `detectSalesFindings` run plain rules over ERPNext data. Each finding stores the **rule text** as evidence, so a user can see why it was flagged:

- Item out of stock: `Bin.actual_qty <= 0`
- Below reorder level: `Bin.actual_qty < reorder level`
- Draft stock transfers older than N days
- Negative stock
- Batches expiring within N days
- Stock reconciliation differences
- Draft sales orders older than N days
- Overdue invoices: `outstanding_amount > 0 AND due_date < today`
- Delivered but not billed: `per_billed < 100`
- Orders at risk: pending sales-order qty is more than the stock available

Findings are **upserted** (`upsertException`) by a stable key. Re-scanning updates existing findings instead of duplicating them, and a finding keeps its lifecycle (new → investigating → resolved or dismissed, with an assignee) plus an event history.

### Purchasing assistant: the reorder formula

For each item, from sales in the last *window* days:

```
average daily sales = qty sold in window ÷ window days
safety stock        = max(item's safety stock, safety_days × average daily)
reorder point       = average daily × lead time + safety stock
suggested qty       = average daily × (lead time + cover days) + safety − available − already incoming
urgency             = critical if stock runs out before a new order could arrive,
                      soon if within lead time + 14 days, else ok
```

Suggestions are grouped by **supplier**, so you place one PO per supplier. "Create draft PO" creates a **draft** only. Nothing is ever auto-submitted.

### Safety design

- Writes default to **draft**. Submitting needs a confirmation checkbox (`I understand this submits the document`) and shows a warning.
- `roleAllowed` checks the role sent with a request before transfers. (Real login is planned but deferred: Lowdefy 7 auth needs a MongoDB adapter.)
- Every write, including denied ones, gets an `audit_log` row.
- The app logs in to ERPNext as a dedicated user (`copilot-api@copilot.local`) with only the roles it needs, not as Administrator.

### QR / barcode scanner

`/scanner` opens the phone or laptop camera. It uses the browser's built-in `BarcodeDetector` (QR, Code128, EAN, UPC) and falls back to the bundled `jsQR` library where the browser lacks it. A scanned code is sent back to the Lowdefy Scan page as `?code=...`. That page reads it with `_url_query` and calls `/lookup` to decide whether it is a serial number or an item code.

## The 3D warehouse floor

**Files:** `server/vendor/warehouse-floor.html` (one self-contained page), `server/vendor/three.min.js` (the three.js 3D library, r128), and `buildFloorSnapshot` in the helper.

**How it gets on screen:** `pages/floor.yaml` contains a `DangerousHtml` block with an `<iframe src="http://127.0.0.1:4010/floor">`. The helper serves the HTML, swaps the CDN script for its local copy of three.js, and injects `WF_CONFIG = { snapshotUrl: '/floor/snapshot', refreshMs: 30000 }`.

**Data:** the page fetches `/floor/snapshot` once, then again every 30 seconds. The snapshot contains:

| Key | From ERPNext | Drawn as |
|---|---|---|
| `items` | `Bin` in the Stores + WIP warehouses (top 10 by value), `Putaway Rule` capacities | One silo per item: solid = Stores, lighter top = WIP |
| `ws` | `Workstation`, open `Job Card`s | Workbenches: lights on top = job slots, crates in front = queued job cards, base strip colour = running/idle/waiting/down |
| `routes` | Latest `Routing` operations (else workstation order) | The blue path with moving dots |
| `fg` | `Bin` in the Finished Goods warehouse | The Finished Goods store building (and a silo per item when stocked) |
| `inbound` | Latest submitted **Purchase Receipts**; open **Purchase Orders** | Supplier truck at the receiving dock |
| `outbound` | Latest submitted **Delivery Notes**; open **Sales Orders** | Delivery truck at the dispatch dock |
| `log` | `Stock Ledger Entry` | "Recent movements" in the side panel |

The warehouses are found automatically by name prefix (`Stores…`, `Work In Progress…`, `Finished Goods…`) or set explicitly in Settings (`floor_stores`, `floor_wip`, `floor_fg`). If something is wrong, the snapshot includes `setup.problems` and the page shows a banner.

**How the 3D works (three.js in brief):**

- A **scene** holds meshes. A **mesh** = geometry (box, cylinder, cone) + material (colour). A **camera** looks at the scene, and a **renderer** draws it to a `<canvas>` about 60 times a second (`requestAnimationFrame(frame)`).
- Everything is built from a few shared unit shapes, stretched with `scale`. A silo is a cylinder scaled to the item's fill level. A truck is about 12 boxes and cylinders in a `Group`.
- **Layout** (`computeLayout`) places everything on one line along the x axis in flow order: receiving dock → silos → workbenches → Finished Goods store → dispatch dock.
- **Smooth motion:** each frame, objects move a fraction of the way toward their target (`x += (tx - x) * k`). Data changes therefore glide instead of jumping.
- **Trucks** follow a timed loop (arrive 4.5 s → unload/load 5.5 s → leave 4 s → pause 2 s) along a path of points. Curves are made from short straight steps (`arcPts`), and the truck's heading comes from the direction of travel. Each loop shows the next document in the list.
- **Flying crates** are a pool of 28 reusable boxes that travel in an arc (`sin(π·t)` lift): truck → Stores silos, last workbench → FG store, FG store → truck. Reusing objects avoids creating new 3D objects every second.
- **Clicking:** a raycaster turns the mouse position into a 3D ray and finds the first mesh hit. Every mesh carries `userData.id`, which selects the silo, workbench, store, dock or truck in the side panel.
- **Labels** are normal HTML `<div>`s positioned each frame by projecting a 3D point to screen coordinates. That keeps them crisp and styleable with CSS.
- **Theme:** colours are CSS variables (`--accent`, `--good`, `--road`, ...) read with `getComputedStyle`, so dark and light mode stay consistent.
- **Accessibility:** "reduced motion" users get parked trucks and no flying crates, and the Inspect dropdown lets keyboard users select everything.

**Honest caveats:** truck trips *replay* recent documents in a loop. They are not live GPS. The green "finished product" crates are an illustration of flow while job cards exist, not real completion events. The numbers in the side panel are real.

## Data stored locally (`data/copilot.sqlite`)

| Table | Holds |
|---|---|
| `settings` | Key/value rules editable on the Settings page (no code change needed) |
| `exceptions`, `exception_events` | Findings and their lifecycle history |
| `audit_log` | Every write: who, role, action, document, result, message, correlation id |

Deleting this file resets settings and history. It does not touch ERPNext.
