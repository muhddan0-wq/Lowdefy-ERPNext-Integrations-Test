"""Phases 1-6 gap fill: scrap warehouse, custom fields, operators, opening stock,
historical production runs and simulated shop-floor execution."""

import math
import os
import random
from collections import defaultdict

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime

from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

from mes_common import all_codes, company_of, ensure, phase, process_of, run, warehouses
from seed_mes import bom_order, next_working_start

SEED = 20261124
DRY_RUN = os.environ.get("MES_DRY_RUN") == "1"


def commit():
    if not DRY_RUN:
        frappe.db.commit()


def custom_fields():
    create_custom_fields(
        {
            "BOM Operation": [
                {"fieldname": "custom_ideal_cycle_time", "label": "Ideal Cycle Time (mins/unit)", "fieldtype": "Float", "insert_after": "time_in_mins", "description": "Best demonstrated time per unit, used for OEE performance"},
            ],
            "Job Card Time Log": [
                {"fieldname": "custom_rejected_qty", "label": "Rejected Qty", "fieldtype": "Float", "insert_after": "completed_qty", "in_list_view": 1, "columns": 1},
            ],
            "Job Card": [
                {"fieldname": "custom_work_instructions", "label": "Work Instructions", "fieldtype": "Text Editor", "insert_after": "operation", "read_only": 1, "fetch_from": "operation.description", "fetch_if_empty": 0},
            ],
            "Production Plan": [
                {"fieldname": "custom_mes_tag", "label": "MES Tag", "fieldtype": "Data", "insert_after": "posting_date", "in_standard_filter": 1},
            ],
        },
        update=True,
    )


def ideal_cycle_times(P, company):
    rows = frappe.db.sql(
        """select bo.name, bo.operation, bo.time_in_mins from `tabBOM Operation` bo
        join `tabBOM` b on b.name = bo.parent where b.company = %s""",
        company,
        as_dict=True,
    )
    for r in rows:
        factor = P["processes"][process_of(P, r.operation)]["ideal_factor"]
        frappe.db.set_value("BOM Operation", r.name, "custom_ideal_cycle_time", round(r.time_in_mins * factor, 3), update_modified=False)


def scrap_warehouse(S, company):
    w = warehouses(S)
    group = f"{S['code']} {S['name']} - {S['company']['abbr']}"
    ensure("Warehouse", w["scrap"], lambda: {"doctype": "Warehouse", "warehouse_name": f"{S['code']} Scrap", "company": company, "parent_warehouse": group})


def company_accounts(S, company):
    account = f"Expenses Included In Valuation - {S['company']['abbr']}"
    if not frappe.db.get_value("Company", company, "default_operating_cost_account") and frappe.db.exists("Account", account):
        frappe.db.set_value("Company", company, "default_operating_cost_account", account)


def operators(S, company):
    for g in ("Male", "Female"):
        ensure("Gender", g, lambda x=g: {"doctype": "Gender", "gender": x})
    female = {"Nurul Izzah", "Siti Aisyah", "Farah Nadia", "Tan Mei Ling", "Priya Devi"}
    out = {}
    for ws, full in S["operators"].items():
        existing = frappe.db.get_value("Employee", {"employee_name": full, "company": company}, "name")
        if not existing:
            first, _, last = full.partition(" ")
            doc = frappe.get_doc({
                "doctype": "Employee",
                "first_name": first,
                "last_name": last,
                "gender": "Female" if full in female else "Male",
                "date_of_birth": "1992-05-14",
                "date_of_joining": "2024-01-02",
                "company": company,
                "status": "Active",
                "designation": None,
            })
            doc.insert()
            existing = doc.name
        out[ws] = existing
    return out


def tag_forward_plan(company):
    for pp in frappe.get_all("Production Plan", filters={"company": company, "docstatus": 1}, fields=["name", "custom_mes_tag"]):
        if not pp.custom_mes_tag:
            frappe.db.set_value("Production Plan", pp.name, "custom_mes_tag", "forward", update_modified=False)


