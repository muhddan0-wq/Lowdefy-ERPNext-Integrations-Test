# --- MES prelude (prepended to every mes_* API server script by install_server_scripts.py) ---
# Server scripts run with separate globals/locals, so top-level functions cannot see each other.
# Everything shared lives in the dict M and every helper takes M as its first argument.
M = {
    @@SITE@@
    "ROLES": ["Manufacturing User", "Manufacturing Manager", "System Manager"],
}

mes_roles = frappe.get_all("Has Role", filters={"parent": frappe.session.user, "parenttype": "User"}, pluck="role")
if frappe.session.user != "Administrator" and not [r for r in mes_roles if r in M["ROLES"]]:
    frappe.throw("Not permitted: requires Manufacturing User or Manufacturing Manager", frappe.PermissionError)


def mes_arg(M, key, default=None):
    v = frappe.form_dict.get(key)
    return default if v in (None, "", "null", "undefined") else v


def mes_json_arg(M, key, default=None):
    v = M["arg"](M, key, default)
    if isinstance(v, str):
        v = json.loads(v)
    return v


def mes_minutes(M, t):
    """Time (timedelta or 'HH:MM:SS') -> minutes after midnight."""
    return int(frappe.utils.to_timedelta(t).total_seconds() // 60)


def mes_at(M, day, minutes):
    return frappe.utils.add_to_date(frappe.utils.get_datetime(str(frappe.utils.getdate(day))), minutes=minutes)


def mes_dt_minutes(M, dt):
    dt = frappe.utils.get_datetime(dt)
    return dt.hour * 60 + dt.minute + dt.second / 60.0


def mes_calendar(M, workstation):
    w = frappe.db.get_value(
        "Workstation", workstation,
        ["name", "workstation_type", "production_capacity", "holiday_list", "plant_floor"], as_dict=True)
    if not w:
        frappe.throw("Workstation %s not found" % (workstation,))
    rows = frappe.db.sql(
        """select start_time, end_time from `tabWorkstation Working Hour`
        where parent=%s and parenttype='Workstation' and enabled=1 order by start_time""",
        workstation, as_dict=True)
    w["shifts"] = [[M["minutes"](M, r.start_time), M["minutes"](M, r.end_time)] for r in rows]
    w["capacity"] = int(w.production_capacity or 1)
    hol = []
    if w.holiday_list:
        hol = frappe.get_all("Holiday", filters={"parent": w.holiday_list}, fields=["holiday_date", "description"])
    w["holidays"] = {str(h.holiday_date): h.description for h in hol}
    return w


def mes_conflicts(M, from_time=None, to_time=None, workstation=None):
    """Every scheduled slot where more distinct open job cards overlap than the workstation capacity."""
    cond = ""
    vals = {"company": M["COMPANY"]}
    if from_time:
        cond += " and s.to_time > %(from_time)s"
        vals["from_time"] = from_time
    if to_time:
        cond += " and s.from_time < %(to_time)s"
        vals["to_time"] = to_time
    if workstation:
        cond += " and jc.workstation = %(workstation)s"
        vals["workstation"] = workstation
    rows = frappe.db.sql(
        """select jc.name, jc.workstation, s.from_time, s.to_time
        from `tabJob Card` jc join `tabJob Card Scheduled Time` s on s.parent = jc.name
        where jc.company = %(company)s and jc.docstatus < 2 and jc.status != 'Completed'""" + cond,
        vals, as_dict=True)
    by_ws = {}
    for r in rows:
        by_ws.setdefault(r.workstation, []).append(r)
    caps = {}
    out = []
    for ws in by_ws:
        slots = by_ws[ws]
        if ws not in caps:
            caps[ws] = int(frappe.db.get_value("Workstation", ws, "production_capacity") or 1)
        cap = caps[ws]
        for slot in slots:
            others = [o for o in slots if o.from_time < slot.to_time and slot.from_time < o.to_time]
            points = [slot.from_time] + [o.from_time for o in others if slot.from_time < o.from_time < slot.to_time]
            worst = 0
            worst_names = []
            for t in points:
                names = sorted({o.name for o in others if o.from_time <= t < o.to_time})
                if len(names) > worst:
                    worst = len(names)
                    worst_names = names
            if worst > cap:
                out.append({"workstation": ws, "job_card": slot.name, "from_time": slot.from_time,
                            "to_time": slot.to_time, "concurrent": worst, "capacity": cap,
                            "with": [n for n in worst_names if n != slot.name]})
    return out


M["SF"] = {
    "API_USERS": ["appsmith-mes@local.test", "copilot-api@copilot.local"],
    "UNIT_DOCTYPE": "Tracked Item",
    "BLOCKING_DEFECT": ["Reported", "Under Review", "Rework Required"],
    "OPEN_ISSUE": ["Open", "Acknowledged", "In Progress"],
    "NOTIFY_ROLES": ["Maintenance Manager", "Maintenance User", "Manufacturing Manager"],
    "ENFORCE_FINISH_GATE": True,
}


def mes_operator(M, need=None):
    """The shopfloor person behind this call. Appsmith sends its logged-in user's email as `operator`;
    it must be an enabled ERPNext user, and their ERPNext roles decide what they may do."""
    email = M["arg"](M, "operator")
    if not email:
        frappe.throw("Operator is required")
    u = frappe.db.get_value("User", email, ["name", "full_name", "enabled"], as_dict=True)
    if not u or not u.enabled or u.name in M["SF"]["API_USERS"]:
        frappe.throw("%s is not an active ERPNext user for the shopfloor" % (email,), frappe.PermissionError)
    roles = frappe.get_all("Has Role", filters={"parent": u.name, "parenttype": "User"}, pluck="role")
    admin = u.name == "Administrator" or "System Manager" in roles
    sup = admin or "Manufacturing Manager" in roles
    maint = admin or "Maintenance Manager" in roles or "Maintenance User" in roles
    op = sup or "Manufacturing User" in roles
    if not (op or maint):
        frappe.throw("%s has no shopfloor role" % (email,), frappe.PermissionError)
    who = {"user": u.name, "name": u.full_name or u.name, "operate": op, "supervisor": sup,
           "maintenance": maint, "admin": admin,
           "role": "Administrator" if admin else "Supervisor" if sup else "Maintenance" if maint and not op else "Shopfloor"}
    if need and not who[need]:
        frappe.throw("Not permitted: this needs %s rights" % (need,), frappe.PermissionError)
    return who


def mes_find_employee(M, code):
    """Resolve an ID badge: the Employee ID, the attendance device ID, or the employee's full name (any case)."""
    code = (code or "").strip()
    if not code:
        return None
    fields = ["name", "employee_name", "status", "company", "designation", "department", "image"]
    e = frappe.db.get_value("Employee", code, fields, as_dict=True)
    if not e:
        hit = frappe.get_all("Employee", filters={"attendance_device_id": code}, pluck="name", limit_page_length=2)
        if not hit:
            hit = frappe.get_all("Employee", filters={"employee_name": code, "company": M["COMPANY"]}, pluck="name", limit_page_length=2)
        if len(hit) == 1:
            e = frappe.db.get_value("Employee", hit[0], fields, as_dict=True)
    return e


def mes_employee(M, required=True):
    """The person at the station, identified by their ID badge (`employee`). Recorded on every scan, issue, time log and report."""
    code = M["arg"](M, "employee")
    if not code:
        if required:
            frappe.throw("Scan your ID badge first, so ERPNext records who did this")
        return None
    e = M["find_employee"](M, code)
    if not e:
        frappe.throw("ID badge %s is not an employee in ERPNext" % (code,))
    if e.status != "Active":
        frappe.throw("Employee %s %s is %s and cannot work on the shopfloor" % (e.name, e.employee_name, e.status))
    if e.company != M["COMPANY"]:
        frappe.throw("Employee %s %s does not belong to %s" % (e.name, e.employee_name, M["COMPANY"]))
    return {"id": e.name, "name": e.employee_name, "designation": e.designation, "department": e.department, "image": e.image}


def mes_replay(M, doctype, request_id):
    """Idempotency: a request id that was already stored returns the stored record instead of a duplicate."""
    if not request_id:
        return None
    return frappe.db.get_value(doctype, {"request_id": request_id}, "name")


def mes_has_units(M):
    if "units_cached" not in M:
        M["units_cached"] = bool(frappe.db.exists("DocType", M["SF"]["UNIT_DOCTYPE"]))
    return M["units_cached"]


def mes_item_info(M, item_code):
    it = frappe.db.get_value("Item", item_code, ["name", "item_name", "image", "has_serial_no", "has_batch_no", "stock_uom", "disabled"], as_dict=True)
    if not it:
        return None
    units = it.has_serial_no or (not it.has_batch_no and M["has_units"](M) and frappe.db.exists(M["SF"]["UNIT_DOCTYPE"], {"item_code": item_code}))
    whole = frappe.db.get_value("UOM", it.stock_uom, "must_be_whole_number")
    it["mode"] = "unit" if units else ("batch" if it.has_batch_no else ("scan" if whole else "confirm"))
    it["mode_label"] = {"unit": "Scan every unit", "batch": "Scan batch label, then quantity", "scan": "Scan item, then quantity",
                        "confirm": "Confirm quantity"}[it["mode"]]
    return it


def mes_resolve_scan(M, value):
    """Scanned text -> {item_code, unit_id, serial_no, kind}. Accepts tracked-unit labels (raw id or QR URL),
    ERPNext serial numbers, ERPNext batch numbers, Item Barcodes and plain item codes. Returns None when nothing matches."""
    v = (value or "").strip()
    if not v:
        return None
    if "?" in v and "=" in v:
        params = {}
        for part in v.split("?", 1)[1].split("&"):
            kv = part.split("=", 1)
            if len(kv) == 2 and kv[0]:
                params[kv[0]] = kv[1].replace("%20", " ").replace("+", " ")
        for key in ("tracking_id", "serial_no", "batch_no", "barcode", "item_code"):
            if params.get(key):
                v = params[key]
                break
    if M["has_units"](M):
        t = frappe.db.get_value(M["SF"]["UNIT_DOCTYPE"], {"name": v}, ["name", "item_code", "serial_no"], as_dict=True) \
            or frappe.db.get_value(M["SF"]["UNIT_DOCTYPE"], {"barcode": v}, ["name", "item_code", "serial_no"], as_dict=True) \
            or frappe.db.get_value(M["SF"]["UNIT_DOCTYPE"], {"serial_no": v}, ["name", "item_code", "serial_no"], as_dict=True)
        if t:
            return {"item_code": t.item_code, "unit_id": t.name, "serial_no": t.serial_no or "", "batch_no": "", "kind": "tracked unit", "value": v}
    s = frappe.db.get_value("Serial No", v, ["name", "item_code"], as_dict=True)
    if s:
        return {"item_code": s.item_code, "unit_id": s.name, "serial_no": s.name, "batch_no": "", "kind": "serial number", "value": v}
    bt = frappe.db.get_value("Batch", v, ["name", "item"], as_dict=True)
    if bt:
        return {"item_code": bt.item, "unit_id": "", "serial_no": "", "batch_no": bt.name, "kind": "batch", "value": v}
    b = frappe.db.get_value("Item Barcode", {"barcode": v}, "parent")
    if b:
        return {"item_code": b, "unit_id": "", "serial_no": "", "batch_no": "", "kind": "item barcode", "value": v}
    if frappe.db.exists("Item", v):
        return {"item_code": v, "unit_id": "", "serial_no": "", "batch_no": "", "kind": "item code", "value": v}
    return None


def mes_batch_state(M, batch_no, warehouses, work_order):
    """Live state of one ERPNext batch: stock in the given warehouses, less quantity already claimed by valid MES scans
    on open work orders (claimed on this order is reported separately)."""
    b = frappe.db.get_value("Batch", batch_no, ["name", "item", "disabled", "expiry_date"], as_dict=True)
    stock = 0
    seen = []
    for w in warehouses:
        if w in seen:
            continue
        seen.append(w)
        stock += frappe.utils.flt(frappe.call("erpnext.stock.doctype.batch.batch.get_batch_qty", batch_no=batch_no, warehouse=w))
    rows = frappe.db.sql("""select s.work_order, coalesce(sum(s.qty), 0) as qty from `tabMES Material Scan` s
        join `tabWork Order` w on w.name = s.work_order
        where s.batch_no=%s and s.result='Valid' and w.status not in ('Completed', 'Closed', 'Cancelled')
        group by s.work_order""", batch_no, as_dict=True)
    mine = sum([frappe.utils.flt(r.qty) for r in rows if r.work_order == work_order])
    others = sum([frappe.utils.flt(r.qty) for r in rows if r.work_order != work_order])
    expired = bool(b.expiry_date) and str(b.expiry_date) < frappe.utils.nowdate()
    return {"stock": stock, "claimed_here": mine, "claimed_elsewhere": others, "free": max(stock - mine - others, 0),
            "disabled": bool(b.disabled), "expired": expired, "expiry_date": str(b.expiry_date or "")}


def mes_new_batch_id(M, item_code):
    if M["has_units"](M):
        try:
            n = frappe.call("item_tracking.item_tracking.doctype.tracked_item.tracked_item.reserve_number")
        except Exception:
            n = None
        if n and not frappe.db.exists("Batch", n):
            return n
    prefix ="%s-%s-" % (item_code, frappe.utils.nowdate().replace("-", ""))
    seq = frappe.db.count("Batch", {"name": ["like", prefix + "%"]}) + 1
    while frappe.db.exists("Batch", "%s%03d" % (prefix, seq)):
        seq += 1
    return "%s%03d" % (prefix, seq)


def mes_batch_moves(M, wo_name, purpose):
    out = {}
    bundled = frappe.db.sql("""select d.item_code, b.batch_no, sum(abs(b.qty)) as qty from `tabStock Entry Detail` d
        join `tabStock Entry` e on e.name = d.parent
        join `tabSerial and Batch Entry` b on b.parent = d.serial_and_batch_bundle
        where e.work_order=%s and e.purpose=%s and e.docstatus=1 and coalesce(d.s_warehouse, '') != ''
        and coalesce(b.batch_no, '') != '' group by d.item_code, b.batch_no""", (wo_name, purpose), as_dict=True)
    plain = frappe.db.sql("""select d.item_code, d.batch_no, sum(d.qty) as qty from `tabStock Entry Detail` d
        join `tabStock Entry` e on e.name = d.parent
        where e.work_order=%s and e.purpose=%s and e.docstatus=1 and coalesce(d.s_warehouse, '') != ''
        and coalesce(d.serial_and_batch_bundle, '') = '' and coalesce(d.batch_no, '') != ''
        group by d.item_code, d.batch_no""", (wo_name, purpose), as_dict=True)
    for r in bundled + plain:
        k = r.item_code + "::" + r.batch_no
        out[k] = out.get(k, 0) + frappe.utils.flt(r.qty)
    return out


def mes_batch_available(M, wo_name, purpose):
    if purpose == "Material Transfer for Manufacture":
        src = frappe.db.sql("""select item_code, batch_no, sum(qty) as qty, min(creation) as first from `tabMES Material Scan`
            where work_order=%s and result='Valid' and coalesce(batch_no, '') != ''
            group by item_code, batch_no order by first""", wo_name, as_dict=True)
        used = M["batch_moves"](M, wo_name, purpose)
    else:
        moved = M["batch_moves"](M, wo_name, "Material Transfer for Manufacture")
        src = []
        for k in moved:
            src.append({"item_code": k.split("::")[0], "batch_no": k.split("::", 1)[1], "qty": moved[k]})
        used = M["batch_moves"](M, wo_name, "Manufacture")
    out = []
    for r in src:
        left = frappe.utils.flt(r["qty"]) - used.get(r["item_code"] + "::" + r["batch_no"], 0)
        if left > 1e-9:
            out.append({"item_code": r["item_code"], "batch_no": r["batch_no"], "qty": left})
    return out


def mes_batch_split(M, se, available, strict):
    rows = []
    taken = []
    missing = []
    for row in se.items:
        d = row.as_dict()
        for k in ("name", "idx", "parent", "parentfield", "parenttype", "creation", "modified", "owner", "modified_by", "docstatus"):
            d.pop(k, None)
        mine = [a for a in available if a["item_code"] == row.item_code]
        batched = row.s_warehouse and frappe.db.get_value("Item", row.item_code, "has_batch_no")
        if not batched or (not strict and not mine):
            rows.append(d)
            continue
        need = frappe.utils.flt(row.qty)
        cf = frappe.utils.flt(row.conversion_factor) or 1
        for a in mine:
            if need <= 1e-9:
                break
            take = min(need, a["qty"])
            if take <= 1e-9:
                continue
            a["qty"] = a["qty"] - take
            need = need - take
            part = dict(d)
            part.update({"qty": take, "transfer_qty": take * cf, "batch_no": a["batch_no"], "use_serial_batch_fields": 1,
                         "serial_and_batch_bundle": None})
            rows.append(part)
            taken.append({"item_code": row.item_code, "batch_no": a["batch_no"], "qty": take})
        if need > 1e-9:
            missing.append("%s: %s more not covered by a scanned batch" % (row.item_code, frappe.utils.flt(need, 3)))
    if missing:
        frappe.throw("Scan the batch labels before issuing these batch items:<br>" + "<br>".join(missing))
    se.set("items", [])
    for d in rows:
        se.append("items", d)
    return taken


def mes_unit_state(M, res):
    """Live stock state of one unit from ERPNext: (warehouse, status, usable)."""
    if res["kind"] == "tracked unit":
        t = frappe.db.get_value(M["SF"]["UNIT_DOCTYPE"], res["unit_id"], ["current_warehouse", "current_status"], as_dict=True)
        wh = t.current_warehouse
        st = t.current_status
        if res["serial_no"]:
            sn = frappe.db.get_value("Serial No", res["serial_no"], ["status", "warehouse"], as_dict=True)
            if sn and sn.status != "Active":
                return {"warehouse": wh, "status": "serial %s" % (sn.status,), "usable": False}
        return {"warehouse": wh, "status": st, "usable": st == "In Stock"}
    sn = frappe.db.get_value("Serial No", res["serial_no"], ["status", "warehouse"], as_dict=True)
    return {"warehouse": sn.warehouse, "status": sn.status, "usable": sn.status == "Active" and bool(sn.warehouse)}


def mes_materials(M, wo):
    """Required materials of a work order with live MES verification state and stock."""
    scans = frappe.get_all("MES Material Scan", filters={"work_order": wo.name},
                           fields=["item_code", "result", "qty", "unit_id", "creation"], order_by="creation asc")
    defects = frappe.get_all("MES Defect Report", filters={"work_order": wo.name},
                             fields=["item_code", "unit_id", "qty_affected", "status", "disposition"])
    out = []
    for r in wo.required_items:
        info = M["item_info"](M, r.item_code) or {}
        mine = [s for s in scans if s.item_code == r.item_code]
        valid = [s for s in mine if s.result == "Valid"]
        bad_units = [s for s in mine if s.result == "Defective"]
        invalid = [s for s in mine if s.result == "Invalid"]
        held_qty = 0
        open_defect = False
        for d in defects:
            if d.item_code != r.item_code:
                continue
            if d.status in M["SF"]["BLOCKING_DEFECT"] or (d.status == "Accepted" and not d.disposition):
                open_defect = True
            if not d.unit_id and d.status != "Rejected" and d.disposition != "Use As Is":
                held_qty += d.qty_affected or 0
        verified = len(valid) if info.get("mode") == "unit" else max(sum([s.qty or 0 for s in valid]) - held_qty, 0)
        required = r.required_qty or 0
        wh = r.source_warehouse or wo.source_warehouse or M["WH"]["stores"]
        if open_defect:
            status = "Defective Material"
        elif verified >= required - 1e-9 and required > 0:
            status = "Verified"
        elif verified > 0:
            status = "Partially Verified"
        elif mine and mine[-1].result == "Invalid":
            status = "Invalid Material"
        elif scans:
            status = "Awaiting Scan"
        else:
            status = "Not Started"
        out.append({"item_code": r.item_code, "item_name": r.item_name, "image": info.get("image"),
                    "mode": info.get("mode"), "mode_label": info.get("mode_label"), "uom": r.stock_uom,
                    "per_unit": round(required / wo.qty, 6) if wo.qty else 0, "required_qty": required,
                    "verified_qty": verified, "remaining_qty": max(required - verified, 0),
                    "units_scanned": len(valid) if info.get("mode") == "unit" else 0,
                    "defective_units": len(bad_units), "held_qty": held_qty, "invalid_scans": len(invalid),
                    "source_warehouse": wh, "issued_qty": r.transferred_qty or 0,
                    "in_stock": frappe.db.get_value("Bin", {"item_code": r.item_code, "warehouse": wh}, "actual_qty") or 0,
                    "status": status})
    return out


def mes_machine_down(M, workstation):
    if not workstation:
        return None
    return frappe.db.get_value("MES Machine Issue",
                               {"workstation": workstation, "machine_status": "Completely Down", "status": ["in", M["SF"]["OPEN_ISSUE"]]},
                               ["name", "issue_type", "creation"], as_dict=True)


def mes_kits(M, wo, mats):
    """Complete sets scanned: how many finished units the verified materials cover (the scarcest material decides)."""
    best = wo.qty or 0
    for m in mats:
        if m["per_unit"] > 0:
            best = min(best, int(frappe.utils.flt(m["verified_qty"]) / m["per_unit"] + 1e-6))
    return max(best, 0)


def mes_gate(M, wo, workstation=None, done_qty=None):
    """Every reason production on this work order may not start or complete. Empty list = clear.
    done_qty: finished units to be covered; materials then only need to be scanned for that many complete sets."""
    mats = M["materials"](M, wo)
    reasons = []
    kits = M["kits"](M, wo, mats)
    for m in mats:
        if done_qty is not None:
            if kits + 1e-9 < done_qty and m["per_unit"] > 0 and frappe.utils.flt(m["verified_qty"]) / m["per_unit"] + 1e-6 < done_qty:
                reasons.append("%s %s: only %s %s scanned, enough for %s of the %s finished units" % (m["item_code"], m["item_name"],
                               frappe.utils.flt(m["verified_qty"], 3), m["uom"] or "", int(frappe.utils.flt(m["verified_qty"]) / m["per_unit"] + 1e-6), frappe.utils.flt(done_qty, 3)))
        elif m["status"] != "Verified":
            reasons.append("%s %s: %s of %s %s verified (%s)" % (m["item_code"], m["item_name"], frappe.utils.flt(m["verified_qty"], 3),
                                                                 frappe.utils.flt(m["required_qty"], 3), m["uom"] or "", m["status"]))
    for d in frappe.get_all("MES Defect Report", filters={"work_order": wo.name}, fields=["name", "item_code", "status", "disposition"]):
        if d.status in M["SF"]["BLOCKING_DEFECT"]:
            reasons.append("Defect %s on %s is %s and needs a supervisor decision" % (d.name, d.item_code, d.status))
        elif d.status == "Accepted" and not d.disposition:
            reasons.append("Defect %s on %s is accepted but has no disposition" % (d.name, d.item_code))
    down = M["machine_down"](M, workstation)
    if down:
        reasons.append("Machine %s is Completely Down (issue %s); maintenance must resolve it first" % (workstation, down.name))
    return {"reasons": reasons, "materials": mats, "kits": kits}


def mes_start_reasons(M, wo, workstation=None):
    """What blocks STARTING production: materials not issued, undecided defects, machine down.
    Scanning is not needed to start; it is needed before good units can be reported or the job completed."""
    reasons = []
    if not wo.skip_transfer and (wo.material_transferred_for_manufacturing or 0) <= 0 and wo.required_items:
        reasons.append("Materials for %s have not been issued yet: tap Issue materials first" % (wo.name,))
    for d in frappe.get_all("MES Defect Report", filters={"work_order": wo.name}, fields=["name", "item_code", "status", "disposition"]):
        if d.status in M["SF"]["BLOCKING_DEFECT"]:
            reasons.append("Defect %s on %s is %s and needs a supervisor decision" % (d.name, d.item_code, d.status))
    down = M["machine_down"](M, workstation)
    if down:
        reasons.append("Machine %s is Completely Down (issue %s); maintenance must resolve it first" % (workstation, down.name))
    return reasons


def mes_notify(M, subject, doctype, name, text, roles=None, users=None):
    if users is None:
        users = frappe.get_all("Has Role", filters={"role": ["in", roles or M["SF"]["NOTIFY_ROLES"]], "parenttype": "User"}, pluck="parent")
    sent = []
    for u in sorted(set(users)):
        if u in M["SF"]["API_USERS"] or u == "Guest" or not frappe.db.get_value("User", u, "enabled"):
            continue
        frappe.get_doc({"doctype": "Notification Log", "for_user": u, "type": "Alert", "subject": subject,
                        "email_content": text, "document_type": doctype, "document_name": name}).insert(ignore_permissions=True)
        sent.append(u)
    return sent


def mes_attach(M, doctype, name, files):
    """Store base64 attachments ({file_name, data}) as private ERPNext Files on the record."""
    out = []
    for f in files or []:
        fn = (f.get("file_name") or "attachment").replace("/", "_").replace("\\", "_")[:120]
        data = f.get("data") or ""
        if "," in data[:100] and data.startswith("data:"):
            data = data.split(",", 1)[1]
        if not data:
            continue
        if len(data) > 14000000:
            frappe.throw("Attachment %s is larger than 10 MB" % (fn,))
        doc = frappe.get_doc({"doctype": "File", "file_name": fn, "attached_to_doctype": doctype, "attached_to_name": name,
                              "is_private": 1, "content": data, "decode": True})
        doc.insert(ignore_permissions=True)
        out.append({"file_name": doc.file_name, "file_url": doc.file_url})
    return out


def mes_files(M, doctype, name):
    return frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name},
                          fields=["file_name", "file_url", "is_private"], order_by="creation asc")


