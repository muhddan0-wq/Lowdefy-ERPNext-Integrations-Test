# Shopfloor labels, 2026-11-26

What each of the 18 work orders (MFG-WO-2026-00145 to 00162) needs to scan, with label images. Exported from the sandbox by `mes/setup/export_shopfloor_labels.py` as the Appsmith API user. Every number here is a real ERPNext record. Running the export again rebuilds this folder.

The batch and unit for each row are a **suggestion**. Nothing is reserved in ERPNext. The export picks them so that no two orders get the same unit and no batch is overdrawn. Any free unit or batch of the right item also scans.

## Files

| File | What it is |
|---|---|
| `all-work-orders.csv` | Every row from the per-order CSVs in one file (365 rows). |
| `work-orders/<work order>_<item>.csv` | One per work order. Columns: `work_order`, `production_item`, `wo_qty`, `item_code`, `item_name`, `scan_mode`, `batch_no`, `tracking_id`, `barcode` (what to scan), `qty`, `uom`, `label_file`, `note`. |
| `work-orders/<work order>_<item>.html` | A printable sheet per order: the table, then every label it needs. |
| `batches.csv` | The 12 batches the drill orders use: number, item, quantity in P1 Stores, date, expiry, and which order uses how much. Leftover test batches (1-unit `-LOW-` batches, `-ACC-`/`-EXP-` acceptance batches, TEST-BATCH-01) are left out. |
| `batch-labels.html` | A printable sheet of those 12 batch labels, grouped by item. |
| `unit-labels.html` | A printable sheet of the 280 unit labels suggested for the orders, grouped by item. |
| `batches/<batch>.png` | CODE128 label for each batch with stock, from ERPNext's own renderer (Barcode Printing BP-2026-11-26-00017). |
| `units/<item>/<tracking id>.png` | CODE128 label for each suggested unit. It encodes the unit's 8-digit barcode. |
| `items/<item>.png` | CODE128 of the item code, for materials with no batch or unit label. |

The HTML sheets have the label images built in, so each one opens and prints on its own. `labels-2026-11-26.zip` (next to this folder) holds the whole folder.

## How each material is scanned

| `scan_mode` | Items | What the operator does |
|---|---|---|
| Scan every unit | SA-MOT-S, SA-HSG-DRL, SA-HARN-S, SA-GBX-DRL, SA-HSG-RH | Scan each unit's 8-digit barcode, or its QR or tracking ID. One scan counts as one unit. |
| Scan batch label, then quantity | The six drill raw materials ending in `-B` | On the order screen, **before Issue materials**, scan the 8-digit batch number of the batch you take from stores. The station counts the order's remaining need, up to what the batch has free, and Issue then moves exactly those batches in ERPNext. |
| Scan item, then quantity | Other materials counted in whole units | Scan the item code (`items/*.png`). |
| Confirm quantity | Materials by weight or length (wire, resin, varnish, paper) | Confirm the quantity on screen. |

## Drill batches

| Order | Item | Batches |
|---|---|---|
| MFG-WO-2026-00159 | FG-DRL-800 × 30 | 00000458 to 00000463 (your batches), 30 from each |
| MFG-WO-2026-00160 | FG-DRL-800-B × 25 | 00000703 to 00000708 (received today), 25 from each |
