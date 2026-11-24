import os
import sys

import frappe
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))


def load():
    with open(os.path.join(HERE, "products.yaml"), encoding="utf-8") as fh:
        P = yaml.safe_load(fh)
    with open(os.path.join(HERE, "site.yaml"), encoding="utf-8") as fh:
        S = yaml.safe_load(fh)
    return P, S


def connect():
    frappe.init(site=os.environ.get("FRAPPE_SITE", "frontend"), sites_path=".")
    frappe.connect()
    frappe.set_user("Administrator")


def quiet_item_tracking(S):
    if not S.get("skip_item_tracking_labels", True):
        return
    try:
        import item_tracking.item_tracking.events as ev
    except ImportError:
        return
    ev._auto_create_tracked_items = lambda *args, **kwargs: []
    ev._create_finished_good_barcode_printing = lambda *args, **kwargs: None


def run(main):
    connect()
    try:
        P, S = load()
        quiet_item_tracking(S)
        main(P, S)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.destroy()


def ensure(doctype, name, builder):
    if frappe.db.exists(doctype, name):
        return name
    doc = frappe.get_doc(builder())
    doc.insert()
    return doc.name


def company_of(S):
    return S["company"]["name"]


def abbr_of(S):
    return S["company"]["abbr"]


def wh(S, label):
    return f"{S['code']} {label} - {abbr_of(S)}"


def warehouses(S):
    return {
        "stores": wh(S, "Stores"),
        "wip": wh(S, "Work In Progress"),
        "fg": wh(S, "Finished Goods"),
        "scrap": wh(S, "Scrap"),
    }


def process_of(P, operation):
    return P["operations"][operation]


def all_codes(P):
    return [r[0] for r in P["raw_materials"]] + [r[0] for r in P["sub_assemblies"]] + [r[0] for r in P["finished_goods"]]


def phase(msg):
    print(f"[MES] {msg}", flush=True)
    sys.stdout.flush()
