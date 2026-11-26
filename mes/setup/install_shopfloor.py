"""Create or update the shopfloor MES DocTypes (idempotent). Runs inside the bench as Administrator.

MES Material Scan  every scan attempt, valid or not, with the reason (traceability)
MES Defect Report  defects against materials or products, with ERPNext File attachments
MES Machine Issue  machine stalls and breakdowns linked to a Workstation
MES Batch Genealogy  one finished-goods batch and the input batches it consumed
MES Batch Reader   role with read on ERPNext Batch, given to the Appsmith API user (nothing else)

unit_key and request_id are unique columns: the database itself refuses a second valid scan of the same
unit and a replayed submission, so two simultaneous requests cannot both succeed.
Only System Manager may write these DocTypes directly. Everyone else, including the Appsmith API user,
reads them; every change goes through the validating mes_sf_* server scripts (which insert with
ignore_permissions), so a hand-made REST call cannot mark a defect resolved or a scan valid.

Usage: FRAPPE_SITE=<site> python install_shopfloor.py [--test-users]  (test users come from test_users in the site YAML)
"""
import os
import sys

import frappe

DEFECT_CATEGORIES = "Physical Damage\nIncorrect Component\nMissing Component\nManufacturing Defect\nSurface Defect\nElectrical Issue\nMechanical Issue\nOther"
ISSUE_TYPES = "Machine Stalled\nMachine Breakdown\nMechanical Failure\nElectrical Failure\nAbnormal Noise\nOverheating\nSafety Concern\nMaintenance Required\nOther"


def f(fieldname, fieldtype, label=None, **kw):
    d = {"fieldname": fieldname, "fieldtype": fieldtype, "label": label or fieldname.replace("_", " ").title()}
    d.update(kw)
    return d


def perms(*rows):
    out = []
    for role, write in rows:
        out.append({"role": role, "read": 1, "report": 1, "export": 1, "print": 1,
                    "write": write, "create": write, "delete": 1 if role == "System Manager" else 0})
    return out


