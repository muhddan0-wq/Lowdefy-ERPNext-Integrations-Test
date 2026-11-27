# Demo barcodes (clean build, 27 Nov 2026)

Every code here is a real ERPNext record on the sandbox (`http://localhost:8000`, company Voltra Power Tools Sdn Bhd).

## Main test order: MFG-WO-2026-00203, 13mm Electric Drill 800W (batch), FG-DRL-800-B × 5

Open `work-orders/MFG-WO-2026-00203_FG-DRL-800-B.html` and print it, or show it on a second screen and scan it from there.

| What | Scan mode | Codes |
|---|---|---|
| Motor Assembly 800W (SA-MOT-S) | every unit | 00000834 – 00000838 |
| Drill Housing Set (SA-HSG-DRL) | every unit | 00000794 – 00000798 |
| Switch & Cable Harness 10A (SA-HARN-S) | every unit | 00000774 – 00000778 |
| Drill Gearbox Assembly (SA-GBX-DRL) | every unit | 00000744 – 00000748 |
| Carton Box (RM-BOX-S-B) | batch, once | 00000839 |
| Keyless Chuck 13mm (RM-CHUCK-13-B) | batch, once | 00000840 |
| Rating Label set (RM-LABEL-B) | batch, once | 00000841 |
| User Manual (RM-MANUAL-B) | batch, once | 00000842 |
| Screw Kit M4 (RM-SCREW-KIT-B) | batch, once | 00000843 |
| Side Handle (RM-SIDE-HDL-B) | batch, once | 00000844 |

That is 20 unit scans plus 6 batch scans. Each batch holds 60, but the station counts only the 5 this order needs.

**Operator badge:** scan `HR-EMP-00009` (Hafiz Rahman, Final Assembly P1-FAL-01) from `badges.html`.

**Codes that should be refused (good to show):**
- Scanning the same unit twice gives "Duplicate scan".
- `99999999` gives "Unknown barcode".
- A unit from another order's list, for example `00000829` (an SA-MOT-S unit set aside for MFG-WO-2026-00204), is accepted. Units are interchangeable stock; the lists only stop two orders sharing a unit.

## Other orders with sheets

| Order | Product | Sheet |
|---|---|---|
| MFG-WO-2026-00204 | FG-DRL-800 × 5 | `work-orders/MFG-WO-2026-00204_FG-DRL-800.html` |
| MFG-WO-2026-00205 | FG-RH-800 × 5 | `work-orders/MFG-WO-2026-00205_FG-RH-800.html` |
| MFG-WO-2026-00206 | FG-CS-1400 × 5 | `work-orders/MFG-WO-2026-00206_FG-CS-1400.html` |

## Files

- `work-orders/*.html|csv`: one printable sheet and one CSV per order (`all-work-orders.csv` has all of them).
- `unit-labels.html`, `batch-labels.html`: every label, grouped by item.
- `badges.html`, `badges.csv`: operator ID badges (Employee ID).
- `units/`, `batches/`, `items/`, `badges/`: the individual PNGs.

To regenerate the sheets (from the repo root):

```powershell
python mes/setup/export_shopfloor_labels.py demo-barcodes MFG-WO-2026-00203 MFG-WO-2026-00204 MFG-WO-2026-00205 MFG-WO-2026-00206
```
