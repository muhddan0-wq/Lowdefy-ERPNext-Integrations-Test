# Workflow test results

Run 2026-11-26T11:46:57: 42 of 45 checks pass.

| ID | Result | Criterion | Evidence |
|---|---|---|---|
| D1 | PASS | Finished products are discovered from active BOMs (every finished product, nothing else) | 7 products found, 7 expected |
| D2 | PASS | Sub-assemblies and raw materials are not reported as finished products | [] |
| D3 | PASS | Nested BOM is retrieved: SA-MOT-L expands into its own components | ['RM-BRG-6000', 'RM-BRG-6201', 'RM-BRUSH-6X8', 'RM-FAN-L', 'SA-ARM-L', 'SA-STA-L'] |
| D4 | PASS | Quantities are multiplied down the tree (per finished unit) | {'SA-ARM-L': (1.0, 1.0), 'SA-STA-L': (1.0, 1.0), 'RM-BRG-6000': (1.0, 1.0), 'RM-BRG-6201': (1.0, 1.0)} |
| D5 | PASS | A component without a BOM is a normal material with no children | RM-BLADE-185 |
| D6 | PASS | An item with no image gets no guessed image and a 'No image' flag | 35 nodes without image |
| D7 | PASS | Images come from ERPNext Item.image, never from a name guess | FG-DRL-800: 26 components with images |
| D8 | NOT TESTED | Circular BOM references are reported without infinite recursion | the sandbox has no circular BOM and this test does not write BOM master data; the cycle guard is in the prelude (mes_bom_node) |
| D9 | PASS | BOM signature is stable for an unchanged BOM | repeatable |
| P1 | PASS | Shopfloor user cannot use workflow discovery | denied |
| G1-FG-CS-1400 | FAIL | Draft generated from the BOM of FG-CS-1400: one step per direct component plus a final check | 13 steps (expected 10), status Draft |
| G2-FG-CS-1400 | PASS | Every generated step is flagged for review and none is High confidence | ['Expert Review', 'Missing Image'] |
| G3-FG-CS-1400 | PASS | Components without an image are flagged Missing Image in the draft | 4 |
| G4-FG-CS-1400 | PASS | Sub-assemblies come first and their steps list the ERPNext components to build from | Build sub-assembly: Motor Assembly 1400W |
| G5-FG-CS-1400 | PASS | A second generate is refused, so an existing draft is never silently replaced | refused (417) |
| G1-FG-RH-800 | FAIL | Draft generated from the BOM of FG-RH-800: one step per direct component plus a final check | 13 steps (expected 10), status Draft |
| G2-FG-RH-800 | PASS | Every generated step is flagged for review and none is High confidence | ['Expert Review', 'Missing Image'] |
| G3-FG-RH-800 | PASS | Components without an image are flagged Missing Image in the draft | 3 |
| G4-FG-RH-800 | PASS | Sub-assemblies come first and their steps list the ERPNext components to build from | Build sub-assembly: Motor Assembly 800W |
| G5-FG-RH-800 | PASS | A second generate is refused, so an existing draft is never silently replaced | refused (417) |
| E1-FG-CS-1400 | PASS | Admin edits are saved as version 2 with every step stored | (2, 14) |
| E2-FG-CS-1400 | PASS | A step pointing at an item that does not exist in ERPNext is rejected | frappe.exceptions.ValidationError: Step 15: item NOT-A-REAL-ITEM-9 does not exist in ERPNext |
| E3-FG-CS-1400 | PASS | Version history keeps both saved versions | [(2, 'Draft'), (1, 'Draft')] |
| E4-FG-CS-1400 | PASS | Original steps are kept after an edit (saving deletes nothing) | 14 |
| E1-FG-RH-800 | PASS | Admin edits are saved as version 2 with every step stored | (2, 14) |
| E2-FG-RH-800 | PASS | A step pointing at an item that does not exist in ERPNext is rejected | frappe.exceptions.ValidationError: Step 15: item NOT-A-REAL-ITEM-9 does not exist in ERPNext |
| E3-FG-RH-800 | PASS | Version history keeps both saved versions | [(2, 'Draft'), (1, 'Draft')] |
| E4-FG-RH-800 | PASS | Original steps are kept after an edit (saving deletes nothing) | 14 |
| A1 | PASS | Approval makes the saved version live; the response lists every flagged step | approved v2, 13 warnings |
| A2 | PASS | Approved steps are retrievable, each with its ERPNext image field | 14 |
| A3 | PASS | Generating a new draft over an approved workflow is refused | refused |
| J1 | PASS | Shopfloor job shows the approved workflow for its work order (dataset B) | v2, 14 steps |
| J2 | PASS | Employee view carries no admin-only fields (review flags, source, notes) | ['batch_required', 'checklist', 'comments', 'description', 'image', 'instructions', 'item_code', 'item_name'] |
| J3 | PASS | Exactly one step is Current | 1 |
| J4 | PASS | Work order is bound to the approved version | 2 |
| J5 | PASS | Material steps show the required quantity for this work order | [('SA-MOT-S', 25.0), ('SA-HSG-RH', 25.0), ('SA-HARN-S', 25.0)] |
| J6 | PASS | A newer approved version does not change a work order already bound to an older one | still v2 |
| J7 | PASS | Product with no approved workflow shows status none and no steps, without error | none |
| S1 | PASS | Sync check on an unchanged BOM reports In Sync | FG-CS-1400 In Sync |
| S2 | PASS | A quantity change in the BOM flags the matching step for review | Quantity Changed |
| S3 | PASS | A component removed from the BOM is reported and no step is added for it | Component Removed: NO-SUCH-COMPONENT-99 under FG-CS-1400 (was 1.0, now None)
Quantity Changed: RM-BLADE-185 under FG-CS-1400 (was 3.0, now 1.0) |
| S4 | PASS | Approved instructions are unchanged by the sync check | approved v2, 14 steps |
| S5 | PASS | Steps and version history are not deleted by a sync | 14 steps, 2 versions |
| S6 | PASS | Acknowledging the BOM change returns the workflow to In Sync without regenerating instructions | In Sync |
| P2 | PASS | Shopfloor user cannot approve workflows | denied |
