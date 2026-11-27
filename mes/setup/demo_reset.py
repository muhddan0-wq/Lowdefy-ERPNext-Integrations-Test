"""Demo reset: remove test/demo junk items, wipe every Voltra transaction (work orders, job cards, stock, scans, defects,
batches, tracked units) and rebuild a clean demo floor: fresh stock (raw materials, per-unit sub-assemblies with
8-digit barcodes, one batch per -B raw material) and one open work order per default BOM.

Masters stay: company, items, BOMs, workstations, employees, roles, users, server scripts, assembly workflows.

Runs inside the bench: FRAPPE_SITE=frontend ../env/bin/python demo_reset.py <products.yaml> <site.yaml> [--wipe-only | --orders-only]
"""
import json
import math
import sys
from collections import defaultdict

import frappe
import yaml
from frappe.utils import add_to_date, get_datetime, now_datetime

JUNK_ITEM_REGEX = "^(TEST-|DEMO-SKU|TRACK-DEMO|EXAMPLE-)"
JUNK_SALES_ORDERS = ["SAL-ORD-2026-01504", "SAL-ORD-2026-01505"]
JUNK_CUSTOMERS = ["Replay Buyer", "Multi Line"]
UNIT_ITEMS = ["SA-GBX-DRL", "SA-HARN-S", "SA-HSG-DRL", "SA-HSG-RH", "SA-MOT-S"]
FG_QTY = 5
SA_QTY = 10
STOCK_FACTOR = 2
WO_ORDER = ["FG-DRL-800-B", "FG-DRL-800", "FG-RH-800", "FG-CS-1400"]

LOG = {"junk": {}, "wiped": {}, "receipts": [], "work_orders": []}


def phase(msg):
    print(f"[demo-reset] {msg}", flush=True)


def delete_docs(dt, names):
    names = list(names)
    if not names:
        return 0
    meta = frappe.get_meta(dt)
    for i in range(0, len(names), 500):
        chunk = names[i:i + 500]
        for tf in meta.get_table_fields():
            frappe.db.delete(tf.options, {"parent": ("in", chunk), "parenttype": dt})
        for ref in ("Comment", "Communication"):
            frappe.db.delete(ref, {"reference_doctype": dt, "reference_name": ("in", chunk)})
        frappe.db.delete("Version", {"ref_doctype": dt, "docname": ("in", chunk)})
        frappe.db.delete(dt, {"name": ("in", chunk)})
    LOG["wiped"][dt] = LOG["wiped"].get(dt, 0) + len(names)
    return len(names)


def remove_junk():
    items = frappe.db.sql_list("select name from tabItem where name regexp %s", JUNK_ITEM_REGEX)
    sos = [s for s in JUNK_SALES_ORDERS if frappe.db.get_value("Sales Order", s, "docstatus") == 0]
    delete_docs("Sales Order", sos)
    delete_docs("Customer", [c for c in JUNK_CUSTOMERS if frappe.db.exists("Customer", c) and not frappe.db.exists("Sales Order", {"customer": c})])
    for item in items:
        for dt, f in (("Tracked Item", "item_code"), ("Batch", "item"), ("Bin", "item_code"), ("Item Price", "item_code"),
                      ("Stock Ledger Entry", "item_code")):
            delete_docs(dt, frappe.get_all(dt, filters={f: item}, pluck="name"))
    delete_docs("Item", items)
    LOG["junk"] = {"items": items, "sales_orders": sos, "customers": JUNK_CUSTOMERS}
    phase(f"junk removed: {len(items)} items, {len(sos)} draft sales orders")


def voltra_items(company):
    defaults = set(frappe.get_all("Item Default", filters={"company": company, "parenttype": "Item"}, pluck="parent"))
    bom_items = set(frappe.get_all("BOM", filters={"company": company}, pluck="item"))
    bom_items |= set(frappe.db.sql_list("select distinct bi.item_code from `tabBOM Item` bi join tabBOM b on b.name = bi.parent where b.company = %s", company))
    return sorted(defaults | bom_items)


def snapshot_rates(company):
    rates = {}
    for item, rate in frappe.db.sql("select item_code, max(valuation_rate) from tabBin where company = %s group by item_code", company):
        if rate:
            rates[item] = float(rate)
    return rates


