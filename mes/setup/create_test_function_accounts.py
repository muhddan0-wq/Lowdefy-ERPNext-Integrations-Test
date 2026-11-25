"""Create one test role per business function and one test account holding only that role (idempotent).

Run inside the bench, with the output directory passed through the environment:
   docker exec -i -e OUT_DIR=<dir> comp_demo-bench-1 bash -lc "cd /home/frappe/frappe-bench/sites && ../env/bin/python -W ignore -" < mes/setup/create_test_function_accounts.py

Writes one password setup link per new account to OUT_DIR/test_account_links.txt.
"""
import os

import frappe

SITE = "frontend"
DOMAIN = "voltra.local"
FUNCTIONS = ["Finance", "Purchasing", "Inventory", "Sales", "Production", "Quality", "Maintenance", "Human Resources"]
OUT_DIR = os.environ["OUT_DIR"]


def role_name(function):
    return f"Test {function}"


def account_email(function):
    return f"test.{function.lower().replace(' ', '.')}@{DOMAIN}"


frappe.init(site=SITE, sites_path=".")
frappe.connect()
frappe.set_user("Administrator")

links = []
for function in FUNCTIONS:
    role = role_name(function)
    if frappe.db.exists("Role", role):
        print(f"role {role}: exists")
    else:
        frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
        print(f"role {role}: created")

    email = account_email(function)
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
        print(f"user {email}: exists")
    else:
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": f"Test {function}",
            "user_type": "System User",
            "send_welcome_email": 0,
            "enabled": 1,
        }).insert(ignore_permissions=True)
        print(f"user {email}: created")
        links.append(f"{email}\t{user._reset_password(send_email=False)}")

    user = frappe.get_doc("User", email)
    user.roles = [r for r in user.roles if r.role == role]
    if not user.roles:
        user.append("roles", {"role": role})
    user.save(ignore_permissions=True)
    print(f"user {email} roles: {[r.role for r in user.roles]}")

frappe.db.commit()

if links:
    path = os.path.join(OUT_DIR, "test_account_links.txt")
    with open(path, "w") as fh:
        fh.write("\n".join(links) + "\n")
    print(f"LINKS_WRITTEN={path}")
