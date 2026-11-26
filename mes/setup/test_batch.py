"""Acceptance tests for batch production and API permissions, run against the live sandbox through the Appsmith API
user and the mes_* endpoints. Writes mes/state/batch-test-results.md (and .json).

It writes to the sandbox: one 75-unit batch and two small rejection batches (Material Receipts), one expired Batch,
a qty-2 Work Order for a batch-tracked product with its scans, issue and finish stock entries, an output batch with
its MES Batch Genealogy, and one Barcode Printing document. Fixtures are discovered at run time; a check whose
fixture is missing is reported NOT TESTED.

Usage (from the repo root): python mes/setup/test_batch.py
"""
import json
import re
import pathlib
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

MES = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MES))
import site_config  # noqa: E402

CFG = site_config.load()
ENV = dict(l.split("=", 1) for l in (MES / ".secrets" / "appsmith-mes.env").read_text().split() if "=" in l)
AUTH = "token %s:%s" % (ENV["ERP_API_KEY"], ENV["ERP_API_SECRET"])
ERP = CFG["erp"]["public_url"].rstrip("/")
CONTAINER = CFG["erp"]["container"]
FSITE = CFG["erp"]["site"]
COMPANY = CFG["company"]["name"]
WH = CFG["warehouses"]
OP = [u["email"] for u in CFG["test_users"] if "Manufacturing User" in u["roles"] and "Manufacturing Manager" not in u["roles"]][0]
STAMP = time.strftime("%Y%m%d%H%M%S")
RESULTS = []
TRACKED = "item_tracking.item_tracking.doctype.tracked_item.tracked_item."