def exploded_rm(item, company):
    bom = frappe.db.get_value("BOM", {"item": item, "company": company, "is_default": 1, "docstatus": 1}, "name")
    return {r.item_code: r.stock_qty for r in frappe.get_all("BOM Explosion Item", filters={"parent": bom}, fields=["item_code", "stock_qty"])}


def opening_stock(P, S, company):
    w = warehouses(S)
    remark = f"MES opening stock {S['code']}"
    if frappe.db.exists("Stock Entry", {"company": company, "remarks": remark, "docstatus": 1}):
        phase("P5 opening stock already posted")
        return
    demand = defaultdict(float)
    plans = [S["demo_plan"]] + [{k: v for k, v in h.items() if k.startswith("FG-")} for h in S["history_plans"]]
    for plan in plans:
        for fg, qty in plan.items():
            for rm, per in exploded_rm(fg, company).items():
                demand[rm] += per * qty
    rates = {r[0]: (r[2], r[3]) for r in P["raw_materials"]}
    items = []
    for code, qty in sorted(demand.items()):
        uom, rate = rates[code]
        buffered = qty * 1.25
        q = math.ceil(buffered) if uom in ("Nos", "Pair", "Set") else math.ceil(buffered * 10) / 10
        items.append({"item_code": code, "qty": q, "t_warehouse": w["stores"], "basic_rate": rate, "uom": uom})
    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Receipt",
        "company": company,
        "posting_date": "2026-10-30",
        "posting_time": "09:00:00",
        "set_posting_time": 1,
        "remarks": remark,
        "items": items,
    })
    se.insert()
    se.submit()
    phase(f"P5 opening stock {se.name}: {len(items)} raw materials, value MYR {se.total_incoming_value:,.2f}")


def history_plans(P, S, company, boms):
    w = warehouses(S)
    for h in S["history_plans"]:
        if frappe.db.exists("Production Plan", {"company": company, "custom_mes_tag": h["tag"], "docstatus": 1}):
            continue
        start = get_datetime(f"{h['start']} {S['calendar']['shifts'][0][0]}")
        fg = {k: v for k, v in h.items() if k.startswith("FG-")}
        pp = frappe.get_doc({
            "doctype": "Production Plan",
            "company": company,
            "posting_date": getdate(h["start"]),
            "custom_mes_tag": h["tag"],
            "get_items_from": "",
            "sub_assembly_warehouse": w["stores"],
            "for_warehouse": w["stores"],
            "combine_sub_items": 1,
            "po_items": [
                {"item_code": item, "bom_no": boms[item], "planned_qty": qty, "warehouse": w["fg"], "planned_start_date": start, "stock_uom": "Nos"}
                for item, qty in fg.items()
            ],
        })
        pp.insert()
        pp.get_sub_assembly_items()
        pp.save()
        pp.submit()
        pp.make_work_order()
        wos = frappe.get_all("Work Order", filters={"production_plan": pp.name, "docstatus": 0}, fields=["name", "production_item"])
        by_item = defaultdict(list)
        for wo in wos:
            by_item[wo.production_item].append(wo.name)
        ends = {}
        for item in bom_order(P):
            for wo_name in by_item.get(item, []):
                wo = frappe.get_doc("Work Order", wo_name)
                child_ends = [ends[c] for c in P["boms"][item]["items"] if c in ends]
                wo.planned_start_date = max(child_ends) if child_ends else start
                wo.source_warehouse = w["stores"]
                wo.wip_warehouse = w["wip"]
                wo.fg_warehouse = w["fg"] if item in fg else w["stores"]
                wo.save()
                wo.submit()
                wo.reload()
                end = get_datetime(wo.planned_end_date)
                ends[item] = max(ends.get(item, end), end)
        commit()
        phase(f"P5 history plan {h['tag']} {pp.name}: {len(wos)} work orders, {start} -> {max(ends.values())}")


