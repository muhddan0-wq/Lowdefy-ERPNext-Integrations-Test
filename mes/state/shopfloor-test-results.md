# Shopfloor acceptance test results

Run 2026-11-26 11:46 against http://localhost:8000. Fixtures: work orders MFG-WO-2026-00048 (job PO-JOB00066), MFG-WO-2026-00141 (job PO-JOB00271), MFG-WO-2026-00142 (job PO-JOB00274); tracked units SA-MOT-S-0011, SA-MOT-S-0012.

Passed 55, failed 0, not tested 0.

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| I1 | ERPNext items are retrieved correctly | PASS | {'FG-RH-800': '/files/RotaryHammerDrill.jpg', 'RM-SHAFT-L': '/files/SawArmatureShaft.jpg', 'SA-ARM-L': '/files/SawArmature.jpg'} |
| I2 | Imported images are linked to the correct items and served by ERPNext | PASS | FG-RH-800 image /files/RotaryHammerDrill.jpg |
| I3 | Images are only ERPNext item images or empty (UI shows placeholder, nothing breaks) | PASS | SA-ARM-L image='/files/SawArmature.jpg' |
| I4 | Materials are issued to each fixture job with stock (ERPNext material transfer, required before production starts) | PASS | [('PO-JOB00066', {'needed': True, 'issued': 30.0, 'left': 0.0, 'entries': [{'name': 'MAT-STE-2026-00077', 'posting_date': '2026-11-26', 'fg_completed_qty': 30.0}]}), ('PO-JOB00271', {'needed': True, 'issued': 2.0, 'left': 0.0, 'entries': [{'name': 'MAT-STE-2026-00078', 'posting_date': '2026-11-26', 'fg_completed_qty': 2.0}]}), ('PO-JOB00274', {'shortage reported': ['SA-HSG-RH Rotary Hammer Housing Set: need 1.0, 0.0 in P1 Stores - VPT']})] |
| M1 | Employee can open an assigned job / work order | PASS | {'job_card': 'PO-JOB00271', 'operation': 'Final Assembly', 'workstation': 'P1-FAL-01', 'docstatus': 0, 'status': 'Open', 'qty': 2.0, 'completed_qty': 0.0, 'remaining_qty': 2.0, 'running_since': None, 'time_logs': []} |
| M2 | Employee sees the finished product | PASS | SDS-Plus Rotary Hammer Drill 800W |
| M3 | Employee sees all required BOM materials | PASS | ['RM-CASE-BMC', 'RM-LABEL', 'RM-MANUAL', 'RM-SCREW-KIT', 'RM-SIDE-HDL', 'SA-HARN-S', 'SA-HMECH-RH', 'SA-HSG-RH', 'SA-MOT-S'] |
| M4 | Materials needing unit/serial scanning are identified | PASS | SA-MOT-S=unit, RM-SHAFT-L=scan, RM-INS-PAPER=confirm |
| M5 | Valid tracked unit is accepted | PASS | ('Valid', 'Verified as tracked unit', 1) |
| M6 | Duplicate unit scan on the same work order is rejected with a reason | PASS | Duplicate scan: unit SA-MOT-S-0011 is already recorded on this work order (MES-SCN-00222) |
| M7 | Unit already used on another work order cannot be reused | PASS | Unit SA-MOT-S-0011 was already used on work order MFG-WO-2026-00141 |
| M8 | Incorrect item is rejected and the expected materials are named | PASS | Incorrect item: RM-BOX-S-B Carton Box (Drill / Rotary Hammer) is not required for work order MFG-WO-2026-00141. Expected: SA-MOT-S, SA-HSG-RH, SA-HARN-S, SA-HMECH-RH, RM-SIDE-HDL, RM-SCREW-KIT, RM-LABEL, RM-MANUAL, RM-CASE-BMC |
| M9 | Unknown barcode is rejected with a reason | PASS | Unknown barcode or serial number: NO-SUCH-CODE-123 is not an item, barcode, serial number or tracked unit in ERPNext |
| M10 | Scanning the item code of a unit-tracked material is refused (each unit must be scanned) | PASS | SA-MOT-S is tracked per unit: scan the unit's own label, not the item code |
| M11 | Quantity above the requirement is rejected | PASS | Quantity exceeds requirement: only 2.0 Nos of SA-HMECH-RH still needed |
| M12 | Invalid scans never count towards verification | PASS | invalid scans 2 -> 3, verified materials unchanged 0 |
| M13 | Fractional quantity of a whole-unit item is rejected | PASS | SA-HMECH-RH is counted in whole Nos: 2.5 is not a whole number |
| R1 | Duplicate submission (same request id) is stored once | PASS | first MES-SCN-00230, replay MES-SCN-00230 replayed=True, verified 1 |
| R2 | Simultaneous scans of the same unit on two work orders: exactly one succeeds | PASS | results [True, False], requests overlapped in time: True, reasons ['Verified as tracked unit', 'Unit SA-MOT-S-0012 was already used on work order MFG-WO-2026-00141'] |
| R3 | Simultaneous quantity confirmations cannot overshoot the requirement (row lock) | PASS | two x 14.4 of 24.0 required -> verified 14.4; ['Verified as item code', 'Quantity exceeds requirement: only 9.6 Meter of RM-INS-PAPER still needed'] |
| M14 | Quantity-based materials can be confirmed until verified | PASS | {'materials_total': 6, 'materials_verified': 6, 'outstanding': 0, 'invalid_scans': 1, 'defective': 0, 'open_defects': 0} |
| C1 | Unverified materials prevent reporting good units (starting only needs the materials issued) | PASS | ('Work In Progress', 'frappe.exceptions.ValidationError: Scan every required item before reporting finished units. Still to verify: SA-HSG-RH, SA-HARN-S, SA-HMECH-RH, RM-SIDE-HDL, RM') |
| C2 | Missing materials prevent completing production | PASS | ['SA-HSG-RH Rotary Hammer Housing Set: 0.0 of 2.0 Nos verified (Awaiting Scan)', 'SA-HARN-S Switch & Cable Harness 10A: 0.0 of 2.0 Nos verified (Awaiting Scan)'] |
| C3 | Partial quantities are reported as blocking (backend gate) | PASS | ['SA-HMECH-RH Hammer Mechanism Assembly: 1.0 of 2.0 Nos verified (Partially Verified)'] |
| D1 | Employee can report a defective material with comments | PASS | {'ok': True, 'replayed': False, 'defect': 'MES-DEF-00014', 'files': [{'file_name': 'damage.png', 'file_url': '/private/files/damage.png'}, {'file_name': 'note.txt', 'file_url': '/private/files/note.txt'}], 'flagged_scans': ['MES-SCN-00222'], 'notified': ['Administrator', 'muhddan0@gmail.com', 'planner@fix.local', 'sup1@local.test']} |
| D2 | Employee can attach photographs and files (stored as ERPNext Files) | PASS | [{'file_name': 'damage.png', 'file_url': '/private/files/damage.png'}, {'file_name': 'note.txt', 'file_url': '/private/files/note.txt'}] |
| D3 | A defective unit stops counting as verified | PASS | ('Defective Material', 1) |
| D4 | A unit with an open defect cannot be scanned elsewhere | PASS | Unit SA-MOT-S-0011 was already used on work order MFG-WO-2026-00141 |
| D5 | Supervisors can review defect reports (with attachments) | PASS | defects listed: 14 |
| P1 | Shopfloor employee cannot decide (override) a defect | PASS | frappe.exceptions.PermissionError: Not permitted: only supervisors decide defects |
| D6 | A defect cannot be resolved without a disposition | PASS | frappe.exceptions.ValidationError: Choose a disposition before marking the defect Resolved |
| D7 | Supervisor can authorise a disposition; a replaced unit stays excluded | PASS | status Partially Verified, valid units 1 (expected 1 after R2) |
| D8 | Employees can view their own submitted reports | PASS | 14 |
| C4 | An open defect blocks completion until a supervisor decides it | PASS | ['RM-SHAFT-L Armature Shaft 10mm: 29.0 of 30.0 Nos verified (Defective Material)', 'Defect MES-DEF-00015 on RM-SHAFT-L is Reported and needs a supervisor decision'] |
| X1 | Employee can report a machine breakdown with a photo | PASS | {'ok': True, 'replayed': False, 'issue': 'MES-MCH-00015', 'severity': 'Critical', 'files': [{'file_name': 'panel.png', 'file_url': '/private/files/damage.png'}], 'notified': ['Administrator', 'maint1@local.test', 'muhddan0@gmail.com', 'planner@fix.local', 'sup1@local.test'], 'blocked_job_cards': ['PO-JOB00233', 'PO-JOB00220', 'PO-JOB00194', 'PO-JOB00162', 'PO-JOB00132', 'PO-JOB00130', 'PO-JOB00068', 'PO-JOB00066']} |
| X2 | Priority follows machine state (Completely Down raises Low to Critical) | PASS | Critical |
| X3 | Maintenance and managers receive an ERPNext notification | PASS | ['sup1@local.test', 'planner@fix.local', 'muhddan0@gmail.com', 'maint1@local.test', 'Administrator'] |
| X4 | Employee can report a machine stall (priority raised to High) | PASS | {'ok': True, 'replayed': False, 'issue': 'MES-MCH-00016', 'severity': 'High', 'files': [], 'notified': ['Administrator', 'maint1@local.test', 'muhddan0@gmail.com', 'planner@fix.local', 'sup1@local.test'], 'blocked_job_cards': []} |
| X5 | Machine issues appear on the maintenance dashboard | PASS | 16 |
| X6 | A Completely Down machine blocks the affected job | PASS | ['Machine P1-WND-02 is Completely Down (issue MES-MCH-00015); maintenance must resolve it first'] |
| X7 | Other workstations are not stopped by one machine's issue | PASS | 15 jobs on P1-FAL-01, none flagged down |
| P2 | Shopfloor employee cannot resolve a machine issue | PASS | frappe.exceptions.PermissionError: Not permitted: only maintenance can assign, progress or resolve machine issues |
| P3 | Supervisor cannot resolve a machine issue (maintenance only) | PASS | frappe.exceptions.PermissionError: Not permitted: only maintenance can assign, progress or resolve machine issues |
| X8 | Maintenance can acknowledge, assign and resolve (notes required) | PASS | ack 200, resolve without notes -> 417, resolve with notes -> Resolved |
| C5 | Once defects are decided and the machine is back, the job is clear to start | PASS | [] |
| P4 | Maintenance-only users cannot record material scans | PASS | frappe.exceptions.PermissionError: Not permitted: this needs operate rights |
| C6 | Employee can start production once all checks pass | PASS | {'ok': True, 'action': 'start', 'job_card': 'PO-JOB00066', 'blocking': [], 'status': 'Work In Progress', 'docstatus': 0, 'completed_qty': 0.0, 'qty': 30.0} |
| C7 | Employee can report progress (good quantity) on the ERPNext Job Card | PASS | {'ok': True, 'action': 'report', 'job_card': 'PO-JOB00066', 'blocking': [], 'running': True, 'status': 'Work In Progress', 'docstatus': 0, 'completed_qty': 15.0, 'qty': 30.0} |
| C8 | A completed quantity above the job quantity is refused | PASS | frappe.exceptions.ValidationError: Quantity too high: 15.0 already done, 10000.0 more would exceed the job quantity 30.0 |
| C9 | Valid completion submits the ERPNext Job Card | PASS | {'ok': True, 'action': 'complete', 'job_card': 'PO-JOB00066', 'blocking': [], 'status': 'Completed', 'docstatus': 1, 'completed_qty': 30.0, 'qty': 30.0} |
| C10 | The work order operation is updated by ERPNext | PASS | [('Armature Winding', 30.0, 'Completed')] |
| C11 | Finishing a work order via the planner API is refused while materials are unverified (no stock entry made) | PASS | MFG-WO-2026-00056: HTTP 417, stock entries 78 -> 78 |
| P5 | Calls without a valid ERPNext operator are refused | PASS | frappe.exceptions.PermissionError: someone@nowhere.test is not an active ERPNext user for the shopfloor |
| F1 | API errors return an error status, never a success payload | PASS | (417, 'frappe.exceptions.ValidationError: Job card NO-SUCH-JC not found') |
| A1 | Audit history is kept (scans stored, change history on defect reports, comments on work orders) | PASS | defect report versions: 14 |
