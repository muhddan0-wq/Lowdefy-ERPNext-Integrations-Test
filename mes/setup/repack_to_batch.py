"""Move existing stock of an item into one new batch of its batch-tracked copy (<item>-B) with an ERPNext Repack
entry: qty leaves <item> and enters <item>-B in the same warehouse, so total stock and value do not change.
The batch is named by ERPNext on submit, which item_tracking turns into the next 8-digit shared number.
Runs inside the bench as Administrator.

Usage: FRAPPE_SITE=<site> python repack_to_batch.py <company> <warehouse> <qty> <item_code> [...]
"""
import os
import sys

import frappe

args = sys.argv[1:]
if len(args) < 4:
    raise SystemExit(__doc__)
company, warehouse, qty, items = args[0], args[1], float(args[2]), args[3:]
frappe.init(site=os.environ["FRAPPE_SITE"], sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
for code in items:
    target = code + "-B"
    if not frappe.db.get_value("Item", target, "has_batch_no"):
        raise SystemExit("%s is not a batch-tracked item: run create_batch_item.py %s first" % (target, code))
    have = frappe.db.get_value("Bin", {"item_code": code, "warehouse": warehouse}, "actual_qty") or 0
    if have < qty:
        raise SystemExit("%s has only %s in %s, %s needed" % (code, have, warehouse, qty))
    se = frappe.new_doc("Stock Entry")
    se.company = company
    se.stock_entry_type = "Repack"
    se.purpose = "Repack"
    se.remarks = "Repack %s %s into a batch of %s" % (qty, code, target)
    se.append("items", {"item_code": code, "qty": qty, "s_warehouse": warehouse})
    se.append("items", {"item_code": target, "qty": qty, "t_warehouse": warehouse, "is_finished_item": 1})
    se.insert()
    se.submit()
    frappe.db.commit()
    se.reload()
    row = [d for d in se.items if d.item_code == target][0]
    batch = row.batch_no or frappe.db.get_value("Serial and Batch Entry", {"parent": row.serial_and_batch_bundle}, "batch_no")
    print("%s: %s %s -> batch %s of %s (%s), %s now %s" % (se.name, qty, code, batch, target,
          frappe.db.get_value("Batch", batch, "batch_qty"), code, frappe.db.get_value("Bin", {"item_code": code, "warehouse": warehouse}, "actual_qty")))
frappe.destroy()
