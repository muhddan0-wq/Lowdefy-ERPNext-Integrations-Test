"""Point every tracked unit's 1D barcode at the 8 digits of its serial (SN-00000077 -> 00000077), idempotent.

New units get this from item_tracking itself; this updates units created before the change. Units without an
SN-######## serial keep their tracking ID. Old labels keep working: the MES and item_tracking scanners still
resolve the tracking ID. Runs inside the bench as Administrator (see install-mes.ps1 -Only barcodes).
"""
import os

import frappe

frappe.init(site=os.environ["FRAPPE_SITE"], sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
if not frappe.db.exists("DocType", "Tracked Item"):
    print("no Tracked Item DocType: nothing to do")
else:
    rows = frappe.db.sql("""select name, serial_no, barcode from `tabTracked Item`
        where serial_no regexp '^SN-[0-9]{8}$' and coalesce(barcode, '') != substring(serial_no, 4)""", as_dict=True)
    for r in rows:
        frappe.db.set_value("Tracked Item", r.name, "barcode", r.serial_no[3:], update_modified=False)
    frappe.db.commit()
    total = frappe.db.count("Tracked Item")
    short = frappe.db.sql("select count(*) from `tabTracked Item` where barcode regexp '^[0-9]{8}$'")[0][0]
    print(f"unit barcodes updated {len(rows)}; {short} of {total} units now carry an 8-digit barcode")
frappe.destroy()
