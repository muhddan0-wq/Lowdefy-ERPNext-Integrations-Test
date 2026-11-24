# POST /api/method/mes_create_plan
#   items   = [{"item": "FG-DRL-800", "qty": 10, "start": "2026-12-02"}, ...]   (JSON list)
#   preview = 1 -> only explode the BOMs and return sub-assemblies, no writes.
# Create: Production Plan (combine_sub_items=1, tagged custom_mes_tag="mes-api") -> sub-assemblies -> submit ->
# work orders -> P1 warehouses -> submit in BOM order, each parent starting when its children finish.
# Same flow as mes/seed_mes.py demo_plan().


def mes_site_bom(M, item):
    boms = frappe.get_all("BOM", filters={"item": item, "company": M["COMPANY"], "docstatus": 1, "is_active": 1},
                          fields=["name", "is_default"], order_by="is_default desc, creation asc")
    for b in boms:
        types = frappe.get_all("BOM Operation", filters={"parent": b.name, "parenttype": "BOM"}, pluck="workstation_type")
        if types and all([(t or "").startswith(M["SITE_PREFIX"]) for t in types]):
            return b.name
    return None


def mes_explode(M, bom, qty, level, acc, graph, order):
    """Walk the BOM tree; acc = sub-assembly totals, graph = item -> made children, order = children first."""
    item = frappe.db.get_value("BOM", bom, "item")
    bom_qty = frappe.db.get_value("BOM", bom, "quantity") or 1
    rows = frappe.get_all("BOM Item", filters={"parent": bom, "parenttype": "BOM"},
                          fields=["item_code", "item_name", "stock_qty", "qty", "bom_no"], order_by="idx asc")
    kids = graph.setdefault(item, [])
    for r in rows:
        if not r.bom_no:
            continue
        q = qty * (r.stock_qty or r.qty) / bom_qty
        if r.item_code not in kids:
            kids.append(r.item_code)
        if r.item_code not in acc:
            acc[r.item_code] = {"item": r.item_code, "item_name": r.item_name, "qty": 0, "bom": r.bom_no, "level": level + 1, "used_in": []}
        acc[r.item_code]["qty"] = acc[r.item_code]["qty"] + q
        acc[r.item_code]["level"] = max(acc[r.item_code]["level"], level + 1)
        if item not in acc[r.item_code]["used_in"]:
            acc[r.item_code]["used_in"].append(item)
        M["explode"](M, r.bom_no, q, level + 1, acc, graph, order)
    if item not in order:
        order.append(item)


def mes_first_working(M, cal, start):
    """First moment >= start that lies inside a shift on a working day."""
    day = frappe.utils.getdate(start)
    for i in range(M["HORIZON_DAYS"] + 30):
        if str(day) not in cal["holidays"]:
            for sh in cal["shifts"]:
                s = M["at"](M, day, sh[0])
                e = M["at"](M, day, sh[1])
                if e > start:
                    return max(s, start)
        day = frappe.utils.add_days(day, 1)
    frappe.throw("No working time found within the planning horizon")


M["site_bom"] = mes_site_bom
M["explode"] = mes_explode
M["first_working"] = mes_first_working

if frappe.utils.cint(M["arg"](M, "list_items", 0)):
    # finished goods that have an active P1 BOM for Voltra (feeds the New Plan dropdown)
    fg_items = frappe.get_all("Item", filters={"item_group": "Finished Goods", "disabled": 0}, fields=["item_code", "item_name"], order_by="item_code asc")
    frappe.response["message"] = {"items": [{"item": i.item_code, "item_name": i.item_name, "bom": M["site_bom"](M, i.item_code)}
                                            for i in fg_items if M["site_bom"](M, i.item_code)],
                                  "next_working_day": str(frappe.utils.getdate(M["first_working"](M, M["calendar"](M, frappe.get_all("Workstation", filters={"plant_floor": M["PLANT_FLOOR"]}, pluck="name", limit=1)[0]), frappe.utils.get_datetime(frappe.utils.add_days(frappe.utils.today(), 1)))))}
