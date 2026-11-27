# Demo runbook: ERPNext + MES in a box (27 Nov 2026)

Clean build prepared on the morning of 27 Nov 2026. The demo company is **Voltra Power Tools Sdn Bhd**, plant **P1 Shah Alam**.

## 1. What the clean build contains

- **Kept unchanged:** roles, users, permissions, MES server scripts, the Appsmith app, Voltra masters (66 items, BOMs, 12 workstations, 13 employees, assembly workflows, recipes), and all SHRDC items and data.
- **Removed:** junk items (TEST-\*, DEMO-SKU-\*, TRACK-DEMO-001, EXAMPLE-T-SHIRT-SMALL), their 2 draft sales orders and 2 customers, and **every Voltra transaction**: 131 old work orders, 264 job cards, 104 stock entries, 401 scans, 15 defects, 16 machine issues, 47 batches and 633 old tracked units.
- **Fresh stock** in P1 Stores, received 27 Nov:
  - MAT-STE-2026-00114: raw materials and quantity-counted sub-assemblies.
  - MAT-STE-2026-00115: per-unit sub-assemblies, each with an 8-digit barcode (00000729–00000838).
  - MAT-STE-2026-00116: one 60-unit batch per drill batch item (00000839–00000844).
- **18 new work orders**, MFG-WO-2026-00203 to 00220, all Not Started, all planned from **Mon 30 Nov 08:00**, so none shows Late today:
  - 4 finished goods × 5 each: FG-DRL-800-B, FG-DRL-800, FG-RH-800, FG-CS-1400.
  - 14 sub-assemblies × 10 each, covering every station (moulding, winding, oven, sub-assembly, motor, test, packing).
- **Go-Kart showcase line:** the existing GO-KART product (shared with SHRDC, linked to Shopify) now has a Voltra BOM, `BOM-GO-KART-002`: Frame, Steering Wheel, 4 Wheels and Seat, routed Final Assembly → Test → Packing. P1 Stores holds parts for 8 karts. **MFG-WO-2026-00223, GO-KART × 3** is the headline order. SHRDC's go-kart BOM, stock and serials are untouched.
- **Barcodes:** [demo-barcodes/](demo-barcodes/README.md). Showcase order **MFG-WO-2026-00223** (go-kart); drill test order **MFG-WO-2026-00203**.
- **Backup of the state before the reset:** `mes/state/pre-demo-backup-20261127/` (database plus files). Restoring it is in section 6.

## 2. Links

| What | Link | Sign in as |
|---|---|---|
| MES app (Appsmith): Work Orders | http://localhost:8081/app/mes-test/work-orders-6b052d6fbf901dfb3528488b | your Appsmith account (already signed in in Chrome) |
| MES: Shopfloor station | http://localhost:8081/app/mes-test/shopfloor-6b065bcabf901dfb352848ca | same |
| MES: Plant Dashboard | http://localhost:8081/app/mes-test/plant-dashboard-6b065bcdbf901dfb352848cd | same |
| MES: Schedule Board | http://localhost:8081/app/mes-test/schedule-board-6b052d6fbf901dfb3528488e | same |
| ERPNext desk | http://localhost:8000/app | Administrator or your own user |
| ERPNext: the go-kart work order | http://localhost:8000/app/work-order/MFG-WO-2026-00223 | |
| ERPNext: go-kart BOM (Voltra) | http://localhost:8000/app/bom/BOM-GO-KART-002 | |
| ERPNext: serial numbers | http://localhost:8000/app/serial-no | |
| ERPNext: the drill work order | http://localhost:8000/app/work-order/MFG-WO-2026-00203 | |
| ERPNext: drill BOM | http://localhost:8000/app/bom/BOM-FG-DRL-800-B-002 | |
| ERPNext: tracked units | http://localhost:8000/app/tracked-item | |
| ERPNext: batches | http://localhost:8000/app/batch | |
| ERPNext: MES scans (audit trail) | http://localhost:8000/app/mes-material-scan | |
| ERPNext: Stock Balance report | http://localhost:8000/app/query-report/Stock%20Balance | |
| Metabase (optional) | http://localhost:3005 | |
| Node-RED (optional, machine data later) | http://localhost:1880 | |

The older Lowdefy "ERP Copilot" app (port 3010) is **not part of this demo**. It is not running, and its demo company no longer exists.

