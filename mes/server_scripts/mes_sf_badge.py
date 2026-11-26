# POST /api/method/mes_sf_badge  {operator, employee}
# Station sign-in: the person scans their ID badge (Employee ID, attendance device ID or full name).
# Returns the ERPNext Employee who will be recorded on every scan, issue, time log and report from this station.
who = M["operator"](M)
emp = M["employee"](M, True)
frappe.response["message"] = {"ok": True, "employee": emp, "operator": who}
