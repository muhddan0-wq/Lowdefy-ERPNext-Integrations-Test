# GET /api/method/mes_schedule_board?from_date=&to_date=&workstation_type=
# Gantt data: P1 workstations (groups) and job card scheduled blocks (items), company Voltra only.
from_date = frappe.utils.getdate(M["arg"](M, "from_date", frappe.utils.add_days(frappe.utils.today(), -7)))
to_date = frappe.utils.getdate(M["arg"](M, "to_date", frappe.utils.add_days(from_date, 60)))
wtype = M["arg"](M, "workstation_type")
filters = {"plant_floor": M["PLANT_FLOOR"]}
if wtype:
    filters["workstation_type"] = wtype
stations = frappe.get_all("Workstation", filters=filters, fields=["name", "workstation_type", "production_capacity", "status"], order_by="name asc")
names = [s.name for s in stations] or ["-"]
rows = frappe.db.sql(
    """select jc.name, jc.work_order, jc.production_item, jc.item_name, jc.operation, jc.workstation,
        jc.workstation_type, jc.status, jc.docstatus, jc.is_paused, jc.for_quantity, jc.total_completed_qty,
        jc.expected_start_date, jc.expected_end_date, jc.sequence_id,
        s.name as block, s.from_time, s.to_time, s.time_in_mins, wo.production_plan, pp.custom_mes_tag as plan_tag
    from `tabJob Card` jc join `tabJob Card Scheduled Time` s on s.parent = jc.name
    left join `tabWork Order` wo on wo.name = jc.work_order
    left join `tabProduction Plan` pp on pp.name = wo.production_plan
    where jc.company = %(company)s and jc.docstatus < 2 and jc.workstation in %(ws)s
      and s.to_time >= %(f)s and s.from_time <= %(t)s
      and (%(hist)s = 1 or ifnull(pp.custom_mes_tag, '') not like 'history-%%')
    order by s.from_time""",
    {"company": M["COMPANY"], "ws": tuple(names), "f": str(from_date), "t": str(frappe.utils.add_days(to_date, 1)),
     "hist": frappe.utils.cint(M["arg"](M, "include_history", 0))}, as_dict=True)
status_of = {}
items = []
for r in rows:
    if r.is_paused:
        st = "Paused"
    elif r.docstatus == 1:
        st = "Completed"
    else:
        st = r.status
    status_of[r.name] = st
    items.append({"id": r.block, "job_card": r.name, "group": r.workstation, "start": r.from_time, "end": r.to_time,
                  "mins": r.time_in_mins, "status": st, "work_order": r.work_order, "plan": r.production_plan, "item": r.production_item,
                  "item_name": r.item_name, "operation": r.operation, "qty": r.for_quantity,
                  "completed_qty": r.total_completed_qty, "workstation_type": r.workstation_type,
                  "expected_start": r.expected_start_date, "expected_end": r.expected_end_date})
conf = M["conflicts"](M, str(from_date), str(frappe.utils.add_days(to_date, 1)))
all_types = frappe.get_all("Workstation", filters={"plant_floor": M["PLANT_FLOOR"]}, pluck="workstation_type")
frappe.response["message"] = {
    "from_date": str(from_date), "to_date": str(to_date),
    "groups": [{"id": s.name, "workstation_type": s.workstation_type, "capacity": s.production_capacity, "status": s.status} for s in stations],
    "items": items, "job_card_count": len(status_of),
    "workstation_types": sorted(set(all_types)),
    "conflicts": {"count": len(conf), "job_cards": sorted({c["job_card"] for c in conf}), "rows": conf},
}
