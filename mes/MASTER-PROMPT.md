# Master prompt: make the MES a portable "MES in a box" with batch scanning

Paste this whole file into a fresh session, with the repo open at `erpnext-copilot/`. Work from `mes/`. Do not commit or push unless asked.

## 0. Ground rules

- Read `AGENTS.md` (repo root), then `mes/PORTABILITY-SCOPE.md`, `mes/SHOPFLOOR-AUDIT.md` and `mes/BATCH-PRODUCTION-SCOPE.md`.
- No code comments (repo convention). Keep changes minimal and reuse existing server-script steps.
- Verify through the REST API as the Appsmith API user (`mes/.secrets/appsmith-mes.env`), not through UI clicks. A UI action is not proof of a change.
- Anything that writes ERPNext master data (item settings, stock, batches, roles, DocTypes) needs a backup first (`install-mes.ps1` does this) and a confirmation from the user before running on the sandbox.
- Report failures as failures. Record each acceptance result with evidence in `mes/state/`.

## 1. Verified facts (checked 2026-11-26)

- **Units:** `item_tracking` creates one `Tracked Item` per physical unit (`tracking_id` like `SA-HARN-S-0007`, globally unique `serial_no` `SN-########`). 255 Tracked Items exist. `bulk_transfer_tracked_items` (`item_tracking/.../tracked_item.py`) creates many at once, but it is whitelisted and inserts with `ignore_permissions=True`, with no role check. Any logged-in user can call it.
- **Scanning:** `barcode_shrdc` `scan_barcode` (`doctype/barcode_printing/barcode_printing.py`) resolves, in order: Item Barcode, Serial No, Batch, Item code. The Batch branch only returns the item and batch. It does not check quantity, expiry, item-on-work-order or blocked status.
- **MES scan:** `server_scripts/mes_sf_scan.py` has no batch path at all. Grep finds no `batch` in `mes_sf_*.py`.
- **API user** `appsmith-mes@local.test` (roles Manufacturing User, Manufacturing Manager, Stock User) gets:
  - HTTP 200 on Serial No and Tracked Item.
  - HTTP 403 on Batch, Maintenance Request, Issue, Asset and Item Barcode.
- **Batches in use:** no P1 item has `has_batch_no` set. No Batch records were read (the API user cannot read them).
- **Serial tracking:** ERPNext refuses to enable it on items that already have stock transactions. Batch tracking may have the same limit. Not yet tested.
- **Tests:** last shopfloor run 44 pass, 10 fail (`mes/state/shopfloor-test-results.md`). Workflow run 38 of 40 (`mes/state/workflow-test-results.md`).
- **Portability:** `install-mes.ps1` is config-driven from `mes/sites/p1-shah-alam.yaml`. Literals remain in `mes_analytics.py:220` (report title), `mes_execution.py:404`, 7 Appsmith widgets (`Voltra`, `localhost` URLs), `run-seed.ps1`, `run-mes.ps1`, `setup/test_*.py` and `setup/verify_api.sh`.

## 2. Decisions to confirm before building (ask the user, with a recommended default)

1. **Batch vs unit IDs.** A batch ID is one ID for a lot of many units. 50 to 100 identical units should use one batch ID with a quantity, scanned once. Per-unit IDs stay for serialised sub-assemblies (SA-HARN-S, SA-MOT-S, SA-HSG-DRL, SA-GBX-DRL). Default: batches for the bulk products and raw materials, units for the four sub-assemblies.
2. **Maintenance Request access for the API user.** Decided: **no** (confirmed by the user, 2026-11-26). Build a dedicated `MES Machine Issue` DocType linked to Workstation, as recommended in `SHOPFLOOR-AUDIT.md` section 6. The API user stays at 403 on Maintenance Request, Issue and Asset.
3. **Batch ID format.** Decided 2026-11-26: an 8-digit number from the sequence shared with unit serials (unit barcodes encode the same 8 digits), printed as CODE128 with the item as text. Batches created before then keep `<ITEM>-<YYYYMMDD>-<seq>`.
4. **Expiry.** Tracked? Default: no, unless the item has a shelf life.

## 3. Batch IDs for bulk production (the new requirement)

Goal: a supervisor creates one batch ID for 50 to 100 units and scans that ID once per material issue or finished-goods completion, entering a quantity.

**Status 2026-11-26:**
- **Done:** steps 1, 2 and 4, and the station text from step 6.
  - Step 1: batch tracking can't be enabled on items with stock history, so batch-tracked `-B` copies were made: RM-CHUCK-13-B, RM-SIDE-HDL-B, RM-SCREW-KIT-B and RM-BOX-S-B, used in `BOM-FG-DRL-800-003`.
  - Step 2: `mes_batch_create`.
  - Step 4: `mes_sf_scan` has a batch mode, with the batch row locked during a scan and claims counted across open orders.