DOCTYPES = [
    {
        "name": "MES Material Scan", "autoname": "MES-SCN-.#####", "title_field": "item_code",
        "fields": [
            f("work_order", "Link", options="Work Order", reqd=1, in_list_view=1, in_standard_filter=1),
            f("job_card", "Link", options="Job Card"),
            f("item_code", "Link", options="Item", in_list_view=1, in_standard_filter=1),
            f("item_name", "Data"),
            f("scan_mode", "Select", options="Unit\nBatch\nQuantity\nConfirm"),
            f("result", "Select", options="Valid\nInvalid\nDefective\nVoided", reqd=1, in_list_view=1, in_standard_filter=1),
            f("reason", "Small Text"),
            f("col1", "Column Break"),
            f("scanned_value", "Data"),
            f("resolved_as", "Data"),
            f("unit_id", "Data", "Unit / Tracking ID", in_list_view=1),
            f("serial_no", "Data", "Serial No"),
            f("batch_no", "Link", "Batch No", options="Batch", in_standard_filter=1),
            f("qty", "Float"),
            f("warehouse", "Link", options="Warehouse"),
            f("operator", "Link", options="User", in_standard_filter=1),
            f("operator_name", "Data"),
            f("employee", "Link", options="Employee", in_standard_filter=1),
            f("employee_name", "Data"),
            f("unit_key", "Data", unique=1, read_only=1, hidden=1),
            f("request_id", "Data", unique=1, read_only=1, hidden=1),
        ],
        "permissions": perms(("System Manager", 1), ("Manufacturing Manager", 0), ("Manufacturing User", 0)),
    },
    {
        "name": "MES Defect Report", "autoname": "MES-DEF-.#####", "title_field": "item_code",
        "fields": [
            f("work_order", "Link", options="Work Order", in_list_view=1, in_standard_filter=1),
            f("job_card", "Link", options="Job Card"),
            f("item_code", "Link", options="Item", reqd=1, in_list_view=1),
            f("item_name", "Data"),
            f("unit_id", "Data", "Unit / Serial No"),
            f("qty_affected", "Float", default="1"),
            f("category", "Select", options=DEFECT_CATEGORIES, reqd=1, in_list_view=1, in_standard_filter=1),
            f("description", "Text", reqd=1),
            f("col1", "Column Break"),
            f("status", "Select", options="Reported\nUnder Review\nAccepted\nRejected\nRework Required\nResolved",
              default="Reported", reqd=1, in_list_view=1, in_standard_filter=1),
            f("disposition", "Select", options="\nUse As Is\nReplace\nRework\nScrap\nReturn to Supplier"),
            f("resolution_comments", "Text"),
            f("reported_by", "Link", options="User"),
            f("reported_by_name", "Data"),
            f("employee", "Link", options="Employee", in_standard_filter=1),
            f("reviewed_by", "Link", options="User"),
            f("reviewed_on", "Datetime"),
            f("request_id", "Data", unique=1, read_only=1, hidden=1),
        ],
        "permissions": perms(("System Manager", 1), ("Manufacturing Manager", 0), ("Quality Manager", 0), ("Manufacturing User", 0)),
    },
    {
        "name": "MES Machine Issue", "autoname": "MES-MCH-.#####", "title_field": "workstation",
        "fields": [
            f("workstation", "Link", options="Workstation", reqd=1, in_list_view=1, in_standard_filter=1),
            f("work_order", "Link", options="Work Order"),
            f("job_card", "Link", options="Job Card"),
            f("issue_type", "Select", options=ISSUE_TYPES, reqd=1, in_list_view=1),
            f("severity", "Select", options="Low\nMedium\nHigh\nCritical", default="Medium", reqd=1, in_list_view=1, in_standard_filter=1),
            f("machine_status", "Select", options="Operating Normally\nExperiencing Problems\nStalled\nCompletely Down", reqd=1, in_list_view=1),
            f("description", "Text", reqd=1),
            f("col1", "Column Break"),
            f("status", "Select", options="Open\nAcknowledged\nIn Progress\nResolved\nClosed", default="Open", reqd=1,
              in_list_view=1, in_standard_filter=1),
            f("assigned_to", "Link", options="User"),
            f("resolution_notes", "Text"),
            f("reported_by", "Link", options="User"),
            f("reported_by_name", "Data"),
            f("employee", "Link", options="Employee", in_standard_filter=1),
            f("acknowledged_by", "Link", options="User"),
            f("acknowledged_on", "Datetime"),
            f("resolved_by", "Link", options="User"),
            f("resolved_on", "Datetime"),
            f("request_id", "Data", unique=1, read_only=1, hidden=1),
        ],
        "permissions": perms(("System Manager", 1), ("Maintenance Manager", 0), ("Maintenance User", 0),
                             ("Manufacturing Manager", 0), ("Manufacturing User", 0)),
    },
]

DOCTYPES.append({
    "name": "MES Batch Genealogy", "autoname": "field:output_batch", "title_field": "output_batch",
    "fields": [
        f("output_batch", "Link", options="Batch", reqd=1, unique=1, in_list_view=1, in_standard_filter=1),
        f("item_code", "Link", options="Item", in_list_view=1, in_standard_filter=1),
        f("qty", "Float"),
        f("work_order", "Link", options="Work Order", in_list_view=1, in_standard_filter=1),
        f("stock_entry", "Link", options="Stock Entry"),
        f("inputs", "Table", options="MES Batch Genealogy Input"),
    ],
    "permissions": perms(("System Manager", 1), ("Manufacturing Manager", 0), ("Manufacturing User", 0), ("Stock User", 0)),
})

READ_ROLES = {"MES Batch Reader": ["Batch"]}

STEP_SCAN = "None\nUnit\nQuantity\nConfirm"
REVIEW_FLAGS = "None\nMissing Information\nExpert Review\nMissing Image\nComponent Removed\nComponent Added\nQuantity Changed\nNot In BOM"

