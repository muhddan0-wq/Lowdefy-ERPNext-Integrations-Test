"""MES-in-a-box site loader. Runs inside the Frappe bench (see run-seed.ps1).

Usage: python seed_mes.py <products.yaml> <site.yaml> [--no-plan] [--reset-plan]
Idempotent: every record is looked up first and only created when missing.
"""

import datetime
import os
import sys

import frappe
import yaml
from frappe.utils import add_days, get_datetime, getdate


def ensure(doctype, name, builder):
    if frappe.db.exists(doctype, name):
        return name
    doc = frappe.get_doc(builder())
    doc.insert()
    return doc.name


def ensure_masters(P):
    for uom in P["uoms"]:
        ensure("UOM", uom, lambda u=uom: {"doctype": "UOM", "uom_name": u, "must_be_whole_number": int(u in ("Nos", "Pair", "Set"))})
    for comp in P["operating_components"]:
        ensure("Workstation Operating Component", comp, lambda c=comp: {"doctype": "Workstation Operating Component", "component_name": c})
    for group in ("Raw Material", "Sub Assemblies", "Finished Goods"):
        ensure("Item Group", group, lambda g=group: {"doctype": "Item Group", "item_group_name": g, "parent_item_group": "All Item Groups"})
    ensure("Supplier Group", "Manufacturing Components", lambda: {"doctype": "Supplier Group", "supplier_group_name": "Manufacturing Components", "parent_supplier_group": "All Supplier Groups"})
    for op in P["operations"]:
        ensure("Operation", op, lambda o=op: {"doctype": "Operation", "name": o})
    for supplier in P["suppliers"]:
        ensure("Supplier", supplier, lambda s=supplier: {"doctype": "Supplier", "supplier_name": s, "supplier_group": "Manufacturing Components", "supplier_type": "Company", "country": "Malaysia"})


def ensure_company(S):
    c = S["company"]
    if not frappe.db.exists("Company", c["name"]):
        frappe.get_doc({
            "doctype": "Company",
            "company_name": c["name"],
            "abbr": c["abbr"],
            "default_currency": c["currency"],
            "country": c["country"],
            "chart_of_accounts": "Standard",
            "create_chart_of_accounts_based_on": "Standard Template",
        }).insert()
        print(f"created company {c['name']}")
    return c["name"], c["abbr"]


def ensure_warehouses(S, company, abbr):
    root = f"All Warehouses - {abbr}"
    group_label = f"{S['code']} {S['name']}"
    group = ensure("Warehouse", f"{group_label} - {abbr}", lambda: {"doctype": "Warehouse", "warehouse_name": group_label, "company": company, "is_group": 1, "parent_warehouse": root})
    out = {}
    for key, label in (("stores", "Stores"), ("wip", "Work In Progress"), ("fg", "Finished Goods")):
        wname = f"{S['code']} {label}"
        out[key] = ensure("Warehouse", f"{wname} - {abbr}", lambda w=wname: {"doctype": "Warehouse", "warehouse_name": w, "company": company, "parent_warehouse": group})
    return out


def ensure_holiday_list(S):
    cal = S["calendar"]
    name = f"{S['code']} {S['name']} {getdate(cal['from_date']).year}-{getdate(cal['to_date']).year}"
    if frappe.db.exists("Holiday List", name):
        return name
    hl = frappe.new_doc("Holiday List")
    hl.holiday_list_name = name
    hl.from_date = cal["from_date"]
    hl.to_date = cal["to_date"]
    for day in cal["weekly_off"]:
        hl.weekly_off = day
        hl.get_weekly_off_dates()
    taken = {getdate(h.holiday_date) for h in hl.holidays}
    country = cal.get("public_holidays_country")
    if country:
        import holidays

        start, end = getdate(cal["from_date"]), getdate(cal["to_date"])
        for day, label in sorted(holidays.country_holidays(country, years=range(start.year, end.year + 1)).items()):
            if start <= day <= end and day not in taken:
                hl.append("holidays", {"holiday_date": day, "description": label, "weekly_off": 0})
                taken.add(day)
    hl.insert()
    return name


