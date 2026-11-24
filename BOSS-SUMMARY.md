# ERP Copilot: how it works

## What it is

A web dashboard that reads live data from ERPNext and shows it as 9 pages: Dashboard, Inventory, Scanner, 3D Floor, Movements, Exceptions, Orders, Reports and Settings. It can also make a few controlled changes in ERPNext: stock transfers, draft purchase orders, and submitting/cancelling documents.

## The three layers

```
Browser  ──▶  Lowdefy app (port 3011)  ──▶  Helper service (port 4010)  ──▶  ERPNext (port 8000)
              the screens                   the logic                        the data
```

**1. ERPNext (the data layer).** The real database. Every record type (Item, Bin, Sales Order, Job Card, ...) is called a *doctype*, and ERPNext exposes each one over a REST API, for example `GET /api/resource/Bin?filters=...`. The app reads about 20 doctypes.

**2. Helper service (the logic layer).** One Node.js file (`server/copilot-api.mjs`, about 3,000 lines) running as a small web server on port 4010. It has 33 endpoints, roughly one per screen or action (`/inventory`, `/exceptions`, `/purchasing`, `/floor/snapshot`, ...). For each request it:
1. Calls ERPNext's API, often several doctypes in parallel.
2. Combines and calculates (totals, rules, reorder quantities).
3. Returns one JSON result shaped for that screen.

It is also the only place that holds the ERPNext API key, and it keeps a small local SQLite database for settings, the exceptions list and the audit log.

**3. Lowdefy (the screen layer).** Lowdefy builds web pages from YAML configuration instead of hand-written frontend code. Each page file declares:
- **blocks:** what's on screen (cards, tables, buttons, charts)
- **requests:** which helper endpoint feeds it
- **events:** what happens on page load or button click

The 9 pages total about 5,900 lines of YAML.

## How one screen gets its data (example: Inventory)

1. You open `/inventory`. The page's `onInitAsync` event fires a request called `inventory_req`.
2. Lowdefy's **server** (not the browser) sends `GET http://127.0.0.1:4010/inventory?search=...&warehouse=...`.
3. The helper's `buildInventory()` calls ERPNext for Items, Bins (stock per item per warehouse) and reorder levels, then joins them into rows with a status (OK / low / out).
4. The JSON comes back to Lowdefy, and the table block displays `inventory_req.data.rows`.
5. Clicking a row runs three actions in order: save the item code, call `/item` for details, open the side drawer.

Every page works the same way: **page event → helper endpoint → ERPNext API → combined JSON → blocks on screen.**

All ERPNext calls go through one function, `erp()`. It adds the API key, applies a 30-second timeout and turns ERPNext errors into readable messages ("Cannot reach ERPNext", "Insufficient permission for X").

## How often things update

| What | When it updates |
|---|---|
| Normal pages (Dashboard, Inventory, Movements, Reports, Orders, Settings) | When the page opens, and when you click **Refresh**. No background polling. |
| 3D Floor | Automatically **every 30 seconds** |
| Exceptions list | Stored in SQLite. New problems are found only when someone clicks **Run detection scan** (`POST /exceptions/scan`). Opening the page just reads the stored list. |
| Helper's short-term cache | Reused for a few seconds so repeated clicks don't hit ERPNext again: warehouses 60 s, items 45 s, stock levels 30 s, reorder levels 60 s, item groups 2 min, companies 5 min, 3D snapshot 10 s |

So data on screen is at most about 30–60 seconds behind ERPNext.

## How changes are written back to ERPNext

- **Stock transfer:** `POST /transfer` creates a Stock Entry in ERPNext. It is a **draft** by default. Submitting needs a ticked confirmation box.
- **Purchasing:** `POST /purchase-orders` creates **draft** Purchase Orders, one per supplier. Never auto-submitted.
- **Submit / cancel documents:** uses ERPNext's `frappe.client.submit` / `cancel`. Only on explicit button + confirmation.
- **Every write is logged** in the `audit_log` table (who, role, action, document, success/fail, message), including refused attempts.
- The helper logs in to ERPNext as a dedicated user, `copilot-api@copilot.local`, with only stock/buying/selling/manufacturing roles, not Administrator. Before this change, resetting the admin key broke the app.

## The 3D Floor in specifics

- The Lowdefy page embeds `http://127.0.0.1:4010/floor` in an iframe. The 3D is drawn with **three.js** (a browser 3D library) on a `<canvas>` at about 60 frames per second.
- Every 30 seconds it fetches `/floor/snapshot`. The helper's `buildFloorSnapshot()` reads:
  - **Bin** → silo height = actual stock quantity in Stores / Work In Progress
  - **Putaway Rule** → silo capacity
  - **Workstation + Job Card** → workbenches; lights = job slots in use, crates = queued job cards, colour = running / waiting / down
  - **Routing** → the order of the path between workbenches
  - **Purchase Receipt / Purchase Order** → the supplier truck's label (document number + supplier)
  - **Delivery Note / Sales Order** → the delivery truck's label (document number + customer)
  - **Stock Ledger Entry** → "recent movements" in the side panel
- Layout, left to right, follows the manufacturing flow: receiving dock → raw-material silos → workbenches → Finished Goods store → dispatch dock.
- Clicking an object finds the 3D object under the mouse (raycasting) and shows its ERPNext details in the side panel.
- The trucks cycle through the latest real documents (one trip about every 16 seconds). The quantities are real; the truck movement is an animation, not GPS.

## Two calculations worth knowing

**Reorder suggestion (Purchasing):**
```
suggested qty = average daily sales × (lead time + days of cover) + safety stock − stock on hand − stock already ordered
```
Average daily sales comes from the last N days of sales. Lead time, cover and safety days are editable on the Settings page, not hard-coded.

**Exception rules:** each one is a plain condition on ERPNext data, and the rule text is shown next to the problem. Examples:
- overdue invoice: `outstanding > 0 and due date < today`
- order at risk: pending order qty > available stock
- also negative stock, expiring batches, delivered-but-not-billed, and old drafts

## Current limits

- No login yet. Lowdefy's login feature needs a MongoDB database, which isn't set up.
- Normal pages don't auto-refresh. Only the 3D floor does.
- Prototype running against a demo ERPNext; no automated tests yet.
