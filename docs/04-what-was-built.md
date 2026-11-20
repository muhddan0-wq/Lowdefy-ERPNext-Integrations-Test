# 4. What was built, session by session

This app was built with an AI coding assistant (Claude Code) over several sessions. This page records what each session did and why, so the decisions aren't lost.

## Before these sessions: the base app

The ERP Copilot Lowdefy app was already working: Inventory, Scanner, Movements, Exceptions, Purchasing, Reports, Monitoring pages, Settings and the Audit Log, with the Node helper service and SQLite. See the README for the original feature list and `DEMO.md` for a 3-minute walkthrough.

## Session 1: "Lowdefy ERPNext API connection"

**Goal:** make the app's connection to ERPNext reliable, and give the UI a consistent design.

- **Dedicated API user.** The app had been using Administrator's API key. Other tools that regenerated Administrator's secret kept breaking the app with 401 errors. The app now uses its own ERPNext user, `copilot-api@copilot.local`, with only the roles it needs (Stock, Purchase, Sales, Accounts, Manufacturing, Item roles) plus a custom role, "Copilot Integration", that can read **Error Log**. No System Manager. **If auth breaks, regenerate keys for this user only, never Administrator.**
- **Restyle / design system.** One stylesheet, `public/styles.css`, with colour tokens mirrored in `lowdefy.yaml → theme.antd`. Reusable classes: `kpi kpi-<mint|violet|sky|amber|coral|lime|pink|orange>`, `kpi-sm`, `page-hero`, `section-title`.
- **Lowdefy 7 styling lessons** (written up in `02-lowdefy-basics.md` §8): the `.element` class slot, the `.lf-row` wrapper fix, YAML ` #` comments eating CSS colours.

## Session 2: "ERPNext 3D dashboard in Lowdefy"

**Goal:** bring the 3D warehouse view from the `msf4-0/erpnext-3d` project into this Lowdefy app, driven by live ERPNext data.

- The 3D page (`warehouse-floor.html`, three.js) was originally built to run inside ERPNext as a Frappe app. It was moved into the helper service. `GET /floor` serves the page and `GET /floor/snapshot` serves the data.
- `buildFloorSnapshot` was written to read Bins, Putaway Rules, the Stock Ledger, Workstations, Job Cards and the latest Routing, and to find the Stores / WIP / Finished Goods warehouses automatically (or from Settings).
- A new **3D Floor** page (`pages/floor.yaml`) embeds it with an iframe, plus an "Open full screen" button.

## Session 3: "Manufacturing flow + repository" (this one)

**Goal:** complete the manufacturing story in 3D, then put the project on GitHub.

- **Supplier trucks (inbound).** The snapshot now includes recent **Purchase Receipts** and open **Purchase Orders**. A truck drives into a new *receiving dock*, unloads crates into the Stores silos and leaves. Its label shows the receipt number and supplier.
- **Finished Goods store.** A building that is always drawn, even when the FG warehouse is empty. Finished-product crates fly into it from the last workbench.
- **Delivery trucks (outbound).** Recent **Delivery Notes** and open **Sales Orders**. A truck comes to a new *dispatch dock*, loads crates from the store and drives off.
- Roads, dock pads, an inspector panel for docks/trucks/store, hover tooltips, an extended routing path, and new legend entries.
- **Bug fix:** ERPNext returns times like `11:59:8` (no zero padding), which made some timestamps unreadable. `floorMs` now pads each part.
- **Repository:** `.gitignore` (excludes `.env`, `data/`, `node_modules/`, `.lowdefy/`), first commit, pushed to `github.com/muhddan0-wq/Lowdefy-ERPNext-Integrations-Test` (private). The original target was the msf4-0 org; the repo can be transferred there later in GitHub settings.
- These docs.

## Known limitations and next steps

- **No login yet.** Lowdefy 7 auth needs a MongoDB adapter; the plan (manager/viewer roles) is in the README. Until then, the audit actor is a fixed name.
- The 3D trucks replay recent documents; they are not real-time vehicle tracking.
- `setup-env.ps1` has a machine-specific default source path (`F:\ERPNEXT\…`).
- The `erpnext` connection in `lowdefy.yaml` hardcodes `http://localhost:8000`. It should read from a secret like the others.
- There is no automated test suite. Verification is manual (the README's Verification section).