def call(method, **args):
    args.setdefault("employee", "HR-EMP-00001")
    req = urllib.request.Request(ERP + "/api/method/" + method, data=json.dumps(args).encode(), method="POST",
                                 headers={"Authorization": AUTH, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read()).get("message")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
            msg = body.get("exception") or body.get("_server_messages") or raw
        except Exception:
            msg = raw
        return e.code, str(msg)[:500]


def rest(path):
    req = urllib.request.Request(ERP + urllib.parse.quote(path, safe="/?=&"), headers={"Authorization": AUTH, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def bench(code):
    script = ("import frappe, json\nfrappe.init(site=%r, sites_path='.')\nfrappe.connect()\nfrappe.set_user('Administrator')\n" % (FSITE,)
              + textwrap.dedent(code))
    p = subprocess.run(["docker", "exec", "-i", "-w", "/home/frappe/frappe-bench/sites", CONTAINER, "../env/bin/python", "-W", "ignore", "-"],
                       input=script, capture_output=True, text=True, timeout=300)
    lines = [l for l in p.stdout.splitlines() if l.startswith("@@")]
    if not lines:
        raise RuntimeError(p.stderr[-1200:])
    return json.loads(lines[-1][2:])


def check(cid, text, ok, evidence):
    RESULTS.append({"id": cid, "criterion": text, "result": "PASS" if ok else "FAIL", "evidence": str(evidence)[:600]})
    print("%-4s %-4s %s | %s" % (cid, "PASS" if ok else "FAIL", text, str(evidence)[:200]), flush=True)


def skip(cid, text, why):
    RESULTS.append({"id": cid, "criterion": text, "result": "NOT TESTED", "evidence": why})
    print("%-4s SKIP %s | %s" % (cid, text, why), flush=True)


def rid():
    return "tb-" + uuid.uuid4().hex


def batch_qty(b):
    s, d = rest("/api/resource/Batch/" + b)
    return d["data"]["batch_qty"] if s == 200 else "HTTP %s" % s


def scan(jc, value, **kw):
    s, r = call("mes_sf_scan", operator=OP, job_card=jc, value=value, request_id=rid(), **kw)
    return r if s == 200 else {"ok": False, "reason": "HTTP %s %s" % (s, r), "scan": None}


def finish_report():
    (MES / "state").mkdir(exist_ok=True)
    (MES / "state" / "batch-test-results.json").write_text(json.dumps(RESULTS, indent=1), encoding="utf-8")
    n = {k: sum(r["result"] == k for r in RESULTS) for k in ("PASS", "FAIL", "NOT TESTED")}
    lines = ["# Batch production acceptance results", "",
             "Run %s against %s as the Appsmith API user (%s). Passed %d, failed %d, not tested %d." % (
                 time.strftime("%Y-%m-%d %H:%M"), ERP, CFG["api_user"]["email"], n["PASS"], n["FAIL"], n["NOT TESTED"]), "",
             "| ID | Criterion | Result | Evidence |", "|---|---|---|---|"]
    for r in RESULTS:
        lines.append("| %s | %s | %s | %s |" % (r["id"], r["criterion"], r["result"], r["evidence"].replace("|", "/").replace("\n", " ")))
    (MES / "state" / "batch-test-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nPASS %(PASS)d  FAIL %(FAIL)d  NOT TESTED %(NOT TESTED)d" % n)


codes = {}
for dt in ("Batch", "Serial No", "Maintenance Request", "Issue", "Asset"):
    codes[dt] = rest("/api/resource/%s?limit_page_length=1" % (dt,))[0]
check("P1", "API user can read Batch", codes["Batch"] == 200, "GET /api/resource/Batch -> %s" % codes["Batch"])
check("P2", "API user cannot read Maintenance Request, Issue or Asset",
      all(codes[d] == 403 for d in ("Maintenance Request", "Issue", "Asset")), {d: codes[d] for d in ("Maintenance Request", "Issue", "Asset")})

fx = bench("""
company, stores = %r, %r
roles = frappe.get_roles(%r)
units = {}
barcodes = {}
for t in frappe.get_all('Tracked Item', filters={'current_status': 'In Stock', 'current_warehouse': stores}, fields=['name', 'item_code', 'barcode'], order_by='name asc'):
    units.setdefault(t.item_code, []).append(t.name)
    barcodes[t.name] = t.barcode
used = set(frappe.get_all('MES Material Scan', filters={'unit_key': ['is', 'set']}, pluck='unit_id'))
units = {k: [u for u in v if u not in used] for k, v in units.items()}
product = None
for it in frappe.get_all('Item', filters={'has_batch_no': 1, 'disabled': 0}, pluck='name', order_by='name asc'):
    bom = frappe.db.get_value('BOM', {'item': it, 'is_active': 1, 'is_default': 1, 'docstatus': 1, 'company': company}, 'name')
    if bom:
        product = {'item': it, 'bom': bom, 'rows': frappe.get_all('BOM Item', filters={'parent': bom}, fields=['item_code', 'qty'])}
        break
plan = None
if product:
    q = 2
    comp = []
    ok = True
    for r in product['rows']:
        need = r.qty * q
        info = frappe.db.get_value('Item', r.item_code, ['has_batch_no', 'has_serial_no'], as_dict=True)
        if info.has_batch_no:
            kind = 'batch'
        elif r.item_code in units:
            kind = 'unit'
        else:
            kind = 'qty'
        row = {'item_code': r.item_code, 'need': need, 'kind': kind}
        row['have'] = frappe.db.get_value('Bin', {'item_code': r.item_code, 'warehouse': stores}, 'actual_qty') or 0
        if kind == 'unit':
            row['units'] = units[r.item_code][:int(need)]
            ok = ok and len(row['units']) >= need
        comp.append(row)
    target = ([c for c in comp if c['kind'] == 'batch'] or [None])[0]
    short = ['%%s: %%s in stock, %%s needed' %% (c['item_code'], c['have'], c['need']) for c in comp if c is not target and c['have'] < c['need']]
    if short:
        plan = {'short': short}
    elif ok and target:
        wo = frappe.new_doc('Work Order')
        wo.update({'production_item': product['item'], 'bom_no': product['bom'], 'qty': q, 'company': company,
                   'source_warehouse': stores, 'wip_warehouse': %r, 'fg_warehouse': %r,
                   'planned_start_date': frappe.utils.now_datetime(), 'use_multi_level_bom': 0})
        wo.get_items_and_operations_from_bom()
        wo.insert()
        wo.submit()
        jcs = frappe.get_all('Job Card', filters={'work_order': wo.name, 'docstatus': 0}, fields=['name', 'sequence_id', 'operation', 'workstation'], order_by='sequence_id asc, creation asc')
        exp = frappe.get_doc({'doctype': 'Batch', 'batch_id': target['item_code'] + '-EXP-' + %r, 'item': target['item_code'],
                              'expiry_date': frappe.utils.add_days(frappe.utils.nowdate(), -1)}).insert()
        req = {r.item_code for r in product['rows']}
        foreign = frappe.db.sql("select name, item from `tabBatch` where item not in %%s and disabled=0 limit 1", (tuple(req),), as_dict=True)
        plan = {'wo': wo.name, 'jcs': jcs, 'comp': comp, 'target': target['item_code'], 'expired': exp.name,
                'foreign': foreign[0] if foreign else None}
        frappe.db.commit()
top_serial = frappe.db.sql("select max(cast(substring(serial_no, 4) as unsigned)) from `tabTracked Item` where serial_no regexp '^SN-[0-9]{8}$'")[0][0]
print('@@' + json.dumps({'roles': roles, 'product': product, 'barcodes': {u: barcodes[u] for c in (plan or {}).get('comp', []) for u in c.get('units', [])},
                         'top_serial': top_serial, 'plan': plan, 'units': {k: len(v) for k, v in units.items()},
                         'tracked_total': frappe.db.count('Tracked Item')}, default=str))
""" % (COMPANY, WH["stores"], CFG["api_user"]["email"], WH["wip"], WH["fg"], STAMP))
print("fixtures:", json.dumps({k: fx[k] for k in ("product", "plan")}, default=str)[:600], flush=True)

api_roles = fx["roles"]
before = fx["tracked_total"]
st = {}
some_item = (fx["product"] or {}).get("item") or "x"
st["bulk_transfer_tracked_items"] = call(TRACKED + "bulk_transfer_tracked_items", rows=json.dumps([{"item_code": some_item, "qty": 1}]))[0]
st["bulk_create_tracked_items"] = call(TRACKED + "bulk_create_tracked_items", item_code=some_item, qty=1)[0]
st["bulk_transfer_all_stock_items"] = call(TRACKED + "bulk_transfer_all_stock_items", warehouse=WH["stores"])[0]
after = bench("print('@@' + json.dumps(frappe.db.count('Tracked Item')))")
check("T1", "A Manufacturing User (no Stock or System Manager role) cannot create tracked units in bulk",
      all(v == 403 for v in st.values()) and after == before and not {"Stock Manager", "System Manager"} & set(api_roles),
      "API user roles %s; HTTP %s; Tracked Items %s -> %s" % (sorted(r for r in api_roles if r not in ("All", "Guest", "Desk User")), st, before, after))

plan = fx["plan"]
if plan and plan.get("short"):
    for cid in ("B1", "B2", "B3", "S1", "S2", "S3", "S4", "S5", "S6", "W1", "W2", "W3", "L1"):
        skip(cid, "Batch flow", "not enough ERPNext stock in %s for a qty-2 order: %s" % (WH["stores"], plan["short"]))
    finish_report()
    raise SystemExit(0)
if not plan:
    why = "no batch-tracked product with a default BOM and enough free tracked units" if fx["product"] else "no batch-tracked product with a default BOM"
    for cid in ("B1", "B2", "B3", "S1", "S2", "S3", "S4", "S5", "S6", "W1", "W2", "W3", "L1"):
        skip(cid, "Batch flow", why)
    finish_report()
    raise SystemExit(0)

T = plan["target"]
JC = plan["jcs"][0]["name"]
ACC = "%s-ACC-%s" % (T, STAMP)
tracked_t = bench("print('@@' + json.dumps(frappe.db.count('Tracked Item', {'item_code': %r})))" % (T,))
s1, r1 = call("mes_batch_create", item_code=T, qty=75, batch_id=ACC)
q1 = batch_qty(ACC)
tracked_t2 = bench("print('@@' + json.dumps(frappe.db.count('Tracked Item', {'item_code': %r})))" % (T,))
check("B1", "One batch ID is created for 75 units with one stock receipt",
      s1 == 200 and r1["status"] == "created" and r1["stock_entry"] and q1 == 75, "%s %s; batch_qty %s" % (s1, r1, q1))
check("B2", "Batch receipts do not create per-unit Tracked Items (item_tracking skips has_batch_no items)",
      tracked_t2 == tracked_t, "Tracked Items for %s: %s -> %s" % (T, tracked_t, tracked_t2))
s2, r2 = call("mes_batch_create", item_code=T, qty=75, batch_id=ACC)
q2 = batch_qty(ACC)
check("B3", "A second create with the same batch ID is idempotent (no second receipt)",
      s2 == 200 and r2["status"] == "exists" and not r2["stock_entry"] and q2 == 75, "%s %s; batch_qty %s" % (s2, r2, q2))

NUM = re.compile(r"^[0-9]{8}$")
sN, rN = call("mes_batch_create", item_code=T, qty=0)
check("N1", "A new batch gets an 8-digit number from the sequence it shares with unit serials",
      sN == 200 and bool(NUM.match(rN["batch_id"])) and int(rN["batch_id"]) > int(fx["top_serial"] or 0),
      "%s %s; highest unit serial %s" % (sN, rN.get("batch_id") if sN == 200 else rN, fx["top_serial"]))
auto = bench("""
it = %r
if not frappe.db.get_value('Item', it, 'create_new_batch'):
    print('@@' + json.dumps(None))
else:
    se = frappe.new_doc('Stock Entry')
    se.update({'company': %r, 'stock_entry_type': 'Material Receipt', 'purpose': 'Material Receipt', 'remarks': 'MES test: ERPNext-named batch'})
    se.append('items', {'item_code': it, 'qty': 1, 't_warehouse': %r, 'basic_rate': frappe.db.get_value('Item', it, 'valuation_rate') or 0, 'allow_zero_valuation_rate': 1})
    se.insert()
    se.submit()
    frappe.db.commit()
    se.reload()
    row = se.items[0]
    b = row.batch_no or frappe.db.get_value('Serial and Batch Entry', {'parent': row.serial_and_batch_bundle}, 'batch_no')
    print('@@' + json.dumps([se.name, b]))
""" % (T, COMPANY, WH["stores"]))
if auto:
    check("N5", "A batch that ERPNext names itself on a receipt gets the next shared 8-digit number (item_tracking hook)",
          bool(NUM.match(auto[1] or "")) and int(auto[1]) > int(rN["batch_id"] if sN == 200 else 0), "%s created batch %s" % (auto[0], auto[1]))
else:
    skip("N5", "ERPNext-named batch gets a shared number", "%s does not auto-create batches" % (T,))
some_unit = next(iter(fx["barcodes"]), None)
if some_unit:
    sL, rL = call("item_tracking.item_tracking.api.lookup_tracked_item", search_value=fx["barcodes"][some_unit])
    check("N2", "The desk scanner resolves a unit's 8-digit barcode to its tracked unit",
          sL == 200 and NUM.match(fx["barcodes"][some_unit] or "") and rL.get("tracking_id") == some_unit,
          "%s -> %s" % (fx["barcodes"][some_unit], rL.get("tracking_id") if sL == 200 else rL))
else:
    skip("N2", "Desk scanner resolves an 8-digit unit barcode", "no unit components on the test order")

rej = []
r = scan(JC, T, qty=1)
rej.append(r.get("scan"))
check("S1", "Scanning the item code of a batch-tracked material is refused", not r["ok"] and "tracked by batch" in (r["reason"] or ""), r["reason"])
if plan["foreign"]:
    r = scan(JC, plan["foreign"]["name"], qty=1)
    rej.append(r.get("scan"))
    check("S2", "A batch of an item that is not on the work order is rejected", not r["ok"] and "Incorrect item" in (r["reason"] or ""),
          "%s (%s): %s" % (plan["foreign"]["name"], plan["foreign"]["item"], r["reason"]))
else:
    skip("S2", "Wrong-item batch is rejected", "no batch of an item outside the BOM exists")
r = scan(JC, plan["expired"], qty=1)
rej.append(r.get("scan"))
check("S3", "An expired batch is rejected", not r["ok"] and "expired" in (r["reason"] or ""), "%s: %s" % (plan["expired"], r["reason"]))
SMALL = "%s-LOW-%s" % (T, STAMP)
call("mes_batch_create", item_code=T, qty=1, batch_id=SMALL)
r = scan(JC, SMALL, qty=2)
rej.append(r.get("scan"))
check("S4", "A batch with less free quantity than entered is rejected", not r["ok"] and "Not enough in batch" in (r["reason"] or ""),
      "%s (qty 1), scanned 2: %s" % (SMALL, r["reason"]))
names = [n for n in rej if n]
s, logged = rest("/api/resource/MES Material Scan?fields=%s&filters=%s&limit_page_length=20" % (
    json.dumps(["name", "result", "reason"]), json.dumps([["name", "in", names]])))
logged = logged.get("data", []) if s == 200 else []
check("S5", "Every rejected scan is stored in the MES scan log with its reason",
      len(logged) == len(names) and all(x["result"] == "Invalid" and x["reason"] for x in logged), [(x["name"], x["reason"][:50]) for x in logged])

r = scan(JC, ACC, qty_mode="remaining")
need_t = [c for c in plan["comp"] if c["item_code"] == T][0]["need"]
check("S6", "The batch label is scanned once and the remaining requirement is taken from it",
      r["ok"] and abs((r.get("qty") or 0) - need_t) < 1e-9 and r.get("batch_no") == ACC, (r.get("result"), r.get("qty"), r.get("reason")))

problems = []
digit_scans = []
for c in plan["comp"]:
    if c["item_code"] == T:
        continue
    if c["kind"] == "unit":
        for u in c["units"]:
            code = fx["barcodes"].get(u) or u
            x = scan(JC, code)
            digit_scans.append((code, u, x.get("unit_id"), x["ok"]))
            if not x["ok"]:
                problems.append((u, x["reason"]))
    elif c["kind"] == "batch":
        pick = bench("""
        rows = frappe.get_all('Batch', filters={'item': %r, 'disabled': 0}, fields=['name', 'batch_qty', 'expiry_date'], order_by='batch_qty desc')
        rows = [r for r in rows if (r.batch_qty or 0) >= %r and not (r.expiry_date and str(r.expiry_date) < frappe.utils.nowdate())]
        print('@@' + json.dumps(rows[0].name if rows else None))
        """ % (c["item_code"], c["need"]))
        if not pick:
            problems.append((c["item_code"], "no batch with %s free" % c["need"]))
            continue
        x = scan(JC, pick, qty_mode="remaining")
        if not x["ok"]:
            problems.append((pick, x["reason"]))
    else:
        x = scan(JC, c["item_code"], qty_mode="remaining")
        if not x["ok"]:
            problems.append((c["item_code"], x["reason"]))
if digit_scans:
    check("N3", "Unit labels scanned by their 8-digit barcode are verified as the right tracked unit in the MES",
          all(NUM.match(code) and got == u and ok for code, u, got, ok in digit_scans), digit_scans[:6])
s, j = call("mes_sf_job", operator=OP, job_card=JC)
unverified = [m["item_code"] for m in j["materials"] if m["status"] != "Verified"] if s == 200 else ["HTTP %s" % s]
if problems or unverified:
    for cid in ("W1", "W2", "W3"):
        skip(cid, "Issue and finish with batches", "materials of %s could not all be verified: %s %s" % (plan["wo"], problems[:4], unverified))
else:
    s, r = call("mes_work_order_action", work_order=plan["wo"], action="issue", qty=2)
    rows = []
    if s == 200:
        se = rest("/api/resource/Stock Entry/" + r["stock_entry"])[1]["data"]
        rows = [(d["item_code"], d.get("batch_no"), d["qty"]) for d in se["items"] if d["item_code"] == T]
    check("W1", "Issuing materials moves the scanned batch (ERPNext Material Transfer for Manufacture)",
          s == 200 and rows == [(T, ACC, need_t)], "%s %s; %s rows %s" % (s, r if s != 200 else r["stock_entry"], T, rows))
    backdated = []
    for i, jc in enumerate(plan["jcs"]):
        a = call("mes_sf_progress", operator=OP, job_card=jc["name"], action="start")
        time.sleep(1.5)
        b = call("mes_sf_progress", operator=OP, job_card=jc["name"], action="complete", qty=2) if a[0] == 200 else a
        if b[0] == 200 and b[1].get("ok"):
            continue
        if "OverlapError" not in str(b[1]):
            problems.append((jc["name"], b[1]))
            continue
        bench("""
        jc = frappe.get_doc('Job Card', %r)
        jc.time_logs = []
        jc.append('time_logs', {'from_time': '2026-06-01 09:%02d:00', 'to_time': '2026-06-01 09:%02d:00', 'time_in_mins': 9, 'completed_qty': jc.for_quantity})
        jc.save()
        jc.submit()
        frappe.db.commit()
        print('@@' + json.dumps(jc.status))
        """ % (jc["name"], i * 10, i * 10 + 9))
        backdated.append(jc["name"])
    s, r = call("mes_work_order_action", work_order=plan["wo"], action="finish", qty=2)
    left = batch_qty(ACC)
    check("W2", "Finishing consumes the batch quantity through ERPNext (75 received, %s used)" % (need_t,),
          s == 200 and left == 75 - need_t, "%s %s; job cards %s%s; %s batch_qty now %s" % (s, r if s != 200 else r["stock_entry"], problems or "completed",
          " (%s completed in the bench with a back-dated log: the workstation is booked by the planner)" % (backdated,) if backdated else "", ACC, left))
    if s == 200 and r.get("output_batch"):
        gs, g = rest("/api/resource/MES Batch Genealogy/" + r["output_batch"])
        ins = [(x["item_code"], x["batch_no"], x["qty"]) for x in g["data"]["inputs"]] if gs == 200 else g
        check("W3", "The finished-goods batch is created and records the input batches it used",
              gs == 200 and batch_qty(r["output_batch"]) == 2 and (T, ACC, need_t) in ins,
              "output %s qty %s; inputs %s" % (r["output_batch"], batch_qty(r["output_batch"]), ins))
        OUT = r["output_batch"]
        check("N4", "The finished-goods output batch is numbered from the shared sequence", bool(NUM.match(OUT)), OUT)
    else:
        check("W3", "The finished-goods batch is created with its genealogy", False, r)
        OUT = None

s, r = call("mes_batch_labels", batch_ids=json.dumps([b for b in (ACC, SMALL, locals().get("OUT")) if b]))
if s == 200:
    (MES / "state" / "batch-labels").mkdir(parents=True, exist_ok=True)
    page = "<!doctype html><meta charset=utf-8><title>Batch labels</title><base href=\"%s/\">%s" % (ERP, r["html"])
    (MES / "state" / "batch-labels" / "acceptance-labels.html").write_text(page, encoding="utf-8")
check("L1", "One call prints one CODE128 label per batch (Barcode Printing document + label images)",
      s == 200 and r["count"] == len(r["labels"]) >= 2 and all(str(x["image"]).startswith("/files/") for x in r["labels"]),
      "%s %s" % (s, {"barcode_printing": r.get("barcode_printing"), "labels": [(x["batch_no"], x["qty"], x["date"]) for x in r["labels"]]} if s == 200 else r))
finish_report()
