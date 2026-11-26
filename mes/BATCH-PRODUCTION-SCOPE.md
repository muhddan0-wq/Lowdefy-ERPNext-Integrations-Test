# Batch production scope: MES on ERPNext

Status: scoping. Nothing in this document has been built or changed yet.
Owner: to be assigned in the handoff session.

## 1. Why this scope exists

The shopfloor MES (`mes/`) was tested briefly by hand on MFG-WO-2026-00070 (45 × 13mm Electric Drill 800W). The design works for unit-serialised items, where every physical unit gets its own scan. It is not a good fit for batch production, where many identical units come from one batch or lot and scanning each unit is slow, error-prone, and does not match how ERPNext already tracks stock.

The fix is a batch-level design that uses ERPNext's own batch tracking as the source of truth. A new ERPNext batch function may be needed, but it should be checked first whether the built-in Batch feature already covers the need.

## 2. Current state (facts from the sandbox)

- Units are tracked by the installed `item_tracking` app: one `Tracked Item` per physical unit, with barcode and status. Scans are validated per unit in `mes_sf_scan` (see `mes/server_scripts/mes_sf_scan.py`).
- Items used in work order MFG-WO-2026-00070 that are serialised per unit: SA-HARN-S, SA-MOT-S, SA-HSG-DRL, SA-GBX-DRL. Each now has 45 tracked units in P1 Stores - VPT.
- Other sub-assemblies and raw materials are not unit-tracked. They are verified by item code and quantity only (`has_serial_no = 0`, no `Tracked Item`).
- Stock receipts create the tracked units automatically. Untracked stock stays in the bin and cannot be scanned per unit (e.g. SA-HARN-S: bin 100, tracked 45).
- ERPNext batch tracking (`Item.has_batch_no`, `Batch` doctype) is not used anywhere in the MES today. No batch-related code exists in `mes/`.
- ERPNext refuses to enable serial tracking on items that already have stock transactions (found in the Phase 1 audit). Batch tracking may have the same restriction. This must be checked first.
- Work order MFG-WO-2026-00070: Not Started, qty 45, nothing issued, nothing produced. The MES scan log holds three invalid SA-HARN-S scans from earlier testing.

## 3. Problem statement

For batch production the MES must:
1. Record the batch (lot) of each material consumed, not an identity per unit.
2. Verify quantity against the batch, with the batch barcode scanned once per batch instead of once per unit.
3. Keep the work order, job card and finished-goods batch traceable (which batches went into which finished batch).
4. Stop incomplete or wrong-batch production, using the same validation rules as today (invalid items rejected, required quantities enforced, production completion restricted).

The existing unit design must keep working for serialised items. Batch support is an addition, not a replacement.

## 4. Options

| Option | What it is | Pros | Cons |
|---|---|---|---|
| A. Use ERPNext native batches | Set `has_batch_no` on batch-produced items. Create a `Batch` per lot (ERPNext names or auto-generates). MES scans the batch barcode and validates qty against the batch. | ERPNext is the source of truth. Built-in traceability, FEFO, expiry, batch stock ledger. No custom stock tables. | Needs item master changes (check the stock-transaction restriction). Batch must be created before receipt. Needs batch barcode labels. |
| B. Custom batch layer in MES | MES stores its own batch records outside ERPNext's Batch doctype. | Works on items that already have stock. | Duplicates ERPNext data. Breaks "ERPNext is the source of truth". Not recommended. |
| C. Keep unit tracking, add bulk scanning | Scan one unit, then a quantity, as today. | Smallest change. | Still per-unit. Does not solve the batch problem. |

**Recommendation to validate in the handoff:** Option A. Check first whether ERPNext will accept `has_batch_no` on the four serialised items and on the batch-produced items, given existing stock. If not, decide between migrating those items (new item codes or a stock reset in a test environment) and keeping unit tracking for them.

## 5. Scope

### In scope
- ERPNext batch configuration for the items used in the MES demo (items that will be batch-tracked). Decide which items use batch and which keep unit tracking.
- A batch barcode scheme (which ERPNext field carries the scannable batch ID, and label generation).
- MES scan validation for batch-tracked items: batch exists, batch is for the item, batch has enough remaining quantity, batch is not expired or blocked, scan is recorded against the work order.
- Quantity consumption per batch when materials are issued and when finished goods are produced.
- Finished-goods batch creation and traceability record (which input batches went into each output batch).
- Changes to the shopfloor material-verification UI so batch items show "scan batch, enter qty" instead of "scan each unit".
- Acceptance tests for the batch flow, added to the existing test set (`mes/setup/`).

### Out of scope
- Redesigning the unit (serial) flow for existing serialised items.
- Costing, accounting, valuation changes beyond what ERPNext already does.
- Quality management workflows beyond what is already in the MES (defects, machine issues).
- Migrating historical stock in production. Sandbox only, unless the user approves otherwise.
- Changes to the item_tracking app itself.

## 6. Decisions needed from the user (before building)

1. Which items are batch-produced, and which stay unit-serialised? (The four sub-assemblies today.)
2. Batch ID format: ERPNext auto names, or a supplier lot number? What must the barcode contain?
3. Is expiry or shelf-life tracked? (Affects FEFO and expired-batch rejection.)
4. Must one finished batch trace back to specific input batches, or only to the work order?
5. May the sandbox stock be reset or migrated to test batch tracking? (Existing tracked units and receipts would need handling.)

## 7. Deliverables

1. Feasibility note: can ERPNext enable `has_batch_no` on the chosen items given current stock? Result and workaround.
2. Batch configuration: item settings, batch naming, and a seed script for the test dataset.
3. MES server scripts for batch scan validation and quantity consumption (new `mes_sf_batch_*` scripts or extensions to `mes_sf_scan`), with the same locking and idempotency rules as `mes_sf_scan`.
4. Appsmith shopfloor changes for batch items (batch scan, quantity entry, progress).
5. Acceptance test script for the batch flow, with results written to `mes/state/`.
6. Updated `mes/SHOPFLOOR-REPORT.md` section for batch production, or a separate `mes/BATCH-REPORT.md`.

## 8. Acceptance criteria

- A batch-tracked item can be issued to a work order by scanning its batch barcode and entering a quantity.
- A scan of an unknown, wrong-item, expired or insufficient batch is rejected with a reason, and the attempt is logged.
- Quantity consumed from a batch is reflected in ERPNext stock for that batch.
- Completing a job card with batch-consumed materials is blocked until every required quantity is verified.
- Finished goods are created with a batch and the input batches are recorded.
- Existing unit-serialised flow (MES acceptance suite `mes/setup/test_shopfloor.py`) still passes. Note: that suite needs fresh work orders.
- The batch flow works on the sandbox without Appsmith source-code changes beyond the mes widgets.

## 9. Risks

- ERPNext may refuse batch tracking on items with stock (see section 2). This is the first thing to check, and could change the whole plan.
- Existing tracked units and untracked stock may conflict with batch stock on the same items.
- Work orders for these items may already be partly consumed, which complicates the test data.
- Batch barcode scanning on a standard reader needs labels printed in a supported symbology (Code 128 used today).

## 10. First steps for the handoff session

1. Read `mes/SHOPFLOOR-REPORT.md`, `mes/server_scripts/mes_sf_scan.py`, `mes/setup/install_shopfloor.py`, and `mes/state/workflow-test-results.md`.
2. Run the feasibility check in the sandbox: try enabling `has_batch_no` on one test item with stock, and record the response.
3. Answer decisions 1 to 5 with the user.
4. Write the feasibility note, then start the batch configuration.
