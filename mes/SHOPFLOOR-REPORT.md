# Shopfloor MES: implementation report

Status at 2026-11-25: Phases 1 to 8 are implemented on the local sandbox (ERPNext v16 at http://localhost:8000).
The backend acceptance suite passes 54 of 54 checks, and the main shopfloor flow was driven by hand in the
browser through the dev harness. **Not yet done:** importing the new pages into the real Appsmith instance and
testing them there. Section 14 lists what is still open.

Evidence:
- Backend tests: [state/shopfloor-test-results.md](state/shopfloor-test-results.md), produced by `python mes/setup/test_shopfloor.py`
- Image import: [state/item-image-import.md](state/item-image-import.md)
- Phase 1 audit: [SHOPFLOOR-AUDIT.md](SHOPFLOOR-AUDIT.md)

## 1. Existing architecture (what was kept)

- Appsmith is the screen layer only. Each page is one Custom Widget and one REST query (`Erp`). The widget raises
  `onCall`; Appsmith runs the query on its server with the ERPNext API key, so the key never reaches the browser.
- ERPNext API server scripts (`mes/server_scripts/mes_*.py`, with a shared `_prelude.py`) hold all reads, writes and
  validation. They are installed by `mes/setup/install-server-scripts.ps1`.
- The six planner pages (Work Orders, Work Order Detail, New Plan, Schedule Board, Capacity, Workstation Queue) are
  unchanged, apart from a nav link to the new pages.
- Installed custom apps were reused: `item_tracking` (Tracked Item: one record per physical unit, with barcode or QR,
  warehouse and status) and `barcode_shrdc` (barcode label generation). No barcode or scanning code existed in the MES.

## 2. What changed

| Area | Change |
|---|---|
| Item images | 11 photos uploaded into ERPNext and linked to `Item.image`. Matching is repeatable and reported. |
| Data model | 3 new ERPNext DocTypes: MES Material Scan, MES Defect Report, MES Machine Issue |
| Backend | 7 new API server scripts (`mes_sf_*`) and shared helpers in `_prelude.py`. The existing finish action now enforces the shopfloor gate. |
| UI | 2 new Appsmith pages: **Shopfloor** (new default landing page) and **Shopfloor Admin** |
| Test users | `op1@local.test` (shopfloor), `sup1@local.test` (supervisor), `maint1@local.test` (maintenance). No passwords set. |
| Tooling | Installers, image importer, acceptance test suite, dev harness updates |

## 3. Appsmith pages

| Page | Status | What it does |
|---|---|---|
| Shopfloor | New, default page | Workstation picker and job list with product photos. Job tabs: Job, Material Verification, Barcode Scanner, Report Defect, Machine Issue, Production Progress. Also My Reports and a standalone Report Machine Issue. |
| Shopfloor Admin | New | Maintenance: machine issue board (acknowledge, assign, start work, resolve with notes, close). Supervisors also get Defect Reports (status, disposition, comments) and Invalid Scans. Tabs follow the user's ERPNext roles. Refreshes every 30 s. |
| Work Orders … Workstation Queue | Unchanged | Nav bar gains links to the two new pages |

The shopfloor pages use a dark, high-contrast theme with 60–84 px touch targets, 16–34 px text, and large green or red
scan results with an audio cue.

## 4. JavaScript and queries

| File | Status | Purpose |
|---|---|---|
| `widgets/sf_base.js/.css` | New | Shared theme, `api()` (adds `operator`), image and placeholder rendering, request ids, beep, file reading |
| `widgets/shopfloor.js` | New | Shopfloor page |
| `widgets/mes_admin.js` | New | Supervisor / maintenance page |
| `widgets/common.js` | Changed | Nav bar lists the new pages |
| `build_app.py` | Changed | Two new pages, shared widget files per page, and an `onCall` allow-list: only `/api/method/mes_*` paths may run through the `Erp` query |
| `dev_harness.py` | Changed | Reuses `build_app.widget_src`; `?as=<erpnext user>` picks the operator; same `mes_*` allow-list |
| Query `Erp` | Unchanged | Still one POST query per page |

## 5. Database tables (ERPNext DocTypes)

All are custom DocTypes in module Manufacturing, created by `mes/setup/install_shopfloor.py`. Only System Manager
may write them directly; everyone else reads them. Every change goes through the validating server scripts, so a
hand-made REST call cannot mark a scan valid or a defect resolved.

| DocType | Key fields | Notes |
|---|---|---|
| MES Material Scan (`MES-SCN-#####`) | work_order, job_card, item_code, scan_mode (Unit/Quantity/Confirm), result (Valid/Invalid/Defective/Voided), reason, scanned_value, unit_id, serial_no, qty, warehouse, operator | Every attempt is stored, invalid ones included. `unit_key` and `request_id` are unique columns. |
| MES Defect Report (`MES-DEF-#####`) | work_order, job_card, item_code, unit_id, qty_affected, category, description, status, disposition, resolution_comments, reported_by, reviewed_by/on | Attachments are private ERPNext Files. Category options are editable in Customize Form. Change history is on. |
| MES Machine Issue (`MES-MCH-#####`) | workstation, work_order, job_card, issue_type, severity, machine_status, description, status, assigned_to, resolution_notes, reported/acknowledged/resolved by and on | Linked to ERPNext Workstation (the machine). Attachments are private Files. |

No item, BOM, stock or serial data is duplicated: those are read live from ERPNext.

## 6. ERPNext DocTypes and fields used

Item (`image`, `has_serial_no`, `stock_uom`, `disabled`), UOM (`must_be_whole_number`), Work Order (`required_items`,
`operations`, warehouses, status), Job Card (`time_logs`, `for_quantity`, `total_completed_qty`, submit), Bin
(`actual_qty`), Serial No (`status`, `warehouse`), Item Barcode, Tracked Item (`item_tracking` app: `barcode`,
`serial_no`, `current_warehouse`, `current_status`), Workstation (`plant_floor`), File, Notification Log, Comment
(work order timeline), User and Has Role.

Machine issues do not use Maintenance Request or Asset. P1 machines are ERPNext Workstations, not Assets, and the API
user has no Asset access. A dedicated record linked to Workstation avoids widening that access. This was decision 2 of
the audit.

## 7. Image import results

`mes/setup/import-item-images.ps1`, with the mapping in `mes/setup/item_images.yaml`. It backs up the site first, and
`-DryRun` previews without writing.

- 58 files: **11 imported**, 3 held, 44 unmatched. Full table: [state/item-image-import.md](state/item-image-import.md).
- Imported: RM-BRG-608 (exact name match). Approved matches: FG-DRL-800, FG-RH-800, FG-CS-1400, RM-COMM-24,
  RM-GEARCASE-AL, RM-BASE-CS, RM-BLADE-185, RM-CABLE, RM-CHUCK-13, RM-BRUSH-6X8.
- Held as ambiguous or wrong: `Ball Bearing 6001ZZ.jpg` (no 6001ZZ item), `TriggerSwitch.jpg` (two switches),
  `CoolingFan.jpg` (two fans).
- Files are public ERPNext Files attached to the Item. The URLs are served without login, which the test suite verifies.
- Strong single-candidate matches **not** imported, awaiting your confirmation: `HammerMechanism.png` → SA-HMECH-RH,
  `DrillGearBox.jpg` → SA-GBX-DRL, `BladeGuardBaseplate.jpg` → SA-GUARD-CS, `SteelBladeGuard.jpg` → RM-GUARD-CS,
  `CordStrainRelief.jpg` → RM-STRAIN, `GearGrease.jpg` → RM-GREASE, `SawSpindle.jpg` → RM-SPINDLE-CS,
  `SlideHandle&DepthRod.jpg` → RM-SIDE-HDL, `Piston&RamSet.jpg` → RM-PISTON-SET, `SDSPlusChuck.jpg` → RM-SDS-HOLD.
  To import them, add them under `manual:` and rerun the importer.

## 8. Barcode scanning

- **USB / keyboard-wedge scanners:** the scan field is auto-focused and submits on Enter. Tested in the browser.
- **Manual entry:** the same field.
- **Camera:** live scanning with `getUserMedia` and the browser's `BarcodeDetector` (all formats the device supports:
  QR, Code 128, EAN and others), plus a "Scan from photo" fallback (`capture="environment"`). **Not tested on a device
  with a camera.** See limitations.