def weighted(rng, weights):
    total = sum(weights.values())
    pick = rng.uniform(0, total)
    acc = 0
    for k, v in weights.items():
        acc += v
        if pick <= acc:
            return k
    return k


def post_entry(doc_dict, when, remarks=None):
    se = frappe.get_doc(doc_dict)
    if not se.stock_entry_type:
        se.stock_entry_type = se.purpose
    se.posting_date = getdate(when)
    se.posting_time = get_datetime(when).strftime("%H:%M:%S")
    se.set_posting_time = 1
    if remarks:
        se.remarks = remarks
    se.insert()
    se.submit()
    return se


def simulate(P, S, company, ops_by_ws):
    rng = random.Random(SEED)
    w = warehouses(S)
    now = now_datetime()
    skip = [t for t in os.environ.get("MES_SKIP_TAGS", "").split(",") if t]
    history = frappe.get_all("Production Plan", filters={"company": company, "custom_mes_tag": ["like", "history-%"], "docstatus": 1}, fields=["name", "custom_mes_tag"])
    history = [h.name for h in history if h.custom_mes_tag not in skip]
    if not history:
        return
    wo_rows = frappe.get_all("Work Order", filters={"production_plan": ["in", history], "docstatus": 1}, fields=["name", "production_item", "qty", "produced_qty", "bom_no"])
    wo_info = {r.name: r for r in wo_rows}
    jcs = frappe.db.sql(
        """select jc.name, jc.work_order, jc.workstation, jc.operation, jc.for_quantity, jc.bom_no,
            jc.production_item, jc.docstatus, jc.operation_id,
            min(s.from_time) start_t, max(s.to_time) end_t
        from `tabJob Card` jc join `tabJob Card Scheduled Time` s on s.parent = jc.name
        where jc.work_order in %(wos)s group by jc.name order by start_t, jc.name""",
        {"wos": list(wo_info)},
        as_dict=True,
    )
    wo_ops = defaultdict(list)
    for jc in jcs:
        wo_ops[jc.work_order].append(jc)
    op_seq = {}
    for wo_name in wo_info:
        rows = frappe.get_all("Work Order Operation", filters={"parent": wo_name}, fields=["name", "idx"], order_by="idx")
        for r in rows:
            op_seq[r.name] = r.idx

    good_by_op = {}
    for jc in jcs:
        if jc.docstatus == 1:
            good_by_op[jc.operation_id] = frappe.db.get_value("Job Card", jc.name, "total_completed_qty")
    pool = defaultdict(float)
    for r in frappe.db.sql(
        """select item_code, sum(actual_qty) q from `tabStock Ledger Entry`
        where warehouse = %s and is_cancelled = 0 and item_code like 'SA-%%' group by item_code""",
        w["stores"],
        as_dict=True,
    ):
        pool[r.item_code] = r.q
    reserved = {}
    downtime_count = done = 0
    for jc in jcs:
        if jc.docstatus != 0 or get_datetime(jc.end_t) > now:
            continue
        wo = wo_info[jc.work_order]
        proc = process_of(P, jc.operation)
        spec = P["processes"][proc]
        seq = op_seq.get(jc.operation_id, 1)
        prev = [o for o in wo_ops[jc.work_order] if op_seq.get(o.operation_id, 1) == seq - 1]
        target = jc.for_quantity
        if prev:
            target = min(target, good_by_op.get(prev[0].operation_id, 0))
        elif jc.work_order not in reserved:
            comps = {c: q for c, q in P["boms"][wo.production_item]["items"].items() if c.startswith("SA-")}
            if comps:
                kit = min(math.floor(pool[c] / q) for c, q in comps.items())
                target = min(target, kit)
                for c, q in comps.items():
                    pool[c] -= target * q
            reserved[jc.work_order] = target
        ideal = frappe.db.get_value("BOM Operation", {"parent": jc.bom_no, "operation": jc.operation}, "custom_ideal_cycle_time") or 1
        speed = rng.uniform(0.84, 0.97)
        employee = ops_by_ws.get(jc.workstation)
        slots = frappe.get_all("Job Card Scheduled Time", filters={"parent": jc.name}, fields=["from_time", "to_time"], order_by="from_time")
        doc = frappe.get_doc("Job Card", jc.name)
        doc.time_logs = []
        remaining = target
        for slot in slots:
            if remaining <= 0:
                break
            start, end = get_datetime(slot.from_time), get_datetime(slot.to_time)
            minutes = (end - start).total_seconds() / 60
            stop = None
            if minutes >= 20 and rng.random() < spec["downtime_prob"]:
                length = rng.randint(8, int(min(60, minutes * 0.45)))
                offset = rng.uniform(0, minutes - length)
                stop = (offset, length)
            run_cap = minutes - (stop[1] if stop else 0)
            capacity = int(run_cap * speed / ideal)
            made, good, rejects = 0, 0, 0
            while made < capacity and good < remaining:
                made += 1
                if rng.random() < spec["scrap_rate"]:
                    rejects += 1
                else:
                    good += 1
            if made == 0:
                continue
            need = made * ideal / speed
            if stop and stop[0] < need:
                first = stop[0]
                split = max(0, min(good, round(good * first / need)))
                rsplit = max(0, min(rejects, round(rejects * first / need)))
                t1 = add_to_date(start, minutes=first)
                t2 = add_to_date(t1, minutes=stop[1])
                t3 = add_to_date(t2, minutes=need - first)
                if first >= 1:
                    doc.append("time_logs", {"from_time": start, "to_time": t1, "completed_qty": split, "custom_rejected_qty": rsplit, "employee": employee, "time_in_mins": first})
                else:
                    split, rsplit = 0, 0
                doc.append("time_logs", {"from_time": t2, "to_time": t3, "completed_qty": good - split, "custom_rejected_qty": rejects - rsplit, "employee": employee, "time_in_mins": need - first})
                reason = weighted(rng, spec["reasons"])
                remark = {"Other": "Material shortage at line side"}.get(reason, f"{reason} during {jc.operation}")
                frappe.get_doc({
                    "doctype": "Downtime Entry",
                    "workstation": jc.workstation,
                    "operator": employee,
                    "from_time": t1,
                    "to_time": t2,
                    "stop_reason": reason,
                    "remarks": f"{remark} ({jc.name})",
                }).insert()
                downtime_count += 1
            else:
                doc.append("time_logs", {"from_time": start, "to_time": add_to_date(start, minutes=need), "completed_qty": good, "custom_rejected_qty": rejects, "employee": employee, "time_in_mins": need})
            remaining -= good
        if not doc.time_logs:
            continue
        doc.save()
        doc.submit()
        good_by_op[jc.operation_id] = doc.total_completed_qty
        done += 1
        last_seq = max(op_seq.get(o.operation_id, 1) for o in wo_ops[jc.work_order])
        if seq == last_seq:
            finish_work_order(P, S, company, wo, wo_ops[jc.work_order], good_by_op, pool, reserved)
        commit()
    phase(f"P6 simulated {done} job cards, {downtime_count} downtime entries")


