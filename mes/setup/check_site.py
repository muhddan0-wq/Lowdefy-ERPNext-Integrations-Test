"""Read-only precondition check for an MES install on an ERPNext site. Runs inside the bench (see install-mes.ps1).

Reports each value from the site YAML that the MES needs on the site, and whether it exists.
BLOCK rows stop the install; WARN rows are reported and the install continues.
Exit code 1 when any BLOCK row fails. Usage: python check_site.py [--strict] (WARN also fails).
"""
import os
import sys

import frappe

import site_config

cfg = site_config.from_bench()
frappe.init(site=os.environ.get("FRAPPE_SITE", cfg["erp"]["site"]), sites_path=".")
frappe.connect()
frappe.set_user("Administrator")

rows = []


def check(level, what, name, ok, hint=""):
    rows.append((level, what, name, bool(ok), hint))


company = cfg["company"]["name"]
check("BLOCK", "Company", company, frappe.db.exists("Company", company), "create the company or fix company.name")
pf = frappe.db.get_value("Plant Floor", cfg["plant_floor"], ["name", "company"], as_dict=True)
check("BLOCK", "Plant Floor", cfg["plant_floor"], pf, "create the Plant Floor or fix plant_floor")
if pf and pf.company and pf.company != company:
    check("WARN", "Plant Floor company", f"{pf.company} (expected {company})", False, "plant floor belongs to another company")
for key in site_config.WAREHOUSE_KEYS:
    wh = cfg["warehouses"][key]
    wc = frappe.db.get_value("Warehouse", wh, "company")
    check("BLOCK", f"Warehouse {key}", wh, wc, "create the warehouse or fix warehouses." + key)
    if wc and wc != company:
        check("WARN", f"Warehouse {key} company", f"{wc} (expected {company})", False, "")
stations = frappe.get_all("Workstation", filters={"plant_floor": cfg["plant_floor"]}, pluck="name")
check("WARN", "Workstations on plant floor", f"{len(stations)} found", stations, "assign Workstations to the plant floor")
prefixed = frappe.db.sql(
    "select count(*) from `tabBOM Operation` where workstation_type like %s", cfg["site_prefix"] + "%")[0][0]
check("WARN", "BOM operations with site_prefix", f"{cfg['site_prefix']!r}: {prefixed}", prefixed,
      "planning only counts operations whose workstation type starts with site_prefix")
for role, wtype in cfg["sector_roles"].items():
    check("WARN", f"Workstation Type for {role}", wtype, frappe.db.exists("Workstation Type", wtype),
          "fix sector_roles in the site YAML")
check("WARN", "DocType Tracked Item", "Tracked Item", frappe.db.exists("DocType", "Tracked Item"),
      "unit scans need tracked-unit stock")
INSTALLED_ROLES = {"MES Batch Reader"}
for role in cfg["api_user"]["roles"]:
    if role in INSTALLED_ROLES:
        check("WARN", "Role for API user", role, frappe.db.exists("Role", role), "created by install-mes.ps1 -Only doctypes")
    else:
        check("BLOCK", "Role for API user", role, frappe.db.exists("Role", role), "")
for dt in ("MES Material Scan", "MES Machine Issue", "MES Batch Genealogy"):
    check("WARN", "DocType", dt, frappe.db.exists("DocType", dt), "install-mes.ps1 -Only doctypes")
api_user = cfg["api_user"]["email"]
if frappe.db.exists("User", api_user):
    from frappe.permissions import has_permission
    expect = [("Batch", True), ("Serial No", True), ("Work Order", True), ("MES Machine Issue", True),
              ("Maintenance Request", False), ("Issue", False), ("Asset", False)]
    for dt, want in expect:
        if not frappe.db.exists("DocType", dt):
            continue
        got = bool(has_permission(dt, "read", user=api_user, print_logs=False))
        check("WARN", f"API user read {dt}", f"{'allowed' if got else 'denied'} (expected {'allowed' if want else 'denied'})",
              got == want, "fix the API user's roles")
else:
    check("WARN", "API user", api_user, False, "install-mes.ps1 -Only apiuser")
check("WARN", "Script API enabled", "server_script_enabled", frappe.conf.get("server_script_enabled"),
      "bench --site <site> set-config -g server_script_enabled 1")

strict = "--strict" in sys.argv[1:]
failed = 0
print(f"site config {cfg['source']} -> site {frappe.local.site}")
for level, what, name, ok, hint in rows:
    tag = "ok   " if ok else level.ljust(5)
    print(f"{tag} {what}: {name}" + ("" if ok or not hint else f"  ({hint})"))
    if not ok and (level == "BLOCK" or strict):
        failed += 1
print(f"CHECK {'FAILED' if failed else 'PASSED'}: {failed} blocking, {sum(1 for r in rows if not r[3])} not ok of {len(rows)}")
frappe.destroy()
sys.exit(1 if failed else 0)