- **What a scan can resolve to**, in order (`mes_resolve_scan`): Tracked Item (raw id, barcode, serial, or an
  `item_tracking` QR URL), ERPNext Serial No, Item Barcode, then plain item code.

## 9. Material validation logic (`mes_sf_scan`, `mes_materials`, `mes_gate`)

The verification mode per material comes from ERPNext settings:
- **Unit:** the item has serial numbers or Tracked Item units. Each unit must be scanned.
- **Scan:** whole-number UOM. Scan the item, then enter a quantity.
- **Confirm:** fractional UOM (kg, m, litre). Enter the quantity only.

Each scan is checked for:
- item exists and is enabled
- item is required by this work order's BOM; otherwise the message names the materials still expected
- a unit-tracked item was scanned as a unit, not by item code
- the unit is in stock or Active
- the unit is in the work order's source or WIP warehouse
- the unit is not already used on this or another work order
- the unit has no open defect
- the quantity is above zero, a whole number where the UOM requires it, within the remaining requirement, and within
  available stock

Concurrency:
- The request rolls back its read-only transaction, then locks the work order row and the unit's own row as its first
  statements, so every later read is current.
- `unit_key` is a unique column, so the database itself refuses a second valid scan of the same unit.
- `request_id` makes resubmissions idempotent.
- Tested with 2 to 5 parallel requests: exactly the right number succeed, and the losers get a plain-language reason.

