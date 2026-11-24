# POST /api/method/mes_reschedule_job_card  {job_card, new_start, workstation?, dry_run?}
# Validated replacement for planner_shift_job_card. Refuses the move when:
#   - the job card is not an open, unstarted Voltra job card
#   - the workstation is not on P1 or is a different workstation type
#   - new_start is in the past, beyond the horizon, on a holiday or outside a shift
#   - any part of the new time would exceed the workstation's production_capacity
#   - it starts before the previous operation (or a sub-assembly it needs) ends,
#     or ends after the next operation (or the parent work order) starts
# Otherwise it rewrites the scheduled time blocks (split across shifts/days) and expected start/end,
# and mirrors the change on the work order operation.


def mes_walk(M, cal, start, total):
    """Lay `total` minutes into shifts from `start`; returns blocks split at shift/day boundaries."""
    blocks = []
    remaining = total
    cur = start
    day = frappe.utils.getdate(start)
    for i in range(M["HORIZON_DAYS"] + 30):
        if str(day) not in cal["holidays"]:
            for sh in cal["shifts"]:
                s = M["at"](M, day, sh[0])
                e = M["at"](M, day, sh[1])
                if e <= cur:
                    continue
                bs = max(s, cur)
                avail = frappe.utils.time_diff_in_seconds(e, bs) / 60.0
                take = min(avail, remaining)
                be = frappe.utils.add_to_date(bs, minutes=take)
                blocks.append({"from_time": bs, "to_time": be, "time_in_mins": round(take, 2)})
                remaining = remaining - take
                cur = be
                if remaining <= 0.001:
                    return blocks
        day = frappe.utils.add_days(day, 1)
    frappe.throw("The job does not fit inside the planning horizon")


def mes_fmt(M, dt):
    d = frappe.utils.get_datetime(dt)
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.weekday()] + " " + str(d)[:16]


def mes_refuse(M, msg):
    frappe.throw(msg, title="Reschedule refused")


M["walk"] = mes_walk
M["fmt"] = mes_fmt
M["refuse"] = mes_refuse

jc_name = M["arg"](M, "job_card")
raw_start = M["arg"](M, "new_start")
target = M["arg"](M, "workstation")
dry_run = frappe.utils.cint(M["arg"](M, "dry_run", 0))
if not jc_name or not frappe.db.exists("Job Card", jc_name):
    M["refuse"](M, "Job card %s not found" % (jc_name,))
if not raw_start:
    M["refuse"](M, "new_start is required")
jc = frappe.get_doc("Job Card", jc_name)
if jc.company != M["COMPANY"]:
    frappe.throw("Job card %s does not belong to %s" % (jc_name, M["COMPANY"],), frappe.PermissionError)
if jc.docstatus != 0:
    M["refuse"](M, "Job card %s is submitted or cancelled and cannot be moved" % (jc_name,))
if jc.status not in ("Open", "Material Transferred") or jc.time_logs:
    M["refuse"](M, "Job card %s has already started (status %s); only jobs that have not started can be moved" % (jc_name, jc.status,))

new_start = frappe.utils.get_datetime(raw_start).replace(second=0, microsecond=0)
ws = target or jc.workstation
cal = M["calendar"](M, ws)
if cal.plant_floor != M["PLANT_FLOOR"]:
    M["refuse"](M, "Workstation %s is not on %s" % (ws, M["PLANT_FLOOR"],))
if cal.workstation_type != jc.workstation_type:
    M["refuse"](M, "%s is a %s workstation; %s (%s) needs %s" % (ws, cal.workstation_type, jc_name, jc.operation, jc.workstation_type,))
now = frappe.utils.now_datetime()
if new_start < now:
    M["refuse"](M, "%s is in the past" % (M["fmt"](M, new_start),))
if frappe.utils.date_diff(frappe.utils.getdate(new_start), frappe.utils.getdate(now)) > M["HORIZON_DAYS"]:
    M["refuse"](M, "%s is beyond the %s-day planning horizon" % (M["fmt"](M, new_start), M["HORIZON_DAYS"],))
day_key = str(frappe.utils.getdate(new_start))
if day_key in cal["holidays"]:
    M["refuse"](M, "%s is a non-working day at %s (%s)" % (M["fmt"](M, new_start)[:14], ws, cal["holidays"][day_key],))
