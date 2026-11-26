# Batch tracking feasibility (MASTER-PROMPT section 3, step 1)

Checked on the sandbox (site `frontend`), 2026-11-26.

| Check | Result |
|---|---|
| `has_batch_no` on a new throwaway item (`TEST-BATCH-01`) | Works. Batches `TB-TEST-001` (10) and `TEST-BATCH-01-20261126-001/002` were created and received. |
| `has_batch_no` on the real P1 items (RM-CHUCK-13, RM-SIDE-HDL, RM-SCREW-KIT, RM-BOX-S, FG-DRL-800) | Refused by ERPNext: these items already have stock transactions. |

Workaround used (no stock reset): batch-tracked copies named `<item>-B`.

- Raw materials: RM-CHUCK-13-B, RM-SIDE-HDL-B, RM-SCREW-KIT-B, RM-BOX-S-B, with the original valuation rates (16.5, 6.8, 1.1, 3.2). These are used in `BOM-FG-DRL-800-003`, which is now the default BOM of FG-DRL-800.
- Finished good: `FG-DRL-800-B` with `BOM-FG-DRL-800-B-001` (copied from `BOM-FG-DRL-800-003`), created by `setup/create_batch_item.py FG-DRL-800 --bom BOM-FG-DRL-800-003`.
- The first four `-B` receipts (MAT-STE-2026-00053 to 00056) were posted at zero value before the rates were set. They were left as they are. Later receipts carry value.