M["WF"] = {"MAX_DEPTH": 10, "IMAGE_EXT": ["jpg", "jpeg", "png", "gif", "webp", "svg"],
           "STATUS_FLAGS": ["Expert Review", "Missing Information", "Missing Image", "Component Removed", "Component Added", "Quantity Changed", "Not In BOM"]}


def mes_item_image(M, code, image_field):
    if image_field:
        return image_field, "Item image field"
    for f in frappe.get_all("File", filters={"attached_to_doctype": "Item", "attached_to_name": code},
                            fields=["file_url"], order_by="creation asc"):
        ext = (f.file_url or "").lower().rsplit(".", 1)[-1]
        if ext in M["WF"]["IMAGE_EXT"]:
            return f.file_url, "File attachment"
    return None, None


def mes_item_facts(M, code):
    it = frappe.db.get_value("Item", code, ["name", "item_name", "description", "item_group", "image", "stock_uom",
                                            "has_serial_no", "has_batch_no", "disabled"], as_dict=True)
    if not it:
        return None
    it["barcodes"] = [r[0] for r in frappe.db.sql(
        "select barcode from `tabItem Barcode` where parenttype='Item' and parent=%s order by idx", code)]
    img = M["item_image"](M, code, it.image)
    it["image"] = img[0]
    it["image_source"] = img[1]
    return it