sm = M["dt_minutes"](M, new_start)
if not any([sh[0] <= sm and sm < sh[1] for sh in cal["shifts"]]):
    hours = ", ".join(["%02d:%02d-%02d:%02d" % (int(sh[0] // 60), int(sh[0] % 60), int(sh[1] // 60), int(sh[1] % 60)) for sh in cal["shifts"]])
    M["refuse"](M, "%s is outside the working hours of %s (%s)" % (str(new_start)[11:16], ws, hours,))

total = sum([frappe.utils.flt(r.time_in_mins) for r in jc.scheduled_time_logs]) or frappe.utils.flt(jc.time_required)
if total <= 0:
    M["refuse"](M, "Job card %s has no planned duration" % (jc_name,))
blocks = M["walk"](M, cal, new_start, total)
new_end = blocks[-1]["to_time"]

# capacity on the target workstation
others = frappe.db.sql(
    """select s.parent, s.from_time, s.to_time, jc.work_order, jc.operation from `tabJob Card Scheduled Time` s
    join `tabJob Card` jc on jc.name = s.parent
    where jc.workstation = %s and jc.docstatus < 2 and jc.status != 'Completed' and jc.name != %s
      and s.to_time > %s and s.from_time < %s""",
    (ws, jc_name, new_start, new_end), as_dict=True)
for b in blocks:
    ov = [o for o in others if o.from_time < b["to_time"] and b["from_time"] < o.to_time]
    points = [b["from_time"]] + [o.from_time for o in ov if b["from_time"] < o.from_time and o.from_time < b["to_time"]]
    for t in points:
        busy = [o for o in ov if o.from_time <= t and t < o.to_time]
        if len({o.parent for o in busy}) + 1 > cal["capacity"]:
            o = busy[0]
            M["refuse"](M, "Overlap: %s is already booked by %s (%s, %s) from %s to %s (capacity %s)" % (ws, o.parent, o.work_order, o.operation, M["fmt"](M, o.from_time), M["fmt"](M, o.to_time), cal["capacity"],))

# routing order inside the work order
my_idx = frappe.db.get_value("Work Order Operation", jc.operation_id, "idx") or jc.sequence_id or 0
siblings = frappe.get_all("Job Card", filters={"work_order": jc.work_order, "docstatus": ["<", 2], "name": ["!=", jc_name]},
                          fields=["name", "operation", "operation_id", "status", "expected_start_date", "expected_end_date", "actual_end_date"])
has_prev = False
has_next = False
for s in siblings:
    s_idx = frappe.db.get_value("Work Order Operation", s.operation_id, "idx") or 0
    if s_idx < my_idx:
        has_prev = True
        prev_end = s.actual_end_date if (s.status == "Completed" and s.actual_end_date) else s.expected_end_date
        if prev_end and new_start < frappe.utils.get_datetime(prev_end):
            M["refuse"](M, "Starts before the previous operation ends: %s (%s) ends %s" % (s.operation, s.name, M["fmt"](M, prev_end),))
    elif s_idx > my_idx:
        has_next = True
        if s.expected_start_date and new_end > frappe.utils.get_datetime(s.expected_start_date):
            M["refuse"](M, "Would end %s, after the next operation %s (%s) starts %s. Move that job first." % (M["fmt"](M, new_end), s.operation, s.name, M["fmt"](M, s.expected_start_date),))

# sub-assembly links inside the same production plan
plan = frappe.db.get_value("Work Order", jc.work_order, "production_plan")
if plan:
    if not has_prev:
        needs = frappe.get_all("Work Order Item", filters={"parent": jc.work_order, "parenttype": "Work Order"}, pluck="item_code")
        kids = frappe.get_all("Work Order", filters={"production_plan": plan, "docstatus": 1, "production_item": ["in", needs or ["-"]]}, pluck="name")
        for k in kids:
            k_end = frappe.db.sql("select max(expected_end_date) as e from `tabJob Card` where work_order=%s and docstatus<2", k, as_dict=True)[0].e
            if k_end and new_start < k_end:
                M["refuse"](M, "Starts before sub-assembly work order %s finishes at %s" % (k, M["fmt"](M, k_end),))
    if not has_next:
        item = frappe.db.get_value("Work Order", jc.work_order, "production_item")
        parents = frappe.db.sql(
            """select distinct wo.name from `tabWork Order` wo join `tabWork Order Item` i on i.parent = wo.name
            where wo.production_plan = %s and wo.docstatus = 1 and i.item_code = %s""", (plan, item), as_dict=True)
        for p in parents:
            p_start = frappe.db.sql("select min(expected_start_date) as s from `tabJob Card` where work_order=%s and docstatus<2", p.name, as_dict=True)[0].s
            if p_start and new_end > p_start:
                M["refuse"](M, "Would end %s, after work order %s that needs this sub-assembly starts %s" % (M["fmt"](M, new_end), p.name, M["fmt"](M, p_start),))

before = {"workstation": jc.workstation, "start": jc.expected_start_date, "end": jc.expected_end_date}
if not dry_run:
    jc.set("scheduled_time_logs", [])
    for b in blocks:
        jc.append("scheduled_time_logs", b)
    jc.expected_start_date = blocks[0]["from_time"]
    jc.expected_end_date = new_end
    jc.workstation = ws
    # Job Card.validate() runs execution checks (validate_sequence_id refuses ANY save of a later operation
    # until the earlier ones are completed). This is a schedule-only change on an unstarted job card, and every
    # scheduling rule was checked above, so skip the controller validate; mandatory/link checks still run.
    jc.flags.ignore_validate = True
    jc.save()
    frappe.db.set_value("Work Order Operation", jc.operation_id,
                        {"planned_start_time": blocks[0]["from_time"], "planned_end_time": new_end, "workstation": ws})
    span = frappe.db.sql("select min(planned_start_time) as s, max(planned_end_time) as e from `tabWork Order Operation` where parent=%s",
                         jc.work_order, as_dict=True)[0]
    frappe.db.set_value("Work Order", jc.work_order, {"planned_start_date": span.s, "planned_end_date": span.e})
    jc.add_comment("Info", "Rescheduled via MES API by %s: %s %s -> %s %s" % (frappe.session.user, before["workstation"], before["start"], ws, blocks[0]["from_time"],))
frappe.response["message"] = {"ok": 1, "dry_run": dry_run, "job_card": jc_name, "workstation": ws,
                              "start": blocks[0]["from_time"], "end": new_end, "blocks": blocks, "before": before}
