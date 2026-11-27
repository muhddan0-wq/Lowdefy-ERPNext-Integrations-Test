# POST /api/method/mes_sf_issue  {operator, job_card}
# "Issue materials" from the station screen: ERPNext's own Material Transfer for Manufacture stock entry
# (stores -> work in progress) for the quantity of the work order not yet transferred, built with
# work_order.make_stock_entry, then inserted and submitted. Shortages are reported in plain language first.
# Batch-tracked materials are issued only from the batches scanned on this order; unscanned ones are listed, nothing is issued.
# Serial-numbered materials scanned before Issue are moved by exactly those serial numbers (otherwise ERPNext picks them).
# Every batch-tracked material must be scanned (verified) first; per-unit and plain items are scanned later at Build, before
# units can be reported. The person's ID badge (`employee`) is required and recorded.
WO_API = "erpnext.manufacturing.doctype.work_order.work_order."
who = M["operator"](M, "operate")
emp = M["employee"](M, True)
name = M["arg"](M, "job_card")
if not name or not frappe.db.exists("Job Card", name):
    frappe.throw("Job card %s not found" % (name,))
jc = frappe.get_doc("Job Card", name)
if jc.company != M["COMPANY"]:
    frappe.throw("Job card %s does not belong to %s" % (name, M["COMPANY"]), frappe.PermissionError)
frappe.db.rollback()
frappe.db.sql("select name from `tabWork Order` where name=%s for update", jc.work_order)
wo = frappe.get_doc("Work Order", jc.work_order)
if wo.docstatus != 1 or wo.status in ("Closed", "Cancelled", "Completed", "Stopped"):
    frappe.throw("Work order %s is %s; materials cannot be issued" % (wo.name, wo.status))
result = {"ok": True, "work_order": wo.name, "stock_entry": None, "shortages": []}
qty = (wo.qty or 0) - (wo.material_transferred_for_manufacturing or 0)
if wo.skip_transfer:
    result["message"] = "This work order consumes materials directly; no issue is needed"
elif qty <= 0:
    result["message"] = "All materials for %s are already issued" % (wo.name,)
else:
    short = []
    for r in wo.required_items:
        need = frappe.utils.flt((r.required_qty or 0) - (r.transferred_qty or 0), 6)
        wh = r.source_warehouse or wo.source_warehouse
        have = frappe.db.get_value("Bin", {"item_code": r.item_code, "warehouse": wh}, "actual_qty") or 0
        if need > 0 and have + 1e-9 < need:
            short.append("%s %s: need %s, %s in %s" % (r.item_code, r.item_name, frappe.utils.flt(need, 3), frappe.utils.flt(have, 3), wh))
    pending = [m for m in M["materials"](M, wo) if m["mode"] == "batch" and m["status"] != "Verified"]
    if short:
        result["ok"] = False
        result["shortages"] = short
    elif pending:
        result["ok"] = False
        result["scans_needed"] = ["%s %s: %s" % (m["item_code"], m["item_name"], m["status"]) for m in pending]
        result["message"] = "Scan the batch label of every batch-tracked material before issuing, so ERPNext moves exactly those batches"
    else:
        purpose = "Material Transfer for Manufacture"
        se = frappe.get_doc(frappe.call(WO_API + "make_stock_entry", work_order_id=wo.name, purpose=purpose, qty=qty))
        if not se.stock_entry_type:
            se.stock_entry_type = frappe.db.get_value("Stock Entry Type", {"purpose": purpose, "name": purpose}, "name") \
                or frappe.db.get_value("Stock Entry Type", {"purpose": purpose}, "name")
        avail = M["batch_available"](M, wo.name, purpose)
        unscanned = []
        for row in se.items:
            if row.s_warehouse and frappe.db.get_value("Item", row.item_code, "has_batch_no"):
                have = sum([a["qty"] for a in avail if a["item_code"] == row.item_code])
                if have + 1e-9 < frappe.utils.flt(row.qty):
                    unscanned.append("%s %s: %s %s to issue, %s covered by scanned batches" % (
                        row.item_code, row.item_name, frappe.utils.flt(row.qty, 3), row.stock_uom or row.uom, frappe.utils.flt(have, 3)))
        if unscanned:
            result["ok"] = False
            result["batch_scans_needed"] = unscanned
            result["message"] = "Scan the batch label of each batch-tracked material before issuing, so ERPNext moves the batches you took"
        else:
            result["batches"] = M["batch_split"](M, se, avail, True)
            result["serials"] = []
            for row in se.items:
                if row.s_warehouse and frappe.db.get_value("Item", row.item_code, "has_serial_no"):
                    sns = frappe.get_all("MES Material Scan", filters={"work_order": wo.name, "item_code": row.item_code, "result": "Valid",
                                                                        "serial_no": ["is", "set"]}, pluck="serial_no", order_by="creation asc")
                    sns = [s for s in sns if frappe.db.get_value("Serial No", s, "warehouse") == row.s_warehouse]
                    need = int(frappe.utils.flt(row.qty))
                    if need > 0 and len(sns) >= need:
                        row.serial_no = "\n".join(sns[:need])
                        row.use_serial_batch_fields = 1
                        row.serial_and_batch_bundle = None
                        result["serials"] = result["serials"] + sns[:need]
            se.remarks = "Issued at the shopfloor by %s %s (%s)" % (emp["id"], emp["name"], who["user"])
            se.insert()
            se.submit()
            wo.add_comment("Comment", "Materials issued from the shopfloor by %s %s (%s, qty %s)" % (emp["id"], emp["name"], se.name, qty))
            result["stock_entry"] = se.name
            result["qty"] = qty
after = frappe.db.get_value("Work Order", wo.name, ["status", "material_transferred_for_manufacturing"], as_dict=True)
result["status"] = after.status
result["transferred_qty"] = after.material_transferred_for_manufacturing
frappe.response["message"] = result