def finish_work_order(P, S, company, wo, jcs, good_by_op, pool, reserved):
    w = warehouses(S)
    names = [j.name for j in jcs]
    logs = frappe.get_all("Job Card Time Log", filters={"parent": ["in", names], "parenttype": "Job Card", "parentfield": "time_logs", "to_time": ["is", "set"]}, fields=["from_time", "to_time", "custom_rejected_qty"])
    if not logs:
        return
    qty = min(good_by_op.get(j.operation_id, 0) for j in jcs)
    first = min(get_datetime(l.from_time) for l in logs)
    last = max(get_datetime(l.to_time) for l in logs)
    rejects = sum(l.custom_rejected_qty or 0 for l in logs)
    sa_comps = [c for c in P["boms"][wo.production_item]["items"] if c.startswith("SA-")]
    for c in sa_comps:
        arrived = frappe.db.sql(
            """select max(timestamp(posting_date, posting_time)) from `tabStock Ledger Entry`
            where item_code = %s and warehouse = %s and actual_qty > 0 and is_cancelled = 0""",
            (c, w["stores"]),
        )[0][0]
        if arrived and get_datetime(arrived) >= first:
            first = add_to_date(get_datetime(arrived), minutes=1)
    last = max(last, add_to_date(first, minutes=1))
    if qty > 0:
        try:
            post_entry(make_stock_entry(wo.name, "Material Transfer for Manufacture", qty), first)
            post_entry(make_stock_entry(wo.name, "Manufacture", qty), last)
        except Exception:
            state = frappe.db.get_value("Work Order", wo.name, ["qty", "material_transferred_for_manufacturing", "produced_qty", "status"])
            print(f"  failed on {wo.name} {wo.production_item} qty={qty} state={state} first={first} last={last}")
            raise
        if wo.production_item.startswith("SA-"):
            pool[wo.production_item] += qty
    held = reserved.get(wo.name)
    if held is not None and held > qty:
        comps = {c: q for c, q in P["boms"][wo.production_item]["items"].items() if c.startswith("SA-")}
        for c, q in comps.items():
            pool[c] += (held - qty) * q
    if rejects:
        rm = {c: q for c, q in P["boms"][wo.production_item]["items"].items() if c.startswith("RM-")}
        if rm:
            post_entry(
                {
                    "doctype": "Stock Entry",
                    "stock_entry_type": "Material Transfer",
                    "company": company,
                    "items": [{"item_code": c, "qty": round(q * rejects, 3), "s_warehouse": w["stores"], "t_warehouse": w["scrap"]} for c, q in rm.items()],
                },
                last,
                remarks=f"MES scrap for {int(rejects)} rejected {wo.production_item} on {wo.name}",
            )