def mes_active_boms(M, code):
    return frappe.get_all("BOM", filters={"item": code, "is_active": 1, "docstatus": 1},
                          fields=["name", "is_default", "quantity", "uom", "creation"],
                          order_by="is_default desc, creation desc")


def mes_bom_node(M, code, per_unit, parents, depth, bom_name=None, operation=None):
    f = M["item_facts"](M, code)
    node = {"item_code": code, "item_name": f.item_name if f else code, "description": (f.description or "") if f else "",
            "item_group": f.item_group if f else None, "uom": f.stock_uom if f else None,
            "qty_per_unit": round(per_unit, 6), "operation": operation or None,
            "has_serial_no": int(f.has_serial_no or 0) if f else 0, "has_batch_no": int(f.has_batch_no or 0) if f else 0,
            "barcodes": f.barcodes if f else [], "image": f.image if f else None,
            "image_source": f.image_source if f else None, "disabled": int(f.disabled or 0) if f else 0,
            "exists": bool(f), "bom": None, "bom_candidates": 0, "operations": [], "children": [], "flags": [], "cycle": 0}
    if not f:
        node["flags"].append("Item not found in ERPNext")
    if f and f.disabled:
        node["flags"].append("Item is disabled")
    if f and not f.image:
        node["flags"].append("No image")
    if code in parents:
        node["cycle"] = 1
        node["flags"].append("Circular BOM reference")
        return node
    if depth >= M["WF"]["MAX_DEPTH"]:
        node["flags"].append("Depth limit reached")
        return node
    if bom_name:
        boms = frappe.get_all("BOM", filters={"name": bom_name, "is_active": 1, "docstatus": 1},
                              fields=["name", "is_default", "quantity", "uom", "creation"])
    else:
        boms = M["active_boms"](M, code)
    if not boms:
        return node
    bom = boms[0]
    node["bom"] = bom.name
    node["bom_candidates"] = len(boms)
    if len(boms) > 1:
        node["flags"].append("Ambiguous: %d active BOMs, %s used" % (len(boms), bom.name))
    node["operations"] = frappe.get_all("BOM Operation", filters={"parent": bom.name, "parenttype": "BOM"},
                                        fields=["operation", "workstation", "time_in_mins", "idx"], order_by="idx asc")
    qty = bom.quantity or 1
    for r in frappe.get_all("BOM Item", filters={"parent": bom.name, "parenttype": "BOM"},
                            fields=["item_code", "qty", "bom_no", "operation", "idx"], order_by="idx asc"):
        node["children"].append(M["bom_node"](M, r.item_code, per_unit * (r.qty or 0) / qty, parents + [code], depth + 1,
                                              r.bom_no or None, r.operation))
    return node


