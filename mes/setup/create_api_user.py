"""Create the dedicated Appsmith API user (idempotent). Email, roles and company come from the site YAML.
Run by install-mes.ps1 (-NewKeys rotates). Writes the key/secret to ./appsmith-mes.env when keys are generated;
install-mes.ps1 moves it to mes/.secrets/ and deletes it from the bench."""
import os
import sys

import frappe

import site_config

CFG = site_config.from_bench()
USER = CFG["api_user"]["email"]
COMPANY = CFG["company"]["name"]
ROLES = CFG["api_user"]["roles"]

frappe.init(site=os.environ.get("FRAPPE_SITE", CFG["erp"]["site"]), sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
if not frappe.db.exists("User", USER):
    u = frappe.get_doc({"doctype": "User", "email": USER, "first_name": "Appsmith", "last_name": "MES",
                        "user_type": "System User", "send_welcome_email": 0, "enabled": 1})
    u.insert()
u = frappe.get_doc("User", USER)
have = {r.role for r in u.roles}
for r in ROLES:
    if r not in have:
        u.append("roles", {"role": r})
u.save()
if not frappe.db.exists("User Permission", {"user": USER, "allow": "Company", "for_value": COMPANY}):
    frappe.get_doc({"doctype": "User Permission", "user": USER, "allow": "Company", "for_value": COMPANY,
                    "apply_to_all_doctypes": 1, "is_default": 1}).insert()
frappe.db.commit()
if "--new-keys" in sys.argv or not u.api_key:
    from frappe.core.doctype.user.user import generate_keys
    secret = generate_keys(USER)["api_secret"]
    key = frappe.db.get_value("User", USER, "api_key")
    frappe.db.commit()
    with open(os.environ.get("KEY_FILE", "appsmith-mes.env"), "w") as fh:
        fh.write(f"ERP_API_KEY={key}\nERP_API_SECRET={secret}\n")
    print("KEYS_WRITTEN=" + os.environ.get("KEY_FILE", "appsmith-mes.env"))
else:
    print("user exists with api_key; use --new-keys to rotate")
print("roles:", [r.role for r in frappe.get_doc("User", USER).roles])
