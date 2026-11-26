# POST /api/method/mes_sf_admin  {operator, action, ...}
#   overview                       supervisor or maintenance: defect reports, machine issues, recent invalid scans
#   my_reports                     anyone: the operator's own defect reports and machine issues
#   defect_update  {name, status, disposition?, comments?}           supervisor
#   issue_update   {name, status?, assigned_to?, notes?}             maintenance (supervisor may only acknowledge)
#   void_scan      {name, reason}                                    supervisor: withdraws a valid scan made by mistake
who = M["operator"](M)
action = (M["arg"](M, "action") or "").lower()
DEF_FIELDS = ["name", "work_order", "job_card", "item_code", "item_name", "unit_id", "qty_affected", "category", "description",
              "status", "disposition", "resolution_comments", "reported_by_name", "reviewed_by", "reviewed_on", "creation"]
ISS_FIELDS = ["name", "workstation", "work_order", "job_card", "issue_type", "severity", "machine_status", "description", "status",
              "assigned_to", "resolution_notes", "reported_by_name", "acknowledged_by", "acknowledged_on", "resolved_by",
              "resolved_on", "creation"]
now = frappe.utils.now_datetime()
out = {"ok": True, "operator": who}

if action == "overview":
    if not (who["supervisor"] or who["maintenance"]):
        frappe.throw("Not permitted: supervisors and maintenance only", frappe.PermissionError)
    if who["supervisor"]:
        out["defects"] = frappe.get_all("MES Defect Report", fields=DEF_FIELDS, order_by="creation desc", limit_page_length=100)
        for d in out["defects"]:
            d["image"] = frappe.db.get_value("Item", d.item_code, "image")
            d["files"] = M["files"](M, "MES Defect Report", d.name)
        out["invalid_scans"] = frappe.get_all("MES Material Scan", filters={"result": "Invalid"},
                                              fields=["name", "work_order", "item_code", "scanned_value", "reason", "operator_name", "creation"],
                                              order_by="creation desc", limit_page_length=50)
    issues = frappe.get_all("MES Machine Issue", fields=ISS_FIELDS, order_by="creation desc", limit_page_length=100)
    rank = {"Open": 0, "Acknowledged": 1, "In Progress": 2, "Resolved": 3, "Closed": 4}
    sev = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    issues = sorted(issues, key=lambda i: (rank.get(i.status, 9), sev.get(i.severity, 9)))
    for i in issues:
        i["files"] = M["files"](M, "MES Machine Issue", i.name)
    out["issues"] = issues
    out["maintenance_users"] = sorted(set(frappe.get_all("Has Role", filters={"role": ["in", ["Maintenance User", "Maintenance Manager"]],
                                                                               "parenttype": "User"}, pluck="parent")))
elif action == "my_reports":
    out["defects"] = frappe.get_all("MES Defect Report", filters={"reported_by": who["user"]}, fields=DEF_FIELDS, order_by="creation desc", limit_page_length=50)
    out["issues"] = frappe.get_all("MES Machine Issue", filters={"reported_by": who["user"]}, fields=ISS_FIELDS, order_by="creation desc", limit_page_length=50)
elif action == "defect_update":
    if not who["supervisor"]:
        frappe.throw("Not permitted: only supervisors decide defects", frappe.PermissionError)
    doc = frappe.get_doc("MES Defect Report", M["arg"](M, "name"))
    status = M["arg"](M, "status") or doc.status
    disposition = M["arg"](M, "disposition", doc.disposition or "")
    comments = M["arg"](M, "comments")
    meta = frappe.get_meta("MES Defect Report")
    if status not in meta.get_field("status").options.split("\n"):
        frappe.throw("Unknown status %s" % (status,))
    if disposition and disposition not in meta.get_field("disposition").options.split("\n"):
        frappe.throw("Unknown disposition %s" % (disposition,))
    if status in ("Resolved", "Rework Required") and not disposition:
        frappe.throw("Choose a disposition before marking the defect %s" % (status,))
    if status == "Rejected":
        disposition = ""
    doc.status = status
    doc.disposition = disposition
    if comments:
        doc.resolution_comments = ((doc.resolution_comments or "") + "\n" if doc.resolution_comments else "") + "%s: %s" % (who["name"], comments)
    doc.reviewed_by = who["user"]
    doc.reviewed_on = now
    doc.save(ignore_permissions=True)
    restored = []
    if doc.unit_id and doc.work_order and (status == "Rejected" or disposition == "Use As Is"):
        for s in frappe.get_all("MES Material Scan", filters={"work_order": doc.work_order, "unit_id": doc.unit_id, "result": "Defective"}, pluck="name"):
            frappe.db.set_value("MES Material Scan", s, {"result": "Valid", "reason": "Restored by %s after defect %s: %s" % (who["name"], doc.name, status if status == "Rejected" else disposition)})
            restored.append(s)
    if doc.work_order:
        frappe.get_doc("Work Order", doc.work_order).add_comment("Comment", "Defect %s set to %s%s by %s" % (doc.name, status, (" / " + disposition) if disposition else "", who["name"]))
    if doc.reported_by:
        M["notify"](M, "Defect %s is now %s" % (doc.name, status), "MES Defect Report", doc.name, comments or status, users=[doc.reported_by])
    out["defect"] = frappe.db.get_value("MES Defect Report", doc.name, DEF_FIELDS, as_dict=True)
    out["restored_scans"] = restored
