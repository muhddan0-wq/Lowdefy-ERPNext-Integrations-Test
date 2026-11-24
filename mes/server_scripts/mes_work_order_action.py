# POST /api/method/mes_work_order_action  {work_order, action: stop|resume|close|issue|finish, qty}
# Wraps ERPNext's own whitelisted work order methods; issue/finish build the stock entry with
# work_order.make_stock_entry, then insert + submit it. ERPNext stock validation applies unchanged.
WO_API = "erpnext.manufacturing.doctype.work_order.work_order."
name = M["arg"](M, "work_order")
action = (M["arg"](M, "action") or "").lower()
if not name or not frappe.db.exists("Work Order", name):
    frappe.throw("Work order %s not found" % (name,))
wo = frappe.get_doc("Work Order", name)
if wo.company != M["COMPANY"]:
    frappe.throw("Work order %s does not belong to %s" % (name, M["COMPANY"],), frappe.PermissionError)
if wo.docstatus != 1:
    frappe.throw("Work order %s is not submitted" % (name,))
result = {"work_order": name, "action": action, "before": wo.status}

if action == "stop":
    if wo.status not in ("Not Started", "In Process"):
        frappe.throw("Only Not Started or In Process work orders can be stopped (status is %s)" % (wo.status,))
    frappe.call(WO_API + "stop_unstop", work_order=name, status="Stopped")
elif action == "resume":
    if wo.status != "Stopped":
        frappe.throw("Only Stopped work orders can be resumed (status is %s)" % (wo.status,))
    frappe.call(WO_API + "stop_unstop", work_order=name, status="Resumed")
elif action == "close":
    if wo.status in ("Closed", "Cancelled", "Completed"):
        frappe.throw("Work order is already %s" % (wo.status,))
    frappe.call(WO_API + "close_work_order", work_order=name, status="Closed")
elif action in ("issue", "finish"):
    if wo.status in ("Closed", "Cancelled", "Completed", "Stopped"):
        frappe.throw("Work order is %s; no stock entries allowed" % (wo.status,))
    qty = frappe.utils.flt(M["arg"](M, "qty"))
    if action == "issue":
        purpose = "Material Transfer for Manufacture"
        limit = (wo.qty or 0) - (wo.material_transferred_for_manufacturing or 0)
    else:
        purpose = "Manufacture"
        limit = (wo.material_transferred_for_manufacturing or 0) - (wo.produced_qty or 0)
    if qty <= 0:
        frappe.throw("Quantity must be greater than 0")
    if qty > limit:
        frappe.throw("Quantity %s is more than the %s that can be %s" % (qty, limit, "issued" if action == "issue" else "finished (issue materials first)",))
    se_dict = frappe.call(WO_API + "make_stock_entry", work_order_id=name, purpose=purpose, qty=qty)
    se = frappe.get_doc(se_dict)
    if not se.stock_entry_type:
        # the desk form fills this from the purpose; the standard Stock Entry Types share the purpose name
        se.stock_entry_type = frappe.db.get_value("Stock Entry Type", {"purpose": purpose, "name": purpose}, "name") \
            or frappe.db.get_value("Stock Entry Type", {"purpose": purpose}, "name")
    se.insert()
    se.submit()
    result["stock_entry"] = se.name
    result["purpose"] = purpose
    result["qty"] = qty
else:
    frappe.throw("Unknown action %s; use stop, resume, close, issue or finish" % (action,))

after = frappe.db.get_value("Work Order", name, ["status", "material_transferred_for_manufacturing", "produced_qty"], as_dict=True)
result["status"] = after.status
result["transferred_qty"] = after.material_transferred_for_manufacturing
result["produced_qty"] = after.produced_qty
frappe.response["message"] = result
