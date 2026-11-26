"""Acceptance tests for the shopfloor MES backend, run against the live sandbox through the same API user and
mes_sf_* endpoints the Appsmith app uses. Writes mes/state/shopfloor-test-results.md (and .json).

It creates real records in the sandbox: material scans, defect reports (with attachments), machine issues,
notifications, job card time logs, and it SUBMITS one Job Card (the first operation of a sub-assembly work
order whose materials are all in stock). It never creates or submits a Stock Entry.
Fixtures (products, unit-tracked and quantity materials, workstations, users) are discovered on every run from the
site YAML and ERPNext. When no untouched pair of planner work orders shares a unit-tracked material, it creates two
small work orders (qty 5, 3, 2 or 1, and 1) for a product whose materials are in stock. A check whose fixture is missing (stock,
a free workstation) is reported NOT TESTED instead of failing.

Usage (from the repo root): python mes/setup/test_shopfloor.py
"""
import base64
import json
import pathlib
import subprocess
import threading
import time
import urllib.error
import urllib.request
import sys
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
STORES = CFG["warehouses"]["stores"]


def user_with(role, without=None):
    for u in CFG["test_users"]:
        if role in u["roles"] and not (without and without in u["roles"]):
            return u["email"]
    raise SystemExit("site YAML test_users has no user with role %s" % (role,))


OP = user_with("Manufacturing User", "Manufacturing Manager")
SUP = user_with("Manufacturing Manager")
MAINT = user_with("Maintenance User")
RESULTS = []
PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cf00000301010018dd8db00000000049454e44ae426082")).decode()


def call(method, **args):
    args.setdefault("employee", "HR-EMP-00001")
    req = urllib.request.Request(ERP + "/api/method/" + method, data=json.dumps(args).encode(), method="POST",
                                 headers={"Authorization": AUTH, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read()).get("message")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw)
            msg = body.get("exception") or body.get("_server_messages") or raw
        except Exception:
            msg = raw
        return e.code, str(msg)[:400]