elif action == "issue_update":
    doc = frappe.get_doc("MES Machine Issue", M["arg"](M, "name"))
    status = M["arg"](M, "status") or doc.status
    assigned = M["arg"](M, "assigned_to")
    notes = M["arg"](M, "notes")
    order = ["Open", "Acknowledged", "In Progress", "Resolved", "Closed"]
    if status not in order:
        frappe.throw("Unknown status %s" % (status,))
    if not who["maintenance"]:
        if not (who["supervisor"] and status == "Acknowledged" and doc.status == "Open" and not assigned):
            frappe.throw("Not permitted: only maintenance can assign, progress or resolve machine issues", frappe.PermissionError)
    if doc.status == "Closed" and status != "Closed":
        frappe.throw("Issue %s is closed" % (doc.name,))
    if order.index(status) < order.index(doc.status) and not (doc.status == "Resolved" and status == "In Progress"):
        frappe.throw("Cannot move issue from %s back to %s" % (doc.status, status))
    if status in ("Resolved", "Closed") and not (notes or doc.resolution_notes):
        frappe.throw("Add resolution notes before marking the issue %s" % (status,))
    if assigned:
        roles = frappe.get_all("Has Role", filters={"parent": assigned, "parenttype": "User"}, pluck="role")
        if not [r for r in roles if r in ("Maintenance User", "Maintenance Manager")]:
            frappe.throw("%s is not maintenance personnel" % (assigned,))
        doc.assigned_to = assigned
    if status != doc.status and status in ("Acknowledged", "In Progress") and not doc.acknowledged_by:
        doc.acknowledged_by = who["user"]
        doc.acknowledged_on = now
    if status in ("Resolved", "Closed") and doc.status not in ("Resolved", "Closed"):
        doc.resolved_by = who["user"]
        doc.resolved_on = now
    if notes:
        doc.resolution_notes = ((doc.resolution_notes or "") + "\n" if doc.resolution_notes else "") + "%s: %s" % (who["name"], notes)
    doc.status = status
    doc.save(ignore_permissions=True)
    rcpt = [u for u in (doc.reported_by, doc.assigned_to) if u and u != who["user"]]
    if rcpt:
        M["notify"](M, "Machine issue %s on %s: %s" % (doc.name, doc.workstation, status), "MES Machine Issue", doc.name, notes or status, users=rcpt)
    out["issue"] = frappe.db.get_value("MES Machine Issue", doc.name, ISS_FIELDS, as_dict=True)
elif action == "void_scan":
    if not who["supervisor"]:
        frappe.throw("Not permitted: only supervisors can void a scan", frappe.PermissionError)
    reason = (M["arg"](M, "reason") or "").strip()
    if len(reason) < 3:
        frappe.throw("Give a reason for voiding the scan")
    s = frappe.db.get_value("MES Material Scan", M["arg"](M, "name"), ["name", "result", "work_order"], as_dict=True)
    if not s or s.result not in ("Valid", "Defective"):
        frappe.throw("Only a valid or defective scan can be voided")
    frappe.db.set_value("MES Material Scan", s.name, {"result": "Voided", "unit_key": None, "reason": "Voided by %s: %s" % (who["name"], reason)})
    frappe.get_doc("Work Order", s.work_order).add_comment("Comment", "Scan %s voided by %s: %s" % (s.name, who["name"], reason))
    out["scan"] = s.name
else:
    frappe.throw("Unknown action %s" % (action,))
frappe.response["message"] = out
