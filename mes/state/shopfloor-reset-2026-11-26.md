# Shopfloor reset and new work orders, 2026-11-26

Sandbox: `http://localhost:8000`, site `frontend`, company Voltra Power Tools Sdn Bhd, plant floor P1 Shah Alam Plant. Every check below was run against the sandbox. Unless a line says Administrator or bench, the call was made as the Appsmith API user `appsmith-mes@local.test`. Nothing was committed.

## Summary

- **Old orders:** all 97 open Voltra work orders are closed with ERPNext's own `close_work_order`. Their 82 valid scans are voided, which releases every unit and batch they claimed. No stock entry was cancelled.
- **New orders:** 18 work orders are submitted, MFG-WO-2026-00145 to 00162, one for each item with a default BOM. Quantities run from 10 to 50, and each order has job cards on the P1 workstations.
- **Stock:** every new order can be issued in full, whether alone or all at once.
  - The four sub-assemblies tracked per unit (plus SA-HSG-RH) were received as units, each with an 8-digit barcode.
  - The six drill raw materials each got one new 60-unit batch: 00000703 to 00000708.
- **Labels:** CSVs, PNGs and printable HTML are in `state/labels-2026-11-26/` (see its `README.md`).
- **Your two questions:** both are answered with REST evidence in [Test question answers](#test-question-answers).
- **Station screen:** it already worked with 8-digit codes. It now shows the unit's tracking ID or the batch next to a scanned code. It also finds a unit by its 8-digit barcode on the defect screen, including on large orders.
  - It was rebuilt, but it is **not deployed**, because the browser was not signed in to Appsmith.
- **Station issue fixed (follow-up):** the station's **Issue materials** button used to ignore which batch was scanned, so ERPNext issued its oldest batch instead. Now the order screen asks for the batch labels first, and Issue moves exactly the scanned batches. See [Station issue fix](#station-issue-fix-follow-up).

## Why the carton scan failed on MFG-WO-2026-00070

MFG-WO-2026-00070 was made from the old BOM `BOM-FG-DRL-800-001`, which lists the non-batch item RM-BOX-S. Batch 00000461 belongs to the batch-tracked copy, RM-BOX-S-B. So "Incorrect item: RM-BOX-S-B … is not required" was the correct answer for that order.

The new drill orders use the batch BOMs: MFG-WO-2026-00159 uses BOM-FG-DRL-800-004 and MFG-WO-2026-00160 uses BOM-FG-DRL-800-B-002. Both list RM-BOX-S-B. Scanning 00000461 on MFG-WO-2026-00159 now counts (scan MES-SCN-00287: Valid, 30 counted). No code change was needed for this.

## Sandbox changes, in order

1. **Backup:** `bench --site frontend backup` wrote `20261126_124459-frontend-database.sql.gz`. `install-mes.ps1 -Only scripts` took a second one later, `20261126_125402-…`.
2. **Running job cards stopped:**
   - The MES pause call (`mes_sf_progress action=pause`) was refused with ERPNext OverlapError on PO-JOB00070, 00134, 00151 and 00202. Their day-old open time logs overlapped other bookings.
   - Their four open time logs were closed in the bench at 12:45:47, with 0 completed quantity, and the job cards were set to On Hold.
   - PO-JOB00259, 00265 and 00271 showed Work In Progress but had no running log.
3. **Valid scans voided:** all 82 valid MES Material Scans on the 97 orders are now result `Voided`, with `unit_key` cleared and the reason "shopfloor reset, work order closed …".
4. **Planner bookings released:**
   - The 244 `Job Card Scheduled Time` rows on the draft job cards of those 97 orders were deleted. ERPNext's close does not touch job cards, so their bookings would otherwise have kept FAL, WND, IMM and the other stations reserved until 2 Dec. They would also have caused OverlapError on new starts.
   - The job cards themselves remain, and the station screen hides them because their orders are closed. Every deleted row is listed in the JSON.
   - At the end, 6 more rows were released the same way. They belonged to orders closed before today: MFG-WO-2026-00043, 00108 and 00134, on P1-SAB-01, P1-FAL-02, P1-TST-01, P1-PCK-01 and P1-IMM-01. No Voltra closed order holds a booking now.
5. **97 orders closed:** MFG-WO-2026-00036 to 00142, every Voltra order that was Not Started (71) or In Process (26). The closed orders came from production plans MFG-PP-2026-00001 to 00008, and 8 had no plan.
   - The 26 In Process orders had already moved materials to P1 Work In Progress - VPT. ERPNext's close leaves that stock in WIP.
6. **18 new work orders submitted** (table below). Each uses its default BOM, with `use_multi_level_bom: 0`, source P1 Stores - VPT and WIP P1 Work In Progress - VPT. Finished goods go to P1 Finished Goods - VPT and sub-assemblies to P1 Stores - VPT (the same rule as `mes_create_plan`).
   - They were created directly, not through `mes_create_plan`. That endpoint only takes finished goods, and it would merge the sub-assembly quantities into combined orders above 50.
   - Every order has planned start 26 Nov. ERPNext capacity planning queued the job cards on the shared stations, so the planned ends run to 1 Dec.
7. **Stock received** (Material Receipts into P1 Stores - VPT, at each item's Bin valuation rate, or its default BOM cost where the Bin rate was 0):

   | Entry | What | Value (MYR) |
   |---|---|---|
   | MAT-STE-2026-00096 | Per-unit sub-assemblies, received with item_tracking on, so every unit got a Tracked Item with an 8-digit barcode: SA-GBX-DRL 51 (00000469 to 00000519), SA-HARN-S 41 (00000520 to 00000560), SA-HSG-DRL 55 (00000561 to 00000615), SA-HSG-RH 20 (00000616 to 00000635), SA-MOT-S 67 (00000636 to 00000702) | 11,624.29 |
   | MAT-STE-2026-00097 | Quantity-counted sub-assemblies: SA-ARM-L 14, SA-ARM-S 37, SA-HMECH-RH 8, SA-MOT-L 15, SA-STA-L 12, SA-STA-S 39. Received with item_tracking's per-unit auto-create turned off, as in `mes_common.quiet_item_tracking`, so they stay "scan item, then quantity" | 11,859.72 |
   | MAT-STE-2026-00098 | One 60-unit batch per drill raw material, named by the item_tracking hook: RM-BOX-S-B **00000703**, RM-CHUCK-13-B **00000704**, RM-LABEL-B **00000705**, RM-MANUAL-B **00000706**, RM-SCREW-KIT-B **00000707**, RM-SIDE-HDL-B **00000708** | 1,145.01 |
   | MAT-STE-2026-00105 | Test-stock top-up after the station check and `test_batch.py`: SA-GBX-DRL 3, SA-HARN-S 2, SA-HSG-DRL 3, SA-MOT-S 3 (units 00000712 to 00000722) | 547.41 |
   | MAT-STE-2026-00108 | Test-stock top-up after the issue-fix check: SA-GBX-DRL 2, SA-HSG-DRL 2, SA-MOT-S 2 (units 00000723 to 00000728) | 336.72 |

   No raw material needed a receipt. Existing P1 stock already covered every raw material, and the original non-batch items were not added to.
8. **Station issue check (test fixture):**
   - MFG-WO-2026-00163, FG-DRL-800 × 1: scans, then `mes_sf_issue` created MAT-STE-2026-00099.
   - Afterwards its scans were voided, its 3 bookings released and the order closed. One set stays in P1 WIP.
9. **`test_batch.py`:** the batch suite ran and created its usual fixtures (listed under Test results).
10. **Server script `mes_sf_job` updated** and installed with `install-mes.ps1 -Only scripts` (see the station section). `-Only check` passed afterwards.
11. **Barcode Printing documents:** BP-2026-11-26-00012, 00015 and 00016 (earlier label exports, superseded) and BP-2026-11-26-00017 (final label export, 12 batches).
12. **Station issue fix (follow-up):** `mes_sf_issue` was changed and installed. It was tested on fixtures MFG-WO-2026-00165 (FG-DRL-800 × 2, issue MAT-STE-2026-00106) and MFG-WO-2026-00166 (SA-HARN-L × 1, issue MAT-STE-2026-00107). Both orders were closed afterwards with their scans voided and bookings released, and their issued materials stay in P1 WIP. The stock was topped up by MAT-STE-2026-00108. The labels were re-exported.

Detail files:
- `shopfloor-reset-2026-11-26-closed.json`: closed orders, voided scans, paused logs and released bookings.
- `shopfloor-reset-2026-11-26-new-orders.json`: new orders with their required items and job cards.
- `shopfloor-reset-2026-11-26-receipts.json`: receipts, batches and unit ranges.
- `shopfloor-reset-2026-11-26-shortages.json`: shortage check.
- `shopfloor-reset-2026-11-26-evidence.json`: test question evidence.
- `shopfloor-reset-2026-11-26-station-issue-check.json`: station issue check.

## New work orders

| Work order | Item | Qty | BOM | Job cards | Planned end |
|---|---|---|---|---|---|
| MFG-WO-2026-00145 | SA-ARM-S | 35 | BOM-SA-ARM-S-001 | PO-JOB00283 P1-WND-01, PO-JOB00284 P1-OVN-01 | 2026-11-27 14:25 |
| MFG-WO-2026-00146 | SA-STA-S | 45 | BOM-SA-STA-S-001 | PO-JOB00285 P1-WND-01, PO-JOB00286 P1-OVN-01 | 2026-11-30 09:50 |
| MFG-WO-2026-00147 | SA-ARM-L | 38 | BOM-SA-ARM-L-001 | PO-JOB00287 P1-WND-01, PO-JOB00288 P1-OVN-01 | 2026-11-30 15:43 |
| MFG-WO-2026-00148 | SA-STA-L | 42 | BOM-SA-STA-L-001 | PO-JOB00289 P1-WND-01, PO-JOB00290 P1-OVN-01 | 2026-12-01 08:59 |
| MFG-WO-2026-00149 | SA-MOT-S | 40 | BOM-SA-MOT-S-001 | PO-JOB00291 P1-MAS-01, PO-JOB00292 P1-TST-01 | 2026-11-30 09:20 |
| MFG-WO-2026-00150 | SA-MOT-L | 16 | BOM-SA-MOT-L-001 | PO-JOB00293 P1-MAS-01, PO-JOB00294 P1-TST-01 | 2026-11-30 10:34 |
| MFG-WO-2026-00151 | SA-HARN-S | 50 | BOM-SA-HARN-S-001 | PO-JOB00295 P1-SAB-01 | 2026-11-27 10:30 |
| MFG-WO-2026-00152 | SA-HARN-L | 33 | BOM-SA-HARN-L-001 | PO-JOB00296 P1-SAB-01 | 2026-11-27 13:19 |
| MFG-WO-2026-00153 | SA-HSG-DRL | 12 | BOM-SA-HSG-DRL-001 | PO-JOB00297, PO-JOB00298 P1-IMM-01 | 2026-11-27 08:37 |
| MFG-WO-2026-00154 | SA-GBX-DRL | 18 | BOM-SA-GBX-DRL-001 | PO-JOB00299 P1-SAB-01 | 2026-11-27 14:59 |
| MFG-WO-2026-00155 | SA-HSG-RH | 22 | BOM-SA-HSG-RH-001 | PO-JOB00300, PO-JOB00301 P1-IMM-01 | 2026-11-27 09:59 |
| MFG-WO-2026-00156 | SA-HMECH-RH | 28 | BOM-SA-HMECH-RH-001 | PO-JOB00302 P1-SAB-01 | 2026-11-30 10:21 |
| MFG-WO-2026-00157 | SA-HSG-CS | 10 | BOM-SA-HSG-CS-001 | PO-JOB00303, PO-JOB00304 P1-IMM-01 | 2026-11-27 10:51 |
| MFG-WO-2026-00158 | SA-GUARD-CS | 26 | BOM-SA-GUARD-CS-001 | PO-JOB00305 P1-SAB-01 | 2026-11-30 10:36 |
| MFG-WO-2026-00159 | FG-DRL-800 | 30 | BOM-FG-DRL-800-004 | PO-JOB00306 P1-FAL-01, PO-JOB00307 P1-TST-01, PO-JOB00308 P1-PCK-01 | 2026-11-27 16:50 |
| MFG-WO-2026-00160 | FG-DRL-800-B | 25 | BOM-FG-DRL-800-B-002 | PO-JOB00309 P1-FAL-01, PO-JOB00310 P1-TST-01, PO-JOB00311 P1-PCK-01 | 2026-12-01 08:50 |
| MFG-WO-2026-00161 | FG-RH-800 | 20 | BOM-FG-RH-800-001 | PO-JOB00312 P1-FAL-01, PO-JOB00313 P1-TST-01, PO-JOB00314 P1-PCK-01 | 2026-11-30 16:20 |
| MFG-WO-2026-00162 | FG-CS-1400 | 15 | BOM-FG-CS-1400-001 | PO-JOB00315 P1-FAL-01, PO-JOB00316 P1-TST-01, PO-JOB00317 P1-PCK-01 | 2026-12-01 09:25 |

**Shortage check:** for each order and each required item, the outstanding quantity was compared with the P1 Stores Bin. This is the same formula `mes_sf_issue` uses, run read-only, because calling `mes_sf_issue` would have issued the materials. The check was also run cumulatively across all 18 orders. Result after the final top-up: **no shortages**, all 18 orders Not Started.

## Labels and numbers

`state/labels-2026-11-26/`, described in its `README.md`:

- `all-work-orders.csv` (365 rows) and one CSV plus one printable HTML sheet per work order. Each row gives the work order, the item, the batch number or unit tracking ID, the 8-digit barcode and the quantity.
- `batches.csv` lists the 12 batches the drill orders use, with item, quantity in P1 Stores, date and the order that uses them. Leftover 1-unit test batches are no longer listed.
- PNGs: 12 batch labels, 280 unit labels and 49 item-code labels. The `batch-labels.html` and `unit-labels.html` sheets have the images built in, and the whole folder is zipped as `state/labels-2026-11-26.zip`.
- Each order gets distinct units, and batches are never overdrawn:
  - Units are taken newest first, so they are backed by real stock.
  - The 8-digit batches are preferred. MFG-WO-2026-00159 uses your batches 00000458 to 00000463 (30 from each), and MFG-WO-2026-00160 uses the new 00000703 to 00000708 (25 from each).
- These suggestions are not reserved in ERPNext.

The export script `mes/setup/export_shopfloor_labels.py` is new. Run it with `python mes/setup/export_shopfloor_labels.py <out_dir> <work order> ...`.

## Test question answers

### (a) Correct batch, but the batch holds more than the order needs

Batch 00000461 (RM-BOX-S-B, 50 in P1 Stores) was scanned on MFG-WO-2026-00159, which needs 30 cartons. Job card PO-JOB00306, operator op1@local.test.

| Case | Request | Result |
|---|---|---|
| a1: operator types a quantity above the need | `qty=50` | **Refused and logged.** MES-SCN-00286 Invalid: "Quantity exceeds requirement: only 30.0 Nos of RM-BOX-S-B still needed". Nothing was counted. |
| a2: what the station screen sends (`qty_mode=remaining`, no quantity) | `qty_mode=remaining` | **Valid, counts only 30.** MES-SCN-00287 qty 30, and RM-BOX-S-B shows Verified 30 of 30. |
| a3: the same batch on another order | MFG-WO-2026-00160 (needs 25), `qty_mode=remaining` | **Valid for the 20 left free.** MES-SCN-00288 qty 20, Partially Verified 20 of 25. The batch keeps track of what other open orders have claimed. |
| a4: scanning the same batch again on the first order | `qty_mode=remaining` | Refused: "Duplicate: RM-BOX-S-B is already fully verified for this work order" (MES-SCN-00289). |
| a5: stock after the scans | `get_batch_qty(00000461, P1 Stores)` | Still 50. A scan only claims quantity. Stock moves when materials are issued and the order is finished. |

So scanning a batch that holds more than the order needs is fine. The station counts only what the order still needs and leaves the rest of the batch free for other orders. Only a typed quantity above the need is refused.

These evidence scans were voided afterwards, so both orders start clean.

### (b) Are these numbers recognised by ERPNext?

**Batch numbers (00000458 to 00000463, 00000703 to 00000708): yes. They are real ERPNext Batch records.**

| Check | Result |
|---|---|
| `GET /api/resource/Batch/00000461` | 200: item RM-BOX-S-B, batch_qty 50, manufacturing date 2026-11-26, created by Stock Entry MAT-STE-2026-00087. All 12 drill batches are listed by `GET /api/resource/Batch`. |
| ERPNext report **Batch-Wise Balance History** (RM-BOX-S-B, P1 Stores) | 00000461: in 50, balance 50, value 160.00. 00000703: in 60, balance 60, value 169.90. |
| Stock ledger (bench, as Administrator) | The Stock Ledger Entry of MAT-STE-2026-00087 carries batch 00000461 (+50), and MAT-STE-2026-00098 carries 00000703 (+60). The Stock Ledger report rejected a batch filter over REST with a MariaDB 1064 error inside the report itself, so the ledger was read in the bench instead. |
| ERPNext's own scan (`erpnext.stock.utils.scan_barcode`, used by the Stock Entry "Scan Barcode" field) | `00000461` → `{batch_no: 00000461, item_code: RM-BOX-S-B, has_batch_no: 1}`, and the same for 00000703. Scanning a batch label into a Stock Entry fills the item and the batch. |
| barcode_shrdc scan | `00000461` → item RM-BOX-S-B, batch 00000461. |
| item_tracking desk scanner (`lookup_tracked_item`) | `00000461` → the **item** RM-BOX-S-B (stock 451), not the batch. It finds the item but cannot tell you which batch. |
| MES scan (`mes_sf_scan`) | Resolves the batch and checks it against the order (see (a)). |

**Unit 8-digit codes (for example 00000673 = SA-MOT-S-0083): only partly. They live in the item_tracking app, not in ERPNext's own Serial No.**

| Check | Result |
|---|---|
| ERPNext's own scan (`scan_barcode`) | `00000673` → `{}` (not found). `SA-MOT-S-0083` → `{}`. `SN-00000673` → `{}`. |
| ERPNext Serial No record `SN-00000673` | 404. The unit items (SA-MOT-S, SA-HARN-S, SA-HSG-DRL, SA-GBX-DRL, SA-HSG-RH) have "Has Serial No" off, and there are 0 Serial No records for them. |
| barcode_shrdc scan | `00000673` → `{}`. |
| Tracked Item (item_tracking DocType, readable in ERPNext desk) | `barcode = 00000673` → SA-MOT-S-0083, serial SN-00000673, In Stock, P1 Stores - VPT. |
| item_tracking desk scanner (`lookup_tracked_item`; also Shift+I in desk, and its "Scan Tracked Item" button on Stock Entry) | `00000673` → SA-MOT-S-0083, Motor Assembly 800W, P1 Stores - VPT, In Stock. |
| MES scan | `00000673` on MFG-WO-2026-00159 → Valid, "Verified as tracked unit" SA-MOT-S-0083 (MES-SCN-00290). Scanning it again → "Duplicate scan: unit SA-MOT-S-0083 is already recorded on this work order". |

In short:
- **Batch numbers** work everywhere in ERPNext.
- **Unit barcodes** work in the MES station and in the item_tracking scanner (desk popup, Shift+I, and the Stock Entry "Scan Tracked Item" button). They do **not** work in ERPNext's standard Scan Barcode field or as ERPNext Serial Nos.
- ERPNext's stock ledger counts the unit items as plain quantities. The tracking ID and history live only in Tracked Item.

## Station screen (Appsmith)

**Checked** in `widgets/station.js` and `sf_base.js`:
- Nothing assumes the old long IDs. There is no length check or ID regex.
- The keyboard-wedge scanner needs only 3 or more characters within 300 ms, so 8 digits are fine.
- Scans go through `mes_sf_scan`, which resolves the Tracked Item `barcode` field and Batch names.

**Changed:**
- `station.js`, scan result messages:
  - A successful scan now names what the code resolved to: "Unit SA-MOT-S-0083 (label 00000673)", or "Batch 00000461 · Qty 30". Before, it echoed the code ("Qty 30 · 00000461").
  - A refused unit or batch scan now starts with the unit or batch and its item, then gives the reason.
- `station.js`, defect screen: scanning a unit's 8-digit barcode now finds it even when the unit was first scanned by its QR or tracking ID. It also matches on the batch number.
- `server_scripts/mes_sf_job.py`: the job payload's scans now include `batch_no` and the unit's `barcode`.
  - The scan list limit was raised from 25 to 500. With the new 30-unit drill orders (about 126 scans each), the defect screen could not otherwise see most of the scanned units. The old Shopfloor screen still shows only the 12 newest.
  - Installed with `-Only scripts`. `-Only check` reports "CHECK PASSED: 0 blocking, 0 not ok of 30".
- `python mes/appsmith/build_app.py` rebuilt `MES-Phase1.json` (9 pages).

**Verified:**
- `mes_sf_job` for PO-JOB00306 returns `barcode` 00000673 for SA-MOT-S-0083 and `batch_no` 00000461.
- `node --check station.js` passes, and the new message helper was checked with sample responses.
- The dev harness (`?page=station&as=op1@local.test`) shows the new orders at P1-FAL-01: MFG-WO-2026-00159, 00160 and 00161, with "0 of 10 scanned".
- A live scan in the harness UI was **not** done, because the screen only allows scanning after materials are issued and the job is started, and that would have issued stock on your orders.

**Not deployed:** the browser pane's Appsmith session at :8081 is anonymous. Redeploy with `python mes/appsmith/deploy_appsmith.py` (it asks for your Appsmith login), or from a signed-in browser through the harness `/build` endpoint. Until then, the live Appsmith app runs the previous station.js. The `mes_sf_job` change is already live, and the old screen ignores the new fields.

## Test results

| Test | Result | Evidence |
|---|---|---|
| Old orders closed, claims voided | PASS | 97 closed, 0 errors. Afterwards: 0 Valid scans on open orders, 0 open time logs, 0 bookings left on the closed orders' draft job cards. |
| New orders submitted, one per BOM item, qty 10 to 50 | PASS | 18 orders, MFG-WO-2026-00145 to 00162, all Not Started, each with job cards. |
| Every new order can be issued from stock | PASS | Shortage check, individually and cumulatively: none. |
| Labels exported | PASS | 365 rows, 0 missing label files, 280 distinct units, no shortages in the allocation. |
| (a) Over-quantity batch scan | PASS | MES-SCN-00286 refused, 00287 counts 30, 00288 counts 20 on another order. |
| (b) Batch numbers recognised by ERPNext | PASS | Batch record, Batch-Wise Balance History, `scan_barcode`. |
| (b) Unit 8-digit codes recognised by ERPNext's own scan | FAIL (by design) | `scan_barcode('00000673')` → `{}`. No Serial No records. Recognised by item_tracking and the MES. |
| Carton scan on a new drill order | PASS | 00000461 on MFG-WO-2026-00159 → Valid (MES-SCN-00287). |
| Station issue moves the scanned batch | FAIL before the fix, **PASS after** | Before: MAT-STE-2026-00099 issued RM-BOX-S-B-20261126-001 although 00000461 was scanned. After: MAT-STE-2026-00106 moved exactly the six scanned batches (see Station issue fix). |
| Station issue refuses unscanned batch items | PASS | MFG-WO-2026-00165 with 5 of 6 batch items unscanned: `ok: false`, `batch_scans_needed` lists all 5, no stock entry created. |
| Station issue for an order with no batch items (regression) | PASS | MFG-WO-2026-00166 (SA-HARN-L): MAT-STE-2026-00107 issued as before. |
| `install-mes.ps1 -Only check` | PASS | 0 blocking, 0 not ok of 30. |
| `setup/test_batch.py` | PASS, 21 of 21 | Fixtures: WO MFG-WO-2026-00164 (FG-DRL-800-B × 2, finished); MAT-STE-2026-00100 to 00104; batches RM-SIDE-HDL-B-ACC/-EXP/-LOW-20261126125750, 00000709, 00000710 and the output batch 00000711; BP-2026-11-26-00014. See `batch-test-results.md`. |
| Station screen with 8-digit codes | PASS (code and API), live UI scan NOT TESTED | See the station section. |
| Shopfloor suite, workflow suite | NOT TESTED | Not re-run in this session. |

## Station issue fix (follow-up)

**The problem:** on the station, Issue comes before Start, and scanning came after Start. `mes_sf_issue` let ERPNext choose batches, which it does oldest first. In check order MFG-WO-2026-00163, batches 00000458 to 00000463 were scanned, but MAT-STE-2026-00099 issued RM-CHUCK-13-B-20261126-001, RM-SIDE-HDL-B-20261126-001, RM-SCREW-KIT-B-20261126-001 and RM-BOX-S-B-20261126-001 instead.

**The fix:** you scan a batch when you take it from stores, so the batch scan now happens at the Issue step.
- **`server_scripts/mes_sf_issue.py`:** batch-tracked materials are issued only from batches scanned on this order, using the same `batch_split` as the planner's `mes_work_order_action`.
  - If any batch item is not fully covered by scans, nothing is issued.
  - The reply says `ok: false` and lists `batch_scans_needed`, for example "RM-CHUCK-13-B Keyless Chuck 13mm: 2.0 Nos to issue, 0.0 covered by scanned batches".
  - Orders without batch items issue exactly as before.
- **`widgets/station.js`, order screen:**
  - When the selected order still has unscanned batch materials, a yellow panel lists them with "verified of required" and a scan box, and the Issue button reads "Scan the batch labels below first" and is disabled.
  - A USB scanner, typing in the box, or a camera scan on the order screen now counts as a material scan for the selected order. It still selects an order when the code is an order or job number.
  - After Issue, the message names the batches moved.
  - The scan rules are unchanged (`mes_sf_scan`, `qty_mode=remaining`), so a batch holding more than the order needs still counts only what the order needs.
- **Units and quantity materials** are still scanned on the assembly page. Issue does not need them.

**Verified:**
- **API:** see `shopfloor-reset-2026-11-26-issue-fix.json`.
  - Issuing MFG-WO-2026-00165 with 5 of 6 batch items unscanned was refused, and no stock entry was made.
  - After scanning RM-CHUCK-13-B-20261126-001, RM-SIDE-HDL-B-ACC-20261126125750, RM-SCREW-KIT-B-20261126-001, RM-BOX-S-B-ACC-20261126113513, 00000705 and 00000706, MAT-STE-2026-00106 moved exactly those six batches. This was read from the stock entry in ERPNext. ERPNext's own choice for the carton would have been RM-BOX-S-B-20261126-001.
- **Dev harness (op1@local.test, P1-FAL-01):**
  - The panel listed the six batch materials and Issue was disabled.
  - Typing RM-BOX-S-B-ACC-20261126113513 into the box showed "Carton Box … verified · Batch RM-BOX-S-B-ACC-20261126113513 · Qty 2" and removed the carton from the list.
  - After the issue, the order showed "Materials issued · MAT-STE-2026-00106", "6 of 10 scanned", and Start enabled.
- `install-mes.ps1 -Only check` passed again, `node --check` passed, and `build_app.py` rebuilt `MES-Phase1.json`.

**Not re-run:** `test_batch.py` and the shopfloor suite. The batch suite goes through `mes_work_order_action`, which did not change. The shopfloor suite uses `mes_sf_issue` on FG-RH-800, which has no batch items: that is the same path as the MFG-WO-2026-00166 regression check above.

## Leftover test batches cleared (follow-up, at the user's request)

The batch acceptance tests left batches in P1 Stores that are not production stock: 1-unit `-LOW-` batches, 69–73-unit `-ACC-` batches, empty `-EXP-` batches, the 1-unit numbered batches 00000467 and 00000710, and TEST-BATCH-01.

- **Backup:** `20261126_135656-frontend-database.sql.gz`.
- **Material Issue MAT-STE-2026-00109:** 452 units from 16 batches out of P1 Stores - VPT, value MYR 1,929.20.
- **Disabled:** the 24 test batches that are now empty everywhere, so they no longer appear in batch pickers or scans.
- **Kept enabled:** RM-BOX-S-B-ACC-20261126113513 and RM-SIDE-HDL-B-ACC-20261126125750. Each has 2 units in P1 Work In Progress from the closed check order MFG-WO-2026-00165.
- **Evidence:** `shopfloor-reset-2026-11-26-test-batch-clear.json`.
- **Afterwards:** the 12 order batches (00000458 to 00000463, 00000703 to 00000708) are unchanged, and the shortage check still finds no shortages.
- **First-generation batches, cleared in a second step at the user's request:**
  - Backup `20261126_140026-…`.
  - Material Issue MAT-STE-2026-00110 took RM-BOX-S-B-20261126-001 (44), RM-CHUCK-13-B-20261126-001 (36), RM-SCREW-KIT-B-20261126-001 (36) and RM-SIDE-HDL-B-20261126-001 (38) out of P1 Stores.
  - Its value is MYR 0.00, because these batches came from this morning's zero-value receipts (MAT-STE-2026-00053 to 00056).
  - They stay enabled because 1 to 3 units of each are in P1 Work In Progress from closed orders.
- **Result:** P1 Stores now holds only the 12 order batches. The shortage check still finds no shortages.
- **Note:** each run of `setup/test_batch.py` creates a new set of `-ACC-`, `-LOW-` and `-EXP-` batches.

## Live Appsmith screen still the old one (user report, 14:23)

What the server recorded from your session as muhddan0@gmail.com:
- **14:22:** "Issue materials" on MFG-WO-2026-00161 (FG-RH-800 × 20, no batch materials) created MAT-STE-2026-00111, and the job was started.
- **14:23:** batch 00000458 (chuck) was scanned on that same rotary-hammer order and refused as "Incorrect item", which is correct.
- **No record for MFG-WO-2026-00159 or 00000459.** The old screen rejects a code on the order page by itself, without calling the server ("is not an order at this station").

So the live Appsmith app still runs the old station screen. That screen cannot scan batch labels before Issue, while the server now requires them for the drill orders, so Issue on MFG-WO-2026-00159 or 00160 is refused there. Deploying the rebuilt app fixes this.

The order list's quantity column also changed. It used to show "remaining/total" (30/30 on an untouched order), which read like finished. It now shows "0 of 30 done", the same figure as "QTY complete" on the selected order. Rebuilt and checked in the harness. Not deployed.

## Open findings

1. **Fixed: the station's Issue materials step ignored the scanned batch.** See [Station issue fix](#station-issue-fix-follow-up). Orders issued before the fix, all of which are now closed, may have moved different batches from the ones scanned.
2. **Appsmith not redeployed** (see above).
3. **WIP stock left by the closed orders.** The 26 orders that were In Process, plus MFG-WO-2026-00163, keep their issued materials in P1 Work In Progress - VPT. Returning them to Stores would need a Material Transfer per order, which needs your decision.
4. **Tracked Items still drift from real stock.** Older units still say In Stock although they were consumed earlier, so SA-MOT-S, for example, has 115 "In Stock" units for a Bin of 75, and SA-HSG-DRL has 111 for 55. The CSVs only suggest units received today, plus the newest old ones, so every suggested unit is backed by Bin stock. The MES also refuses a unit scan beyond the Bin quantity.
5. **SA-HSG-RH is a fifth per-unit item.** Earlier test receipts created 2 Tracked Items for it, which put it in "scan every unit" mode, and today's 20-unit receipt followed that. If it should be counted by quantity, those 22 Tracked Items would need removing, which needs your OK.
6. **Defective units stay blocked.** 7 Defective scans on closed orders (for example MES-SCN-00001, SA-HARN-S-0001) keep their `unit_key`, so those units still say "already used". This was left on purpose, because they were reported defective.
7. **Old draft job cards remain.** The draft job cards of the 97 closed orders (status Open or On Hold) remain, without bookings. The station hides them. Deleting them was not done.
8. **Approved test workflows** on FG-CS-1400 and FG-RH-800 were left as instructed. The station will show them on MFG-WO-2026-00161 and 00162.
9. **The item_tracking desk scanner resolves a batch number to its item**, not to the batch (see (b)).
