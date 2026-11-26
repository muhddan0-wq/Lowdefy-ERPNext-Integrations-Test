# POST /api/method/mes_sf_jobs  {operator, workstation?, work_order?}
# work_order: also list that order's open job cards at every station (opening an order from the Work Orders page).
# Shopfloor home: who is working, the plant's workstations, and the open job cards (optionally one workstation).
who = M["operator"](M)
ws_filter = M["arg"](M, "workstation")
stations = frappe.get_all("Workstation", filters={"plant_floor": M["PLANT_FLOOR"]}, fields=["name", "workstation_type"], order_by="name asc")
open_issues = frappe.get_all("MES Machine Issue", filters={"status": ["in", M["SF"]["OPEN_ISSUE"]]},
                             fields=["name", "workstation", "issue_type", "severity", "machine_status", "status", "creation"],
                             order_by="creation desc")
by_ws = {}
for i in open_issues:
    by_ws.setdefault(i.workstation, []).append(i)
for s in stations:
    issues = by_ws.get(s.name, [])
    s["open_issues"] = len(issues)
    s["down"] = 1 if [i for i in issues if i.machine_status == "Completely Down"] else 0
    s["machine_status"] = "Completely Down" if s["down"] else (issues[0].machine_status if issues else "Operating Normally")

filters = {"company": M["COMPANY"], "docstatus": 0, "status": ["not in", ["Completed", "Cancelled"]]}
if ws_filter:
    filters["workstation"] = ws_filter
jcs = frappe.get_all("Job Card", filters=filters,
                     fields=["name", "work_order", "operation", "workstation", "status", "is_paused", "for_quantity",
                             "total_completed_qty", "expected_start_date", "production_item"],
                     order_by="expected_start_date asc", limit_page_length=300)
wo_cache = {}
jobs = []
for jc in jcs:
    if jc.work_order not in wo_cache:
        wo = frappe.get_doc("Work Order", jc.work_order)
        if wo.status in ("Completed", "Closed", "Cancelled", "Stopped") or wo.company != M["COMPANY"]:
            wo_cache[jc.work_order] = None
        else:
            mats = M["materials"](M, wo)
            done = len([m for m in mats if m["status"] == "Verified"])
            wo_cache[jc.work_order] = {"wo": wo, "materials_total": len(mats), "materials_verified": done,
                                       "defective": len([m for m in mats if m["status"] == "Defective Material"])}
    c = wo_cache[jc.work_order]
    if not c:
        continue
    wo = c["wo"]
    info = M["item_info"](M, wo.production_item) or {}
    running = frappe.db.exists("Job Card Time Log", {"parent": jc.name, "to_time": ["is", "not set"], "from_time": ["is", "set"]})
    jobs.append({"job_card": jc.name, "work_order": wo.name, "operation": jc.operation, "workstation": jc.workstation,
                 "status": "Running" if running else ("Paused" if jc.is_paused else jc.status),
                 "item_code": wo.production_item, "item_name": wo.item_name, "image": info.get("image"),
                 "qty": jc.for_quantity, "completed_qty": jc.total_completed_qty,
                 "remaining_qty": max((jc.for_quantity or 0) - (jc.total_completed_qty or 0), 0),
                 "scheduled_start": jc.expected_start_date,
                 "materials_total": c["materials_total"], "materials_verified": c["materials_verified"],
                 "defective_materials": c["defective"],
                 "machine_down": 1 if [i for i in by_ws.get(jc.workstation, []) if i.machine_status == "Completely Down"] else 0})
wo_jobs = []
wo_arg = M["arg"](M, "work_order")
if wo_arg:
    for j in frappe.get_all("Job Card", filters={"work_order": wo_arg, "company": M["COMPANY"], "docstatus": 0, "status": ["not in", ["Completed", "Cancelled"]]},
                            fields=["name", "workstation", "operation", "status", "sequence_id", "expected_start_date"], order_by="sequence_id asc, expected_start_date asc, name asc"):
        wo_jobs.append({"job_card": j.name, "workstation": j.workstation, "operation": j.operation, "status": j.status})
frappe.response["message"] = {"operator": who, "workstations": stations, "jobs": jobs, "wo_jobs": wo_jobs,
                              "issues": [i for i in open_issues if not ws_filter or i.workstation == ws_filter]}