CHILD_DOCTYPES = [
    {
        "name": "MES Batch Genealogy Input", "istable": 1,
        "fields": [
            f("item_code", "Link", options="Item", in_list_view=1),
            f("batch_no", "Link", "Batch No", options="Batch", in_list_view=1),
            f("qty", "Float", in_list_view=1),
            f("stock_entry", "Link", options="Stock Entry", in_list_view=1),
        ],
        "permissions": [],
    },
    {
        "name": "MES Assembly Step", "istable": 1,
        "fields": [
            f("step_no", "Int", "Step No", in_list_view=1),
            f("step_name", "Data", reqd=1, in_list_view=1),
            f("item_code", "Link", options="Item", in_list_view=1),
            f("item_name", "Data"),
            f("qty", "Float", "Quantity per Unit", in_list_view=1),
            f("uom", "Data"),
            f("description", "Small Text"),
            f("instructions", "Text"),
            f("checklist", "Small Text", "Checklist (one item per line)"),
            f("comments", "Small Text"),
            f("col1", "Column Break"),
            f("scan_mode", "Select", options=STEP_SCAN, default="None", in_list_view=1),
            f("serial_required", "Check", "Serial Number Scan Required"),
            f("batch_required", "Check", "Batch Scan Required"),
            f("quality_inspection", "Check", "Quality Inspection Required"),
            f("photo_required", "Check", "Photo Attachment Required"),
            f("mandatory", "Check", "Mandatory", default="1"),
            f("image_override", "Attach Image", "Reference Image Override"),
            f("operation", "Data"),
            f("workstation", "Link", options="Workstation"),
            f("source", "Select", options="ERPNext BOM\nERPNext Operation\nAI Draft\nAdmin", default="ERPNext BOM"),
            f("confidence", "Select", options="High\nMedium\nLow", default="High"),
            f("review_flag", "Select", options=REVIEW_FLAGS, default="None", in_list_view=1),
            f("review_notes", "Small Text"),
        ],
        "permissions": [],
    },
    {
        "name": "MES Assembly Version", "istable": 1,
        "fields": [
            f("version", "Int", in_list_view=1),
            f("status", "Select", options="Draft\nApproved\nSuperseded", default="Draft", in_list_view=1),
            f("step_count", "Int"),
            f("change_note", "Small Text"),
            f("saved_by", "Data"),
            f("saved_on", "Datetime"),
            f("approved_by", "Data"),
            f("approved_on", "Datetime"),
            f("bom_signature", "Long Text", hidden=1),
            f("snapshot", "Long Text", hidden=1),
        ],
        "permissions": [],
    },
]

DOCTYPES += [
    {
        "name": "MES Assembly Workflow", "autoname": "MES-WF-.#####", "title_field": "finished_item",
        "fields": [
            f("finished_item", "Link", options="Item", reqd=1, unique=1, in_list_view=1, in_standard_filter=1),
            f("item_name", "Data", in_list_view=1),
            f("bom", "Link", options="BOM", read_only=1),
            f("status", "Select", options="Draft\nApproved\nArchived", default="Draft", in_list_view=1, in_standard_filter=1),
            f("sync_status", "Select", options="In Sync\nReview Needed", default="In Sync", in_list_view=1),
            f("source", "Select", options="Rule Draft\nAI Draft\nManual", default="Rule Draft"),
            f("current_version", "Int", read_only=1),
            f("approved_version", "Int", read_only=1),
            f("generation_notes", "Small Text", read_only=1),
            f("sync_notes", "Text", read_only=1),
            f("approved_bom_signature", "Long Text", hidden=1),
            f("col1", "Column Break"),
            f("approved_by", "Data", read_only=1),
            f("approved_on", "Datetime", read_only=1),
            f("generated_on", "Datetime", read_only=1),
            f("sb1", "Section Break", "Working Steps (latest saved version)"),
            f("steps", "Table", options="MES Assembly Step"),
            f("sb2", "Section Break", "Version History"),
            f("versions", "Table", options="MES Assembly Version"),
        ],
        "permissions": perms(("System Manager", 1), ("Manufacturing Manager", 0), ("Manufacturing User", 0)),
    },
    {
        "name": "MES Workflow Binding", "autoname": "field:work_order", "title_field": "work_order",
        "fields": [
            f("work_order", "Link", options="Work Order", reqd=1, unique=1, in_list_view=1),
            f("product", "Link", options="Item", in_list_view=1),
            f("workflow", "Link", options="MES Assembly Workflow", reqd=1, in_list_view=1),
            f("version", "Int", reqd=1, in_list_view=1),
            f("bound_on", "Datetime", reqd=1),
        ],
        "permissions": perms(("System Manager", 1), ("Manufacturing Manager", 0), ("Manufacturing User", 0)),
    },
]

