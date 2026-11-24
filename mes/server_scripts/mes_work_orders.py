# GET /api/method/mes_work_orders?status=&item=&search=&plan=&include_history=0
# Work order list + KPI tiles, company Voltra only. Simulated history plans (custom_mes_tag history-*) hidden by default.
cond = ["wo.company = %(company)s", "wo.docstatus = 1"]
vals = {"company": M["COMPANY"], "now": frappe.utils.now_datetime()}
status = M["arg"](M, "status")
if status and status != "All":
    if status == "Late":
        cond.append("wo.status not in ('Completed','Closed','Cancelled') and wo.planned_end_date < %(now)s")
    else:
        cond.append("wo.status = %(status)s")
        vals["status"] = status
item = M["arg"](M, "item")
if item:
    cond.append("wo.production_item = %(item)s")
    vals["item"] = item
search = M["arg"](M, "search")
if search:
    cond.append("(wo.name like %(q)s or wo.production_item like %(q)s or wo.item_name like %(q)s)")
    vals["q"] = "%" + search + "%"
plan = M["arg"](M, "plan")
if plan:
    cond.append("wo.production_plan = %(plan)s")
    vals["plan"] = plan
if not frappe.utils.cint(M["arg"](M, "include_history", 0)):
    cond.append("ifnull(pp.custom_mes_tag, '') not like %(hist)s")
    vals["hist"] = "history-%"
rows = frappe.db.sql(
    """select wo.name, wo.production_item, wo.item_name, wo.qty, wo.produced_qty,
        wo.material_transferred_for_manufacturing as transferred_qty, wo.status,
        wo.planned_start_date, wo.planned_end_date, wo.actual_start_date, wo.actual_end_date,
        wo.production_plan, pp.custom_mes_tag as plan_tag, wo.bom_no, wo.fg_warehouse
    from `tabWork Order` wo left join `tabProduction Plan` pp on pp.name = wo.production_plan
    where """ + " and ".join(cond) + " order by wo.planned_start_date, wo.name",
    vals, as_dict=True)
now = vals["now"]
kpi = {"not_started": 0, "in_process": 0, "completed": 0, "late": 0, "stopped": 0, "total": len(rows)}
for r in rows:
    r["progress_pct"] = round(100.0 * (r.produced_qty or 0) / r.qty, 1) if r.qty else 0
    is_late = r.status not in ("Completed", "Closed", "Cancelled") and r.planned_end_date and frappe.utils.get_datetime(r.planned_end_date) < now
    r["late"] = 1 if is_late else 0
    kpi["late"] = kpi["late"] + r["late"]
    if r.status == "Not Started":
        kpi["not_started"] = kpi["not_started"] + 1
    elif r.status == "In Process":
        kpi["in_process"] = kpi["in_process"] + 1
    elif r.status == "Completed":
        kpi["completed"] = kpi["completed"] + 1
    elif r.status == "Stopped":
        kpi["stopped"] = kpi["stopped"] + 1
frappe.response["message"] = {"kpi": kpi, "rows": rows, "as_of": now}
