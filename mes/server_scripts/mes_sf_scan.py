# POST /api/method/mes_sf_scan  {operator, job_card, value, qty?, qty_mode?, request_id}
# Batch-tracked items: scan the batch label once; qty_mode "remaining" takes the remaining requirement, capped by the batch's free quantity.
# qty_mode "remaining": a quantity-verified item scanned without a quantity counts for its whole remaining requirement.
# Validates one scan (or a quantity confirmation) against the work order's BOM materials and ERPNext's live
# unit/stock state. Every attempt is stored; only a fully valid one counts towards verification.
# The work order row is locked for the request and unit_key is a unique column, so two people cannot both
# record the same unit or overshoot a quantity at the same moment. Nothing is written before the locks, so the
# read-only transaction is rolled back first: the work order row lock (and, for a unit, the unit's own Tracked
# Item / Serial No row lock) are then the first statements of a fresh transaction, and every later read sees the
# latest committed scans. Locking anything wider would trip MariaDB 11.8 snapshot isolation (error 1020).
who = M["operator"](M, "operate")
emp = M["employee"](M, True)
rid = M["arg"](M, "request_id")


def scan_out(M, doc_name, replayed):
    s = frappe.db.get_value("MES Material Scan", doc_name,
                            ["name", "result", "reason", "item_code", "item_name", "unit_id", "serial_no", "batch_no", "qty", "scanned_value"], as_dict=True)
    img = frappe.db.get_value("Item", s.item_code, "image") if s.item_code else None
    return {"ok": s.result == "Valid", "replayed": replayed, "scan": s.name, "result": s.result, "reason": s.reason,
            "item_code": s.item_code, "item_name": s.item_name, "image": img, "unit_id": s.unit_id,
            "serial_no": s.serial_no, "batch_no": s.batch_no, "qty": s.qty, "value": s.scanned_value}


prev = M["replay"](M, "MES Material Scan", rid)
if prev:
    frappe.response["message"] = scan_out(M, prev, True)
