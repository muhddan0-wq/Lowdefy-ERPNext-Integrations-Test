# POST /api/method/mes_work_order_action  {work_order, action: stop|resume|close|issue|finish, qty}
# Wraps ERPNext's own whitelisted work order methods; issue/finish build the stock entry with
# work_order.make_stock_entry, then insert + submit it. ERPNext stock validation applies unchanged.
# Batch items are issued from the batches scanned on the order; a batch-tracked product gets an output batch and an MES Batch Genealogy on finish.
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
    if action == "finish" and M["SF"]["ENFORCE_FINISH_GATE"]:
        reasons = M["gate"](M, wo, None, (wo.produced_qty or 0) + qty)["reasons"]
        if reasons:
            frappe.throw("Cannot finish %s until the shopfloor checks pass:<br>%s" % (name, "<br>".join(reasons[:12])))
    se_dict = frappe.call(WO_API + "make_stock_entry", work_order_id=name, purpose=purpose, qty=qty)
    se = frappe.get_doc(se_dict)
    if not se.stock_entry_type:
        # the desk form fills this from the purpose; the standard Stock Entry Types share the purpose name
        se.stock_entry_type = frappe.db.get_value("Stock Entry Type", {"purpose": purpose, "name": purpose}, "name") \
            or frappe.db.get_value("Stock Entry Type", {"purpose": purpose}, "name")
    taken = M["batch_split"](M, se, M["batch_available"](M, name, purpose), action == "issue")
    out_batch = None
    if action == "finish" and frappe.db.get_value("Item", wo.production_item, "has_batch_no"):
        out_batch = M["new_batch_id"](M, wo.production_item)
        frappe.get_doc({"doctype": "Batch", "batch_id": out_batch, "item": wo.production_item,
                        "manufacturing_date": frappe.utils.nowdate(), "reference_doctype": "Work Order",
                        "reference_name": name}).insert(ignore_permissions=True)
        for row in se.items:
            if row.item_code == wo.production_item and row.t_warehouse and not row.s_warehouse:
                row.batch_no = out_batch
                row.use_serial_batch_fields = 1
                row.serial_and_batch_bundle = None
    se.insert()
    se.submit()
    if out_batch:
        gen = frappe.get_doc({"doctype": "MES Batch Genealogy", "output_batch": out_batch, "item_code": wo.production_item,
                              "qty": qty, "work_order": name, "stock_entry": se.name})
        for t in taken:
            gen.append("inputs", {"item_code": t["item_code"], "batch_no": t["batch_no"], "qty": t["qty"], "stock_entry": se.name})
        gen.insert(ignore_permissions=True)
        result["output_batch"] = out_batch
        result["genealogy"] = gen.name
    result["batches"] = taken
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