- **Tested on MFG-WO-2026-00132 and 00133:** item code refused; batch scanned once to fill the remaining qty; duplicate refused; another item's batch refused; over-requirement refused; partial quantity then the remainder; 40 of 45 free after another order claimed 5; no free quantity refused. The test claims were voided afterwards.
- **Done later on 2026-11-26** (evidence in `mes/state/acceptance-2026-11-26.md`):
  - Step 3: `mes_batch_labels`.
  - Step 5: `FG-DRL-800-B`, output batch and `MES Batch Genealogy` on finish.
  - Step 7: `MES Batch Reader` role.
  - Issue and finish through `mes_work_order_action` using the scanned batches.
  - item_tracking skips `has_batch_no` items and role-checks its bulk methods.
  - Section 4: tests discover their fixtures. Section 5: literals are tokens from the site YAML, and `check_site.py` checks permissions.
  - The batch suite (`setup/test_batch.py`) passes 16 of 16 and the shopfloor suite 55 of 55. The workflow suite passed 42 of 45; its G1 expectation was corrected but has not been re-run.
- **Still open:**
  - The four zero-value `-B` receipts (MAT-STE-2026-00053 to 00056) were left as they are.
  - Tracked Item drift from real stock.
  - Sub-assembly stock is nearly used up.
  - The workflow suite created approved workflows for FG-CS-1400 and FG-RH-800, which need cleaning up.

1. **Feasibility (no changes yet).** On a throwaway test item, check that `has_batch_no` can be enabled and that a Batch can be created and received. Record the result in `mes/state/batch-feasibility.md`. If enabling fails on the real items, write the workaround (new item codes, or a stock reset on the sandbox only with approval).
2. **Batch creation.** Add a whitelisted server script `mes_batch_create.py` (role-checked: Manufacturing Manager or Stock Manager only) that:
   - takes `item_code`, `qty`, optional `batch_id` and `warehouse`;
   - creates one ERPNext `Batch` (ERPNext's own doctype, the source of truth), and creates the stock receipt for `qty` through `make_stock_entry`, the same way `mes_work_order_action.py` builds stock entries;
   - is idempotent: a repeated request with the same `batch_id` returns the existing batch and does not add stock twice.
3. **Bulk label printing.** One call prints labels for many batch IDs through `barcode_printing` (`CODE128`, one label per batch, with item, qty and date). Keep one label per batch, not per unit.
4. **Scan validation.** Add a batch branch to `mes_sf_scan.py`, with the same locking and logging as the unit branch:
   - batch exists, is for the item on the work order, is not expired or blocked, and has at least the required qty left;
   - a rejected scan is written to the MES scan log with a reason;
   - the scan is recorded against the work order and the quantity is consumed through ERPNext stock entries.
5. **Finished-goods batches.** On completion, create an output batch and record which input batches it used (traceability).
6. **Appsmith.** For batch items the shopfloor screen shows "scan batch, enter qty", not "scan each unit". Keep the unit flow for the four sub-assemblies.
7. **Permissions.** Grant the API user read on `Batch` (and on `Stock Entry` if the batch flow needs it), with the smallest role that works. Verify with REST: 200 for Batch read, still 403 for Maintenance Request.

## 4. Fix the bugs found in the audit

1. `bulk_transfer_tracked_items` and `bulk_transfer_all_stock_items` in `tracked_item.py`: add a role check (System Manager or Stock Manager). Verify a Manufacturing User gets 403 or PermissionError.
2. `scan_barcode` batch branch: keep it as a lookup only. All validation lives in `mes_sf_scan`, and the Appsmith screen must call `mes_sf_scan`, not `scan_barcode`, for stock actions.
3. Machine issues: implement decision 2. Do not widen the API user's rights to Maintenance Request.
4. Test `setup/test_shopfloor.py` and `setup/test_workflow.py`: they still hard-code SKUs and fixtures. Rewrite them to discover a finished product, a work order and tracked or batch stock at run time, and to report "not tested" rather than fail when stock is missing.

## 5. Finish portability ("MES in a box")

1. Remove the remaining literals listed in section 1 (report title, `mes_execution.py` phase text, widget `Voltra` and `localhost` URLs, `run-*.ps1` defaults). Read the URLs and names from `sites/<site>.yaml`.
2. Make `install-mes.ps1` also check: Batch read, Machine Issue DocType present, and the API user's effective permissions (REST spot-checks).
3. Do not start the second-company or second-server work yet. The user has deferred it.

## 6. Acceptance

For each item, record PASS or FAIL with evidence (REST response or script output) in `mes/state/`:
- Batch created once for 75 units, scanned once, qty consumed, second create with the same ID is idempotent.
- Wrong-item batch, expired batch and batch with insufficient qty are rejected and logged.
- Manufacturing User cannot call bulk tracked-item creation.
- API user can read Batch, cannot read Maintenance Request.
- `install-mes.ps1 -Only check` passes; `-Only all` backs up first.
- Shopfloor and workflow suites: state the pass count honestly, with the failing IDs named.

Do not claim a feature works until a test has run against the sandbox and the result is recorded.
