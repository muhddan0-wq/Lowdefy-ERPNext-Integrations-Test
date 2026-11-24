# ERPNEXT V16 INTEGRATIONS — Deck Audit

Canva design `DAHZR-Jr1Nk`, 130 slides, all inspected (text + rendered thumbnail).
Technical claims checked against `F:\ERPNEXT\erpnextcomp_demo` (docker-compose.yml, setup.ps1, setup/metabase-seed.ps1, .env.example, versions.env).
**Status (2026-11-23):** text fixes applied to slides 2, 3, 4, 8, 10, 12, 15, 30, 31, 32, 34, 35, 36, 39, 52, 54, 56, 58, 66, 70, 111, 129 (35/36 reordered: Start before Finish). Full pre-edit backup: Canva design `DAHbuFMAHjs`. Edited working copy: `DAHbuEBxQEo`.
Slides 59 and 71 (animation duplicates of 58/70) also corrected. Still open: slide 89 table, 98–100, 109, 75 and screenshot re-shoots (10–12, 15, 111) untouched; badge restyle not started.

Status key: **FIX** = clear error, fix known · **VERIFY** = needs your confirmation · **GAP** = content missing · **VISUAL** = design consistency

---

## 1. Errors that will mislead or break a live session (fix first)

| Slide | Problem | Correct version | Status |
|---|---|---|---|
| 4 | Day 1 divider title is the placeholder **"smtg"** | e.g. "Software Setup" | FIX |
| 75 | Left half reads **"PLACEHOLDER \*image GIT repo"** | Screenshot of the SHRDCOpenCodeERP repo / download page | FIX (needs screenshot) |
| 15 | Command `docker compose -p comp_demo --env-file .env -f docker-compose.yml up -d` **fails**: docker-compose.yml:236 requires `MARIADB`, which only exists in `versions.env` | `docker compose -p comp_demo --env-file .env --env-file versions.env -f docker-compose.yml up -d` (same form used in setup/metabase-seed.ps1:10) | FIX |
| 10–12 | Text says clone the msf4-0 **erpnext-v16-integrations-demo** repo, but screenshots show `github.com/frappe/frappe_docker.git` and a file called `example.env`. The real repo file is **`.env.example`**; slide text says "env-example" | Re-shoot slides 10–12 on the msf4-0 repo; text: copy `.env.example` → rename to `.env` | FIX (needs screenshots) |
| 8 | Column titled **"OpenCode AI"** shows the ngrok Store page; column titled **"Node.js"** shows `npm install -g node-red` (that's Node-RED). Node.js itself is never installed | Titles "Node-RED" and "ngrok"; add a Node.js installer step before Node-RED (npm needs Node.js) | FIX |
| 56 | **"Sales Return … to confirm billing"** — wrong. A Sales Return reverses a delivery (goods coming back from the customer). Billing is **Create → Sales Invoice**, which clears the Delivery Note's "To Bill" status | Rewrite as "Billing: Create → Sales Invoice → Save → Submit"; keep Sales Return as an optional "what if goods come back" slide | FIX |
| 28–31 | Goods are received with a **Purchase Receipt** (adds stock), then slides 29–31 also create a **Material Receipt** Stock Entry for the same goods → stock is counted twice. Slide 30 also says Material Receipt is for materials "we want to … purchase" (it isn't a purchase) | Pick one path: PO → Purchase Receipt (normal buying), *or* Material Receipt for stock arriving without a PO (e.g. opening stock). Slide 29 title "PURCHASING ORDER" doesn't match its content | VERIFY which path you intended |
| 35–36 | Order is reversed: 35 says "click Finish … ends the order", then 36 says "click Start". 36 also says "a list of **work orders** will be made" — the screenshot shows the Operations table; Job Cards are created when the Work Order is **submitted** (your own slide 52 says this) | Swap 35/36; "Start" → transfers materials to WIP; "Finish" → books finished goods. Fix "work orders" → "operations / Job Cards" | FIX |
| 34, 39, 52 | "Submit the work order and save again" / "submit and save" | ERPNext order is **Save, then Submit** (Submit locks the document) | FIX |
| 32 | "choose the quantity of materials needed" | It's **Qty To Manufacture** (of the finished good); BOM calculates materials | FIX |
| 54 | "Assuming items are available save and submit" on a Sales Order that is already submitted ("To Deliver and Bill") | Remove; go straight to Create → Delivery Note | FIX |
| 66 | `/agent` described as "Triggers the interactive model-selection popup" (copy of /model). Screenshot says **"Switch to the next agent"** | Fix text | FIX |
| 58, 69–70 | "Build shows a list of **skills**" / "allows the user to create Skills". The Build dropdown switches **agents** (Build, Plan, Module-Developer…). Agents ≠ skills. Slide 89 "GUIDE FOR WRITING AI SKILLS" sits inside "Creating an Agent" | Build = agent/mode selector; keep "What is a Skill?" as a separate definition; retitle 89 "Guide for writing agent instructions" or move it | FIX |
| 111 | Metabase DB connection shows a public IP and **port 8080** (8080 is ERPNext's web port). Verified: Metabase reaches ERPNext's MariaDB at host **`db`**, port **3306**, and `setup/metabase-seed.ps1` registers this source automatically | Host `db`, port `3306`, or say "already registered by setup — check it exists". Also state Metabase URL **http://localhost:3005** (not shown anywhere) | FIX |
| 109 | Slide shows Metabase admin login incl. password `DemoPass2026!`. docker-compose.yml:55 flags this exact value as an insecure default | OK for internal training on the sandbox; **remove before sending to clients** | VERIFY |
| 2 | "Over **three** days" — deck runs Day 1–Day 5. "Open Code AI" → "OpenCode" | "Over five days…" | FIX |
| 31, 34 | Warehouse names don't match screenshots: "Store TC" vs "Stores - TC"; "(Store -T-) / (WIP -T-) / (Scrap Warehouse -T-)" vs "Stores - TD", "Work In Progress - TD", "Scrap Yard - TD" | Use the exact names on screen | FIX |
| 3 | Glossary: "Production Plan … based on open Sales Orders or **Material** / Requests" — line break turns "Material" into a bold heading, leaving an orphan entry | Rejoin the sentence | FIX |
| 10 | Copy icon "🗐" renders as an empty box | Use "copy icon (⧉)" or just "the copy button" | FIX |
| 98–100 | Customer prompt lists 4 needs incl. **engineering changes (rev C/D cutoff)**; the results table has no row for it | Add the row, or state it wasn't built yet | VERIFY |

## 2. Unfinished / duplicate slides

| Slide | Issue | Suggestion |
|---|---|---|
| 128 + 129 | 128 = six empty check-mark cards; 129 = same content as plain bullets with a stray "-" at top | Put 129's six items into 128's cards; delete 129 |
| 130 | Day 5 "Assessment" divider is the last slide — nothing after it | Add assessment instructions + closing/summary/Q&A slide |
| 101 + 102 | Two consecutive Day 3 openers in different styles | Keep one (102 style + 101's three bullets) |
| 73 = 74, 115 ≈ 116, 58 ≈ 59 | Same text repeated; only the screenshot changes | Fine as click-through builds; otherwise merge |
| 79 | Left and right say the same thing ("Choose Module-Installer") | Left: pick agent; right: type the prompt |
| 5, 6 | Speaker notes say "CHANGE" | Resolve or clear |

## 3. Information gaps

- **No slide explains the integrations** the deck is named after. Slide 18 lists Node-RED and an ngrok API, and the setup output shows Node-RED webhooks (`/delivery-note`, `/stock-entry`, `/stock-recon`) and a Shopify option (`-SkipShopify`), but nothing says what they do or why participants installed Node-RED and ngrok on Day 1. Needs 1–2 slides: what each integration does, a data-flow diagram, and what the learner should see. (VERIFY: the flows themselves weren't inspected)
- **No agenda**: an overview slide mapping Day 1–5 after the intro.
- **No closing**: summary, next steps, Q&A.
- **Prerequisites missing**: Windows version, RAM/disk for Docker, admin rights, internet; Node.js step (see slide 8).
- **Roles & permissions**: everything is done as Administrator; one slide on which ERPNext roles do which step (ties into the Day 4 role play and slide 103 "Permissions").
- **Expected outcome checkpoints** for Day 2 steps (e.g. "PO status is now *To Receive and Bill*").
- **Slide 16 table** comes from setup.ps1, so it matches the code; `-Full -Wipe` is destructive. Add a warning callout.
- **Slide 20/21**: say where the Administrator password comes from (`admin` per the setup output) instead of "Administrator account and password".

## 4. Visual consistency

- **Section labels: four different treatments.**
  1. Orange text + yellow underline, top-left (slides 2–116, most of the deck).
  2. **Orange pill badge "ROLE PLAY"** (118–127): the reference style you want everywhere.
  3. No label, different template (26–28: left-aligned large title, "SHRDC Training" footer, page numbers 02/04/05, skipping 03).
  4. Label + subtitle stacked so it collides with the title (30, 32, 47–50, 82, 85–100, e.g. "WORKFLOW / How to create a Material Receipt", "AI agent for Production / Planning" wrapping).
- **Day dividers**: 4, 25, 102, 117, 130 share one style; **57 (WORKFLOW DEV)** is centred and empty, **101** is a different style.
- **Title slide (1)**: serif font (rest of deck is sans); subtitle is dark-on-navy and nearly invisible.
- **Glossary (3)**: serif title font.
- **Footer** "S H R D C Training" appears only on slides 1–15; 26–28 use "SHRDC Training"; the rest have none.
- **Purple corner triangle**: present on most content slides, missing on 26–28 and 118–130.
- **Unreadable screenshots** (too small at presentation distance): 23 (right), 27, 28, 29, 37, 40, 49, 51–53, 60–74 (OpenCode menus; crop and zoom on the menu), 96–97, 99. Annotations are inconsistent: some slides use red boxes and arrows, most have none.
- **Text-heavy slides**: 98 (customer prompt paragraph, ~12pt), 94, 95, 67.
- **Mixed body alignment**: centred paragraphs (2, 41–46) vs left bullets elsewhere.

## 5. Counts

- Slides inspected: 130
- Slides with a factual/technical error: 24 (section 1)
- Unfinished/placeholder slides: 4 (4, 75, 128, 129)
- Slides needing new screenshots: ~5 (10–12, 75, plus Node.js on 8)
- Slides off the badge style: ~110
- Fixes applied: **0**, pending your approval

## 6. Blocked / needs you

- New screenshots for 10–12, 75 and Node.js on 8 need to be taken on your machine.
- Slide 28–31 intent (Purchase Receipt vs Material Receipt).
- Whether the Metabase password stays in client-facing copies.
- Whether the engineering-change feature exists in the built module.