else:
    items = M["json_arg"](M, "items", [])
    preview = frappe.utils.cint(M["arg"](M, "preview", 0))
    if not isinstance(items, list) or not items:
        frappe.throw("items must be a non-empty list of {item, qty, start}")
    if len(items) > 10:
        frappe.throw("At most 10 finished goods per plan")

    ref_ws = frappe.get_all("Workstation", filters={"plant_floor": M["PLANT_FLOOR"]}, pluck="name", order_by="name asc", limit=1)
    if not ref_ws:
        frappe.throw("No workstations on %s" % (M["PLANT_FLOOR"],))
    cal = M["calendar"](M, ref_ws[0])
    now = frappe.utils.now_datetime()
    default_start = frappe.utils.get_datetime(frappe.utils.add_days(frappe.utils.today(), 1))

    fgs = []
    seen = []
    for row in items:
        if not isinstance(row, dict):
            frappe.throw("Each item must be an object {item, qty, start}")
        code = (row.get("item") or "").strip()
        if not code or not frappe.db.exists("Item", code):
            frappe.throw("Item %s not found" % (code or "(blank)",))
        if code in seen:
            frappe.throw("Item %s is listed twice; combine the quantities" % (code,))
        seen.append(code)
        if frappe.db.get_value("Item", code, "item_group") != "Finished Goods":
            frappe.throw("%s is not a finished good" % (code,))
        qty = frappe.utils.flt(row.get("qty"))
        if qty <= 0 or qty > 5000 or qty != int(qty):
            frappe.throw("Quantity for %s must be a whole number between 1 and 5000" % (code,))
        bom = M["site_bom"](M, code)
        if not bom:
            frappe.throw("No active P1 BOM for %s" % (code,))
        raw_start = row.get("start")
        start = frappe.utils.get_datetime(raw_start) if raw_start else default_start
        if start < now:
            frappe.throw("Start %s for %s is in the past" % (raw_start, code,))
        if frappe.utils.date_diff(frappe.utils.getdate(start), frappe.utils.getdate(now)) > M["HORIZON_DAYS"]:
            frappe.throw("Start %s is beyond the %s-day capacity planning horizon" % (raw_start, M["HORIZON_DAYS"],))
        start = M["first_working"](M, cal, start)
        fgs.append({"item": code, "item_name": frappe.db.get_value("Item", code, "item_name"), "qty": int(qty), "bom": bom, "start": start})

    acc = {}
    graph = {}
    order = []
    for fg in fgs:
        M["explode"](M, fg["bom"], fg["qty"], 0, acc, graph, order)
    subs = sorted(acc.values(), key=lambda x: (-x["level"], x["item"]))

    if preview:
        frappe.response["message"] = {"preview": 1, "finished_goods": fgs, "sub_assemblies": subs, "build_order": order,
                                      "work_orders_expected": len(fgs) + len(subs)}
    else:
        plan_start = min([f["start"] for f in fgs])
        pp = frappe.get_doc({
            "doctype": "Production Plan",
            "company": M["COMPANY"],
            "posting_date": frappe.utils.today(),
            "get_items_from": "",
            "sub_assembly_warehouse": M["WH"]["stores"],
            "for_warehouse": M["WH"]["stores"],
            "skip_available_sub_assembly_item": 0,
            "combine_sub_items": 1,
            "custom_mes_tag": "mes-api",
            "po_items": [{"item_code": f["item"], "bom_no": f["bom"], "planned_qty": f["qty"], "warehouse": M["WH"]["fg"],
                          "planned_start_date": f["start"], "stock_uom": "Nos"} for f in fgs],
        })
        pp.insert()
        pp.get_sub_assembly_items()
        pp.save()
        pp.submit()
        pp.make_work_order()
        wos = frappe.get_all("Work Order", filters={"production_plan": pp.name, "docstatus": 0}, fields=["name", "production_item"])
        by_item = {}
        for w in wos:
            by_item.setdefault(w.production_item, []).append(w.name)
        fg_start = {f["item"]: f["start"] for f in fgs}
        ends = {}
        out = []
        for item in order:
            for wo_name in by_item.get(item, []):
                wo = frappe.get_doc("Work Order", wo_name)
                child_ends = [ends[c] for c in graph.get(item, []) if c in ends]
                wo.planned_start_date = max(child_ends + [fg_start.get(item, plan_start)])
                wo.source_warehouse = M["WH"]["stores"]
                wo.wip_warehouse = M["WH"]["wip"]
                wo.fg_warehouse = M["WH"]["fg"] if item in fg_start else M["WH"]["stores"]
                wo.save()
                wo.submit()
                wo.reload()
                end = frappe.utils.get_datetime(wo.planned_end_date)
                ends[item] = max(ends.get(item, end), end)
                out.append({"name": wo.name, "item": wo.production_item, "item_name": wo.item_name, "qty": wo.qty,
                            "planned_start_date": wo.planned_start_date, "planned_end_date": wo.planned_end_date})
        leftovers = [w.name for w in wos if w.production_item not in order]
        if leftovers:
            frappe.throw("Work orders outside the BOM order: %s" % (", ".join(leftovers),))
        # check every scheduled block lies inside a shift on a working day
        names = [o["name"] for o in out]
        blocks = frappe.db.sql(
            """select jc.name, jc.work_order, jc.workstation, s.from_time, s.to_time from `tabJob Card` jc
            join `tabJob Card Scheduled Time` s on s.parent = jc.name where jc.work_order in %s""",
            (tuple(names),), as_dict=True)
        cals = {}
        outside = []
        for b in blocks:
            if b.workstation not in cals:
                cals[b.workstation] = M["calendar"](M, b.workstation)
            c = cals[b.workstation]
            f = frappe.utils.get_datetime(b.from_time)
            t = frappe.utils.get_datetime(b.to_time)
            fm = M["dt_minutes"](M, f)
            tm = M["dt_minutes"](M, t)
            ok = str(frappe.utils.getdate(f)) not in c["holidays"] and frappe.utils.getdate(f) == frappe.utils.getdate(t) \
                and any([sh[0] <= fm and tm <= sh[1] for sh in c["shifts"]])
            if not ok:
                outside.append({"job_card": b.name, "workstation": b.workstation, "from_time": b.from_time, "to_time": b.to_time})
        jc_count = len({b.name for b in blocks})
        conf = M["conflicts"](M, str(plan_start))
        frappe.response["message"] = {
            "production_plan": pp.name, "start": plan_start, "end": max(ends.values()) if ends else None,
            "work_orders": out, "job_cards": jc_count, "blocks": len(blocks),
            "blocks_outside_shift": outside, "conflicts": {"count": len(conf), "rows": conf},
            "sub_assemblies": subs,
        }