## 3. Before the visitors arrive (5 minutes)

1. Check the containers are up:

   ```powershell
   docker ps --format "{{.Names}}  {{.Status}}"
   ```

   You should see `comp_demo-bench-1`, `comp_demo-db-1` and `appsmith`, all Up.
2. Print `demo-barcodes/work-orders/MFG-WO-2026-00223_GO-KART.html` (showcase), `demo-barcodes/work-orders/MFG-WO-2026-00203_FG-DRL-800-B.html` (batch demo) and `demo-barcodes/badges.html`. Alternatively, open them on a phone or second screen and scan from there.
3. Plug in the USB scanner. Click into the search box on the Shopfloor page, scan `00000839`, and check the code appears as text. Clear it afterwards.
4. Open the Work Orders and Shopfloor tabs in Chrome. Zoom to 100%.

## 4. Demo script (about 20 minutes)

### A. The plan (3 min): Work Orders page

- "ERPNext is the system of record. MES is the screen the planner and the shopfloor use on top of it."
- Show the 18 open orders, the status tiles, and the progress and planned-end columns.
- Filter by item, for example FG-DRL-800-B. Point out that every row is a real ERPNext Work Order.

### B. Finite scheduling (3 min): Schedule Board and Capacity

- **Schedule Board:** the job cards are laid out on the real P1 workstations, against the shift calendar (08:00–12:00 and 13:00–17:00, weekends off).
- **Capacity:** the load per station. Final Assembly carries the four finished-good orders.
- Optional: drag or reschedule one job. The server checks for conflicts before it accepts the move.

### C. The shopfloor station (10 min): Go-Kart order MFG-WO-2026-00223 (showcase)

1. **Work Orders**, click **MFG-WO-2026-00223 GO-KART**. The app jumps to the Shopfloor at **P1-FAL-02 Final Assembly line 2**.
2. **Badge sign-in:** scan `HR-EMP-00010` (Priya Devi).
3. **Issue materials:** scan every part on the go-kart sheet:
   - 3 frames (FRM-001-0075 to 0077) and 3 seats (SEAT-001-0007 to 0009). These are ERPNext serial numbers.
   - 3 steering wheels (00000850 to 00000852) and 12 wheels (00000873 to 00000884).
   - Show a guard rail: scan a wheel twice ("Duplicate scan"), or a drill motor `00000834` ("not required for this order").
   - Press **Issue**. "ERPNext moved exactly the frames and seats we scanned. Open Serial No FRM-001-0075 and you see it went to this order."
4. **Build:** start the job, record 3 good, complete. Then Test (P1-TST-01) and Packing (P1-PCK-01), the same way.
5. **Finish** the order. ERPNext creates 3 go-karts with serials GO-KART-0001 to 0003 in P1 Finished Goods.

### C2. Batch traceability (optional, 5 min): drill order MFG-WO-2026-00203

1. **Work Orders**, click **MFG-WO-2026-00203**. The app jumps to the Shopfloor at the order's first station, P1-FAL-01 Final Assembly Line.
2. **Badge sign-in:** scan `HR-EMP-00009` (Hafiz Rahman). "Every scan, issue and time log is now recorded against this person."
3. **Issue materials:** the screen lists the 10 materials and what each needs:
   - Scan the 6 batch labels, 00000839 to 00000844. Each shows "Verified from batch …, 5". Point out that the batch holds 60, but only the 5 this order needs are counted.
   - Scan the 20 unit labels (5 each of SA-MOT-S, SA-HSG-DRL, SA-HARN-S, SA-GBX-DRL). Each turns green as it is verified.
   - **Show the guard rails:**
     - Scan one unit again: "Duplicate scan".
     - Scan `99999999`: "Unknown barcode".
     - Scan a wrong part: "not required for this order".
   - Press **Issue**. ERPNext creates the stock entry, moving exactly the scanned batches and units from P1 Stores to WIP. Issue stays refused until everything has been scanned.
4. **Build:** start the job, record good quantity (build by scanned sets), then complete. The time log lands on the ERPNext job card.
5. **Defect ticket (optional):** raise one defect on a unit by scanning its barcode, pick a category, add a photo or note, and show it in ERPNext (MES Defect Report).
6. **Andon (optional):** raise a machine issue on P1-FAL-01. The station shows as down on the Plant Dashboard.

