"""Create a batch-tracked copy of an item that already has stock history (idempotent).

ERPNext refuses to switch on has_batch_no for an item with stock transactions, so the MES uses a copy named
<item>-B with batch numbers on, the same valuation rate, and (for a manufactured item) a submitted default BOM
copied from --bom. Runs inside the bench as Administrator.

Usage: FRAPPE_SITE=<site> python create_batch_item.py <item_code> [--bom <bom name>]
"""
import os
import sys

import frappe

SKIP = {"name", "item_code", "creation", "modified", "owner", "modified_by", "docstatus", "idx",
        "has_batch_no", "create_new_batch", "batch_number_series", "has_serial_no", "serial_no_series",
        "barcodes", "item_defaults", "uoms", "reorder_levels", "supplier_items", "customer_items", "taxes",
        "attributes", "website_specifications", "default_bom"}


def copy_item(src_code):
    new_code = src_code + "-B"
    if frappe.db.exists("Item", new_code):
        doc = frappe.get_doc("Item", new_code)
        if not doc.has_batch_no:
            doc.has_batch_no = 1
            doc.save()
            print("enabled   batch on", new_code)
        else:
            print("unchanged item", new_code)
        return new_code
    src = frappe.get_doc("Item", src_code)
    data = {k: v for k, v in src.as_dict().items() if k not in SKIP and not isinstance(v, list)}
    data.update({"doctype": "Item", "item_code": new_code, "item_name": (src.item_name or src_code) + " (batch)",
                 "has_batch_no": 1, "create_new_batch": 1, "has_serial_no": 0, "is_stock_item": 1})
    doc = frappe.get_doc(data)
    for d in src.item_defaults:
        doc.append("item_defaults", {"company": d.company, "default_warehouse": d.default_warehouse})
    doc.insert()
    print("created   item", new_code)
    return new_code


def copy_bom(bom_name, item_code):
    have = frappe.get_all("BOM", filters={"item": item_code, "docstatus": 1, "is_active": 1}, pluck="name")
    if have:
        print("unchanged bom", have[0])
        return have[0]
    src = frappe.get_doc("BOM", bom_name)
    bom = frappe.copy_doc(src)
    bom.item = item_code
    bom.item_name = frappe.db.get_value("Item", item_code, "item_name")
    bom.is_default = 1
    bom.is_active = 1
    bom.insert()
    bom.submit()
    print("created   bom", bom.name, "from", bom_name)
    return bom.name


args = sys.argv[1:]
if not args:
    raise SystemExit(__doc__)
frappe.init(site=os.environ["FRAPPE_SITE"], sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
code = copy_item(args[0])
if "--bom" in args:
    copy_bom(args[args.index("--bom") + 1], code)
frappe.db.commit()
frappe.destroy()
