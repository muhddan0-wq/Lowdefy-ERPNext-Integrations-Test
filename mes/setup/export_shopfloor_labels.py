"""Export what each shopfloor work order needs to scan: batch numbers and unit barcodes per work order (CSV), the batches
the orders use, with quantity and date (CSV), CODE128 label PNGs from ERPNext's own renderer, and printable HTML
sheets with the images embedded (each opens on its own, offline). Runs as the Appsmith API user; it allocates nothing in ERPNext,
it only suggests which batch or unit to scan so two orders never get the same unit or overdraw a batch.

Usage (from the repo root): python mes/setup/export_shopfloor_labels.py <out_dir> <work_order> [...]
"""
import base64
import csv
import html
import json
import pathlib
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
STORES = CFG["warehouses"]["stores"]
UNIT_IMG = "item_tracking.item_tracking.doctype.tracked_item.tracked_item.get_tracking_barcode_image"
CODE_IMG = "barcode_shrdc.barcode_shrdc.doctype.barcode_printing.barcode_printing.get_barcode_image"
MODE_TEXT = {"unit": "Scan every unit", "batch": "Scan batch label, then quantity", "scan": "Scan item, then quantity",
             "confirm": "Confirm quantity"}


def get(path):
    req = urllib.request.Request(ERP + path, headers={"Authorization": AUTH, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def post(method, **args):
    req = urllib.request.Request(ERP + "/api/method/" + method, data=json.dumps(args).encode(), method="POST",
                                 headers={"Authorization": AUTH, "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["message"]


def resource(doctype, fields, filters, order_by="name asc"):
    q = "?fields=%s&filters=%s&order_by=%s&limit_page_length=0" % (
        urllib.parse.quote(json.dumps(fields)), urllib.parse.quote(json.dumps(filters)), urllib.parse.quote(order_by))
    return json.loads(get("/api/resource/" + urllib.parse.quote(doctype) + q))["data"]


def doc(doctype, name):
    return json.loads(get("/api/resource/%s/%s" % (urllib.parse.quote(doctype), urllib.parse.quote(name))))["data"]


def save_png(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(get(urllib.parse.quote(url)))


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def label_html(img, lines):
    e = html.escape
    body = "".join("<div%s>%s</div>" % (' style="font-weight:bold"' if i == 0 else "", e(str(t))) for i, t in enumerate(lines) if t)
    src = "data:image/png;base64," + base64.b64encode((OUT / img).read_bytes()).decode("ascii")
    return ('<div class="label"><img src="%s">%s</div>' % (src, body))


def sheet(path, title, sections):
    css = ("body{font-family:sans-serif;margin:12px}h1{font-size:18px}h2{font-size:15px;margin:14px 0 4px}"
           ".label{display:inline-block;border:1px solid #999;padding:6px;margin:3px;width:300px;font-size:12px;"
           "vertical-align:top;page-break-inside:avoid}.label img{width:100%;height:64px;object-fit:contain}"
           "table{border-collapse:collapse;font-size:12px}td,th{border:1px solid #bbb;padding:2px 6px;text-align:left}"
           "@media print{h2{page-break-after:avoid}}")
    parts = ["<!doctype html><meta charset=utf-8><title>%s</title><style>%s</style><h1>%s</h1>" % (html.escape(title), css, html.escape(title))]
    for heading, inner in sections:
        parts.append("<h2>%s</h2>%s" % (html.escape(heading), inner))
    path.write_text("".join(parts), encoding="utf-8")


args = sys.argv[1:]
if len(args) < 2:
    raise SystemExit(__doc__)
OUT = pathlib.Path(args[0]).resolve()
WOS = args[1:]
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "work-orders").mkdir(exist_ok=True)

orders = [doc("Work Order", n) for n in WOS]
codes = sorted({r["item_code"] for o in orders for r in o["required_items"]})
items = {i["name"]: i for i in resource("Item", ["name", "item_name", "has_batch_no", "has_serial_no", "stock_uom"], [["name", "in", codes]])}
whole = {u["name"]: u["must_be_whole_number"] for u in resource("UOM", ["name", "must_be_whole_number"], [])}
tracked_codes = {t["item_code"] for t in resource("Tracked Item", ["item_code"], [["item_code", "in", codes]])}
for c in codes:
    it = items[c]
    unit = it["has_serial_no"] or (not it["has_batch_no"] and c in tracked_codes)
    it["mode"] = "unit" if unit else ("batch" if it["has_batch_no"] else ("scan" if whole.get(it["stock_uom"]) else "confirm"))

open_wo = {w["name"] for w in resource("Work Order", ["name"], [["status", "not in", ["Completed", "Closed", "Cancelled"]], ["docstatus", "=", 1]])}
scans = resource("MES Material Scan", ["work_order", "item_code", "unit_id", "unit_key", "batch_no", "qty", "result"], [["result", "=", "Valid"]])
used_units = {s["unit_id"] for s in scans if s.get("unit_key")}
claimed = {}
for s in scans:
    if s.get("batch_no") and s["work_order"] in open_wo:
        claimed[s["batch_no"]] = claimed.get(s["batch_no"], 0) + (s["qty"] or 0)
defects = resource("MES Defect Report", ["unit_id", "status", "disposition"], [["status", "!=", "Rejected"]])
bad_units = {d["unit_id"] for d in defects if d.get("unit_id") and d.get("disposition") != "Use As Is"}

batches = resource("Batch", ["name", "item", "item_name", "batch_qty", "stock_uom", "manufacturing_date", "expiry_date", "creation", "disabled"], [])
today = __import__("datetime").date.today().isoformat()
for b in batches:
    b["p1_qty"] = float(post("erpnext.stock.doctype.batch.batch.get_batch_qty", batch_no=b["name"], warehouse=STORES) or 0)
    b["free"] = max(b["p1_qty"] - claimed.get(b["name"], 0), 0)
    b["usable"] = not b["disabled"] and not (b.get("expiry_date") and b["expiry_date"] < today)
    b["allocated_to"] = []

pool = {}
for c in codes:
    if items[c]["mode"] == "unit":
        units = resource("Tracked Item", ["name", "item_code", "barcode", "serial_no", "creation"],
                         [["item_code", "=", c], ["current_status", "=", "In Stock"], ["current_warehouse", "=", STORES]], order_by="creation desc")
        pool[c] = [u for u in units if u["name"] not in used_units and u["name"] not in bad_units and u.get("barcode")]

rows_all = []
per_order = []
unit_labels = []
for o in orders:
    rows = []
    for r in o["required_items"]:
        it = items[r["item_code"]]
        need = float(r["required_qty"] or 0) - float(r.get("transferred_qty") or 0)
        base = {"work_order": o["name"], "production_item": o["production_item"], "wo_qty": o["qty"], "item_code": r["item_code"],
                "item_name": it["item_name"], "scan_mode": MODE_TEXT[it["mode"]], "batch_no": "", "tracking_id": "", "barcode": "",
                "qty": "", "uom": it["stock_uom"], "label_file": "", "note": ""}
        if need <= 1e-9:
            rows.append(dict(base, qty=0, note="already issued"))
            continue
        if it["mode"] == "batch":
            cands = [b for b in batches if b["item"] == r["item_code"] and b["usable"] and b["free"] > 1e-9]
            fit = sorted([b for b in cands if b["free"] >= need - 1e-9], key=lambda b: (not b["name"].isdigit(), b["free"], b["creation"]))
            picks = fit[:1] if fit else sorted(cands, key=lambda b: (not b["name"].isdigit(), -b["free"]))
            left = need
            for b in picks:
                if left <= 1e-9:
                    break
                take = min(left, b["free"])
                b["free"] -= take
                left -= take
                b["allocated_to"].append("%s:%s" % (o["name"], take))
                rows.append(dict(base, batch_no=b["name"], barcode=b["name"], qty=take, label_file="batches/%s.png" % b["name"],
                                 note="batch holds %s in %s; the station counts only what this order still needs" % (b["p1_qty"], STORES)))
            if left > 1e-9:
                rows.append(dict(base, qty=left, note="SHORT: no free batch quantity left"))
        elif it["mode"] == "unit":
            take = pool[r["item_code"]][:int(round(need))]
            pool[r["item_code"]] = pool[r["item_code"]][len(take):]
            for u in sorted(take, key=lambda u: u["name"]):
                f = "units/%s/%s.png" % (u["item_code"], u["name"])
                rows.append(dict(base, tracking_id=u["name"], barcode=u["barcode"], qty=1, label_file=f, note=u["serial_no"]))
                unit_labels.append((o["name"], u, f))
            if len(take) < need:
                rows.append(dict(base, qty=need - len(take), note="SHORT: not enough free tracked units in %s" % STORES))
        else:
            rows.append(dict(base, barcode=r["item_code"], qty=round(need, 6), label_file="items/%s.png" % r["item_code"],
                             note="no batch or unit label: scan the item code, then enter the quantity"))
    per_order.append((o, rows))
    rows_all.extend(rows)

FIELDS = ["work_order", "production_item", "wo_qty", "item_code", "item_name", "scan_mode", "batch_no", "tracking_id", "barcode",
          "qty", "uom", "label_file", "note"]
for o, rows in per_order:
    write_csv(OUT / "work-orders" / ("%s_%s.csv" % (o["name"], o["production_item"])), rows, FIELDS)
write_csv(OUT / "all-work-orders.csv", rows_all, FIELDS)

stocked = sorted([b for b in batches if b["allocated_to"]], key=lambda b: (b["item"], b["name"]))
lab = post("mes_batch_labels", batch_ids=[b["name"] for b in stocked])
img = {l["batch_no"]: l["image"] for l in lab["labels"]}
for b in stocked:
    save_png(img[b["name"]], OUT / "batches" / ("%s.png" % b["name"]))
write_csv(OUT / "batches.csv", [{
    "batch_no": b["name"], "item_code": b["item"], "item_name": b.get("item_name") or "", "qty_in_p1_stores": b["p1_qty"],
    "uom": b.get("stock_uom") or "", "date": b.get("manufacturing_date") or b["creation"][:10], "expiry_date": b.get("expiry_date") or "",
    "used_by": " ".join(b["allocated_to"]), "label_file": "batches/%s.png" % b["name"]} for b in stocked],
    ["batch_no", "item_code", "item_name", "qty_in_p1_stores", "uom", "date", "expiry_date", "used_by", "label_file"])

for _, u, f in unit_labels:
    save_png(post(UNIT_IMG, tracking_id=u["name"]), OUT / f)
for c in codes:
    if items[c]["mode"] in ("scan", "confirm"):
        save_png(post(CODE_IMG, barcode=c, barcode_type="CODE128", display_value=1), OUT / "items" / ("%s.png" % c))

sheet(OUT / "batch-labels.html", "Batch labels for the work orders (%d)" % len(stocked), [(
    item, "".join(label_html("batches/%s.png" % b["name"], [b["name"], b["item"], b.get("item_name"), "Qty %s %s, date %s" % (
        b["p1_qty"], b.get("stock_uom") or "", b.get("manufacturing_date") or b["creation"][:10])]) for b in stocked if b["item"] == item))
    for item in sorted({b["item"] for b in stocked})])
by_item = {}
for _, u, f in unit_labels:
    by_item.setdefault(u["item_code"], []).append((u, f))
sheet(OUT / "unit-labels.html", "Unit labels suggested for the work orders (%d)" % len(unit_labels), [(
    item, "".join(label_html(f, [u["barcode"], u["name"], items[item]["item_name"], u["serial_no"]]) for u, f in sorted(v, key=lambda x: x[0]["name"])))
    for item, v in sorted(by_item.items())])
for o, rows in per_order:
    table = "<table><tr><th>Item</th><th>How to scan</th><th>Batch / unit</th><th>Barcode</th><th>Qty</th></tr>%s</table>" % "".join(
        "<tr><td>%s %s</td><td>%s</td><td>%s</td><td>%s</td><td>%s %s</td></tr>" % tuple(html.escape(str(x)) for x in (
            r["item_code"], r["item_name"], r["scan_mode"], r["batch_no"] or r["tracking_id"], r["barcode"], r["qty"], r["uom"])) for r in rows)
    labels = "".join(label_html(r["label_file"], [r["barcode"], r["tracking_id"] or r["batch_no"] or r["item_code"], r["item_name"],
                                                  "Qty %s %s" % (r["qty"], r["uom"])]) for r in rows if r["label_file"])
    sheet(OUT / "work-orders" / ("%s_%s.html" % (o["name"], o["production_item"])),
          "%s: %s x %s %s" % (o["name"], o["qty"], o["production_item"], o["item_name"]),
          [("What to scan", table), ("Labels", labels)])

short = [r for r in rows_all if r["note"].startswith("SHORT")]
print(json.dumps({"out": str(OUT), "work_orders": len(orders), "rows": len(rows_all), "batch_labels": len(stocked),
                  "barcode_printing": lab["barcode_printing"], "unit_labels": len(unit_labels),
                  "item_labels": len([c for c in codes if items[c]["mode"] in ("scan", "confirm")]), "short": short}, indent=1))
