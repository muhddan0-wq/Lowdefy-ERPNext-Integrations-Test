# GET /api/method/mes_work_order_detail?work_order=
# Header, progress, operations with job cards, materials vs stock in P1 Stores, allowed actions.
name = M["arg"](M, "work_order")
if not name or not frappe.db.exists("Work Order", name):
    frappe.throw("Work order %s not found" % (name,))
wo = frappe.get_doc("Work Order", name)
if wo.company != M["COMPANY"]:
    frappe.throw("Work order %s does not belong to %s" % (name, M["COMPANY"],), frappe.PermissionError)
now = frappe.utils.now_datetime()
ops = []
for op in wo.operations:
    jcs = frappe.get_all("Job Card", filters={"work_order": name, "operation_id": op.name, "docstatus": ["<", 2]},
                         fields=["name", "status", "docstatus", "is_paused", "workstation", "expected_start_date",
                                 "expected_end_date", "actual_start_date", "actual_end_date", "for_quantity",
                                 "total_completed_qty", "custom_work_instructions"], order_by="creation asc")
    jc = jcs[0] if jcs else {}
    ops.append({"idx": op.idx, "operation": op.operation, "workstation_type": op.workstation_type,
                "workstation": jc.get("workstation") or op.workstation, "time_in_mins": op.time_in_mins,
                "op_status": op.status, "completed_qty": op.completed_qty,
                "job_card": jc.get("name"), "job_card_status": ("Paused" if jc.get("is_paused") else jc.get("status")),
                "scheduled_start": jc.get("expected_start_date") or op.planned_start_time,
                "scheduled_end": jc.get("expected_end_date") or op.planned_end_time,
                "actual_start": jc.get("actual_start_date"), "actual_end": jc.get("actual_end_date"),
                "work_instructions": jc.get("custom_work_instructions"), "job_cards": [j.name for j in jcs]})
mats = []
for r in wo.required_items:
    wh = r.source_warehouse or wo.source_warehouse or M["WH"]["stores"]
    stock = frappe.db.get_value("Bin", {"item_code": r.item_code, "warehouse": wh}, "actual_qty") or 0
    to_transfer = max((r.required_qty or 0) - (r.transferred_qty or 0), 0)
    mats.append({"item_code": r.item_code, "item_name": r.item_name, "source_warehouse": wh,
                 "required_qty": r.required_qty, "transferred_qty": r.transferred_qty, "consumed_qty": r.consumed_qty,
                 "in_stock": stock, "to_transfer": to_transfer, "short": max(to_transfer - stock, 0), "uom": r.stock_uom})
open_status = wo.status not in ("Completed", "Closed", "Cancelled", "Stopped")
remaining_transfer = max((wo.qty or 0) - (wo.material_transferred_for_manufacturing or 0), 0)
remaining_finish = max((wo.material_transferred_for_manufacturing or 0) - (wo.produced_qty or 0), 0)
is_late = open_status and wo.planned_end_date and frappe.utils.get_datetime(wo.planned_end_date) < now
frappe.response["message"] = {
    "header": {"name": wo.name, "production_item": wo.production_item, "item_name": wo.item_name, "qty": wo.qty,
               "produced_qty": wo.produced_qty, "transferred_qty": wo.material_transferred_for_manufacturing,
               "status": wo.status, "planned_start_date": wo.planned_start_date, "planned_end_date": wo.planned_end_date,
               "actual_start_date": wo.actual_start_date, "actual_end_date": wo.actual_end_date, "bom_no": wo.bom_no,
               "production_plan": wo.production_plan, "source_warehouse": wo.source_warehouse,
               "wip_warehouse": wo.wip_warehouse, "fg_warehouse": wo.fg_warehouse,
               "progress_pct": round(100.0 * (wo.produced_qty or 0) / wo.qty, 1) if wo.qty else 0,
               "late": 1 if is_late else 0},
    "operations": ops,
    "materials": mats,
    "actions": {"stop": wo.status in ("Not Started", "In Process"), "resume": wo.status == "Stopped",
                "close": wo.status not in ("Closed", "Cancelled", "Completed"),
                "issue": bool(open_status and remaining_transfer > 0), "finish": bool(open_status and remaining_finish > 0),
                "max_issue_qty": remaining_transfer, "max_finish_qty": remaining_finish},
}