def ensure_plant_floor(S, company, warehouses):
    name = f"{S['code']} {S['name']}"
    return ensure("Plant Floor", name, lambda: {"doctype": "Plant Floor", "floor_name": name, "company": company, "warehouse": warehouses["wip"]})


def workstation_type_name(S, P, process):
    return f"{S['code']} {P['processes'][process]['label']}"


def ensure_workstations(S, P, holiday_list, plant_floor, warehouses):
    shifts = [{"start_time": a, "end_time": b, "enabled": 1} for a, b in S["calendar"]["shifts"]]
    for process, spec in P["processes"].items():
        costs = [{"operating_component": k, "operating_cost": v} for k, v in spec["costs"].items()]
        wtype = workstation_type_name(S, P, process)
        ensure("Workstation Type", wtype, lambda: {"doctype": "Workstation Type", "workstation_type": wtype, "workstation_costs": costs, "description": f"{spec['label']} at {S['name']}"})
        for ws in S["workstations"].get(process, []):
            wname = f"{S['code']}-{ws['code']}"
            ensure("Workstation", wname, lambda w=ws, n=wname: {
                "doctype": "Workstation",
                "workstation_name": n,
                "workstation_type": wtype,
                "plant_floor": plant_floor,
                "production_capacity": w.get("capacity", 1),
                "holiday_list": holiday_list,
                "warehouse": warehouses["wip"],
                "workstation_costs": costs,
                "working_hours": shifts,
                "description": f"{spec['label']} station {w['code']} at {S['name']}",
            })


def ensure_items(P, company, warehouses):
    supplier_of = {code: s for s, codes in P["suppliers"].items() for code in codes}
    for code, name, uom, rate, lead in P["raw_materials"]:
        ensure("Item", code, lambda: {
            "doctype": "Item", "item_code": code, "item_name": name, "item_group": "Raw Material",
            "stock_uom": uom, "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0,
            "include_item_in_manufacturing": 1, "valuation_rate": rate, "lead_time_days": lead,
            "supplier_items": [{"supplier": supplier_of[code]}],
            "item_defaults": [{"company": company, "default_warehouse": warehouses["stores"], "default_supplier": supplier_of[code]}],
        })
        ensure_price(code, "Standard Buying", rate, uom)
    for code, name in P["sub_assemblies"]:
        ensure("Item", code, lambda: {
            "doctype": "Item", "item_code": code, "item_name": name, "item_group": "Sub Assemblies",
            "stock_uom": "Nos", "is_stock_item": 1, "is_purchase_item": 0, "is_sales_item": 0,
            "include_item_in_manufacturing": 1,
            "item_defaults": [{"company": company, "default_warehouse": warehouses["stores"]}],
        })
    for code, name, price in P["finished_goods"]:
        ensure("Item", code, lambda: {
            "doctype": "Item", "item_code": code, "item_name": name, "item_group": "Finished Goods",
            "stock_uom": "Nos", "is_stock_item": 1, "is_purchase_item": 0, "is_sales_item": 1,
            "include_item_in_manufacturing": 1, "has_serial_no": 0,
            "item_defaults": [{"company": company, "default_warehouse": warehouses["fg"]}],
        })
        ensure_price(code, "Standard Selling", price, "Nos")


def ensure_price(code, price_list, rate, uom):
    if frappe.db.exists("Item Price", {"item_code": code, "price_list": price_list}):
        return
    frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": price_list, "price_list_rate": rate, "uom": uom}).insert()


def bom_order(P):
    made = set(P["boms"])
    done, order = set(), []

    def visit(item):
        if item in done:
            return
        for child in P["boms"][item]["items"]:
            if child in made:
                visit(child)
        done.add(item)
        order.append(item)

    for item in P["boms"]:
        visit(item)
    return order


def site_bom(item, company, S):
    prefix = f"{S['code']} "
    for name in frappe.get_all("BOM", filters={"item": item, "company": company, "docstatus": 1, "is_active": 1}, pluck="name", order_by="creation asc"):
        types = frappe.get_all("BOM Operation", filters={"parent": name}, pluck="workstation_type")
        if types and all((t or "").startswith(prefix) for t in types):
            return name
    return None


