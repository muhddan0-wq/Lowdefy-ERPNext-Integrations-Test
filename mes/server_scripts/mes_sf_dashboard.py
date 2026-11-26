# POST /api/method/mes_sf_dashboard  {operator, workstation?, days?}
# Plant dashboard (Tulip-style) and, when a workstation is given, that station's own performance numbers.
# Read-only. "Today" is the site date; days > 1 widens the window back from today.
who = M["operator"](M)
ws_filter = M["arg"](M, "workstation")
days = int(M["arg"](M, "days", 1) or 1)
days = 1 if days < 1 else (30 if days > 30 else days)
now = frappe.utils.now_datetime()
today = frappe.utils.getdate(now)
start_day = frappe.utils.add_days(today, 1 - days)
win_from = frappe.utils.get_datetime(str(start_day) + " 00:00:00")
win_to = frappe.utils.get_datetime(str(today) + " 23:59:59")
SHIFT_FROM = 8 * 60
SHIFT_TO = 17 * 60

now_min = now.hour * 60 + now.minute
elapsed_today = min(max(now_min - SHIFT_FROM, 0), SHIFT_TO - SHIFT_FROM)
shift_frac = float(elapsed_today) / (SHIFT_TO - SHIFT_FROM)
elapsed_window = (days - 1) * (SHIFT_TO - SHIFT_FROM) + elapsed_today

stations = frappe.get_all("Workstation", filters={"plant_floor": M["PLANT_FLOOR"]}, fields=["name", "workstation_type"], order_by="name asc")
ws_names = [s.name for s in stations]
ws_type = {}
for s in stations:
    ws_type[s.name] = s.workstation_type

logs = frappe.db.sql(
    """select jc.name as job_card, jc.workstation, jc.work_order, jc.production_item, l.from_time, l.to_time, l.completed_qty
    from `tabJob Card Time Log` l join `tabJob Card` jc on jc.name = l.parent
    where jc.company = %(c)s and jc.docstatus < 2 and (
        (l.to_time between %(f)s and %(t)s) or (l.from_time between %(f)s and %(t)s) or (l.from_time is not null and l.to_time is null))""",
    {"c": M["COMPANY"], "f": win_from, "t": win_to}, as_dict=True)
planned = frappe.db.sql(
    """select name, workstation, work_order, production_item, for_quantity, total_completed_qty, expected_start_date, status
    from `tabJob Card` where company = %(c)s and docstatus < 2 and expected_start_date between %(f)s and %(t)s""",
    {"c": M["COMPANY"], "f": win_from, "t": win_to}, as_dict=True)
defects = frappe.db.sql(
    """select d.name, d.work_order, d.job_card, d.item_code, d.item_name, d.unit_id, d.qty_affected, d.category, d.status, d.creation,
    d.reported_by_name, jc.workstation
    from `tabMES Defect Report` d left join `tabJob Card` jc on jc.name = d.job_card
    where d.creation between %(f)s and %(t)s order by d.creation desc""",
    {"f": win_from, "t": win_to}, as_dict=True)
issues = frappe.db.sql(
    """select name, workstation, issue_type, severity, machine_status, status, creation, resolved_on, reported_by_name
    from `tabMES Machine Issue`
    where creation <= %(t)s and (resolved_on is null or resolved_on >= %(f)s) order by creation desc""",
    {"f": win_from, "t": win_to}, as_dict=True)


W = {"from": win_from, "to": win_to, "now": now, "shift_from": SHIFT_FROM, "shift_to": SHIFT_TO}


def in_window(W, dt):
    return bool(dt) and W["from"] <= frappe.utils.get_datetime(dt) <= W["to"]


