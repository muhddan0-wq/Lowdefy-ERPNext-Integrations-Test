# Shopfloor MES: Phase 1 audit and plan

Status: audit complete, and the plan has since been implemented. See [SHOPFLOOR-REPORT.md](SHOPFLOOR-REPORT.md).

Corrections found during implementation:
- Sub-assemblies **do** exist as Items, as `SA-*` codes (14 of them). The code regex below missed them.
- Two installed apps were missed: `item_tracking` (Tracked Item, unit-level IDs with barcode or QR) and
  `barcode_shrdc` (barcode labels). Unit scanning now uses Tracked Items.
- Serial tracking cannot be enabled on P1 items, because ERPNext refuses once an item has stock transactions.

## 1. Existing architecture (as found)

- **Appsmith** (http://localhost:8081) is the screen layer. Six pages are built from custom widgets in `mes/appsmith/widgets/` (work_orders, wo_detail, new_plan, schedule_board, capacity, queue). `build_app.py` generates `MES-Phase1.json` for import.
- **Backend** is ERPNext server scripts in `mes/server_scripts/` (`mes_*.py`). Each has a shared prelude (`_prelude.py`) and reads its inputs from `frappe.form_dict`. Permission is checked by role (Manufacturing User, Manufacturing Manager, System Manager) in the prelude.
- **Write path**: `mes_work_order_action.py` wraps ERPNext's own work order methods. Issue and finish build Stock Entries through `make_stock_entry`, then insert and submit them, so ERPNext stock validation applies.
- **Local harness**: `mes/appsmith/dev_harness.py` (http://127.0.0.1:8099) runs the widgets with a mock `appsmith` object and proxies to ERPNext. The API key stays on the server side.

## 2. ERPNext facts checked (via the API user `appsmith-mes@local.test`)

| Check | Result |
|---|---|
| P1 product codes in `products.yaml` | 45 codes. All 45 exist in ERPNext Item. |
| Item `image` field | **Empty for all 45.** Also empty for every other Item in the site. |
| Serial tracking (`has_serial_no`) | **Off for all 45.** Only `FRM-001` and `GO-KART` (outside P1) are serial-tracked. |
| Batch tracking | Off for all items checked. |
| Serial No records | None exist for P1 items. |
| Item Barcode DocType | **Permission denied** for the API user. |
| Asset, Issue, Maintenance Request, Quality Inspection | **Permission denied** for the API user. |
| File | Readable by the API user. Upload not yet tested. |
| Work Order | Readable. Two P1 orders, MFG-WO-2026-00036 (FG-DRL-800, qty 40) and MFG-WO-2026-00037 (FG-RH-800, qty 25). Both Not Started. |

## 3. Barcode and serial scanning

**There is no barcode or serial scanning in the MES today.** No widget or server script contains barcode, QR, or scan code. The spec's examples (SN-000125, SUB-MTR-01) cannot be validated because no P1 item tracks serial numbers.

Prerequisite decision: enable serial tracking on the items that need it (for example the motor and armature sub-assemblies). This changes ERPNext master data and only affects new stock, so it needs your approval.

## 4. Item images

- Folder: `mes/appsmith/ITEMIMAGEs/`, 58 files, untracked by git. Nothing serves it: the built Appsmith import does not include it, and the harness serves only the widget files. Appsmith cannot read it at runtime.
- Images are not stored in ERPNext. Item `image` is empty everywhere.

### Match results (ERPNext item codes against filenames)

Priority per spec: exact code, then exact name, then normalised filename, then manual.

- **Exact code match: 0**
- **Exact or normalised name match: 1**
  - `Ball Bearing 608ZZ.jpg` → `RM-BRG-608` (Ball Bearing 608ZZ)
- **Unmatched: 57.** No automatic assignment, per spec 3.2. Likely manual candidates, to confirm before any upload:
  - `Ball Bearing 6001ZZ.jpg` → `RM-BRG-6000` "Ball Bearing 6000ZZ" (digit differs)
  - `Commutator.jpg` → `RM-COMM-24` "Commutator 24-Bar"
  - `AluminiukGear.jpg` → `RM-GEARCASE-AL` "Aluminium Die-Cast Gear Case" (typo in filename)
  - `AluminiumBaseplate.jpg` → `RM-BASE-CS` "Aluminium Base Plate 185mm"
  - `SawBlade185mm.jpg` → `RM-BLADE-185` "TCT Saw Blade 185mm 24T"
  - `TriggerSwitch.jpg` → `RM-SW-TRIG` or `RM-SW-SAW` (two candidates, so ambiguous)
  - `PowerCord.jpg` → `RM-CABLE` "Power Cable 2.5m"
  - `KeylessChuck.jpg` → `RM-CHUCK-13`
  - `CarbonBrushSet.jpg` → `RM-BRUSH-6X8`
  - `CoolingFan.jpg` → `RM-FAN-S` or `RM-FAN-L` (ambiguous)
  - Many `Drill*`, `Saw*`, `Hammer*` files (for example `DrillMotor.jpg`, `SawMotor.jpg`, `HammerArmature.jpg`) describe sub-assemblies. `products.yaml` has no `SUB-` codes; the 45 codes are all `FG-` or `RM-`, so these sub-assemblies have no matching Item and stay unmatched.

Images for finished goods (`ElectricDrill.jpg`, `RotaryHammerDrill.jpg`, `Circular Saw.jpg`) map to FG-DRL-800, FG-RH-800, FG-CS-1400. These should match by name with confirmation.

The filenames carry no item codes, so matching is by name. The result is a short list of likely matches that needs a human pass before upload.

## 5. Gaps against the spec

| Spec requirement | Current state |
|---|---|
| Shopfloor landing page, job selection | Not built. Current pages are admin-style schedule and queue views. |
| Item images in Appsmith | Not possible: no ERPNext images, and local folder is not served. |
| Material verification and scanning | Not built. No serial tracking on P1 items. |
| Defect reporting with attachments | Not built. |
| Machine issue reporting | Not built. API user cannot read Maintenance Request, Issue or Asset. |
| Notifications to admins | Not built. |
| Production completion validation | Partial. `mes_work_order_action.py` can issue and finish, but has no material-verification or defect checks. |
| Roles beyond Manufacturing User/Manager | Not built. The prelude only checks Manufacturing roles. |
| Shopfloor activity audit | Not built. |

## 6. Decisions needed before implementation

1. **Serial tracking.** Turn on serial numbers for the sub-assemblies that the spec requires scanning (motor, armature, stator and similar), or start with quantity-based verification only? Enabling serials changes master data and applies to new stock only.
2. **Machine issues.** The API user cannot read Maintenance Request, Asset or Issue. Options:
   - (a) grant the API user access to Maintenance Request and Asset, or
   - (b) create a dedicated MES Machine Issue DocType in ERPNext and link it to a Workstation (the workstation is the machine in this site).
   I recommend (b). It avoids widening the API user's rights across maintenance data, and it can link to Workstation, which already exists.
3. **Item images.** Approve the candidate matches above (and the finished-goods name matches) before anything is written to ERPNext. I will not assign ambiguous images.
4. **New MES tables.** Scan history, defect reports and machine issues should be ERPNext DocTypes created by a custom app or Custom Fields, not an external database, so they keep ERPNext permissions. This is a larger change and needs your go-ahead.

## 7. Proposed implementation order

Follows the spec's phases, with the decisions above applied first.

1. **Phase 2, images.** After approval, upload each confirmed image through the File API, set `Item.image`, then verify the URL is retrievable. Write an import report with filename, item code, item name, upload status, match status, and errors.
2. **Phase 3, shopfloor home.** New `shopfloor` page and widget with job selection from Work Orders assigned to the user, large controls, and placeholders for missing images.
3. **Phase 4, scanning.** Backend `mes_material_scan.py`: validate against BOM, serial state, warehouse and quantity, under a database row lock to prevent two employees consuming the same serial. Record valid and invalid scans in a scan log.
4. **Phase 5, defects.** Defect Report DocType with ERPNext File attachments. No automatic stock movement.
5. **Phase 6, machine issues.** Machine Issue DocType linked to Workstation, admin list with status, and a restriction on starting operations on a Completely Down workstation.
6. **Phase 7, completion.** Backend check of all gates (materials verified, quantities, serials, defect disposition, machine status) before calling the existing finish action.
7. **Phase 8, tests.** Run each acceptance criterion against the sandbox and record pass or fail with evidence. No feature is claimed working until it has been tested.

## 8. Not verified in this phase

- Whether the API user can upload Files and write `Item.image`. Not tested, because it changes ERPNext data and is waiting on approval.
- Whether the shopfloor role model can be built on ERPNext's own roles. Not checked.
- Camera scanning in Appsmith. No browser camera test has been done.
