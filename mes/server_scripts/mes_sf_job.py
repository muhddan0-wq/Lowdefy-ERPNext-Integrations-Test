# POST /api/method/mes_sf_job  {operator, job_card}
# One job for the shopfloor: product, materials with verification state, scans, defects, machine issues,
# progress and the backend's own list of what still blocks start/completion.
who = M["operator"](M)
name = M["arg"](M, "job_card")
if not name or not frappe.db.exists("Job Card", name):
    frappe.throw("Job card %s not found" % (name,))
jc = frappe.get_doc("Job Card", name)
if jc.company != M["COMPANY"]:
    frappe.throw("Job card %s does not belong to %s" % (name, M["COMPANY"]), frappe.PermissionError)
wo = frappe.get_doc("Work Order", jc.work_order)
g = M["gate"](M, wo, jc.workstation, max(jc.total_completed_qty or 0, 1))
reasons = g["reasons"]
mats = g["materials"]
fg = M["item_info"](M, wo.production_item) or {}
scans = frappe.get_all("MES Material Scan", filters={"work_order": wo.name},
                       fields=["name", "item_code", "item_name", "result", "reason", "unit_id", "serial_no", "batch_no", "qty",
                               "scanned_value", "operator_name", "employee", "employee_name", "creation"], order_by="creation desc", limit_page_length=500)
unit_ids = list({s.unit_id for s in scans if s.unit_id})
codes = {}
if unit_ids and M["has_units"](M):
    for t in frappe.get_all(M["SF"]["UNIT_DOCTYPE"], filters={"name": ["in", unit_ids]}, fields=["name", "barcode"]):
        codes[t.name] = t.barcode
for s in scans:
    s["barcode"] = codes.get(s.unit_id) or ""
defects = frappe.get_all("MES Defect Report", filters={"work_order": wo.name},
                         fields=["name", "item_code", "item_name", "unit_id", "qty_affected", "category", "description", "status",
                                 "disposition", "resolution_comments", "reported_by_name", "creation"], order_by="creation desc")
for d in defects:
    d["files"] = M["files"](M, "MES Defect Report", d.name)
issues = frappe.get_all("MES Machine Issue", filters={"workstation": jc.workstation},
                        fields=["name", "issue_type", "severity", "machine_status", "status", "description", "reported_by_name",
                                "assigned_to", "resolution_notes", "creation"], order_by="creation desc", limit_page_length=10)
logs = [{"from_time": l.from_time, "to_time": l.to_time, "completed_qty": l.completed_qty, "mins": l.time_in_mins} for l in jc.time_logs]
running = [l for l in jc.time_logs if l.from_time and not l.to_time]
done = jc.docstatus == 1 or jc.status == "Completed"
down = M["machine_down"](M, jc.workstation)
start_reasons = M["start_reasons"](M, wo, jc.workstation)
summary = {"materials_total": len(mats), "materials_verified": len([m for m in mats if m["status"] == "Verified"]),
           "outstanding": len([m for m in mats if m["status"] != "Verified"]),
           "buildable": g["kits"],
           "invalid_scans": sum([m["invalid_scans"] for m in mats]),
           "defective": len([m for m in mats if m["status"] == "Defective Material"]),
           "open_defects": len([d for d in defects if d.status in M["SF"]["BLOCKING_DEFECT"]])}
frappe.response["message"] = {
    "operator": who,
    "job": {"job_card": jc.name, "operation": jc.operation, "workstation": jc.workstation, "docstatus": jc.docstatus,
            "status": "Running" if running else ("Paused" if jc.is_paused else jc.status),
            "qty": jc.for_quantity, "completed_qty": jc.total_completed_qty,
            "remaining_qty": max((jc.for_quantity or 0) - (jc.total_completed_qty or 0), 0),
            "running_since": running[0].from_time if running else None, "time_logs": logs},
    "work_order": {"name": wo.name, "status": wo.status, "qty": wo.qty, "produced_qty": wo.produced_qty,
                   "item_code": wo.production_item, "item_name": wo.item_name, "image": fg.get("image"),
                   "source_warehouse": wo.source_warehouse, "skip_transfer": wo.skip_transfer,
                   "transferred_qty": wo.material_transferred_for_manufacturing or 0, "operations": [{"operation": o.operation, "status": o.status,
                                                                            "completed_qty": o.completed_qty} for o in wo.operations]},
    "materials": mats,
    "workflow": M["job_workflow"](M, wo, mats),
    "summary": summary,
    "blocking": reasons,
    "scans": scans,
    "defects": defects,
    "machine_issues": issues,
    "machine": {"down": 1 if down else 0, "issue": down.name if down else None},
    "start_blocking": start_reasons,
    "issue": {"needed": bool(not wo.skip_transfer and wo.required_items), "issued": (wo.material_transferred_for_manufacturing or 0),
              "left": max((wo.qty or 0) - (wo.material_transferred_for_manufacturing or 0), 0),
              "entries": frappe.get_all("Stock Entry", filters={"work_order": wo.name, "docstatus": 1, "purpose": "Material Transfer for Manufacture"},
                                        fields=["name", "posting_date", "fg_completed_qty"], order_by="creation desc")},
    "actions": {"start": bool(not done and not running and not start_reasons),
                "issue": bool(not done and not wo.skip_transfer and wo.required_items and (wo.material_transferred_for_manufacturing or 0) < (wo.qty or 0)),
                "report": bool(running), "pause": bool(running),
                "complete": bool(not done and not reasons and ((jc.total_completed_qty or 0) > 0 or running))},
}