def mes_walk(M, node, out, depth=0):
    out.append([node, depth])
    for c in node["children"]:
        M["walk"](M, c, out, depth + 1)
    return out


def mes_bom_tree(M, code):
    return M["bom_node"](M, code, 1.0, [], 0)


def mes_tree_summary(M, root):
    rows = M["walk"](M, root, [])
    nodes = [r[0] for r in rows]
    components = [n for n in nodes[1:] if not n["cycle"]]
    leaves = {}
    for n in components:
        if not n["children"] and n["bom"] is None:
            leaves[n["item_code"]] = n
    flags = []
    for r in rows:
        for fl in r[0]["flags"]:
            flags.append({"item_code": r[0]["item_code"], "flag": fl})
    return {"components": len(components), "distinct_components": len({n["item_code"] for n in components}),
            "sub_assemblies": len({n["item_code"] for n in components if n["bom"]}),
            "raw_materials": len(leaves), "max_depth": max([r[1] for r in rows] or [0]),
            "cycles": len([n for n in nodes if n["cycle"]]),
            "missing_images": len({n["item_code"] for n in components if not n["image"]}),
            "ambiguous_boms": len({n["item_code"] for n in nodes if n["bom_candidates"] > 1}),
            "flags": flags}


def mes_edges(M, node, out):
    for c in node["children"]:
        out.append([node["item_code"], c["item_code"], round(c["qty_per_unit"], 4)])
        M["edges"](M, c, out)
    return out


