# POST /api/method/mes_wf_discover  {operator, action, item_code?}
#   products   finished products = items with an active submitted BOM that no other active BOM uses as a component,
#              each with a summary of its BOM tree (components, sub-assemblies, missing images, cycles, flags)
#   tree       full nested BOM for one item (with images, operations, flags and the BOM signature)
# Everything is read live from ERPNext. Nothing is stored here: MES workflows are created by mes_wf_workflow.
who = M["operator"](M, "supervisor")
action = (M["arg"](M, "action") or "products").lower()
out = {"ok": True, "operator": who, "connection": frappe.local.site}

if action == "products":
    boms = {r[0] for r in frappe.db.sql("select distinct item from `tabBOM` where is_active=1 and docstatus=1")}
    used = {r[0] for r in frappe.db.sql(
        "select distinct bi.item_code from `tabBOM Item` bi join `tabBOM` b on b.name=bi.parent "
        "where b.is_active=1 and b.docstatus=1")}
    products = []
    for code in sorted(boms - used):
        root = M["bom_tree"](M, code)
        s = M["tree_summary"](M, root)
        wf = frappe.db.get_value("MES Assembly Workflow", {"finished_item": code},
                                 ["name", "status", "approved_version", "current_version", "sync_status"], as_dict=True)
        products.append({"item_code": code, "item_name": root["item_name"], "image": root["image"],
                         "image_source": root["image_source"], "bom": root["bom"], "bom_candidates": root["bom_candidates"],
                         "summary": {k: s[k] for k in s if k != "flags"}, "flag_count": len(s["flags"]),
                         "workflow": wf})
    out["products"] = products
    out["sub_assembly_items"] = len(boms & used)
elif action == "tree":
    code = M["arg"](M, "item_code")
    if not code or not frappe.db.exists("Item", code):
        frappe.throw("Item %s not found in ERPNext" % (code,))
    root = M["bom_tree"](M, code)
    out["tree"] = root
    out["summary"] = M["tree_summary"](M, root)
    out["bom_signature"] = M["signature"](M, root)
else:
    frappe.throw("Unknown action %s" % (action,))

frappe.response["message"] = out