def ensure_doctype(spec):
    if not frappe.db.exists("DocType", spec["name"]):
        base = {
            "doctype": "DocType", "name": spec["name"], "module": "Manufacturing", "custom": 1,
            "track_changes": 1, "fields": spec["fields"], "permissions": spec["permissions"],
        }
        if spec.get("istable"):
            base.update({"istable": 1, "editable_grid": 1})
        else:
            rule = "By fieldname" if spec["autoname"].startswith("field:") else "Expression (old style)"
            base.update({"autoname": spec["autoname"], "naming_rule": rule,
                         "title_field": spec["title_field"], "sort_field": "creation", "sort_order": "DESC"})
        doc = frappe.get_doc(base)
        doc.insert()
        print("created  ", spec["name"])
        return
    doc = frappe.get_doc("DocType", spec["name"])
    have = {x.fieldname for x in doc.fields}
    added = [x["fieldname"] for x in spec["fields"] if x["fieldname"] not in have]
    for x in spec["fields"]:
        if x["fieldname"] not in have:
            doc.append("fields", x)
    for x in spec["fields"]:
        if x["fieldtype"] == "Select":
            for row in doc.fields:
                if row.fieldname == x["fieldname"] and row.options != x["options"]:
                    row.options = x["options"]
                    added.append(x["fieldname"] + " options")
    rows = {p.role: p for p in doc.permissions if not p.permlevel}
    for p in spec["permissions"]:
        row = rows.get(p["role"])
        if not row:
            doc.append("permissions", p)
            added.append("perm " + p["role"])
            continue
        for k in ("read", "write", "create", "delete"):
            if int(row.get(k) or 0) != p[k]:
                row.set(k, p[k])
                added.append("perm %s %s=%s" % (p["role"], k, p[k]))
    if added:
        doc.save()
        print("updated  ", spec["name"], added)
    else:
        print("unchanged", spec["name"])


def ensure_read_role(role, doctypes):
    from frappe.permissions import add_permission
    if not frappe.db.exists("Role", role):
        frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
        print("created   role", role)
    for dt in doctypes:
        if frappe.db.exists("Custom DocPerm", {"parent": dt, "role": role, "permlevel": 0, "read": 1}):
            print("unchanged read", role, dt)
            continue
        add_permission(dt, role, 0)
        print("granted   read", role, dt)


def ensure_user(email, first, last, roles):
    if frappe.db.exists("User", email):
        u = frappe.get_doc("User", email)
    else:
        u = frappe.get_doc({"doctype": "User", "email": email, "first_name": first, "last_name": last,
                            "send_welcome_email": 0, "enabled": 1, "user_type": "System User"})
        u.flags.no_welcome_mail = True
        u.insert()
        print("created   user", email)
    have = {r.role for r in u.roles}
    missing = [r for r in roles if r not in have]
    if missing:
        u.add_roles(*missing)
        print("roles     ", email, missing)


def test_users():
    import site_config
    return [(u["email"], u["first"], u.get("last", ""), u["roles"]) for u in site_config.from_bench()["test_users"]]


frappe.init(site=os.environ["FRAPPE_SITE"], sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
for spec in CHILD_DOCTYPES + DOCTYPES:
    ensure_doctype(spec)
for role, dts in READ_ROLES.items():
    ensure_read_role(role, dts)
if "--test-users" in sys.argv[1:]:
    for row in test_users():
        ensure_user(*row)
frappe.db.commit()
frappe.destroy()