def mes_signature(M, root):
    return json.dumps(sorted(M["edges"](M, root, [])))


def mes_bom_diff(M, baseline_json, current_json):
    base = {(e[0], e[1]): e[2] for e in json.loads(baseline_json or "[]")}
    cur = {(e[0], e[1]): e[2] for e in json.loads(current_json or "[]")}
    diff = []
    for k in sorted(base):
        if k not in cur:
            diff.append({"kind": "Component Removed", "parent": k[0], "item_code": k[1], "was": base[k], "now": None})
        elif abs(cur[k] - base[k]) > 1e-6:
            diff.append({"kind": "Quantity Changed", "parent": k[0], "item_code": k[1], "was": base[k], "now": cur[k]})
    for k in sorted(cur):
        if k not in base:
            diff.append({"kind": "Component Added", "parent": k[0], "item_code": k[1], "was": None, "now": cur[k]})
    return diff


def mes_workflow_for(M, finished_item):
    return frappe.db.get_value("MES Assembly Workflow", {"finished_item": finished_item}, "name")


def mes_job_workflow(M, wo, mats):
    wf_name = M["workflow_for"](M, wo.production_item)
    binding = frappe.db.get_value("MES Workflow Binding", wo.name, ["workflow", "version"], as_dict=True)
    if not binding:
        if not wf_name:
            return {"status": "none", "steps": []}
        approved = frappe.db.get_value("MES Assembly Workflow", wf_name, "approved_version")
        if not approved:
            return {"status": "none", "steps": []}
        b = frappe.get_doc({"doctype": "MES Workflow Binding", "work_order": wo.name, "product": wo.production_item,
                            "workflow": wf_name, "version": approved, "bound_on": frappe.utils.now_datetime()})
        b.insert(ignore_permissions=True)
        binding = {"workflow": wf_name, "version": approved}
    snap = frappe.db.get_value("MES Assembly Version", {"parent": binding["workflow"], "parenttype": "MES Assembly Workflow",
                                                        "version": binding["version"]}, "snapshot")
    steps = json.loads(snap or "[]")
    by_item = {m["item_code"]: m for m in mats}
    out = []
    for s in steps:
        code = s.get("item_code")
        m = by_item.get(code) if code else None
        signoff = bool(s.get("checklist") or s.get("quality_inspection") or s.get("photo_required"))
        if code and m is None:
            st = "Not Required"
        elif m is not None and m["status"] == "Verified":
            st = "Awaiting sign-off" if signoff else "Complete"
        elif code:
            st = "Upcoming"
        else:
            st = "Awaiting sign-off"
        img = s.get("image_override")
        if not img and code:
            facts = M["item_facts"](M, code)
            img = facts.image if facts else None
        out.append({"step_no": s.get("step_no"), "step_name": s.get("step_name"), "description": s.get("description") or "",
                    "instructions": [x for x in (s.get("instructions") or "").split("\n") if x.strip()],
                    "item_code": code, "item_name": s.get("item_name"), "image": img,
                    "required_qty": round((s.get("qty") or 0) * (wo.qty or 0), 6) if s.get("qty") else None,
                    "verified_qty": m["verified_qty"] if m else None, "uom": s.get("uom"),
                    "scan_mode": s.get("scan_mode") or "None", "serial_required": int(s.get("serial_required") or 0),
                    "batch_required": int(s.get("batch_required") or 0),
                    "checklist": [x for x in (s.get("checklist") or "").split("\n") if x.strip()],
                    "quality_inspection": int(s.get("quality_inspection") or 0),
                    "photo_required": int(s.get("photo_required") or 0), "comments": s.get("comments") or "",
                    "mandatory": int(s.get("mandatory") if s.get("mandatory") is not None else 1), "status": st})
    current = None
    for row in out:
        if row["status"] in ("Complete", "Not Required"):
            continue
        if row["status"] == "Upcoming":
            row["status"] = "Current"
        current = row["step_no"]
        break
    return {"status": "approved", "workflow": binding["workflow"], "version": binding["version"],
            "current_step": current, "steps": out}