def ensure_boms(P, S, company):
    boms = {}
    for item in bom_order(P):
        existing = site_bom(item, company, S)
        if existing:
            boms[item] = existing
            continue
        spec = P["boms"][item]
        first_for_item = not frappe.db.exists("BOM", {"item": item, "company": company, "docstatus": 1, "is_default": 1})
        doc = frappe.get_doc({
            "doctype": "BOM",
            "item": item,
            "company": company,
            "quantity": 1,
            "currency": S["company"]["currency"],
            "is_active": 1,
            "is_default": int(first_for_item),
            "with_operations": 1,
            "rm_cost_as_per": "Price List",
            "buying_price_list": "Standard Buying",
            "set_rate_of_sub_assembly_item_based_on_bom": 1,
            "description": f"{S['name']} ({S['code']}) routing",
            "items": [
                {"item_code": child, "qty": qty, **({"bom_no": boms[child]} if child in boms else {})}
                for child, qty in spec["items"].items()
            ],
            "operations": [
                {"operation": op, "workstation_type": workstation_type_name(S, P, P["operations"][op]), "time_in_mins": mins, "sequence_id": i + 1}
                for i, (op, mins) in enumerate(spec["operations"])
            ],
        })
        doc.insert()
        doc.submit()
        boms[item] = doc.name
    return boms


def configure_manufacturing():
    ms = frappe.get_single("Manufacturing Settings")
    ms.disable_capacity_planning = 0
    ms.capacity_planning_for_days = max(int(ms.capacity_planning_for_days or 0), 60)
    ms.allow_overtime = 0
    ms.allow_production_on_holidays = 0
    ms.save()


def next_working_start(holiday_list, shifts):
    off = set(frappe.get_all("Holiday", filters={"parent": holiday_list}, pluck="holiday_date"))
    day = add_days(getdate(), 1)
    while getdate(day) in off:
        day = add_days(day, 1)
    return get_datetime(f"{getdate(day)} {shifts[0][0]}")


def demo_plan(P, S, company, warehouses, boms, holiday_list):
    marker = f"MES demo plan {S['code']}"
    if frappe.db.exists("Production Plan", {"company": company, "docstatus": ["<", 2]}):
        print("demo plan already exists, skipping")
        return
    start = next_working_start(holiday_list, S["calendar"]["shifts"])
    pp = frappe.get_doc({
        "doctype": "Production Plan",
        "company": company,
        "posting_date": getdate(),
        "get_items_from": "",
        "sub_assembly_warehouse": warehouses["stores"],
        "for_warehouse": warehouses["stores"],
        "skip_available_sub_assembly_item": 0,
        "combine_sub_items": 1,
        "po_items": [
            {"item_code": item, "bom_no": boms[item], "planned_qty": qty, "warehouse": warehouses["fg"], "planned_start_date": start, "stock_uom": "Nos"}
            for item, qty in S["demo_plan"].items()
        ],
    })
    pp.insert()
    pp.get_sub_assembly_items()
    pp.save()
    pp.submit()
    pp.make_work_order()
    wos = frappe.get_all("Work Order", filters={"production_plan": pp.name, "docstatus": 0}, fields=["name", "production_item"])
    by_item = {}
    for wo in wos:
        by_item.setdefault(wo.production_item, []).append(wo.name)
    ends = {}
    for item in bom_order(P):
        for wo_name in by_item.get(item, []):
            wo = frappe.get_doc("Work Order", wo_name)
            child_ends = [ends[c] for c in P["boms"][item]["items"] if c in ends]
            wo.planned_start_date = max(child_ends) if child_ends else start
            wo.source_warehouse = warehouses["stores"]
            wo.wip_warehouse = warehouses["wip"]
            wo.fg_warehouse = warehouses["fg"] if item in S["demo_plan"] else warehouses["stores"]
            wo.save()
            wo.submit()
            wo.reload()
            end = get_datetime(wo.planned_end_date)
            ends[item] = max(ends.get(item, end), end)
            frappe.db.commit()
    print(f"{marker}: {pp.name}, {len(wos)} work orders, planned from {start} to {max(ends.values())}")


