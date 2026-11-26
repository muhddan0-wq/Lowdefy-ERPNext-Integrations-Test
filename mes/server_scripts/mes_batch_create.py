BATCH_ROLES = ["Manufacturing Manager", "Stock Manager", "System Manager"]
roles = frappe.get_all("Has Role", filters={"parent": frappe.session.user, "parenttype": "User"}, pluck="role")
if frappe.session.user != "Administrator" and not [r for r in roles if r in BATCH_ROLES]:
    frappe.throw("Not permitted: requires Manufacturing Manager or Stock Manager", frappe.PermissionError)

item_code = (M["arg"](M, "item_code") or "").strip()
batch_id = (M["arg"](M, "batch_id") or "").strip()
qty = frappe.utils.flt(M["arg"](M, "qty") or 0)
warehouse = M["arg"](M, "warehouse") or M["WH"]["stores"]

if not item_code or not frappe.db.exists("Item", item_code):
    frappe.throw("Item %s not found" % (item_code or "(blank)",))
item = frappe.db.get_value("Item", item_code, ["has_batch_no", "is_stock_item", "valuation_rate"], as_dict=True)
if not item.is_stock_item:
    frappe.throw("Item %s is not a stock item" % (item_code,))
if not item.has_batch_no:
    frappe.throw("Item %s does not use batch numbers. Enable 'Has Batch No' on the item first (master data change, needs approval)." % (item_code,))
if qty < 0:
    frappe.throw("Quantity cannot be negative")
if not frappe.db.exists("Warehouse", warehouse):
    frappe.throw("Warehouse %s not found" % (warehouse,))

if not batch_id:
    batch_id = M["new_batch_id"](M, item_code)

result = {"item_code": item_code, "batch_id": batch_id, "warehouse": warehouse, "stock_entry": None}

if frappe.db.exists("Batch", batch_id):
    existing_item = frappe.db.get_value("Batch", batch_id, "item")
    if existing_item != item_code:
        frappe.throw("Batch %s already exists for item %s, not %s" % (batch_id, existing_item, item_code))
    result["status"] = "exists"
else:
    frappe.get_doc({"doctype": "Batch", "batch_id": batch_id, "item": item_code}).insert(ignore_permissions=True)
    result["status"] = "created"
    if qty > 0:
        se = frappe.new_doc("Stock Entry")
        se.company = M["COMPANY"]
        se.stock_entry_type = "Material Receipt"
        se.purpose = "Material Receipt"
        se.append("items", {
            "item_code": item_code,
            "qty": qty,
            "t_warehouse": warehouse,
            "basic_rate": frappe.utils.flt(item.valuation_rate),
            "allow_zero_valuation_rate": 0 if frappe.utils.flt(item.valuation_rate) > 0 else 1,
            "use_serial_batch_fields": 1,
            "batch_no": batch_id,
        })
        se.insert()
        se.submit()
        result["stock_entry"] = se.name
        result["qty"] = qty

frappe.response["message"] = result
