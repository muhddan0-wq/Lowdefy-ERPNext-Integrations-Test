# --- MES prelude (prepended to every mes_* API server script by install_server_scripts.py) ---
# Server scripts run with separate globals/locals, so top-level functions cannot see each other.
# Everything shared lives in the dict M and every helper takes M as its first argument.
M = {
    "COMPANY": "Voltra Power Tools Sdn Bhd",
    "PLANT_FLOOR": "P1 Shah Alam Plant",
    "SITE_PREFIX": "P1 ",
    "WH": {"stores": "P1 Stores - VPT", "wip": "P1 Work In Progress - VPT", "fg": "P1 Finished Goods - VPT"},
    "ROLES": ["Manufacturing User", "Manufacturing Manager", "System Manager"],
    "HORIZON_DAYS": 60,
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


M["arg"] = mes_arg
M["json_arg"] = mes_json_arg
M["minutes"] = mes_minutes
M["at"] = mes_at
M["dt_minutes"] = mes_dt_minutes
M["calendar"] = mes_calendar
M["conflicts"] = mes_conflicts
# --- end prelude ---