def shift_overlap_minutes(W, a, b):
    """Minutes of [a, b] that fall inside the shift (08:00-17:00) on the days of the window."""
    a = max(frappe.utils.get_datetime(a), W["from"])
    b = min(frappe.utils.get_datetime(b), W["now"])
    if b <= a:
        return 0.0
    total = 0.0
    d = frappe.utils.getdate(a)
    while d <= frappe.utils.getdate(b):
        s = frappe.utils.get_datetime(str(d) + " 00:00:00")
        f = frappe.utils.add_to_date(s, minutes=W["shift_from"])
        t = frappe.utils.add_to_date(s, minutes=W["shift_to"])
        lo = max(a, f)
        hi = min(b, t)
        if hi > lo:
            total += (hi - lo).total_seconds() / 60.0
        d = frappe.utils.add_days(d, 1)
    return total


done_by_ws = {}
hours = {}
for l in logs:
    if l.to_time and in_window(W, l.to_time):
        q = l.completed_qty or 0
        done_by_ws[l.workstation] = done_by_ws.get(l.workstation, 0) + q
        hk = frappe.utils.get_datetime(l.to_time).strftime("%Y-%m-%d %H:00") if days > 1 else "%02d:00" % (frappe.utils.get_datetime(l.to_time).hour,)
        hours[hk] = hours.get(hk, 0) + q
running_by_ws = {}
for l in logs:
    if l.from_time and not l.to_time:
        running_by_ws[l.workstation] = {"job_card": l.job_card, "item_code": l.production_item, "since": l.from_time}

plan_by_ws = {}
for p in planned:
    plan_by_ws[p.workstation] = plan_by_ws.get(p.workstation, 0) + (p.for_quantity or 0)

complete = sum([done_by_ws[k] for k in done_by_ws])
plan = sum([plan_by_ws[k] for k in plan_by_ws])
target_now = plan * (float(days - 1) / days + shift_frac / days) if plan else 0
performance = round(100.0 * complete / target_now, 1) if target_now else None

down_by_ws = {}
down_by_reason = {}
open_by_ws = {}
for i in issues:
    if i.machine_status in ("Stalled", "Completely Down"):
        mins = shift_overlap_minutes(W, i.creation, i.resolved_on or now)
        down_by_ws[i.workstation] = down_by_ws.get(i.workstation, 0) + mins
        down_by_reason[i.issue_type] = down_by_reason.get(i.issue_type, 0) + mins
    if i.status in M["SF"]["OPEN_ISSUE"]:
        open_by_ws.setdefault(i.workstation, []).append(i)

avail_rows = []
for s in ws_names:
    dm = min(down_by_ws.get(s, 0), elapsed_window) if elapsed_window else 0
    avail_rows.append({"workstation": s, "up_min": round(max(elapsed_window - dm, 0)), "down_min": round(dm),
                       "availability": round(100.0 * (elapsed_window - dm) / elapsed_window, 1) if elapsed_window else None})
active_avail = [r for r in avail_rows if r["availability"] is not None]
availability = round(sum([r["availability"] for r in active_avail]) / len(active_avail), 1) if active_avail else None

defect_qty = sum([(d.qty_affected or 1) for d in defects])
quality = round(100.0 * complete / (complete + defect_qty), 1) if (complete + defect_qty) else None
def_by_ws = {}
def_by_cat = {}
for d in defects:
    k = d.workstation or "Unassigned"
    def_by_ws[k] = def_by_ws.get(k, 0) + (d.qty_affected or 1)
    def_by_cat[d.category or "Other"] = def_by_cat.get(d.category or "Other", 0) + (d.qty_affected or 1)


def pareto(src):
    rows = sorted([{"label": k, "value": round(src[k], 1)} for k in src], key=lambda r: -r["value"])
    tot = sum([r["value"] for r in rows]) or 1
    run = 0
    for r in rows:
        run += r["value"]
        r["cum_pct"] = round(100.0 * run / tot, 1)
    return rows


