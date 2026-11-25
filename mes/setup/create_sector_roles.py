"""Create the MES sector roles and the MES admin role, then assign them (idempotent).

Run inside the bench, with the user email passed through the environment:
   docker exec -e NEW_USER=<email> comp_demo-bench-1 bash -lc "cd /home/frappe/frappe-bench/sites && ../env/bin/python -W ignore -" < mes/setup/create_sector_roles.py

Prints PASSWORD_SETUP_LINK=<path> when run with --reset-password; the user sets their own password through it.
"""
import os
import sys

import frappe

SITE = "frontend"
SECTOR_ROLES = {
    "MES Injection Moulding": "P1 Injection Moulding",
    "MES Coil Winding": "P1 Coil Winding",
    "MES Varnish Oven": "P1 Varnish Impregnation Oven",
    "MES Sub-Assembly": "P1 Sub-Assembly Bench",
    "MES Motor Assembly": "P1 Motor Assembly",
    "MES Final Assembly": "P1 Final Assembly Line",
    "MES Electrical Test": "P1 Electrical Safety & Run Test",
    "MES Packing": "P1 Packing",
}
ADMIN_ROLE = "MES Admin"
BASE_ROLES = ["Manufacturing User", "Manufacturing Manager"]
DEFAULT_ROLES_TO_DROP = {"Customer"}
NEW_USER = os.environ.get("NEW_USER", "").strip()
RESET_PASSWORD = "--reset-password" in sys.argv


def ensure_role(name):
    if frappe.db.exists("Role", name):
        return "exists"
    frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(ignore_permissions=True)
    return "created"


frappe.init(site=SITE, sites_path=".")
frappe.connect()
frappe.set_user("Administrator")

for role in list(SECTOR_ROLES) + [ADMIN_ROLE]:
    print(f"role {role}: {ensure_role(role)}")

if NEW_USER:
    if not frappe.db.exists("User", NEW_USER):
        user = frappe.get_doc({
            "doctype": "User",
            "email": NEW_USER,
            "first_name": NEW_USER.split("@")[0],
            "user_type": "System User",
            "send_welcome_email": 0,
            "enabled": 1,
        })
        user.insert(ignore_permissions=True)
        print(f"user {NEW_USER}: created")
    else:
        user = frappe.get_doc("User", NEW_USER)
        print(f"user {NEW_USER}: exists")

    wanted = BASE_ROLES + [ADMIN_ROLE]
    user.roles = [r for r in user.roles if r.role not in DEFAULT_ROLES_TO_DROP]
    have = {r.role for r in user.roles}
    for role in wanted:
        if role not in have:
            user.append("roles", {"role": role})
    user.save(ignore_permissions=True)
    print(f"user {NEW_USER} roles: {sorted(r.role for r in user.roles)}")

    if RESET_PASSWORD:
        link = user._reset_password(send_email=False)
        print(f"PASSWORD_SETUP_LINK={link}")

frappe.db.commit()
print("sector roles:", {k: v for k, v in SECTOR_ROLES.items()})
