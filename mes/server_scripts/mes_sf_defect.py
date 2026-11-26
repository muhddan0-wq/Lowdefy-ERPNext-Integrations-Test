# POST /api/method/mes_sf_defect  {operator, job_card, item_code, unit_id?, qty_affected?, category, description, files?, request_id}
# Reports a defect on a material or the finished product. Files arrive base64-encoded and are stored as private
# ERPNext Files on the report. No stock moves: disposition is a supervisor decision in ERPNext.
# A defective unit that was already verified on this work order stops counting as verified straight away.
who = M["operator"](M, "operate")
emp = M["employee"](M, True)
rid = M["arg"](M, "request_id")
prev = M["replay"](M, "MES Defect Report", rid)
if prev:
    frappe.response["message"] = {"ok": True, "replayed": True, "defect": prev, "files": M["files"](M, "MES Defect Report", prev)}
else:
    name = M["arg"](M, "job_card")
    if not name or not frappe.db.exists("Job Card", name):
        frappe.throw("Job card %s not found" % (name,))
    jc = frappe.get_doc("Job Card", name)
    if jc.company != M["COMPANY"]:
        frappe.throw("Job card %s does not belong to %s" % (name, M["COMPANY"]), frappe.PermissionError)
    wo = frappe.get_doc("Work Order", jc.work_order)
    item_code = M["arg"](M, "item_code")
    allowed = [wo.production_item] + [r.item_code for r in wo.required_items]
    if item_code not in allowed:
        frappe.throw("%s is not the product or a material of work order %s" % (item_code, wo.name))
    category = M["arg"](M, "category")
    cats = (frappe.get_meta("MES Defect Report").get_field("category").options or "").split("\n")
    if category not in cats:
        frappe.throw("Choose a defect category")
    description = (M["arg"](M, "description") or "").strip()
    if len(description) < 3:
        frappe.throw("Describe the defect")
    unit_id = (M["arg"](M, "unit_id") or "").strip()
    if unit_id:
        res = M["resolve_scan"](M, unit_id)
        if not res or not res["unit_id"]:
            frappe.throw("Unit or serial number %s is not known in ERPNext" % (unit_id,))
        if res["item_code"] != item_code:
            frappe.throw("Unit %s belongs to %s, not %s" % (unit_id, res["item_code"], item_code))
        unit_id = res["unit_id"]
    qty = frappe.utils.flt(M["arg"](M, "qty_affected")) or 1
    if unit_id:
        qty = 1
    if qty <= 0:
        frappe.throw("Quantity affected must be more than 0")
    files = M["json_arg"](M, "files", []) or []
    if len(files) > 6:
        frappe.throw("Attach at most 6 files")
    doc = frappe.get_doc({"doctype": "MES Defect Report", "work_order": wo.name, "job_card": jc.name, "item_code": item_code,
                          "item_name": frappe.db.get_value("Item", item_code, "item_name"), "unit_id": unit_id, "qty_affected": qty,
                          "category": category, "description": description[:2000], "status": "Reported",
                          "reported_by": who["user"], "reported_by_name": emp["name"] if emp else who["name"],
                          "employee": emp["id"] if emp else None, "request_id": rid or None})
    doc.insert(ignore_permissions=True)
    stored = M["attach"](M, "MES Defect Report", doc.name, files)
    flagged = []
    if unit_id:
        for s in frappe.get_all("MES Material Scan", filters={"work_order": wo.name, "unit_id": unit_id, "result": "Valid"}, pluck="name"):
            frappe.db.set_value("MES Material Scan", s, {"result": "Defective", "reason": "Defect reported: %s" % (doc.name,)})
            flagged.append(s)
    wo.add_comment("Comment", "Defect %s reported on %s%s by %s: %s" % (doc.name, item_code, (" unit " + unit_id) if unit_id else "", who["name"], category))
    sent = M["notify"](M, "Defect %s on %s (%s)" % (doc.name, item_code, category), "MES Defect Report", doc.name,
                       "%s reported %s on work order %s: %s" % (who["name"], category, wo.name, description[:300]),
                       roles=["Manufacturing Manager", "Quality Manager"])
    frappe.response["message"] = {"ok": True, "replayed": False, "defect": doc.name, "files": stored,
                                  "flagged_scans": flagged, "notified": sent}
