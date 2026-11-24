# POST /api/method/mes_workstation_queue {workstation, date}   (no workstation -> list of P1 workstations)
# Operator queue: unfinished job cards on the workstation scheduled up to the end of `date`
# (overdue first), in scheduled order, plus anything completed today. Actions go to the standard
# /api/v2/document/Job Card/{name}/method/start_timer | pause_job | resume_job | complete_job_card.
ws = M["arg"](M, "workstation")
if not ws:
    # no workstation: return the P1 workstations for the picker
    frappe.response["message"] = {"stations": frappe.get_all("Workstation", filters={"plant_floor": M["PLANT_FLOOR"]},
                                                             fields=["name", "workstation_type", "status"], order_by="name asc")}
else:
    if frappe.db.get_value("Workstation", ws, "plant_floor") != M["PLANT_FLOOR"]:
        frappe.throw("Workstation %s is not on %s" % (ws, M["PLANT_FLOOR"],))
    day = frappe.utils.getdate(M["arg"](M, "date", frappe.utils.today()))
    day_end = frappe.utils.get_datetime(str(frappe.utils.add_days(day, 1)))
    rows = frappe.db.sql(
        """select jc.name, jc.work_order, jc.production_item, jc.item_name, jc.operation, jc.status, jc.docstatus,
            jc.is_paused, jc.for_quantity, jc.total_completed_qty, jc.expected_start_date, jc.expected_end_date,
            jc.custom_work_instructions, jc.actual_start_date, jc.actual_end_date
        from `tabJob Card` jc
        left join `tabWork Order` wo on wo.name = jc.work_order
        left join `tabProduction Plan` pp on pp.name = wo.production_plan
        where jc.company = %(c)s and jc.workstation = %(ws)s and jc.docstatus < 2
          and ifnull(pp.custom_mes_tag, '') not like 'history-%%'
          and ((jc.docstatus = 0 and jc.status != 'Completed' and jc.expected_start_date < %(end)s)
               or (date(jc.actual_end_date) = %(day)s))
        order by jc.expected_start_date""",
        {"c": M["COMPANY"], "ws": ws, "end": day_end, "day": str(day)}, as_dict=True)
    out = []
    for r in rows:
        running = frappe.db.sql("select count(*) as n from `tabJob Card Time Log` where parent=%s and from_time is not null and to_time is null",
                                r.name, as_dict=True)[0].n
        if r.docstatus == 1 or r.status == "Completed":
            state = "Completed"
        elif r.is_paused:
            state = "Paused"
        elif running:
            state = "Running"
        elif r.status == "Work In Progress":
            state = "Paused"
        else:
            state = "Not started"
        out.append({"job_card": r.name, "work_order": r.work_order, "item": r.production_item, "item_name": r.item_name,
                    "operation": r.operation, "status": r.status, "state": state, "qty": r.for_quantity,
                    "completed_qty": r.total_completed_qty, "scheduled_start": r.expected_start_date,
                    "scheduled_end": r.expected_end_date, "overdue": 1 if (state != "Completed" and r.expected_end_date and r.expected_end_date < frappe.utils.now_datetime()) else 0,
                    "work_instructions": r.custom_work_instructions or frappe.db.get_value("Operation", r.operation, "description"),
                    "docstatus": r.docstatus})
    frappe.response["message"] = {"workstation": ws, "date": str(day), "status": frappe.db.get_value("Workstation", ws, "status"), "jobs": out}
