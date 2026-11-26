# POST /api/method/mes_sf_machine_issue  {operator, workstation, job_card?, issue_type, severity, machine_status, description, files?, request_id}
# Lightweight maintenance call: stores an MES Machine Issue on the workstation, raises priority to match the
# machine state, attaches photos and sends an ERPNext notification to maintenance and manufacturing managers.
# A Completely Down machine blocks starting or completing job cards on that workstation until it is resolved.
who = M["operator"](M)
emp = M["employee"](M, False)
if not (who["operate"] or who["maintenance"]):
    frappe.throw("Not permitted", frappe.PermissionError)
rid = M["arg"](M, "request_id")
prev = M["replay"](M, "MES Machine Issue", rid)
if prev:
    frappe.response["message"] = {"ok": True, "replayed": True, "issue": prev}
else:
    ws = M["arg"](M, "workstation")
    if not ws or frappe.db.get_value("Workstation", ws, "plant_floor") != M["PLANT_FLOOR"]:
        frappe.throw("Choose a workstation in %s" % (M["PLANT_FLOOR"],))
    meta = frappe.get_meta("MES Machine Issue")
    issue_type = M["arg"](M, "issue_type")
    machine_status = M["arg"](M, "machine_status")
    severity = M["arg"](M, "severity") or "Medium"
    for field, val in (("issue_type", issue_type), ("machine_status", machine_status), ("severity", severity)):
        if val not in (meta.get_field(field).options or "").split("\n"):
            frappe.throw("Choose a valid %s" % (field.replace("_", " "),))
    order = ["Low", "Medium", "High", "Critical"]
    floor = {"Completely Down": "Critical", "Stalled": "High"}.get(machine_status)
    if issue_type == "Safety Concern":
        floor = "Critical"
    if floor and order.index(floor) > order.index(severity):
        severity = floor
    description = (M["arg"](M, "description") or "").strip()
    if len(description) < 3:
        frappe.throw("Describe the problem")
    jc_name = M["arg"](M, "job_card")
    wo_name = None
    if jc_name:
        jrow = frappe.db.get_value("Job Card", jc_name, ["workstation", "work_order"], as_dict=True) or {}
        jc_ws = jrow.get("workstation")
        wo_name = jrow.get("work_order")
        if jc_ws != ws:
            jc_name = None
            wo_name = None
    files = M["json_arg"](M, "files", []) or []
    if len(files) > 6:
        frappe.throw("Attach at most 6 files")
    doc = frappe.get_doc({"doctype": "MES Machine Issue", "workstation": ws, "job_card": jc_name, "work_order": wo_name,
                          "issue_type": issue_type, "severity": severity, "machine_status": machine_status,
                          "description": description[:2000], "status": "Open", "reported_by": who["user"], "employee": emp["id"] if emp else None,
                          "reported_by_name": emp["name"] if emp else who["name"], "request_id": rid or None})
    doc.insert(ignore_permissions=True)
    stored = M["attach"](M, "MES Machine Issue", doc.name, files)
    sent = M["notify"](M, "[%s] %s: %s on %s" % (severity, machine_status, issue_type, ws), "MES Machine Issue", doc.name,
                       "%s reported %s on %s (%s): %s" % (who["name"], issue_type, ws, machine_status, description[:300]))
    affected = []
    if machine_status == "Completely Down":
        affected = frappe.get_all("Job Card", filters={"workstation": ws, "docstatus": 0, "status": ["not in", ["Completed", "Cancelled"]]}, pluck="name")
    frappe.response["message"] = {"ok": True, "replayed": False, "issue": doc.name, "severity": severity, "files": stored,
                                  "notified": sent, "blocked_job_cards": affected}