Defects interact with verification:
- A defective unit's scan changes to Defective, and a defect quantity is held back.
- The material shows **Defective Material** until a supervisor decides the defect.
- *Use As Is* and *Rejected* restore the unit. *Replace*, *Scrap* and the other dispositions keep it excluded, so a
  replacement must be scanned.

The completion gate is enforced on the backend for reporting good units, complete, and the planner's existing finish
action. Starting a job only needs the materials issued, no open blocking defect and a working machine. The gate
blocks when:
- any material is not Verified
- any defect is Reported, Under Review or Rework Required
- any defect is Accepted without a disposition
- the job's workstation has an open Completely Down issue
- no good quantity has been reported

## 10. Defect reporting (`mes_sf_defect`)

- Covers any material, or the finished product, of the job's work order.
- Optional unit or serial number, which is validated against the item.
- Category, description, quantity affected.
- Up to 6 photos or files of 10 MB each (camera capture, gallery, any file), sent as base64 and stored as **private**
  ERPNext Files on the report.
- Comment added to the work order timeline; supervisors and Quality Managers are notified.
- Statuses: Reported → Under Review / Accepted / Rejected / Rework Required / Resolved. Resolved and Rework Required
  require a disposition.
- No stock moves automatically. Disposition is recorded only; any stock movement stays in normal ERPNext workflows.

## 11. Machine issue notifications (`mes_sf_machine_issue`, `mes_sf_admin`)

- Stores an MES Machine Issue on the Workstation, linked to the job and work order when they are on that machine.
- Priority is raised to fit the situation: Stalled → at least High; Completely Down or Safety Concern → Critical.
- An ERPNext **Notification Log** (desk bell) goes to every enabled Maintenance User, Maintenance Manager and
  Manufacturing Manager. Status changes notify the reporter and the assignee.
