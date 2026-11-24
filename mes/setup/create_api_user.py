"""Create the dedicated Appsmith API user (idempotent). Run inside the bench:
   ../env/bin/python -W ignore create_api_user.py [--new-keys]
Writes the key/secret to ./appsmith-mes.env (copy it out, then delete it)."""
import sys
import frappe

USER = "appsmith-mes@voltra.local"
COMPANY = "Voltra Power Tools Sdn Bhd"
ROLES = ["Manufacturing User", "Manufacturing Manager", "Stock User"]

frappe.init(site="frontend", sites_path=".")
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
    with open("appsmith-mes.env", "w") as fh:
        fh.write(f"ERP_API_KEY={key}\nERP_API_SECRET={secret}\n")
    print("keys generated -> appsmith-mes.env")
else:
    print("user exists with api_key; use --new-keys to rotate")
print("roles:", [r.role for r in frappe.get_doc("User", USER).roles])