def reset_plan(company):
    plans = frappe.get_all("Production Plan", filters={"company": company, "docstatus": ["<", 2]}, pluck="name")
    for pp in plans:
        for wo in frappe.get_all("Work Order", filters={"production_plan": pp}, fields=["name", "docstatus"]):
            for jc in frappe.get_all("Job Card", filters={"work_order": wo.name}, fields=["name", "docstatus"]):
                if jc.docstatus == 1:
                    frappe.get_doc("Job Card", jc.name).cancel()
                frappe.delete_doc("Job Card", jc.name, force=1)
            if wo.docstatus == 1:
                frappe.get_doc("Work Order", wo.name).cancel()
            frappe.delete_doc("Work Order", wo.name, force=1)
        doc = frappe.get_doc("Production Plan", pp)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Production Plan", pp, force=1)
    frappe.db.commit()
    print(f"reset {len(plans)} production plan(s)")


def schedule_conflicts(company):
    rows = frappe.db.sql(
        """select jc.name, jc.workstation, s.from_time, s.to_time
        from `tabJob Card` jc join `tabJob Card Scheduled Time` s on s.parent = jc.name
        where jc.company = %s and jc.docstatus < 2 and jc.status != 'Completed'""",
        company,
        as_dict=True,
    )
    by_ws = {}
    for r in rows:
        by_ws.setdefault(r.workstation, []).append(r)
    conflicts = []
    for ws, slots in by_ws.items():
        capacity = frappe.db.get_value("Workstation", ws, "production_capacity") or 1
        for slot in slots:
            concurrent = [o for o in slots if o.from_time < slot.to_time and slot.from_time < o.to_time]
            if len({o.name for o in concurrent}) > capacity:
                conflicts.append((ws, slot.name, slot.from_time, slot.to_time))
    return conflicts


def report(P, company, S):
    codes = [r[0] for r in P["raw_materials"]] + [r[0] for r in P["sub_assemblies"]] + [r[0] for r in P["finished_goods"]]
    print(f"Items: {frappe.db.count('Item', {'name': ['in', codes]})}")
    print(f"BOMs: {frappe.db.count('BOM', {'company': company, 'docstatus': 1})}")
    print(f"Workstations: {frappe.db.count('Workstation', {'name': ['like', S['code'] + '-%']})}")
    print(f"Work Orders: {frappe.db.count('Work Order', {'company': company, 'docstatus': 1})}")
    print(f"Job Cards: {frappe.db.count('Job Card', {'company': company, 'docstatus': 0})}")
    for bom in frappe.get_all("BOM", filters={"company": company, "docstatus": 1, "item": ["like", "FG-%"]}, fields=["item", "name", "raw_material_cost", "operating_cost", "total_cost"]):
        print(f"  {bom.item} {bom.name}: material {bom.raw_material_cost:.2f} + ops {bom.operating_cost:.2f} = {bom.total_cost:.2f}")
    conflicts = schedule_conflicts(company)
    print(f"Schedule conflicts (workstation over capacity): {len(conflicts)}")
    for ws, jc, a, b in conflicts:
        print(f"  {ws} {jc} {a} -> {b}")


def main():
    products_file, site_file = sys.argv[1], sys.argv[2]
    frappe.init(site=os.environ.get("FRAPPE_SITE", "frontend"), sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")
    with open(products_file, encoding="utf-8") as fh:
        P = yaml.safe_load(fh)
    with open(site_file, encoding="utf-8") as fh:
        S = yaml.safe_load(fh)
    try:
        ensure_masters(P)
        company, abbr = ensure_company(S)
        warehouses = ensure_warehouses(S, company, abbr)
        holiday_list = ensure_holiday_list(S)
        plant_floor = ensure_plant_floor(S, company, warehouses)
        ensure_workstations(S, P, holiday_list, plant_floor, warehouses)
        ensure_items(P, company, warehouses)
        boms = ensure_boms(P, S, company)
        configure_manufacturing()
        frappe.db.commit()
        print("masters, workstations, items and BOMs ready")
        if "--reset-plan" in sys.argv:
            reset_plan(company)
        if "--no-plan" not in sys.argv:
            demo_plan(P, S, company, warehouses, boms, holiday_list)
            frappe.db.commit()
        report(P, company, S)
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