- Completely Down blocks start and complete on that workstation only. Other machines carry on (tested). Production
  resumes only after maintenance marks the issue Resolved or Closed. A running job can still be paused to stop the clock.
- Flow: Open → Acknowledged → In Progress → Resolved → Closed. Resolved can return to In Progress. Resolving needs
  notes. Only maintenance may assign or resolve; supervisors may acknowledge only.

## 12. Roles and permissions

| Who | ERPNext role | Can | Cannot (enforced by the server, tested) |
|---|---|---|---|
| Shopfloor employee | Manufacturing User | View jobs and materials, scan and confirm, report defects and issues, attach photos, start, report, pause and complete jobs, view own reports | Decide defects, void scans, resolve issues, write MES records directly |
| Supervisor | Manufacturing Manager | All of the above, plus review and decide defects and dispositions, void a mistaken scan (with reason), view invalid scans, acknowledge issues | Assign or resolve machine issues |
| Maintenance | Maintenance User / Manager | Issue board: acknowledge, assign, progress, resolve, close; report issues | Record material scans |
| Administrator | System Manager | Everything | |

The operator is the Appsmith user's email, which must be an enabled ERPNext user. Their ERPNext roles are checked on
every call. Unknown users and the API accounts themselves are refused.

## 13. Test results

Automated: **54 PASS, 0 FAIL, 0 NOT TESTED**, covering every acceptance criterion group. See
[state/shopfloor-test-results.md](state/shopfloor-test-results.md). Highlights:

- **Images:** retrieved, correct item, missing image returns no URL. I1–I3
- **Materials:** BOM list, modes, valid unit, duplicate, reuse, wrong item, unknown code, item code for a unit item,
  over-quantity, fractional quantity, invalid scans never counted. M1–M14
- **Reliability:** idempotent resubmit; 2-way unit race; quantity races (2-way in the suite, 5-way ad hoc); API errors
  return error status. R1–R3, F1
- **Defects:** report with photo and file, unit excluded, supervisor review, disposition rules, own reports, blocks
  completion. D1–D8, C4
- **Machine issues:** breakdown and stall, priority, notifications, dashboard, blocks only that machine, maintenance
  resolve flow. X1–X8
- **Completion:** blocked by missing or partial materials; start, report, refuse overrun, complete (Job Card
  submitted, work order operation updated); planner finish refused with no stock entry created. C1–C11
- **Permissions:** P1–P5
- **Audit:** A1

