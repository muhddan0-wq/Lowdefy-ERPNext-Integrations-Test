"""Export CODE128 ID badges for the plant's employees (the station sign-in accepts the Employee ID), as PNGs, a CSV and
a printable HTML sheet. Runs as the Appsmith API user.

Usage (from the repo root): python mes/setup/export_badges.py <out_dir> [employees.json]
employees.json (list of {name, employee_name}) replaces the REST read when the API user cannot read Employee.
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
CODE_IMG = "barcode_shrdc.barcode_shrdc.doctype.barcode_printing.barcode_printing.get_barcode_image"
OUT = pathlib.Path(sys.argv[1]).resolve() / "badges"
OUT.mkdir(parents=True, exist_ok=True)


def call(path, data=None):
    req = urllib.request.Request(ERP + path, data=data, method="POST" if data else "GET",
                                 headers={"Authorization": AUTH, "Accept": "application/json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


fields = urllib.parse.quote(json.dumps(["name", "employee_name", "attendance_device_id"]))
filters = urllib.parse.quote(json.dumps([["company", "=", CFG["company"]["name"]], ["status", "=", "Active"]]))
emps = json.loads(pathlib.Path(sys.argv[2]).read_text()) if len(sys.argv) > 2 else json.loads(call("/api/resource/Employee?fields=%s&filters=%s&limit_page_length=500&order_by=name%%20asc" % (fields, filters)))["data"]
operators = {v: k for k, v in (CFG.get("operators") or {}).items()}
rows, labels = [], []
for e in emps:
    url = json.loads(call("/api/method/" + CODE_IMG, json.dumps({"barcode": e["name"], "barcode_type": "CODE128", "display_value": 1}).encode()))["message"]
    png = OUT / ("%s.png" % e["name"])
    png.write_bytes(call(urllib.parse.quote(url)))
    station = operators.get(e["employee_name"], "")
    rows.append({"employee_id": e["name"], "name": e["employee_name"], "home_station": station, "label_file": "badges/" + png.name})
    src = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode("ascii")
    labels.append('<div class="label"><img src="%s"><div style="font-weight:bold">%s</div><div>%s</div><div>%s</div></div>' % (
        src, html.escape(e["employee_name"]), html.escape(e["name"]), html.escape(station)))
with open(OUT.parent / "badges.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
css = (".label{display:inline-block;border:1px solid #999;padding:8px;margin:4px;width:300px;font:13px sans-serif;"
       "vertical-align:top;page-break-inside:avoid}.label img{width:100%;height:70px;object-fit:contain}")
(OUT.parent / "badges.html").write_text("<!doctype html><meta charset=utf-8><title>Operator badges</title><style>%s</style>"
                                       "<h1 style='font:18px sans-serif'>Operator ID badges (scan at station sign-in)</h1>%s" % (css, "".join(labels)), encoding="utf-8")
print(json.dumps({"badges": len(rows), "out": str(OUT.parent)}))
