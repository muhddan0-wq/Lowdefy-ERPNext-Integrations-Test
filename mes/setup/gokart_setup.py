"""Go-Kart showcase line in the Voltra plant: a Voltra BOM for the existing GO-KART item (Frame, Steering Wheel, 4 Wheels,
Seat) routed through P1 Final Assembly, Test and Packing, stock in P1 Stores and open work orders.

The go-kart items are shared with SHRDC and linked to live Shopify products, so no Item is saved here (an Item save
syncs to Shopify). The BOM is not made default, so SHRDC's BOM-GO-KART-001 stays the item's default.
Serial-numbered parts (Frame, Seat) get ERPNext serial numbers; Wheels and Steering Wheels get item_tracking units with
8-digit barcodes.

Runs inside the bench: FRAPPE_SITE=frontend ../env/bin/python gokart_setup.py <site.yaml> [--orders N,N...] [--stock-sets N]
"""
import json
import os
import sys

import frappe
import yaml
from frappe.model.naming import make_autoname
from frappe.utils import get_datetime

FG = "GO-KART"
PARTS = [("FRM-001", 1), ("STR-001", 1), ("WHL-001", 4), ("SEAT-001", 1)]
OPS = [("Final Assembly", "P1 Final Assembly Line", 25), ("Hi-Pot & Function Test", "P1 Electrical Safety & Run Test", 6),
       ("Packing", "P1 Packing", 5)]
REMARK = "Go-Kart showcase"


def phase(msg):
    print(f"[gokart] {msg}", flush=True)


def buy_rate(code):
    return frappe.db.get_value("Item Price", {"item_code": code, "price_list": "Standard Buying"}, "price_list_rate") or 100


def ensure_bom(company):
    bom = frappe.db.get_value("BOM", {"item": FG, "company": company, "docstatus": 1, "is_active": 1}, "name")
    if bom:
        return bom
    doc = frappe.get_doc({
        "doctype": "BOM", "item": FG, "company": company, "quantity": 1, "is_active": 1, "is_default": 0,
        "with_operations": 1, "rm_cost_as_per": "Price List", "buying_price_list": "Standard Buying", "currency": "MYR",
        "transfer_material_against": "Work Order",
        "items": [{"item_code": c, "qty": q, "rate": buy_rate(c)} for c, q in PARTS],
        "operations": [{"operation": o, "workstation_type": wt, "time_in_mins": t, "sequence_id": i + 1} for i, (o, wt, t) in enumerate(OPS)],
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    phase(f"BOM {doc.name}: cost MYR {doc.total_cost:,.2f}")
    return doc.name


def receipt(company, stores, rows, remark, tracked):
    import item_tracking.item_tracking.events as ev
    orig = ev._auto_create_tracked_items
    if not tracked:
        ev._auto_create_tracked_items = lambda *a, **k: []
    try:
        items = []
        for code, qty in rows:
            row = {"item_code": code, "qty": qty, "t_warehouse": stores, "basic_rate": buy_rate(code), "uom": "Nos",
                   "conversion_factor": 1}
            series = frappe.db.get_value("Item", code, ["has_serial_no", "serial_no_series"], as_dict=True)
            if series.has_serial_no:
                row["serial_no"] = "\n".join(make_autoname(series.serial_no_series or (code + "-.####")) for _ in range(int(qty)))
                row["use_serial_batch_fields"] = 1
            items.append(row)
        se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
                             "company": company, "remarks": f"{REMARK}: {remark}", "items": items})
        se.insert(ignore_permissions=True)
        se.submit()
    finally:
        ev._auto_create_tracked_items = orig
    phase(f"receipt {se.name}: {remark}, MYR {se.total_incoming_value:,.2f}")
    return se.name


def work_order(company, w, bom, qty, start):
    wo = frappe.get_doc({
        "doctype": "Work Order", "company": company, "production_item": FG, "bom_no": bom, "qty": qty,
        "use_multi_level_bom": 0, "source_warehouse": w["stores"], "wip_warehouse": w["wip"], "fg_warehouse": w["fg"],
        "planned_start_date": start,
    })
    wo.set_work_order_operations()
    wo.insert(ignore_permissions=True)
    wo.submit()
    jcs = frappe.get_all("Job Card", filters={"work_order": wo.name}, fields=["name", "workstation"], order_by="sequence_id asc")
    phase(f"work order {wo.name}: {FG} x {qty}, job cards {', '.join(j.name + ' ' + j.workstation for j in jcs)}")
    return {"name": wo.name, "qty": qty, "job_cards": [(j.name, j.workstation) for j in jcs]}


def main():
    S = yaml.safe_load(open(sys.argv[1]))
    args = sys.argv[2:]
    orders = [float(x) for x in args[args.index("--orders") + 1].split(",")] if "--orders" in args else [3]
    sets = int(args[args.index("--stock-sets") + 1]) if "--stock-sets" in args else 0
    company = S["company"]["name"]
    w = S["warehouses"]
    frappe.init(site=os.environ.get("FRAPPE_SITE", "frontend"), sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")
    out = {}
    try:
        out["bom"] = ensure_bom(company)
        frappe.db.commit()
        if sets:
            out["serial_receipt"] = receipt(company, w["stores"], [(c, q * sets) for c, q in PARTS if c in ("FRM-001", "SEAT-001")],
                                            "serial-numbered frames and seats", False)
            frappe.db.commit()
            out["unit_receipt"] = receipt(company, w["stores"], [(c, q * sets) for c, q in PARTS if c in ("WHL-001", "STR-001")],
                                          "wheels and steering wheels (8-digit unit barcodes)", True)
            frappe.db.commit()
        start = get_datetime(os.environ.get("DEMO_START") or frappe.utils.now_datetime().strftime("%Y-%m-%d 08:00:00"))
        out["work_orders"] = [work_order(company, w, out["bom"], q, start) for q in orders if q > 0]
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        print(json.dumps(out, default=str))
        frappe.destroy()


if __name__ == "__main__":
    main()