### D. Plant Dashboard (2 min)

- Today's completed quantity, target, defects, availability per station, and machines down.
- Today's work updates it live. The figures start at zero because this is a clean build.

### E. Proof in ERPNext (2 min)

- Open http://localhost:8000/app/work-order/MFG-WO-2026-00223: status, transferred quantity, linked stock entries and job cards.
- Open **Serial No** FRM-001-0075: Consumed, with the go-kart order's stock entries in its history.
- Open **MES Material Scan**: every scan, valid and invalid, with who, when and why. This is the audit trail.
- Open **Tracked Item** and search `00000873` (a wheel): the unit's record and barcode.

### F. DSH AI Assistant on the ERPNext desk (3 min, optional)

Your colleague's `dsh_bridge` app (msf4-0/erpnext-v16-integrations-demo PR #15) is installed on the sandbox.

1. In ERPNext, click your avatar, then **Session Defaults**, and set **Company = Voltra Power Tools Sdn Bhd**. The assistant works on the active company, and Administrator's default is SHRDC.
2. Open http://localhost:8000/app/dsh-assistant.
3. Prompts that work today:
   - `show inventory` (or `stock levels`): a live stock table card for the active company.
   - `create order 2 x FG-DRL-800 for <customer name>`: a **confirmation card** first. Nothing is written until you press Confirm. It then creates a **draft** Sales Order, links to it, and records the action in **DSH Action Log**.
   - Anything else gets an echo with hints. That is expected.
4. The yellow **fallback** tag means the built-in rule-based router answered. The LLM "sidecar" (`dsh_deepseek-harness`, which needs a model API key) is not set up on this machine.

Shopify safety: an assistant-created draft order has no Shopify ID, so the Shopify app's order hook does nothing and the live store is not touched.

## 5. If something goes wrong

| Symptom | Fix |
|---|---|
| A station screen shows an error or a 401 | ERPNext is down. Run `docker restart comp_demo-bench-1`, wait 30 s, then reload. |
| Issue says "scans needed" | Some materials are not scanned yet. The list shows which. |
| A scan says "Wrong version" | A non -B copy of a batch item was scanned. Use the -B batch labels from the sheet. |
| A station says it overlaps another job | Stop the other running job at that station first. |
| You want to run the same order again | Use MFG-WO-2026-00204, which has its own sheet. To start over completely, see the next section. |

## 6. Reset or restore

Re-run the clean build. This wipes Voltra transactions again and makes new orders with new numbers, so regenerate the barcode sheets afterwards:

```powershell
docker cp mes\setup\demo_reset.py comp_demo-bench-1:/home/frappe/frappe-bench/sites/mes_seed/demo_reset.py
```

```powershell
docker exec -e FRAPPE_SITE=frontend -e DEMO_START="2026-11-30 08:00:00" -w /home/frappe/frappe-bench/sites comp_demo-bench-1 ../env/bin/python -W ignore mes_seed/demo_reset.py mes_seed/products.yaml mes_seed/site.yaml
```

To get back to the exact state before today's reset, restore the backup taken at 09:10 on 27 Nov:

```powershell
docker exec -w /home/frappe/frappe-bench comp_demo-bench-1 bench --site frontend restore sites/frontend/private/backups/20261127_091010-frontend-database.sql.gz --with-public-files sites/frontend/private/backups/20261127_091010-frontend-files.tar --with-private-files sites/frontend/private/backups/20261127_091010-frontend-private-files.tar
```

A copy of those backup files is also in `mes/state/pre-demo-backup-20261127/`.

After a full reset, re-create the go-kart line (BOM is reused, stock for 8 karts, one order of 3), then regenerate the barcode sheets:

```powershell
docker cp mes\setup\gokart_setup.py comp_demo-bench-1:/home/frappe/frappe-bench/sites/mes_seed/gokart_setup.py
```

```powershell
docker exec -e FRAPPE_SITE=frontend -e DEMO_START="2026-11-30 08:00:00" -w /home/frappe/frappe-bench/sites comp_demo-bench-1 ../env/bin/python -W ignore mes_seed/gokart_setup.py mes_seed/site.yaml --stock-sets 8 --orders 3
```

`demo_reset.py --orders-only` also drops the open go-kart order, so run the second command (without `--stock-sets`) after it.