else:
    name = M["arg"](M, "job_card")
    if not name or not frappe.db.exists("Job Card", name):
        frappe.throw("Job card %s not found" % (name,))
    jc = frappe.get_doc("Job Card", name)
    if jc.company != M["COMPANY"] or jc.docstatus != 0:
        frappe.throw("Job card %s is not open for this plant" % (name,))
    value = (M["arg"](M, "value") or "").strip()[:140]
    pre = M["resolve_scan"](M, value)
    frappe.db.rollback()
    frappe.db.sql("select name from `tabWork Order` where name=%s for update", jc.work_order)
    if pre and pre["unit_id"]:
        if pre["kind"] == "tracked unit":
            frappe.db.sql("select name from `tab" + M["SF"]["UNIT_DOCTYPE"] + "` where name=%s for update", pre["unit_id"])
        else:
            frappe.db.sql("select name from `tabSerial No` where name=%s for update", pre["unit_id"])
    if pre and pre.get("batch_no"):
        frappe.db.sql("select name from `tabBatch` where name=%s for update", pre["batch_no"])
    wo = frappe.get_doc("Work Order", jc.work_order)
    if wo.status in ("Completed", "Closed", "Cancelled", "Stopped"):
        frappe.throw("Work order %s is %s; materials can no longer be verified" % (wo.name, wo.status))
    qty_in = frappe.utils.flt(M["arg"](M, "qty"))
    reqs = {}
    for r in wo.required_items:
        reqs[r.item_code] = r
    mats = {}
    for m in M["materials"](M, wo):
        mats[m["item_code"]] = m
    rec = {"doctype": "MES Material Scan", "work_order": wo.name, "job_card": jc.name, "scanned_value": value,
           "operator": who["user"], "operator_name": emp["name"], "employee": emp["id"], "employee_name": emp["name"],
           "request_id": rid or None}
    res = M["resolve_scan"](M, value)
    reason = None
    info = None
    if not value:
        frappe.throw("Scan or type a barcode, serial number or item code")
    if not res:
        reason = "Unknown barcode or serial number: %s is not an item, barcode, serial number or tracked unit in ERPNext" % (value,)
    else:
        rec["item_code"] = res["item_code"]
        rec["resolved_as"] = res["kind"]
        rec["unit_id"] = res["unit_id"]
        rec["serial_no"] = res["serial_no"]
        rec["batch_no"] = res.get("batch_no") or None
        info = M["item_info"](M, res["item_code"])
        rec["item_name"] = info.item_name if info else ""
        if not info or info.disabled:
            reason = "Item %s is disabled or missing in ERPNext" % (res["item_code"],)
        elif res["item_code"] not in reqs:
            expected = [k for k in reqs if mats[k]["status"] != "Verified"]
            code = res["item_code"]
            twin = code[:-2] if code.endswith("-B") else code + "-B"
            if twin in reqs and code.endswith("-B"):
                reason = ("Wrong version: %s is the batch-tracked copy of %s. Work order %s uses %s without batches, "
                          "so its batch labels do not count here. Scan the %s item barcode, or use a work order whose BOM lists %s") % (
                    code, twin, wo.name, twin, twin, code)
            elif twin in reqs:
                reason = ("Wrong version: work order %s uses the batch-tracked copy %s, not %s. "
                          "Scan a batch label of %s") % (wo.name, twin, code, twin)
            else:
                reason = "Incorrect item: %s %s is not required for work order %s. Expected: %s" % (
                    code, info.item_name, wo.name, ", ".join(expected) or "nothing (all materials verified)")
        else:
            m = mats[res["item_code"]]
            r = reqs[res["item_code"]]
            allowed_wh = []
            for w in (r.source_warehouse, wo.source_warehouse, wo.wip_warehouse):
                if w and w not in allowed_wh:
                    allowed_wh.append(w)
            rec["scan_mode"] = {"unit": "Unit", "batch": "Batch", "scan": "Quantity", "confirm": "Confirm"}[info.mode]
            if info.mode == "unit":
                rec["qty"] = 1
                if not res["unit_id"]:
                    reason = "%s is tracked per unit: scan the unit's own label, not the item code" % (res["item_code"],)
                else:
                    ustate = M["unit_state"](M, res)
                    wh = ustate["warehouse"]
                    st = ustate["status"]
                    usable = ustate["usable"]
                    rec["warehouse"] = wh
                    key = res["item_code"] + "::" + res["unit_id"]
                    used = frappe.db.get_value("MES Material Scan", {"unit_key": key}, ["name", "work_order"], as_dict=True)
                    bad = frappe.db.get_value("MES Defect Report", {"item_code": res["item_code"], "unit_id": ["in", [res["unit_id"], res["serial_no"] or res["unit_id"]]],
                                                                    "status": ["!=", "Rejected"], "disposition": ["!=", "Use As Is"]}, "name")
                    if used and used.work_order == wo.name:
                        reason = "Duplicate scan: unit %s is already recorded on this work order (%s)" % (res["unit_id"], used.name)
                    elif used:
                        reason = "Unit %s was already used on work order %s" % (res["unit_id"], used.work_order)
                    elif not usable:
                        reason = "Unit %s is not available for use (status: %s)" % (res["unit_id"], st or "unknown")
                    elif wh not in allowed_wh:
                        reason = "Wrong location: unit %s is in %s, expected %s" % (res["unit_id"], wh or "no warehouse", " or ".join(allowed_wh))
                    elif bad:
                        reason = "Unit %s has an open defect report (%s)" % (res["unit_id"], bad)
                    elif m["units_scanned"] + 1 > (frappe.db.get_value("Bin", {"item_code": r.item_code, "warehouse": m["source_warehouse"]}, "actual_qty") or 0) + (r.transferred_qty or 0) + 1e-9:
                        reason = "Not enough stock: ERPNext has only %s %s in %s, so unit %s cannot be used (its tracking record is out of date)" % (
                            frappe.utils.flt(frappe.db.get_value("Bin", {"item_code": r.item_code, "warehouse": m["source_warehouse"]}, "actual_qty") or 0, 3),
                            res["item_code"], m["source_warehouse"], res["unit_id"])
                    elif m["units_scanned"] >= m["required_qty"] - 1e-9:
                        reason = "Quantity exceeds requirement: all %s units of %s are already verified" % (frappe.utils.flt(m["required_qty"], 3), res["item_code"])
                    else:
                        rec["unit_key"] = key
            elif info.mode == "batch":
                bno = res.get("batch_no")
                rec["warehouse"] = m["source_warehouse"]
                if not bno:
                    reason = "%s is tracked by batch: scan the batch label, not the item code" % (res["item_code"],)
                else:
                    bs = M["batch_state"](M, bno, allowed_wh, wo.name)
                    if qty_in <= 0 and M["arg"](M, "qty_mode") == "remaining":
                        qty_in = min(m["remaining_qty"], bs["free"])
                    rec["qty"] = qty_in
                    whole = frappe.db.get_value("UOM", info.stock_uom, "must_be_whole_number")
                    if bs["disabled"]:
                        reason = "Batch %s is disabled in ERPNext" % (bno,)
                    elif bs["expired"]:
                        reason = "Batch %s expired on %s" % (bno, bs["expiry_date"])
                    elif m["remaining_qty"] <= 1e-9:
                        reason = "Duplicate: %s is already fully verified for this work order" % (res["item_code"],)
                    elif bs["free"] <= 1e-9:
                        reason = "Batch %s has no free quantity: %s %s in %s, %s already claimed on this order, %s on other open orders" % (
                            bno, frappe.utils.flt(bs["stock"], 3), info.stock_uom, " or ".join(allowed_wh),
                            frappe.utils.flt(bs["claimed_here"], 3), frappe.utils.flt(bs["claimed_elsewhere"], 3))
                    elif qty_in <= 0:
                        reason = "Enter the quantity of %s you are using from batch %s (more than 0)" % (res["item_code"], bno)
                    elif whole and qty_in != int(qty_in):
                        reason = "%s is counted in whole %s: %s is not a whole number" % (res["item_code"], info.stock_uom, qty_in)
                    elif qty_in > m["remaining_qty"] + 1e-9:
                        reason = "Quantity exceeds requirement: only %s %s of %s still needed" % (frappe.utils.flt(m["remaining_qty"], 3), info.stock_uom, res["item_code"])
                    elif qty_in > bs["free"] + 1e-9:
                        reason = "Not enough in batch %s: only %s %s free" % (bno, frappe.utils.flt(bs["free"], 3), info.stock_uom)
            else:
                if qty_in <= 0 and M["arg"](M, "qty_mode") == "remaining":
                    qty_in = m["remaining_qty"]
                rec["qty"] = qty_in
                avail = (frappe.db.get_value("Bin", {"item_code": r.item_code, "warehouse": m["source_warehouse"]}, "actual_qty") or 0) + (r.transferred_qty or 0)
                rec["warehouse"] = m["source_warehouse"]
                whole = info.mode == "scan"
                if qty_in <= 0:
                    reason = "Enter the quantity of %s you are using (more than 0)" % (res["item_code"],)
                elif whole and qty_in != int(qty_in):
                    reason = "%s is counted in whole %s: %s is not a whole number" % (res["item_code"], info.stock_uom, qty_in)
                elif m["remaining_qty"] <= 1e-9:
                    reason = "Duplicate: %s is already fully verified for this work order" % (res["item_code"],)
                elif qty_in > m["remaining_qty"] + 1e-9:
                    reason = "Quantity exceeds requirement: only %s %s of %s still needed" % (frappe.utils.flt(m["remaining_qty"], 3), info.stock_uom, res["item_code"])
                elif m["verified_qty"] + qty_in > avail + 1e-9:
                    reason = "Not enough stock: %s has only %s %s available in %s" % (res["item_code"], frappe.utils.flt(avail, 3), info.stock_uom, m["source_warehouse"])
    if not reason and res and info and res["item_code"] in reqs:
        live = frappe.db.sql("""select count(*), coalesce(sum(qty), 0) from `tabMES Material Scan`
            where work_order=%s and item_code=%s and result='Valid'""", (wo.name, res["item_code"]))[0]
        m = mats[res["item_code"]]
        if info.mode == "unit":
            if live[0] >= m["required_qty"] - 1e-9:
                reason = "Quantity exceeds requirement: all %s units of %s were just verified by another scan" % (frappe.utils.flt(m["required_qty"], 3), res["item_code"])
        elif frappe.utils.flt(live[1]) - m["held_qty"] + qty_in > m["required_qty"] + 1e-9:
            reason = "Quantity exceeds requirement: only %s %s of %s still needed (another scan was just recorded)" % (
                frappe.utils.flt(max(m["required_qty"] - (frappe.utils.flt(live[1]) - m["held_qty"]), 0), 3), info.stock_uom, res["item_code"])
    if reason:
        rec["result"] = "Invalid"
        rec["reason"] = reason
        rec["unit_key"] = None
        doc = frappe.get_doc(rec).insert(ignore_permissions=True)
    else:
        rec["result"] = "Valid"
        rec["reason"] = "Verified as %s" % (res["kind"],) if not rec.get("batch_no") else "Verified from batch %s" % (rec["batch_no"],)
        try:
            doc = frappe.get_doc(rec).insert(ignore_permissions=True)
        except Exception as e:
            frappe.log_error("mes_sf_scan insert refused", "%s\n%s" % (rec, e))
            rec["result"] = "Invalid"
            if rec.get("unit_key"):
                rec["reason"] = "Unit %s was recorded by another scan at the same moment" % (res["unit_id"],)
            else:
                rec["reason"] = "This scan clashed with another scan at the same moment; nothing was recorded, scan again"
            rec["unit_key"] = None
            if rid and frappe.db.get_value("MES Material Scan", {"request_id": rid}, "name"):
                rec["request_id"] = None
            doc = frappe.get_doc(rec).insert(ignore_permissions=True)
    out = scan_out(M, doc.name, False)
    out["material"] = [m for m in M["materials"](M, wo) if m["item_code"] == rec.get("item_code")]
    out["expected"] = [k for k in reqs if mats[k]["status"] != "Verified"]
    frappe.response["message"] = out
