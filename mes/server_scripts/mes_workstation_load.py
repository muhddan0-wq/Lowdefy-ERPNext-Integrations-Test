# GET /api/method/mes_workstation_load?from_date=&to_date=&workstation_type=
# Scheduled minutes / available minutes (shift minutes x capacity, 0 on holidays) per P1 workstation per day.
from_date = frappe.utils.getdate(M["arg"](M, "from_date", frappe.utils.today()))
to_date = frappe.utils.getdate(M["arg"](M, "to_date", frappe.utils.add_days(from_date, 13)))
if frappe.utils.date_diff(to_date, from_date) > 92 or to_date < from_date:
    frappe.throw("Date range must be 0-92 days")
wtype = M["arg"](M, "workstation_type")
filters = {"plant_floor": M["PLANT_FLOOR"]}
if wtype:
    filters["workstation_type"] = wtype
stations = frappe.get_all("Workstation", filters=filters, pluck="name", order_by="name asc")
days = [frappe.utils.add_days(from_date, i) for i in range(frappe.utils.date_diff(to_date, from_date) + 1)]
end_dt = frappe.utils.add_days(to_date, 1)
out_rows = []
for ws in stations:
    cal = M["calendar"](M, ws)
    blocks = frappe.db.sql(
        """select s.from_time, s.to_time from `tabJob Card` jc
        join `tabJob Card Scheduled Time` s on s.parent = jc.name
        where jc.company=%s and jc.workstation=%s and jc.docstatus < 2
        and s.to_time > %s and s.from_time < %s""",
        (M["COMPANY"], ws, str(from_date), str(end_dt)), as_dict=True)
    cells = []
    for d in days:
        key = str(d)
        is_holiday = key in cal["holidays"]
        shift_mins = 0 if is_holiday else sum([b - a for a, b in cal["shifts"]])
        available = shift_mins * cal["capacity"]
        day_start = frappe.utils.get_datetime(key)
        day_end = frappe.utils.get_datetime(str(frappe.utils.add_days(d, 1)))
        booked = 0.0
        for b in blocks:
            s = max(frappe.utils.get_datetime(b.from_time), day_start)
            e = min(frappe.utils.get_datetime(b.to_time), day_end)
            if e > s:
                booked += frappe.utils.time_diff_in_seconds(e, s) / 60.0
        if available:
            load = round(100.0 * booked / available, 1)
        else:
            load = None if booked == 0 else 999.0
        cells.append({"date": key, "holiday": cal["holidays"].get(key) if is_holiday else None,
                      "available_mins": available, "scheduled_mins": round(booked, 1), "load_pct": load})
    out_rows.append({"workstation": ws, "workstation_type": cal["workstation_type"], "capacity": cal["capacity"], "cells": cells})
frappe.response["message"] = {"from_date": str(from_date), "to_date": str(to_date), "days": [str(d) for d in days], "rows": out_rows}
