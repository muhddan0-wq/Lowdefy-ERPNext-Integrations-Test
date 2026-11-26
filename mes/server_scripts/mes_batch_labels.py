# POST /api/method/mes_batch_labels  {batch_ids?: [..], item_code?, date?}
# One label per batch (not per unit): a Barcode Printing document with one row per batch and a CODE128 image per batch
# from barcode_shrdc, plus printable HTML with item, quantity and manufacturing date.
LABEL_ROLES = ["Manufacturing Manager", "Stock Manager", "Stock User", "System Manager"]
roles = frappe.get_all("Has Role", filters={"parent": frappe.session.user, "parenttype": "User"}, pluck="role")
if frappe.session.user != "Administrator" and not [r for r in roles if r in LABEL_ROLES]:
    frappe.throw("Not permitted: requires Manufacturing Manager, Stock Manager or Stock User", frappe.PermissionError)

ids = M["json_arg"](M, "batch_ids", []) or []
if isinstance(ids, str):
    ids = [x.strip() for x in ids.split(",") if x.strip()]
item_code = (M["arg"](M, "item_code") or "").strip()
day = (M["arg"](M, "date") or "").strip()
if not ids and item_code:
    filters = {"item": item_code, "disabled": 0}
    if day:
        filters["name"] = ["like", "%s-%s-%%" % (item_code, day.replace("-", ""))]
    ids = frappe.get_all("Batch", filters=filters, pluck="name", order_by="name asc", limit=200)
if not ids:
    frappe.throw("Give batch_ids, or an item_code (and optional date) that has batches")
if len(ids) > 200:
    frappe.throw("Print at most 200 batch labels at once")

labels = []
missing = []
for bid in ids:
    b = frappe.db.get_value("Batch", bid, ["name", "item", "item_name", "batch_qty", "stock_uom", "manufacturing_date", "expiry_date", "creation"], as_dict=True)
    if not b:
        missing.append(bid)
        continue
    labels.append({"batch_no": b.name, "item_code": b.item, "item_name": b.item_name or frappe.db.get_value("Item", b.item, "item_name"),
                   "qty": frappe.utils.flt(b.batch_qty), "uom": b.stock_uom or frappe.db.get_value("Item", b.item, "stock_uom"),
                   "date": str(b.manufacturing_date or frappe.utils.getdate(b.creation)), "expiry_date": str(b.expiry_date or "")})
if missing:
    frappe.throw("Batch not found: %s" % (", ".join(missing),))

bp = frappe.new_doc("Barcode Printing")
bp.company = M["COMPANY"]
bp.show_batch_no = 1
bp.batch_barcode_type = "CODE128"
for lb in labels:
    bp.append("items", {"item_code": lb["item_code"], "item_name": lb["item_name"], "batch_no": lb["batch_no"],
                        "qty": lb["qty"], "barcode": lb["batch_no"], "barcode_type": "CODE128", "uom": lb["uom"]})
bp.insert(ignore_permissions=True)

esc = frappe.utils.escape_html
parts = ['<div class="mes-batch-labels">']
for lb in labels:
    lb["image"] = frappe.call("barcode_shrdc.barcode_shrdc.doctype.barcode_printing.barcode_printing.get_barcode_image",
                              barcode=lb["batch_no"], barcode_type="CODE128", display_value=1)
    parts.append('<div class="mes-batch-label" style="display:inline-block;border:1px solid #999;padding:8px;margin:4px;width:320px;font-family:sans-serif;page-break-inside:avoid">'
                 + '<img src="%s" style="width:100%%;height:70px;object-fit:contain">' % (esc(lb["image"]),)
                 + '<div style="font-weight:bold">%s</div>' % (esc(lb["item_code"]),)
                 + '<div>%s</div>' % (esc(lb["item_name"] or ""),)
                 + '<div>Qty: %s %s &middot; Date: %s</div>' % (esc(str(frappe.utils.flt(lb["qty"], 3))), esc(lb["uom"] or ""), esc(lb["date"]))
                 + '</div>')
parts.append("</div>")
frappe.response["message"] = {"barcode_printing": bp.name, "count": len(labels), "labels": labels, "html": "".join(parts)}