Manual, in the browser (dev harness at http://127.0.0.1:8099):
- Job list with photos and placeholders.
- USB-style scan of a correct item (green) and a wrong item (red, reason, photo).
- Bulk confirmations; Start; report 40; Complete with 25. ERPNext shows Armature Winding Completed, 65.
- Machine issue reported from the Shopfloor page, then resolved by maintenance on the admin page.
- Supervisor defect view.
- No console errors.

## 14. Known limitations and open items

1. **Not yet tested inside Appsmith.** `MES-Phase1.json` is rebuilt with the new pages, but the import into
   http://localhost:8081 needs an Appsmith login, so it hasn't been run. Everything was tested through the dev
   harness, which runs the same widget code with a mock `appsmith` object.
2. **Camera scanning is untested.** No camera was available here. Also:
   - `BarcodeDetector` is not available in desktop Chrome on Windows (it is on Android, ChromeOS and macOS).
   - Appsmith's Custom Widget iframe may not grant camera permission.
   - USB scanners and manual entry work everywhere. If camera scanning is needed on Windows tablets, use Appsmith's
     built-in Code Scanner widget feeding the scan field, or bundle a JS decoder such as ZXing.
3. **Operator identity is asserted by Appsmith.** All calls share one API key, and the operator email comes from
   `appsmith.user.email`. It cannot be changed through the URL, but a technical user with dev tools could forge it.
   Unforgeable identity needs per-user ERPNext tokens or SSO.
4. **API user rights are wider than the shopfloor needs.** `appsmith-mes@local.test` holds Manufacturing Manager and
   can write BOM, Work Order, Stock Entry and Job Card through raw REST. The new `onCall` allow-list blocks this from
   the Appsmith pages, but that check runs in the browser. The existing server scripts run as this user and need some
   of those rights. Recommendation: move the scripts to `ignore_permissions` writes and reduce the API user to a
   minimal role. This is a security-settings change, so I left it for your decision.
5. **No serial numbers on P1 items.** ERPNext refuses to turn on `has_serial_no` once an item has stock, and P1 items
   do. Unit-level checks therefore use Tracked Items, which only `SA-HARN-S` has (10 units). Other materials are
   quantity-verified.
6. **Two checks are implemented but have no test data:** "unit in the wrong warehouse" and "unit consumed or not in
   stock". All tracked SA-HARN-S units are In Stock in P1 Stores.
7. **The finish gate changes the planner flow.** `mes_work_order_action` finish now refuses work orders whose materials
   were not verified on the Shopfloor page. That includes In Process orders from before this change. It is controlled
   by `ENFORCE_FINISH_GATE` in `_prelude.py`.
8. **Final stock entries are untouched.** Completing a job submits the ERPNext Job Card only. The Manufacture stock
   entry (financial) still comes from the existing planner finish action, and was not run, per the rule against
   submitting financial documents without your confirmation.
9. **Jobs are chosen by workstation, not by employee.** The site has no Employee records linked to users. Operators
   pick their workstation, which is remembered on the device.
10. **Notifications are in-app only.** They are ERPNext desk notifications; no email or SMS, since no mail account is
    set up.
11. **Private attachments need an ERPNext login to view.** Defect and machine photos open in ERPNext.
12. **44 images are unmatched.** The 10 strong candidates are listed in section 7.
13. **Test data is left in the sandbox.** 64 scans, defects MES-DEF-00001 to 00004, issues MES-MCH-00001 to 00005,
    and submitted Job Cards PO-JOB00064, PO-JOB00128 (the manual UI run) and PO-JOB00160 (Armature Winding,
    65 units each). The test users op1, sup1 and maint1 also remain. Site backups taken before the changes are in `sites/frontend/private/backups/` (10:42 and
    10:51 on 2026-11-25).
14. **Deployment side effect.** `install-server-scripts.ps1` deploys the working tree, so it also redeployed your
    uncommitted edits to `mes_work_orders.py` and `mes_workstation_queue.py`.

## 15. Deploying the updated MES

From the repo root:

```powershell
.\mes\setup\install-shopfloor.ps1                 # backup, DocTypes, all server scripts (add -TestUsers for op1/sup1/maint1)
.\mes\setup\import-item-images.ps1 -DryRun        # preview image matching
.\mes\setup\import-item-images.ps1                # backup, upload matched images
python mes/appsmith/build_app.py                  # rebuild MES-Phase1.json (8 pages)
python mes/setup/test_shopfloor.py                # acceptance suite (writes to the sandbox, submits one Job Card)
```

In Appsmith (http://localhost:8081):
1. Import `mes/appsmith/MES-Phase1.json`, or re-import over the existing app.
2. Set datasource **ERPNext**: URL `http://host.docker.internal:8000`, header `Authorization: token <key>:<secret>`
   from `mes/.secrets/appsmith-mes.env`.
3. Create each operator's Appsmith account with the same email as an enabled ERPNext user, with the right ERPNext role
   (Manufacturing User, Manufacturing Manager, Maintenance User).
4. Deploy. **Shopfloor** is the default page.
5. If ERPNext is not at `http://localhost:8000` from the operators' browsers, change `ERP_PUBLIC` in
   `widgets/sf_base.js` and `ERP_DESK` in `common.js`, then rebuild.

Local preview without Appsmith: `python mes/appsmith/dev_harness.py`, then open
http://127.0.0.1:8099/?page=shopfloor&as=op1@local.test (or `page=mes_admin&as=sup1@local.test`).