station_rows = []
for s in stations:
    op = open_by_ws.get(s.name, [])
    worst = "Operating Normally"
    for i in op:
        if i.machine_status == "Completely Down":
            worst = "Completely Down"
        elif i.machine_status == "Stalled" and worst != "Completely Down":
            worst = "Stalled"
        elif i.machine_status == "Experiencing Problems" and worst == "Operating Normally":
            worst = "Experiencing Problems"
    run = running_by_ws.get(s.name)
    state = "down" if worst in ("Completely Down", "Stalled") else ("warn" if worst != "Operating Normally" else ("run" if run else "idle"))
    station_rows.append({"workstation": s.name, "type": s.workstation_type, "state": state, "machine_status": worst,
                         "open_issues": len(op), "running": run, "done": done_by_ws.get(s.name, 0), "plan": plan_by_ws.get(s.name, 0)})

events = []
for l in logs:
    if l.from_time and in_window(W, l.from_time):
        events.append({"at": l.from_time, "kind": "start", "title": "Job started " + l.job_card,
                       "text": "%s on %s" % (l.production_item, l.workstation)})
    if l.to_time and in_window(W, l.to_time) and (l.completed_qty or 0) > 0:
        events.append({"at": l.to_time, "kind": "done", "title": "%s good units reported" % (frappe.utils.flt(l.completed_qty, 3),),
                       "text": "%s at %s (%s)" % (l.production_item, l.workstation, l.job_card)})
for d in defects:
    events.append({"at": d.creation, "kind": "defect", "title": "Quality defect " + (d.unit_id or d.item_code),
                   "text": "%s rejected for %s" % (frappe.utils.flt(d.qty_affected or 1, 3), d.category or "Other")})
for i in issues:
    if in_window(W, i.creation):
        events.append({"at": i.creation, "kind": "issue", "title": "%s: %s" % (i.workstation, i.machine_status),
                       "text": "%s (%s) reported" % (i.issue_type, i.severity)})
    if i.resolved_on and in_window(W, i.resolved_on):
        events.append({"at": i.resolved_on, "kind": "resolved", "title": "%s back up" % (i.workstation,),
                       "text": "%s resolved" % (i.issue_type,)})
events = sorted(events, key=lambda e: str(e["at"]), reverse=True)[:25]

out = {
    "operator": who, "now": now, "days": days, "shift": {"from": "08:00", "to": "17:00", "elapsed_pct": round(100 * shift_frac, 1)},
    "totals": {"complete": complete, "plan": plan, "target_now": round(target_now, 1), "defects": defect_qty,
               "performance": performance, "availability": availability, "quality": quality,
               "machines_down": len([s for s in station_rows if s["state"] == "down"])},
    "hourly": [{"label": k, "value": hours[k]} for k in sorted(hours)],
    "availability_by_station": avail_rows,
    "downtime_pareto": pareto(down_by_reason),
    "defects_by_station": [{"label": k, "value": def_by_ws[k]} for k in sorted(def_by_ws)],
    "defect_pareto": pareto(def_by_cat),
    "stations": station_rows,
    "events": events,
}

if ws_filter:
    if ws_filter not in ws_names:
        frappe.throw("Workstation %s is not on %s" % (ws_filter, M["PLANT_FLOOR"]))
    open_jcs = frappe.db.sql(
        """select for_quantity, total_completed_qty from `tabJob Card`
        where company = %(c)s and docstatus = 0 and status not in ('Completed', 'Cancelled') and workstation = %(w)s
        and expected_start_date <= %(t)s""",
        {"c": M["COMPANY"], "w": ws_filter, "t": win_to}, as_dict=True)
    remaining_due = sum([max((j.for_quantity or 0) - (j.total_completed_qty or 0), 0) for j in open_jcs])
    ws_plan = plan_by_ws.get(ws_filter, 0)
    out["station"] = {"workstation": ws_filter, "type": ws_type.get(ws_filter), "remaining_due": remaining_due,
                      "completed": done_by_ws.get(ws_filter, 0), "plan": ws_plan,
                      "target_now": round(ws_plan * shift_frac) if days == 1 else ws_plan,
                      "row": [s for s in station_rows if s["workstation"] == ws_filter][0]}

frappe.response["message"] = out
