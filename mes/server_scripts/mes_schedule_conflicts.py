# GET /api/method/mes_schedule_conflicts?from_date=&to_date=&workstation=
# Workstation slots booked over production_capacity (open job cards, company Voltra only).
rows = M["conflicts"](M, M["arg"](M, "from_date"), M["arg"](M, "to_date"), M["arg"](M, "workstation"))
frappe.response["message"] = {"count": len(rows), "job_cards": sorted({r["job_card"] for r in rows}), "conflicts": rows}
