"""Create the MES sector roles and the MES admin role, then assign them (idempotent).

Role names and the Workstation Type each role works on come from sector_roles in the site YAML.
Run by install-mes.ps1, or with a user (the email passed through the environment):
   mes/setup/install-mes.ps1 -Only roles -AdminUser <email> [-ResetPassword]

Prints PASSWORD_SETUP_LINK=<path> when run with --reset-password; the user sets their own password through it.
"""
import os
import sys

import frappe

import site_config

CFG = site_config.from_bench()
SITE = os.environ.get("FRAPPE_SITE", CFG["erp"]["site"])
SECTOR_ROLES = CFG["sector_roles"]
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