def wipe_voltra(company, items):
    wos = frappe.get_all("Work Order", filters={"company": company}, pluck="name")
    delete_docs("MES Workflow Binding", frappe.get_all("MES Workflow Binding", filters={"work_order": ("in", wos or [""])}, pluck="name"))
    for dt in ("MES Material Scan", "MES Defect Report", "MES Machine Issue"):
        delete_docs(dt, frappe.db.sql_list(f"select name from `tab{dt}` where ifnull(work_order, '') = '' or work_order in %(w)s", {"w": wos or [""]}))
    if frappe.db.exists("DocType", "MES Batch Genealogy"):
        delete_docs("MES Batch Genealogy", frappe.get_all("MES Batch Genealogy", pluck="name"))
    if frappe.db.exists("DocType", "Downtime Entry"):
        delete_docs("Downtime Entry", frappe.db.sql_list("select name from `tabDowntime Entry` where workstation like 'P1-%%'"))
    for dt in ("Stock Entry", "Job Card", "Work Order", "Production Plan", "Serial and Batch Bundle", "Repost Item Valuation",
               "Stock Ledger Entry", "GL Entry", "Payment Ledger Entry", "Stock Reservation Entry", "Bin", "Barcode Printing",
               "Material Request", "Quality Inspection"):
        if not frappe.db.exists("DocType", dt) or not frappe.get_meta(dt).has_field("company"):
            continue
        delete_docs(dt, frappe.get_all(dt, filters={"company": company}, pluck="name"))
    delete_docs("Tracked Item", frappe.get_all("Tracked Item", filters={"item_code": ("in", items)}, pluck="name"))
    if frappe.db.exists("DocType", "Item Tracking History"):
        delete_docs("Item Tracking History", frappe.get_all("Item Tracking History", pluck="name"))
    delete_docs("Batch", frappe.get_all("Batch", filters={"item": ("in", items)}, pluck="name"))
    delete_docs("Serial No", frappe.get_all("Serial No", filters={"item_code": ("in", items)}, pluck="name"))
    for ws in frappe.get_all("Workstation", filters={"name": ("like", "P1-%")}, pluck="name"):
        if frappe.get_meta("Workstation").has_field("status"):
            frappe.db.set_value("Workstation", ws, "status", "Off", update_modified=False)
    phase("voltra wiped: " + ", ".join(f"{k} {v}" for k, v in LOG["wiped"].items()))


def default_bom(item, company):
    return frappe.db.get_value("BOM", {"item": item, "company": company, "is_default": 1, "docstatus": 1, "is_active": 1}, "name")


def plan(company):
    boms = frappe.get_all("BOM", filters={"company": company, "is_default": 1, "docstatus": 1, "is_active": 1}, fields=["name", "item"])
    by_item = {b.item: b.name for b in boms}
    fg = [i for i in WO_ORDER if i in by_item]
    sa = sorted(i for i in by_item if i not in fg)
    return [(i, by_item[i], FG_QTY if i.startswith("FG-") else SA_QTY) for i in fg + sa]


def requirements(orders):
    need = defaultdict(float)
    for item, bom, qty in orders:
        doc = frappe.get_doc("BOM", bom)
        for r in doc.items:
            need[r.item_code] += r.stock_qty / doc.quantity * qty
    return need


def item_rate(code, rates, P, company):
    if rates.get(code):
        return rates[code]
    base = code[:-2] if code.endswith("-B") else code
    if rates.get(base):
        return rates[base]
    for r in P["raw_materials"]:
        if r[0] in (code, base):
            return float(r[3])
    bom = default_bom(code, company) or default_bom(base, company)
    if bom:
        b = frappe.get_doc("BOM", bom)
        return round(b.total_cost / (b.quantity or 1), 2)
    return 1.0


def receipt(company, stores, rows, remark, rates, P, tracked):
    import item_tracking.item_tracking.events as ev
    orig = ev._auto_create_tracked_items
    if not tracked:
        ev._auto_create_tracked_items = lambda *a, **k: []
    try:
        items = []
        for code, qty in rows:
            uom = frappe.db.get_value("Item", code, "stock_uom")
            items.append({"item_code": code, "qty": qty, "t_warehouse": stores, "basic_rate": item_rate(code, rates, P, company),
                          "uom": uom, "conversion_factor": 1})
        se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
                             "company": company, "remarks": remark, "items": items})
        se.insert(ignore_permissions=True)
        se.submit()
    finally:
        ev._auto_create_tracked_items = orig
    LOG["receipts"].append({"name": se.name, "remark": remark, "items": len(items), "value": float(se.total_incoming_value or 0)})
    phase(f"receipt {se.name}: {remark}, {len(items)} lines, MYR {se.total_incoming_value:,.2f}")
    return se


