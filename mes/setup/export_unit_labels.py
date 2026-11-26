"""Download the CODE128 label image of every tracked unit (one PNG per unit) through ERPNext's own renderer, as the
Appsmith API user. Writes mes/state/barcode-labels/<item>/<tracking id>.png and index.csv, and reports how much
narrower the 8-digit barcode is than the old tracking-ID barcode.

Usage (from the repo root): python mes/setup/export_unit_labels.py [item_code ...]
With no item codes, every item that has tracked units and no batch numbers is exported.
"""
import csv
import json
import pathlib
import struct
import sys
import urllib.parse
import urllib.request

MES = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MES))
import site_config  # noqa: E402

CFG = site_config.load()
ENV = dict(l.split("=", 1) for l in (MES / ".secrets" / "appsmith-mes.env").read_text().split() if "=" in l)
AUTH = "token %s:%s" % (ENV["ERP_API_KEY"], ENV["ERP_API_SECRET"])
ERP = CFG["erp"]["public_url"].rstrip("/")
OUT = MES / "state" / "barcode-labels"
TRACKED = "item_tracking.item_tracking.doctype.tracked_item.tracked_item.get_tracking_barcode_image"
RENDER = "barcode_shrdc.barcode_shrdc.doctype.barcode_printing.barcode_printing.get_barcode_image"


def get(path):
    req = urllib.request.Request(ERP + path, headers={"Authorization": AUTH, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def post(method, **args):
    req = urllib.request.Request(ERP + "/api/method/" + method, data=json.dumps(args).encode(), method="POST",
                                 headers={"Authorization": AUTH, "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["message"]


def resource(doctype, fields, filters):
    q = "?fields=%s&filters=%s&limit_page_length=0" % (urllib.parse.quote(json.dumps(fields)), urllib.parse.quote(json.dumps(filters)))
    return json.loads(get("/api/resource/" + urllib.parse.quote(doctype) + q))["data"]


def png_width(data):
    return struct.unpack(">I", data[16:20])[0]


units = resource("Tracked Item", ["name", "item_code", "barcode", "serial_no"], [])
items = sys.argv[1:]
if not items:
    codes = sorted({u["item_code"] for u in units})
    batch = {i["name"] for i in resource("Item", ["name"], [["name", "in", codes], ["has_batch_no", "=", 1]])}
    items = [c for c in codes if c not in batch]
units = sorted([u for u in units if u["item_code"] in items], key=lambda u: u["name"])
rows = []
for u in units:
    url = post(TRACKED, tracking_id=u["name"])
    data = get(urllib.parse.quote(url))
    folder = OUT / u["item_code"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (u["name"] + ".png")).write_bytes(data)
    rows.append({"item_code": u["item_code"], "unit_id": u["name"], "serial_no": u["serial_no"], "barcode": u["barcode"],
                 "file": "%s/%s.png" % (u["item_code"], u["name"]), "width_px": png_width(data)})
with open(OUT / "index.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["item_code"])
    w.writeheader()
    w.writerows(rows)
if rows:
    sample = rows[0]
    old = png_width(get(urllib.parse.quote(post(RENDER, barcode=sample["unit_id"], barcode_type="CODE128", display_value=1))))
    print("exported %d unit labels for %s to %s" % (len(rows), ", ".join(items), OUT))
    print("sample %s: old barcode %r is %d px wide, new barcode %r is %d px wide (%.0f%% narrower)" % (
        sample["unit_id"], sample["unit_id"], old, sample["barcode"], sample["width_px"], 100.0 * (old - sample["width_px"]) / old))
else:
    print("no tracked units for %s" % (items,))