def main(P, S):
    company = company_of(S)
    custom_fields()
    scrap_warehouse(S, company)
    company_accounts(S, company)
    ideal_cycle_times(P, company)
    tag_forward_plan(company)
    frappe.db.commit()
    phase("P1 scrap warehouse, P4 ideal cycle times, custom MES fields ready")
    ops = operators(S, company)
    frappe.db.commit()
    phase(f"operators ready: {len(ops)}")
    opening_stock(P, S, company)
    frappe.db.commit()
    boms = {item: frappe.db.get_value("BOM", {"item": item, "company": company, "is_default": 1, "docstatus": 1}, "name") for item in P["boms"]}
    history_plans(P, S, company, boms)
    simulate(P, S, company, ops)
    if DRY_RUN:
        report_dry(company)
        frappe.db.rollback()
        phase("dry run: rolled back")


def report_dry(company):
    rows = frappe.db.sql(
        """select wo.production_item, sum(wo.qty) q, sum(wo.produced_qty) p from `tabWork Order` wo
        join `tabProduction Plan` pp on pp.name = wo.production_plan
        where wo.company = %s and pp.custom_mes_tag like 'history-%%' group by wo.production_item""",
        company,
    )
    for item, q, p in rows:
        print(f"  {item}: planned {q:g} produced {p:g} ({100 * p / q:.0f}%)")
    bad = frappe.db.sql(
        """select count(*) from `tabStock Entry` where company = %s and docstatus = 1
        and stock_entry_type != 'Material Receipt' and posting_date > '2026-11-23'""",
        company,
    )[0][0]
    print(f"  stock entries dated after 23 Nov: {bad}")


if __name__ == "__main__":
    run(main)
