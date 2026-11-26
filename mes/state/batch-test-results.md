# Batch production acceptance results

Run 2026-11-26 12:58 against http://localhost:8000 as the Appsmith API user (appsmith-mes@local.test). Passed 21, failed 0, not tested 0.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| P1 | API user can read Batch | PASS | GET /api/resource/Batch -> 200 |
| P2 | API user cannot read Maintenance Request, Issue or Asset | PASS | {'Maintenance Request': 403, 'Issue': 403, 'Asset': 403} |
| T1 | A Manufacturing User (no Stock or System Manager role) cannot create tracked units in bulk | PASS | API user roles ['MES Batch Reader', 'Manufacturing Manager', 'Manufacturing User', 'Stock User']; HTTP {'bulk_transfer_tracked_items': 403, 'bulk_create_tracked_items': 403, 'bulk_transfer_all_stock_items': 403}; Tracked Items 691 -> 691 |
| B1 | One batch ID is created for 75 units with one stock receipt | PASS | 200 {'item_code': 'RM-SIDE-HDL-B', 'batch_id': 'RM-SIDE-HDL-B-ACC-20261126125750', 'warehouse': 'P1 Stores - VPT', 'stock_entry': 'MAT-STE-2026-00100', 'status': 'created', 'qty': 75.0}; batch_qty 75.0 |
| B2 | Batch receipts do not create per-unit Tracked Items (item_tracking skips has_batch_no items) | PASS | Tracked Items for RM-SIDE-HDL-B: 45 -> 45 |
| B3 | A second create with the same batch ID is idempotent (no second receipt) | PASS | 200 {'item_code': 'RM-SIDE-HDL-B', 'batch_id': 'RM-SIDE-HDL-B-ACC-20261126125750', 'warehouse': 'P1 Stores - VPT', 'stock_entry': None, 'status': 'exists'}; batch_qty 75.0 |
| N1 | A new batch gets an 8-digit number from the sequence it shares with unit serials | PASS | 200 00000709; highest unit serial 702 |
| N5 | A batch that ERPNext names itself on a receipt gets the next shared 8-digit number (item_tracking hook) | PASS | MAT-STE-2026-00101 created batch 00000710 |
| N2 | The desk scanner resolves a unit's 8-digit barcode to its tracked unit | PASS | 00000106 -> SA-HSG-DRL-0001 |
| S1 | Scanning the item code of a batch-tracked material is refused | PASS | RM-SIDE-HDL-B is tracked by batch: scan the batch label, not the item code |
| S2 | A batch of an item that is not on the work order is rejected | PASS | 00000457 (FG-DRL-800-B): Incorrect item: FG-DRL-800-B 13mm Electric Drill 800W (batch) is not required for work order MFG-WO-2026-00164. Expected: SA-MOT-S, SA-HSG-DRL, SA-HARN-S, SA-GBX-DRL, RM-CHUCK-13-B, RM-SIDE-HDL-B, RM-SCREW-KIT-B, RM-BOX-S-B, RM-LABEL-B, RM-MANUAL-B |
| S3 | An expired batch is rejected | PASS | RM-SIDE-HDL-B-EXP-20261126125750: Batch RM-SIDE-HDL-B-EXP-20261126125750 expired on 2026-11-25 |
| S4 | A batch with less free quantity than entered is rejected | PASS | RM-SIDE-HDL-B-LOW-20261126125750 (qty 1), scanned 2: Not enough in batch RM-SIDE-HDL-B-LOW-20261126125750: only 1.0 Nos free |
| S5 | Every rejected scan is stored in the MES scan log with its reason | PASS | [('MES-SCN-00302', 'RM-SIDE-HDL-B is tracked by batch: scan the batch '), ('MES-SCN-00303', 'Incorrect item: FG-DRL-800-B 13mm Electric Drill 8'), ('MES-SCN-00304', 'Batch RM-SIDE-HDL-B-EXP-20261126125750 expired on '), ('MES-SCN-00305', 'Not enough in batch RM-SIDE-HDL-B-LOW-202611261257')] |
| S6 | The batch label is scanned once and the remaining requirement is taken from it | PASS | ('Valid', 2.0, 'Verified from batch RM-SIDE-HDL-B-ACC-20261126125750') |
| N3 | Unit labels scanned by their 8-digit barcode are verified as the right tracked unit in the MES | PASS | [('00000106', 'SA-HSG-DRL-0001', 'SA-HSG-DRL-0001', True), ('00000115', 'SA-HSG-DRL-0010', 'SA-HSG-DRL-0010', True), ('00000151', 'SA-GBX-DRL-0001', 'SA-GBX-DRL-0001', True), ('00000160', 'SA-GBX-DRL-0010', 'SA-GBX-DRL-0010', True), ('00000077', 'SA-HARN-S-0002', 'SA-HARN-S-0002', True), ('00000078', 'SA-HARN-S-0003', 'SA-HARN-S-0003', True)] |
| W1 | Issuing materials moves the scanned batch (ERPNext Material Transfer for Manufacture) | PASS | 200 MAT-STE-2026-00103; RM-SIDE-HDL-B rows [('RM-SIDE-HDL-B', 'RM-SIDE-HDL-B-ACC-20261126125750', 2.0)] |
| W2 | Finishing consumes the batch quantity through ERPNext (75 received, 2.0 used) | PASS | 200 MAT-STE-2026-00104; job cards completed; RM-SIDE-HDL-B-ACC-20261126125750 batch_qty now 73.0 |
| W3 | The finished-goods batch is created and records the input batches it used | PASS | output 00000711 qty 2.0; inputs [('RM-CHUCK-13-B', '00000704', 2.0), ('RM-SIDE-HDL-B', 'RM-SIDE-HDL-B-ACC-20261126125750', 2.0), ('RM-SCREW-KIT-B', '00000707', 2.0), ('RM-BOX-S-B', 'RM-BOX-S-B-ACC-20261126113513', 2.0), ('RM-LABEL-B', '00000705', 2.0), ('RM-MANUAL-B', '00000706', 2.0)] |
| N4 | The finished-goods output batch is numbered from the shared sequence | PASS | 00000711 |
| L1 | One call prints one CODE128 label per batch (Barcode Printing document + label images) | PASS | 200 {'barcode_printing': 'BP-2026-11-26-00014', 'labels': [('RM-SIDE-HDL-B-ACC-20261126125750', 73.0, '2026-11-26'), ('RM-SIDE-HDL-B-LOW-20261126125750', 1.0, '2026-11-26'), ('00000711', 2.0, '2026-11-26')]} |
