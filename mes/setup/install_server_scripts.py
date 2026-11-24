"""Install/update the MES API server scripts from mes/server_scripts/ (idempotent).

Each mes_*.py becomes an API Server Script with api_method = file name; _prelude.py is prepended.
Run inside the bench (see install-server-scripts.ps1). Only touches scripts named mes_*.
"""
import glob
import os
import sys

import frappe

src = sys.argv[1]
frappe.init(site=os.environ.get("FRAPPE_SITE", "frontend"), sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
with open(os.path.join(src, "_prelude.py"), encoding="utf-8") as fh:
    prelude = fh.read()
for path in sorted(glob.glob(os.path.join(src, "mes_*.py"))):
    name = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8") as fh:
        body = prelude + "\n" + fh.read()
    if frappe.db.exists("Server Script", name):
        doc = frappe.get_doc("Server Script", name)
        if doc.script == body and not doc.disabled:
            print(f"unchanged {name}")
            continue
        doc.script = body
        doc.disabled = 0
        doc.save()
        print(f"updated   {name}")
    else:
        doc = frappe.new_doc("Server Script")
        doc.name = name
        doc.script_type = "API"
        doc.api_method = name
        doc.allow_guest = 0
        doc.script = body
        doc.insert(set_name=name)
        print(f"created   {name}")
frappe.db.commit()
frappe.destroy()