M["item_image"] = mes_item_image
M["item_facts"] = mes_item_facts
M["active_boms"] = mes_active_boms
M["bom_node"] = mes_bom_node
M["walk"] = mes_walk
M["bom_tree"] = mes_bom_tree
M["tree_summary"] = mes_tree_summary
M["edges"] = mes_edges
M["signature"] = mes_signature
M["bom_diff"] = mes_bom_diff
M["workflow_for"] = mes_workflow_for
M["job_workflow"] = mes_job_workflow
M["arg"] = mes_arg
M["json_arg"] = mes_json_arg
M["minutes"] = mes_minutes
M["at"] = mes_at
M["dt_minutes"] = mes_dt_minutes
M["calendar"] = mes_calendar
M["conflicts"] = mes_conflicts
M["operator"] = mes_operator
M["replay"] = mes_replay
M["find_employee"] = mes_find_employee
M["employee"] = mes_employee
M["has_units"] = mes_has_units
M["item_info"] = mes_item_info
M["resolve_scan"] = mes_resolve_scan
M["batch_state"] = mes_batch_state
M["new_batch_id"] = mes_new_batch_id
M["batch_moves"] = mes_batch_moves
M["batch_available"] = mes_batch_available
M["batch_split"] = mes_batch_split
M["unit_state"] = mes_unit_state
M["materials"] = mes_materials
M["machine_down"] = mes_machine_down
M["kits"] = mes_kits
M["gate"] = mes_gate
M["start_reasons"] = mes_start_reasons
M["notify"] = mes_notify
M["attach"] = mes_attach
M["files"] = mes_files
# --- end prelude ---