def rebuild(P, S, rates):
    company = S["company"]["name"]
    w = S["warehouses"]
    orders = plan(company)
    need = requirements(orders)
    whole = {"Nos", "Pair", "Set", "Unit"}
    qty_rows, unit_rows, batch_rows = [], [], []
    for code, q in sorted(need.items()):
        uom = frappe.db.get_value("Item", code, "stock_uom")
        q = q * STOCK_FACTOR
        q = math.ceil(q) if uom in whole else math.ceil(q * 10) / 10
        if frappe.db.get_value("Item", code, "has_batch_no"):
            batch_rows.append((code, max(q, 60)))
        elif code in UNIT_ITEMS:
            unit_rows.append((code, int(q)))
        else:
            qty_rows.append((code, q))
    receipt(company, w["stores"], qty_rows, "Demo opening stock: raw materials and quantity-counted sub-assemblies", rates, P, False)
    frappe.db.commit()
    receipt(company, w["stores"], unit_rows, "Demo opening stock: per-unit sub-assemblies (8-digit unit barcodes)", rates, P, True)
    frappe.db.commit()
    receipt(company, w["stores"], batch_rows, "Demo opening stock: one batch per batch-tracked raw material", rates, P, False)
    frappe.db.commit()
    create_orders(S, orders)


def drop_open_orders(company):
    names = frappe.get_all("Work Order", filters={"company": company, "docstatus": 1, "status": "Not Started"}, pluck="name")
    for n in names:
        if frappe.db.exists("Stock Entry", {"work_order": n}):
            continue
        frappe.get_doc("Work Order", n).cancel()
        delete_docs("Job Card", frappe.get_all("Job Card", filters={"work_order": n}, pluck="name"))
        delete_docs("Work Order", [n])
    frappe.db.commit()
    phase(f"dropped {len(names)} unstarted work orders")


def create_orders(S, orders):
    company = S["company"]["name"]
    w = S["warehouses"]
    start = get_datetime(__import__("os").environ.get("DEMO_START") or now_datetime().strftime("%Y-%m-%d 08:00:00"))
    for item, bom, qty in orders:
        wo = frappe.get_doc({
            "doctype": "Work Order", "company": company, "production_item": item, "bom_no": bom, "qty": qty,
            "use_multi_level_bom": 0, "source_warehouse": w["stores"], "wip_warehouse": w["wip"],
            "fg_warehouse": w["fg"] if item.startswith("FG-") else w["stores"], "planned_start_date": start,
        })
        wo.set_work_order_operations()
        wo.insert(ignore_permissions=True)
        wo.submit()
        jcs = frappe.get_all("Job Card", filters={"work_order": wo.name}, fields=["name", "workstation", "operation"], order_by="sequence_id asc, name asc")
        LOG["work_orders"].append({"name": wo.name, "item": item, "qty": qty, "bom": bom,
                                   "job_cards": [f"{j.name} {j.workstation} {j.operation}" for j in jcs]})
        frappe.db.commit()
        phase(f"work order {wo.name}: {item} x {qty} ({bom}), job cards {', '.join(j.name + ' ' + (j.workstation or '') for j in jcs)}")


def main():
    P = yaml.safe_load(open(sys.argv[1]))
    S = yaml.safe_load(open(sys.argv[2]))
    company = S["company"]["name"]
    frappe.init(site=frappe.utils.cstr(__import__("os").environ.get("FRAPPE_SITE", "frontend")), sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")
    try:
        items = voltra_items(company)
        rates = snapshot_rates(company)
        LOG["rates"] = rates
        if "--orders-only" not in sys.argv:
            remove_junk()
            frappe.db.commit()
            wipe_voltra(company, items)
            frappe.db.commit()
        if "--orders-only" in sys.argv:
            drop_open_orders(company)
            create_orders(S, plan(company))
        elif "--wipe-only" not in sys.argv:
            rebuild(P, S, rates)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        open("demo_reset_log.json", "w").write(json.dumps(LOG, indent=1, default=str))
        frappe.destroy()


if __name__ == "__main__":
    main()
