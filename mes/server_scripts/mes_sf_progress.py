# POST /api/method/mes_sf_progress  {operator, job_card, action: start|report|pause|complete, qty?}
# Production on an ERPNext Job Card: start opens a time log, report/pause close it with the good quantity made,
# complete submits the Job Card (ERPNext then updates the work order operation). The backend re-checks every gate
# (materials verified, defects decided, machine not down, quantity valid) on each call; the UI cannot skip them.
who = M["operator"](M, "operate")
emp = M["employee"](M, True)
name = M["arg"](M, "job_card")
action = (M["arg"](M, "action") or "").lower()
if not name or not frappe.db.exists("Job Card", name):
    frappe.throw("Job card %s not found" % (name,))
frappe.db.rollback()
frappe.db.sql("select name from `tabJob Card` where name=%s for update", name)
jc = frappe.get_doc("Job Card", name)
if jc.company != M["COMPANY"]:
    frappe.throw("Job card %s does not belong to %s" % (name, M["COMPANY"]), frappe.PermissionError)
if jc.docstatus != 0 or jc.status == "Completed":
    frappe.throw("Job card %s is already completed" % (name,))
wo = frappe.get_doc("Work Order", jc.work_order)
if wo.status in ("Completed", "Closed", "Cancelled", "Stopped"):
    frappe.throw("Work order %s is %s" % (wo.name, wo.status))
now = frappe.utils.now_datetime()
open_logs = [l for l in jc.time_logs if l.from_time and not l.to_time]
qty = frappe.utils.flt(M["arg"](M, "qty"))
done_qty = jc.total_completed_qty or 0
result = {"ok": True, "action": action, "job_card": name, "blocking": []}


def close_log(M, jc, log, qty, now, done_qty):
    if qty < 0:
        frappe.throw("Quantity cannot be negative")
    if qty != int(qty):
        frappe.throw("Enter a whole number of units")
    if done_qty + qty > (jc.for_quantity or 0) + 1e-9:
        frappe.throw("Quantity too high: %s already done, %s more would exceed the job quantity %s" % (done_qty, qty, jc.for_quantity))
    log.to_time = now
    log.completed_qty = qty
    log.time_in_mins = frappe.utils.time_diff_in_seconds(now, log.from_time) / 60.0


if action == "start":
    if open_logs:
        frappe.throw("Production is already running on %s" % (name,))
    reasons = M["start_reasons"](M, wo, jc.workstation)
    if reasons:
        result["ok"] = False
        result["blocking"] = reasons
    else:
        jc.append("time_logs", {"from_time": now, "completed_qty": 0, "operation": jc.operation, "employee": emp["id"]})
        jc.save()
        wo.add_comment("Comment", "Production started on %s (%s) by %s" % (name, jc.operation, emp["name"]))
elif action in ("report", "pause"):
    if not open_logs:
        frappe.throw("Production is not running on %s; start it first" % (name,))
    if qty > 0:
        mats = M["materials"](M, wo)
        kits = M["kits"](M, wo, mats)
        if done_qty + qty > kits + 1e-9:
            short = [m["item_code"] for m in mats if m["per_unit"] > 0 and frappe.utils.flt(m["verified_qty"]) / m["per_unit"] + 1e-6 < done_qty + qty]
            frappe.throw("Scan the parts first: the materials scanned make %s complete unit%s and %s %s already counted. Still to scan for the next one: %s" % (
                kits, "" if kits == 1 else "s", done_qty, "is" if done_qty == 1 else "are", ", ".join(short)))
    close_log(M, jc, open_logs[0], qty, now, done_qty)
    restarted = False
    if action == "report":
        if M["machine_down"](M, jc.workstation):
            result["blocking"] = ["Machine %s is Completely Down: the clock is stopped until maintenance resolves it" % (jc.workstation,)]
        else:
            jc.append("time_logs", {"from_time": frappe.utils.add_to_date(now, seconds=1), "completed_qty": 0, "operation": jc.operation, "employee": emp["id"]})
            restarted = True
    jc.save()
    result["running"] = restarted
    wo.add_comment("Comment", "%s %s good units on %s (%s)" % (emp["name"], qty, name, "reported" if action == "report" else "paused"))
elif action == "complete":
    if open_logs:
        close_log(M, jc, open_logs[0], qty, now, done_qty)
        done_qty = done_qty + qty
    reasons = M["gate"](M, wo, jc.workstation, done_qty)["reasons"]
    if done_qty <= 0:
        reasons.append("No good quantity has been reported on this job yet")
    if reasons:
        if open_logs:
            jc.save()
        result["ok"] = False
        result["blocking"] = reasons
    else:
        jc.save()
        jc.reload()
        jc.submit()
        wo.add_comment("Comment", "%s completed %s (%s) with %s good units" % (emp["name"], name, jc.operation, jc.total_completed_qty))
else:
    frappe.throw("Unknown action %s; use start, report, pause or complete" % (action,))

jc.reload()
result["status"] = jc.status
result["docstatus"] = jc.docstatus
result["completed_qty"] = jc.total_completed_qty
result["qty"] = jc.for_quantity
frappe.response["message"] = result
