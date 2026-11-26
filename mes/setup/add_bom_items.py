"""Make a new default BOM version with extra component rows (idempotent). Submitted BOMs cannot be edited, so the
source BOM is copied, the rows are appended, and the copy is submitted as the item's default BOM. The source BOM
stays active, so open work orders keep the BOM they were made with. Runs inside the bench as Administrator.

Usage: FRAPPE_SITE=<site> python add_bom_items.py <source bom> <item_code>:<qty per unit> [...]
"""
import os
import sys

import frappe

args = sys.argv[1:]
if len(args) < 2:
    raise SystemExit(__doc__)
frappe.init(site=os.environ["FRAPPE_SITE"], sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
src = frappe.get_doc("BOM", args[0])
add = []
for a in args[1:]:
    code, qty = a.rsplit(":", 1)
    if not frappe.db.exists("Item", code):
        raise SystemExit("Item %s not found" % (code,))
    add.append((code, float(qty)))
want = {r.item_code for r in src.items} | {c for c, _ in add}
for name in frappe.get_all("BOM", filters={"item": src.item, "is_active": 1, "docstatus": 1}, pluck="name"):
    if {r.item_code for r in frappe.get_doc("BOM", name).items} == want:
        if not frappe.db.get_value("BOM", name, "is_default"):
            frappe.get_doc("BOM", name).db_set("is_default", 1)
            frappe.db.set_value("Item", src.item, "default_bom", name)
        print("unchanged bom", name, "already has", ", ".join(c for c, _ in add))
        frappe.destroy()
        raise SystemExit(0)
bom = frappe.copy_doc(src)
for code, qty in add:
    if code in {r.item_code for r in bom.items}:
        continue
    it = frappe.db.get_value("Item", code, ["item_name", "stock_uom"], as_dict=True)
    bom.append("items", {"item_code": code, "item_name": it.item_name, "qty": qty, "uom": it.stock_uom,
                         "stock_uom": it.stock_uom, "conversion_factor": 1})
bom.is_default = 1
bom.is_active = 1
bom.insert()
bom.submit()
frappe.db.commit()
print("created   bom", bom.name, "from", src.name, "adding", ", ".join("%s x%s" % a for a in add))
frappe.destroy()