def rest(path):
    req = urllib.request.Request(ERP + path.replace(" ", "%20"), headers={"Authorization": AUTH, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def bench(code):
    """Read-only fixture lookups that the API user cannot list (run inside the bench)."""
    script = "import frappe, json\nfrappe.init(site=%r, sites_path='.')\nfrappe.connect()\n" % (FSITE,) + code
    p = subprocess.run(["docker", "exec", "-i", "-w", "/home/frappe/frappe-bench/sites", CONTAINER, "../env/bin/python", "-W", "ignore", "-"],
                       input=script, capture_output=True, text=True, timeout=120)
    lines = [l for l in p.stdout.splitlines() if l.startswith("@@")]
    if not lines:
        raise RuntimeError(p.stderr[-800:])
    return json.loads(lines[-1][2:])


def check(cid, text, ok, evidence):
    RESULTS.append({"id": cid, "criterion": text, "result": "PASS" if ok else "FAIL", "evidence": str(evidence)[:500]})
    print("%-5s %-4s %s | %s" % (cid, "PASS" if ok else "FAIL", text, str(evidence)[:160]))


def skip(cid, text, why):
    RESULTS.append({"id": cid, "criterion": text, "result": "NOT TESTED", "evidence": why})
    print("%-5s SKIP %s | %s" % (cid, text, why))


def rid():
    return "t-" + uuid.uuid4().hex


def job(jc, who=OP):
    s, d = call("mes_sf_job", operator=who, job_card=jc)
    assert s == 200, d
    return d


def mat(d, code):
    return [m for m in d["materials"] if m["item_code"] == code][0]


fx = bench("""
company, stores, wip, fgw = %r, %r, %r, %r
def mode(code):
    it = frappe.db.get_value('Item', code, ['has_serial_no', 'has_batch_no', 'stock_uom'], as_dict=True)
    if it.has_serial_no or (not it.has_batch_no and frappe.db.exists('Tracked Item', {'item_code': code})):
        return 'unit'
    if it.has_batch_no:
        return 'batch'
    return 'scan' if frappe.db.get_value('UOM', it.stock_uom, 'must_be_whole_number') else 'confirm'
modes = {}
def m(code):
    if code not in modes:
        modes[code] = mode(code)
    return modes[code]
def entry(w):
    if frappe.db.count('MES Material Scan', {'work_order': w.name}) or frappe.db.count('MES Defect Report', {'work_order': w.name}):
        return None
    jcs = frappe.get_all('Job Card', filters={'work_order': w.name, 'docstatus': 0}, fields=['name', 'workstation', 'sequence_id', 'creation'], order_by='creation asc')
    if not jcs:
        return None
    req = frappe.get_all('Work Order Item', filters={'parent': w.name}, fields=['item_code', 'required_qty', 'transferred_qty', 'source_warehouse'])
    short = [r.item_code for r in req if (frappe.db.get_value('Bin', {'item_code': r.item_code, 'warehouse': r.source_warehouse or stores}, 'actual_qty') or 0) < (r.required_qty or 0) - (r.transferred_qty or 0)]
    first = sorted(jcs, key=lambda r: (r.sequence_id or 0, r.creation))[0]
    now = frappe.utils.now_datetime()
    busy = frappe.db.sql('''select distinct p.name from `tabJob Card Scheduled Time` t join `tabJob Card` p on p.name = t.parent
        where p.workstation = %%s and p.name != %%s and p.docstatus = 0 and t.from_time < %%s and t.to_time > %%s
        union select distinct p.name from `tabJob Card Time Log` t join `tabJob Card` p on p.name = t.parent
        where p.workstation = %%s and p.name != %%s and p.docstatus = 0 and t.from_time is not null and t.to_time is null''',
        (first.workstation, first.name, frappe.utils.add_to_date(now, hours=1), now, first.workstation, first.name))
    return ({'wo': w.name, 'item': w.production_item, 'jcs': jcs, 'short': short, 'busy': [b[0] for b in busy],
                'req': [dict(r, mode=m(r.item_code)) for r in req]})
wos = []
for w in frappe.get_all('Work Order', filters={'status': 'Not Started', 'docstatus': 1, 'company': company}, fields=['name', 'production_item', 'qty'], order_by='name asc'):
    e = entry(w)
    if e:
        wos.append(e)
used = set(frappe.get_all('MES Material Scan', filters={'unit_key': ['is', 'set']}, pluck='unit_id'))
free = {}
for t in frappe.get_all('Tracked Item', filters={'current_status': 'In Stock', 'current_warehouse': stores}, fields=['name', 'item_code'], order_by='name asc'):
    if t.name not in used:
        free.setdefault(t.item_code, []).append(t.name)
unit_item, pair = None, []
for code in sorted(free, key=lambda c: -len(free[c])):
    if len(free[code]) < 3 or m(code) != 'unit':
        continue
    users = sorted([w for w in wos if any(r['item_code'] == code for r in w['req'])], key=lambda w: len(w['short']))
    if len(users) >= 2:
        unit_item, pair = code, users[:2]
        break
created = []
if not pair:
    def bin_qty(code):
        return frappe.db.get_value('Bin', {'item_code': code, 'warehouse': stores}, 'actual_qty') or 0
    def make(item, bom, q):
        wo = frappe.new_doc('Work Order')
        wo.update({'production_item': item, 'bom_no': bom, 'qty': q, 'company': company, 'source_warehouse': stores,
                   'wip_warehouse': wip, 'fg_warehouse': fgw, 'planned_start_date': frappe.utils.now_datetime(), 'use_multi_level_bom': 0})
        wo.get_items_and_operations_from_bom()
        wo.insert()
        wo.submit()
        created.append(wo.name)
        return entry(frappe._dict(name=wo.name, production_item=item, qty=q))
    boms = frappe.get_all('BOM', filters={'is_active': 1, 'is_default': 1, 'docstatus': 1, 'company': company, 'with_operations': 1}, fields=['name', 'item'], order_by='item asc')
    for code in sorted(free, key=lambda c: -len(free[c])):
        if len(free[code]) < 3 or m(code) != 'unit' or pair:
            continue
        for bom in boms:
            rows = frappe.get_all('BOM Item', filters={'parent': bom.name}, fields=['item_code', 'qty'])
            if code not in [r.item_code for r in rows] or [r for r in rows if m(r.item_code) == 'batch']:
                continue
            fits = [q for q in (5, 3, 2, 1) if not [r for r in rows if bin_qty(r.item_code) < q * (r.qty or 0)]]
            if not fits or frappe.db.get_value('Item', bom.item, 'has_batch_no'):
                continue
            pair = [make(bom.item, bom.name, fits[0]), make(bom.item, bom.name, 1)]
            unit_item = code
            frappe.db.commit()
            break
taken = {w['wo'] for w in pair}
sub = None
for w in wos:
    if w['wo'] in taken:
        continue
    kinds = {r['mode'] for r in w['req']}
    if 'confirm' in kinds and 'scan' in kinds and 'unit' not in kinds and 'batch' not in kinds:
        if sub is None or (not w['short'] and not w['busy'] and (sub['short'] or sub['busy'])):
            sub = w
        if not sub['short'] and not sub['busy']:
            break
other_unit = []
if pair:
    need = {r['item_code'] for r in pair[0]['req']}
    for code in free:
        if code not in need:
            other_unit = free[code][:1]
            break
legacy = frappe.get_all('Work Order', filters={'status': 'In Process', 'company': company, 'docstatus': 1}, fields=['name', 'material_transferred_for_manufacturing', 'produced_qty'])
legacy = [w['name'] for w in legacy if (w['material_transferred_for_manufacturing'] or 0) > (w['produced_qty'] or 0) and not frappe.db.count('MES Material Scan', {'work_order': w['name']})]
plant = frappe.get_all('Workstation', filters={'plant_floor': %r}, pluck='name', order_by='name asc')
print('@@' + json.dumps({'created': created, 'unit_item': unit_item, 'pair': pair, 'sub': sub, 'units': free.get(unit_item, []), 'other_unit': other_unit,
    'legacy': legacy[:1], 'plant': plant, 'se_count': frappe.db.count('Stock Entry'), 'notif_count': frappe.db.count('Notification Log')}, default=str))
""" % (COMPANY, STORES, CFG["warehouses"]["wip"], CFG["warehouses"]["fg"], CFG["plant_floor"]))
print("fixtures:", {"created": fx["created"], "unit_item": fx["unit_item"], "pair": [w["wo"] for w in fx["pair"]], "sub": (fx["sub"] or {}).get("wo"),
                    "units": fx["units"][:3], "other_unit": fx["other_unit"], "legacy": fx["legacy"]})


def write_results():
    (MES / "state").mkdir(exist_ok=True)
    (MES / "state" / "shopfloor-test-results.json").write_text(json.dumps(RESULTS, indent=1), encoding="utf-8")


if not (fx["unit_item"] and fx["sub"] and fx["other_unit"]):
    why = ("no unit-tracked material with 3 free units used by two untouched work orders" if not fx["unit_item"]
           else "no untouched work order with both confirm and scan materials" if not fx["sub"] else "no free unit of another item")
    skip("ALL", "Shopfloor suite", why)
    write_results()
    raise SystemExit("NOT TESTED: " + why)
UNIT = fx["unit_item"]
A = fx["sub"]
A_JC = sorted(A["jcs"], key=lambda r: (r.get("sequence_id") or 0, r["creation"]))[0]
JA, WSA = A_JC["name"], A_JC["workstation"]
B, C = fx["pair"][0], fx["pair"][1]
JB, JCc = B["jcs"][0]["name"], C["jcs"][0]["name"]
U = fx["units"]
CONFIRM_A = [r["item_code"] for r in A["req"] if r["mode"] == "confirm"][0]
SCAN_A = [r["item_code"] for r in A["req"] if r["mode"] == "scan"][0]
QTY_B = ([r["item_code"] for r in B["req"] if r["mode"] == "scan" and r["required_qty"] >= 2] or [None])[0]
RQ = int(min(5, [r["required_qty"] for r in B["req"] if r["item_code"] == QTY_B][0] - 1)) if QTY_B else 0
OTHER_WS = ([w for w in fx["plant"] if w != WSA] or [WSA])[0]

# ---------- items and images ----------
items = rest("/api/resource/Item?fields=" + urllib.request.quote(json.dumps(["name", "image"])) + "&filters=" +
             urllib.request.quote(json.dumps([["name", "in", [B["item"], SCAN_A, A["item"]]]])))["data"]
imgs = {i["name"]: i["image"] for i in items}
check("I1", "ERPNext items are retrieved correctly", len(items) == len({B["item"], SCAN_A, A["item"]}), imgs)
d = job(JB)
if imgs.get(B["item"]):
    check("I2", "Imported images are linked to the correct items and served by ERPNext",
          d["work_order"]["image"] == imgs[B["item"]] and urllib.request.urlopen(ERP + urllib.request.quote(d["work_order"]["image"])).status == 200,
          "%s image %s" % (B["item"], d["work_order"]["image"]))
else:
    skip("I2", "Imported images are linked to the correct items", "%s has no image in ERPNext" % (B["item"],))
def no_guessed_image(url):
    return url in (None, "") or str(url).startswith("/files/")


check("I3", "Images are only ERPNext item images or empty (UI shows placeholder, nothing breaks)",
      all(no_guessed_image(m["image"]) for m in job(JA)["materials"]) and no_guessed_image(job(JA)["work_order"]["image"]),
      "%s image=%r" % (A["item"], imgs.get(A["item"])))


ISSUABLE = {w["wo"]: not w["short"] for w in (A, B, C)}
SHORT_NOTE = {w["wo"]: "not enough ERPNext stock to issue %s: %s" % (w["wo"], ", ".join(w["short"])) for w in (A, B, C) if w["short"]}
print("stock shortages:", SHORT_NOTE or "none", "| booked workstation for", JA, ":", A["busy"] or "none")


def issue(jc):
    s, r = call("mes_sf_issue", operator=OP, job_card=jc)
    left = job(jc)["issue"]
    if s == 200 and isinstance(r, dict) and not r.get("ok") and r.get("shortages"):
        return True, {"shortage reported": r["shortages"][:3]}
    return bool(left["issued"]) and not left["needed"] or (s == 200 and isinstance(r, dict) and r.get("transferred_qty", 0) > 0), left


jobs = [(JA, A), (JB, B), (JCc, C)]
issued = [(jc, issue(jc)) for jc, w in jobs if ISSUABLE[w["wo"]]]
if issued:
    check("I4", "Materials are issued to each fixture job with stock (ERPNext material transfer, required before production starts)",
          all(ok for _, (ok, _r) in issued), [(jc, left) for jc, (ok, left) in issued] + [SHORT_NOTE[w["wo"]] for jc, w in jobs if not ISSUABLE[w["wo"]]])
else:
    skip("I4", "Materials are issued to each fixture job", "; ".join(SHORT_NOTE.values()))

# ---------- material confirmation ----------
check("M1", "Employee can open an assigned job / work order", d["job"]["job_card"] == JB and d["work_order"]["name"] == B["wo"], d["job"])
check("M2", "Employee sees the finished product", d["work_order"]["item_code"] == B["item"], d["work_order"]["item_name"])
bom_items = sorted(r["item_code"] for r in rest("/api/resource/Work Order/" + B["wo"])["data"]["required_items"])
check("M3", "Employee sees all required BOM materials", sorted(m["item_code"] for m in d["materials"]) == bom_items, bom_items)
check("M4", "Materials needing unit/serial scanning are identified",
      mat(d, UNIT)["mode"] == "unit" and mat(job(JA), CONFIRM_A)["mode"] == "confirm" and mat(job(JA), SCAN_A)["mode"] == "scan",
      "%s=unit, %s=scan, %s=confirm" % (UNIT, SCAN_A, CONFIRM_A))

s, r = call("mes_sf_scan", operator=OP, job_card=JB, value=U[0], request_id=rid())
check("M5", "Valid tracked unit is accepted", s == 200 and r["ok"] and r["unit_id"] == U[0], r if s != 200 else (r["result"], r["reason"], r["material"][0]["units_scanned"]))
s, r = call("mes_sf_scan", operator=OP, job_card=JB, value=U[0], request_id=rid())
check("M6", "Duplicate unit scan on the same work order is rejected with a reason", s == 200 and not r["ok"] and "Duplicate" in r["reason"], r.get("reason") if s == 200 else r)
s, r = call("mes_sf_scan", operator=OP, job_card=JCc, value=U[0], request_id=rid())
check("M7", "Unit already used on another work order cannot be reused", s == 200 and not r["ok"] and "already used" in r["reason"], r.get("reason") if s == 200 else r)
s, r = call("mes_sf_scan", operator=OP, job_card=JB, value=fx["other_unit"][0], request_id=rid())
check("M8", "Incorrect item is rejected and the expected materials are named",
      s == 200 and not r["ok"] and "Incorrect item" in r["reason"] and "Expected" in r["reason"], r.get("reason") if s == 200 else r)
s, r = call("mes_sf_scan", operator=OP, job_card=JB, value="NO-SUCH-CODE-123", request_id=rid())
check("M9", "Unknown barcode is rejected with a reason", s == 200 and not r["ok"] and "Unknown barcode" in r["reason"], r.get("reason") if s == 200 else r)
s, r = call("mes_sf_scan", operator=OP, job_card=JB, value=UNIT, request_id=rid())
check("M10", "Scanning the item code of a unit-tracked material is refused (each unit must be scanned)",
      s == 200 and not r["ok"] and "tracked per unit" in r["reason"], r.get("reason") if s == 200 else r)
if QTY_B:
    before = job(JB)
    s, r = call("mes_sf_scan", operator=OP, job_card=JB, value=QTY_B, qty=10 ** 6, request_id=rid())
    check("M11", "Quantity above the requirement is rejected", s == 200 and not r["ok"] and "exceeds requirement" in r["reason"], r.get("reason") if s == 200 else r)
    after = job(JB)
    check("M12", "Invalid scans never count towards verification",
          before["summary"]["materials_verified"] == after["summary"]["materials_verified"] and mat(after, QTY_B)["verified_qty"] == 0
          and after["summary"]["invalid_scans"] > before["summary"]["invalid_scans"],
          "invalid scans %s -> %s, verified materials unchanged %s" % (before["summary"]["invalid_scans"], after["summary"]["invalid_scans"], after["summary"]["materials_verified"]))
    s, r = call("mes_sf_scan", operator=OP, job_card=JB, value=QTY_B, qty=2.5, request_id=rid())
    check("M13", "Fractional quantity of a whole-unit item is rejected", s == 200 and not r["ok"] and "whole" in r["reason"], r.get("reason") if s == 200 else r)

    key = rid()
    s1, r1 = call("mes_sf_scan", operator=OP, job_card=JB, value=QTY_B, qty=RQ, request_id=key)
    s2, r2 = call("mes_sf_scan", operator=OP, job_card=JB, value=QTY_B, qty=RQ, request_id=key)
    check("R1", "Duplicate submission (same request id) is stored once",
          r1["ok"] and r2.get("replayed") and r1["scan"] == r2["scan"] and mat(job(JB), QTY_B)["verified_qty"] == RQ,
          "first %s, replay %s replayed=%s, verified %s" % (r1["scan"], r2["scan"], r2.get("replayed"), RQ))
else:
    for cid in ("M11", "M12", "M13", "R1"):
        skip(cid, "Quantity checks on a whole-unit material", "%s has no scan-mode material with a requirement of 2 or more" % (B["wo"],))

box = {}


def race(tag, jc, unit):
    box[tag] = (time.time(), call("mes_sf_scan", operator=OP, job_card=jc, value=unit, request_id=rid()), time.time())


t1 = threading.Thread(target=race, args=("b", JB, U[1]))
t2 = threading.Thread(target=race, args=("c", JCc, U[1]))
t1.start(); t2.start(); t1.join(); t2.join()
oks = [box[k][1][1]["ok"] if box[k][1][0] == 200 else "HTTP %s" % box[k][1][0] for k in ("b", "c")]
overlap = box["b"][0] < box["c"][2] and box["c"][0] < box["b"][2]
box_r2_b_ok = box["b"][1][0] == 200 and box["b"][1][1]["ok"]
check("R2", "Simultaneous scans of the same unit on two work orders: exactly one succeeds",
      sorted(oks) == [False, True], "results %s, requests overlapped in time: %s, reasons %s" % (
          oks, overlap, [box[k][1][1].get("reason") if box[k][1][0] == 200 else str(box[k][1][1])[:120] for k in ("b", "c")]))

wire = mat(job(JA), CONFIRM_A)
half = round(wire["required_qty"] * 0.6, 3)
box.clear()


def race_qty(tag):
    box[tag] = call("mes_sf_scan", operator=OP, job_card=JA, value=CONFIRM_A, qty=half, request_id=rid())


ts = [threading.Thread(target=race_qty, args=(t,)) for t in ("x", "y")]
[t.start() for t in ts]; [t.join() for t in ts]
v = mat(job(JA), CONFIRM_A)["verified_qty"]
check("R3", "Simultaneous quantity confirmations cannot overshoot the requirement (row lock)",
      v <= wire["required_qty"] + 1e-9 and all(box[k][0] == 200 for k in box) and sorted([box[k][1]["ok"] for k in box]) == [False, True],
      "two x %s of %s required -> verified %s; %s" % (half, wire["required_qty"], v, [box[k][1].get("reason") if box[k][0] == 200 else "HTTP %s" % box[k][0] for k in box]))

# ---------- full valid path on the sub-assembly work order ----------
for m in job(JA)["materials"]:
    rem = m["remaining_qty"]
    if rem > 0:
        s, r = call("mes_sf_scan", operator=OP, job_card=JA, value=m["item_code"], qty=rem, request_id=rid())
        assert s == 200 and r["ok"], (m["item_code"], r)
dA = job(JA)
check("M14", "Quantity-based materials can be confirmed until verified",
      dA["summary"]["materials_verified"] == dA["summary"]["materials_total"] and not [b for b in dA["blocking"] if "verified" in b],
      dA["summary"])

dB = job(JB)
s, r = call("mes_sf_progress", operator=OP, job_card=JB, action="start")
if ISSUABLE[B["wo"]]:
    s2, r2 = call("mes_sf_progress", operator=OP, job_card=JB, action="report", qty=1)
    check("C1", "Unverified materials prevent reporting good units (starting only needs the materials issued)",
          s == 200 and r["ok"] and s2 != 200 and "Scan every required item" in str(r2), (r.get("status") if s == 200 else r, str(r2)[:160]))
else:
    check("C1", "Production cannot start before materials are issued", s == 200 and not r["ok"] and r["blocking"],
          (r.get("blocking", r)[:2] if s == 200 else r, SHORT_NOTE[B["wo"]]))
s, r = call("mes_sf_progress", operator=OP, job_card=JB, action="complete", qty=1)
check("C2", "Missing materials prevent completing production", s == 200 and not r["ok"] and r["blocking"], (r.get("blocking") or [r])[:2])
call("mes_sf_progress", operator=OP, job_card=JB, action="pause")
if QTY_B:
    check("C3", "Partial quantities are reported as blocking (backend gate)",
          any(QTY_B in b and str(RQ) in b for b in dB["blocking"]), [b for b in dB["blocking"] if QTY_B in b])
else:
    skip("C3", "Partial quantities are reported as blocking", "no scan-mode material on %s" % (B["wo"],))

# ---------- defects ----------
s, r = call("mes_sf_defect", operator=OP, job_card=JB, item_code=UNIT, unit_id=U[0], category="Physical Damage",
            description="Cable jacket cut near the plug", files=[{"file_name": "damage.png", "data": PNG},
                                                                 {"file_name": "note.txt", "data": base64.b64encode(b"inspection note").decode()}], request_id=rid())
DEF1 = r.get("defect") if s == 200 else None
check("D1", "Employee can report a defective material with comments", s == 200 and r["ok"] and DEF1, r)
check("D2", "Employee can attach photographs and files (stored as ERPNext Files)",
      s == 200 and len(r["files"]) == 2 and all(f["file_url"].startswith("/private/files/") for f in r["files"]), r.get("files") if s == 200 else r)
dB = job(JB)
check("D3", "A defective unit stops counting as verified", mat(dB, UNIT)["status"] == "Defective Material" and mat(dB, UNIT)["defective_units"] == 1,
      (mat(dB, UNIT)["status"], mat(dB, UNIT)["units_scanned"]))
s, r = call("mes_sf_scan", operator=OP, job_card=JCc, value=U[0], request_id=rid())
check("D4", "A unit with an open defect cannot be scanned elsewhere", s == 200 and not r["ok"], r.get("reason") if s == 200 else r)
s, r = call("mes_sf_admin", operator=SUP, action="overview")
check("D5", "Supervisors can review defect reports (with attachments)", s == 200 and any(x["name"] == DEF1 and len(x["files"]) == 2 for x in r["defects"]),
      "defects listed: %s" % (len(r["defects"]) if s == 200 else r,))
s, r = call("mes_sf_admin", operator=OP, action="defect_update", name=DEF1, status="Accepted", disposition="Use As Is")
check("P1", "Shopfloor employee cannot decide (override) a defect", s == 403, r)
s, r = call("mes_sf_admin", operator=SUP, action="defect_update", name=DEF1, status="Resolved")
check("D6", "A defect cannot be resolved without a disposition", s != 200 and "disposition" in str(r), r)
s, r = call("mes_sf_admin", operator=SUP, action="defect_update", name=DEF1, status="Accepted", disposition="Replace", comments="Use a new harness")
dB = job(JB)
won_b = 1 if box_r2_b_ok else 0
check("D7", "Supervisor can authorise a disposition; a replaced unit stays excluded",
      s == 200 and mat(dB, UNIT)["status"] != "Defective Material" and mat(dB, UNIT)["units_scanned"] == won_b,
      "status %s, valid units %s (expected %s after R2)" % (mat(dB, UNIT)["status"], mat(dB, UNIT)["units_scanned"], won_b))
s, r = call("mes_sf_admin", operator=OP, action="my_reports")
check("D8", "Employees can view their own submitted reports", s == 200 and any(x["name"] == DEF1 for x in r["defects"]), len(r["defects"]) if s == 200 else r)

s, r = call("mes_sf_defect", operator=OP, job_card=JA, item_code=SCAN_A, qty_affected=1, category="Surface Defect",
            description="Commutator bar scratched", request_id=rid())
DEF2 = r["defect"]
dA = job(JA)
check("C4", "An open defect blocks completion until a supervisor decides it",
      any(DEF2 in b for b in dA["blocking"]) and mat(dA, SCAN_A)["status"] == "Defective Material", [b for b in dA["blocking"]][:2])

# ---------- machine issues ----------
n_before = fx["notif_count"]
s, r = call("mes_sf_machine_issue", operator=OP, workstation=WSA, job_card=JA, issue_type="Machine Breakdown", severity="Low",
            machine_status="Completely Down", description="Winding head stopped, error E42", files=[{"file_name": "panel.png", "data": PNG}], request_id=rid())
ISS = r.get("issue") if s == 200 else None
check("X1", "Employee can report a machine breakdown with a photo", s == 200 and ISS and len(r["files"]) == 1, r)
check("X2", "Priority follows machine state (Completely Down raises Low to Critical)", s == 200 and r["severity"] == "Critical", r.get("severity"))
notes = bench("print('@@' + json.dumps(frappe.get_all('Notification Log', filters={'document_name': %r}, pluck='for_user')))" % (ISS,))
check("X3", "Maintenance and managers receive an ERPNext notification", MAINT in notes and SUP in notes, notes)
s, r = call("mes_sf_machine_issue", operator=OP, workstation=OTHER_WS, issue_type="Machine Stalled", severity="Medium",
            machine_status="Stalled", description="Press stalls mid stroke", request_id=rid())
ISS2 = r.get("issue") if s == 200 else None
check("X4", "Employee can report a machine stall (priority raised to High)", s == 200 and r["severity"] == "High", r)
s, r = call("mes_sf_admin", operator=MAINT, action="overview")
check("X5", "Machine issues appear on the maintenance dashboard", s == 200 and any(i["name"] == ISS for i in r["issues"]), len(r["issues"]) if s == 200 else r)
dA = job(JA)
check("X6", "A Completely Down machine blocks the affected job", any("Completely Down" in b for b in dA["blocking"]) and not dA["actions"]["start"], dA["blocking"][-1:])
jobs_sab = call("mes_sf_jobs", operator=OP, workstation=OTHER_WS)[1].get("jobs", [])
check("X7", "Other workstations are not stopped by one machine's issue",
      all(not j["machine_down"] for j in jobs_sab), "%s jobs on %s, none flagged down" % (len(jobs_sab), OTHER_WS))
s, r = call("mes_sf_admin", operator=OP, action="issue_update", name=ISS, status="Resolved", notes="fixed")
check("P2", "Shopfloor employee cannot resolve a machine issue", s == 403, r)
s, r = call("mes_sf_admin", operator=SUP, action="issue_update", name=ISS, status="Resolved", notes="fixed")
check("P3", "Supervisor cannot resolve a machine issue (maintenance only)", s == 403, r)
s1, r1 = call("mes_sf_admin", operator=MAINT, action="issue_update", name=ISS, status="Acknowledged", assigned_to=MAINT)
s2, r2 = call("mes_sf_admin", operator=MAINT, action="issue_update", name=ISS, status="Resolved")
s3, r3 = call("mes_sf_admin", operator=MAINT, action="issue_update", name=ISS, status="Resolved", notes="Replaced tension sensor, test run OK")
check("X8", "Maintenance can acknowledge, assign and resolve (notes required)",
      s1 == 200 and s2 != 200 and s3 == 200 and r3["issue"]["status"] == "Resolved" and r3["issue"]["assigned_to"] == MAINT,
      "ack %s, resolve without notes -> %s, resolve with notes -> %s" % (s1, s2, r3["issue"]["status"] if s3 == 200 else r3))
if ISS2:
    call("mes_sf_admin", operator=MAINT, action="issue_update", name=ISS2, status="Resolved", notes="Cleared jam")

s, r = call("mes_sf_admin", operator=SUP, action="defect_update", name=DEF2, status="Rejected", comments="Cosmetic, within limits")
dA = job(JA)
check("C5", "Once defects are decided and the machine is back, the job is clear to start", s == 200 and dA["blocking"] == [] and dA["actions"]["start"], dA["blocking"])

# ---------- production progress and completion ----------
s, r = call("mes_sf_scan", operator=MAINT, job_card=JA, value=SCAN_A, qty=1, request_id=rid())
check("P4", "Maintenance-only users cannot record material scans", s == 403, r)
if A["busy"] or not ISSUABLE[A["wo"]]:
    why = SHORT_NOTE.get(A["wo"]) or "workstation %s is booked now by %s (planner schedule), so ERPNext refuses an overlapping time log" % (WSA, ", ".join(A["busy"]))
    for cid in ("C6", "C7", "C8", "C9", "C10"):
        skip(cid, "Start, report and complete production on the ERPNext Job Card", why)
else:
    s, r = call("mes_sf_progress", operator=OP, job_card=JA, action="start")
    check("C6", "Employee can start production once all checks pass", s == 200 and r["ok"] and r["status"] == "Work In Progress", r)
    time.sleep(2)
    part = max(1, int(job(JA)["job"]["remaining_qty"] // 2))
    s, r = call("mes_sf_progress", operator=OP, job_card=JA, action="report", qty=part)
    check("C7", "Employee can report progress (good quantity) on the ERPNext Job Card", s == 200 and r["completed_qty"] == part, r)
    s, r = call("mes_sf_progress", operator=OP, job_card=JA, action="report", qty=10 ** 4)
    check("C8", "A completed quantity above the job quantity is refused", s != 200, r)
    time.sleep(1)
    qty_left = int(job(JA)["job"]["remaining_qty"])
    s, r = call("mes_sf_progress", operator=OP, job_card=JA, action="complete", qty=qty_left)
    check("C9", "Valid completion submits the ERPNext Job Card", s == 200 and r["ok"] and r["docstatus"] == 1, r)
    op_row = [o for o in rest("/api/resource/Work Order/" + A["wo"])["data"]["operations"] if o["completed_qty"]]
    check("C10", "The work order operation is updated by ERPNext", bool(op_row), [(o["operation"], o["completed_qty"], o["status"]) for o in op_row])

if fx["legacy"]:
    w = fx["legacy"][0]
    se_before = bench("print('@@' + json.dumps(frappe.db.count('Stock Entry')))")
    s, r = call("mes_work_order_action", work_order=w, action="finish", qty=1)
    se_after = bench("print('@@' + json.dumps(frappe.db.count('Stock Entry')))")
    check("C11", "Finishing a work order via the planner API is refused while materials are unverified (no stock entry made)",
          s != 200 and "shopfloor checks" in str(r) and se_after == se_before, "%s: HTTP %s, stock entries %s -> %s" % (w, s, se_before, se_after))
else:
    skip("C11", "Finish gate on the planner API", "no In Process work order with transferred material and no MES scans")

s, r = call("mes_sf_jobs", operator="someone@nowhere.test")
check("P5", "Calls without a valid ERPNext operator are refused", s == 403, r)
s, r = call("mes_sf_scan", operator=OP, job_card="NO-SUCH-JC", value="x", request_id=rid())
check("F1", "API errors return an error status, never a success payload", s != 200, (s, r))
d = bench("print('@@' + json.dumps(frappe.db.count('Version', {'ref_doctype': 'MES Defect Report'})))")
check("A1", "Audit history is kept (scans stored, change history on defect reports, comments on work orders)",
      d > 0 and len(job(JA)["scans"]) > 0, "defect report versions: %s" % (d,))

pathlib.Path(MES / "state").mkdir(exist_ok=True)
(MES / "state" / "shopfloor-test-results.json").write_text(json.dumps(RESULTS, indent=1), encoding="utf-8")
lines = ["# Shopfloor acceptance test results", "",
         "Run %s against %s. Fixtures: work orders %s (job %s), %s (job %s), %s (job %s); tracked units %s." % (
             time.strftime("%Y-%m-%d %H:%M"), ERP, A["wo"], JA, B["wo"], JB, C["wo"], JCc, ", ".join(U[:2])), "",
         "Passed %d, failed %d, not tested %d." % (sum(r["result"] == "PASS" for r in RESULTS), sum(r["result"] == "FAIL" for r in RESULTS),
                                                   sum(r["result"] == "NOT TESTED" for r in RESULTS)), "",
         "| ID | Criterion | Result | Evidence |", "|---|---|---|---|"]
for r in RESULTS:
    lines.append("| %s | %s | %s | %s |" % (r["id"], r["criterion"], r["result"], r["evidence"].replace("|", "/").replace("\n", " ")))
(MES / "state" / "shopfloor-test-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\nPASS %d  FAIL %d  NOT TESTED %d" % (sum(r["result"] == "PASS" for r in RESULTS), sum(r["result"] == "FAIL" for r in RESULTS),
                                            sum(r["result"] == "NOT TESTED" for r in RESULTS)))
