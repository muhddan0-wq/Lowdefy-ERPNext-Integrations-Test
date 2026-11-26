"""Acceptance tests for dynamic ERPNext discovery and MES assembly workflows, run against the live sandbox through the
mes_wf_* and mes_sf_job endpoints. Writes mes/state/workflow-test-results.md (and .json).

Products are discovered at run time, with no SKU in this file:
  dataset A  a finished product whose BOM tree has ERPNext images and no approved MES workflow
  dataset B  up to two finished products with a nested BOM (a component with its own BOM) and no MES workflow yet,
             fewest images first. Expected tree shapes and quantities are re-derived from the BOM records.

It creates real MES Assembly Workflow records (drafts, versions, approvals) and MES Workflow Bindings. When no product
is left without a workflow, the workflow checks are reported NOT TESTED. It never creates or changes ERPNext
master data, BOMs, work orders or stock. The sync tests simulate a BOM change by editing the stored approval baseline
in the database, because changing a real BOM would alter master data.

Usage (from the repo root): python mes/setup/test_workflow.py
"""
import datetime
import json
import pathlib
import subprocess
import textwrap
import sys
import urllib.error
import urllib.request

MES = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MES))
import site_config  # noqa: E402

CFG = site_config.load()
ENV = dict(l.split("=", 1) for l in (MES / ".secrets" / "appsmith-mes.env").read_text().split() if "=" in l)
AUTH = "token %s:%s" % (ENV["ERP_API_KEY"], ENV["ERP_API_SECRET"])
ERP = CFG["erp"]["public_url"].rstrip("/")
CONTAINER = CFG["erp"]["container"]
FSITE = CFG["erp"]["site"]


def user_with(role, without=None):
    for u in CFG["test_users"]:
        if role in u["roles"] and not (without and without in u["roles"]):
            return u["email"]
    raise SystemExit("site YAML test_users has no user with role %s" % (role,))


OP = user_with("Manufacturing User", "Manufacturing Manager")
SUP = user_with("Manufacturing Manager")
GHOST = "NO-SUCH-COMPONENT-99"
RESULTS = []


def call(method, **args):
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
        return e.code, str(msg)[:600]


def ok_call(method, **args):
    s, d = call(method, **args)
    assert s == 200, "%s -> %s %s" % (method, s, d)
    return d


def bench(code):
    script = "import frappe, json\nfrappe.init(site=%r, sites_path='.')\nfrappe.connect()\nfrappe.set_user('Administrator')\n" % (FSITE,) + textwrap.dedent(code)
    p = subprocess.run(["docker", "exec", "-i", "-w", "/home/frappe/frappe-bench/sites", CONTAINER, "../env/bin/python", "-W", "ignore", "-"],
                       input=script, capture_output=True, text=True, timeout=180)
    lines = [l for l in p.stdout.splitlines() if l.startswith("@@")]
    if not lines:
        raise RuntimeError(p.stderr[-800:])
    return json.loads(lines[-1][2:])


def check(cid, text, ok, evidence):
    RESULTS.append({"id": cid, "criterion": text, "result": "PASS" if ok else "FAIL", "evidence": str(evidence)[:500]})
    print("%-5s %-4s %s | %s" % (cid, "PASS" if ok else "FAIL", text, str(evidence)[:160]), flush=True)


def skip(cid, text, why):
    RESULTS.append({"id": cid, "criterion": text, "result": "NOT TESTED", "evidence": why})
    print("%-5s SKIP %s | %s" % (cid, text, why), flush=True)


def tree_nodes(node, out=None):
    out = [] if out is None else out
    out.append(node)
    for c in node["children"]:
        tree_nodes(c, out)
    return out


truth = bench("""
def boms_of(code):
    return frappe.get_all('BOM', filters={'item': code, 'is_active': 1, 'docstatus': 1}, fields=['name', 'quantity'], order_by='is_default desc, creation desc')
def rows(bom):
    return frappe.get_all('BOM Item', filters={'parent': bom, 'parenttype': 'BOM'}, fields=['item_code', 'qty', 'bom_no'], order_by='idx asc')
with_bom = {r[0] for r in frappe.db.sql("select distinct item from `tabBOM` where is_active=1 and docstatus=1")}
used = {r[0] for r in frappe.db.sql("select distinct bi.item_code from `tabBOM Item` bi join `tabBOM` b on b.name=bi.parent where b.is_active=1 and b.docstatus=1")}
products = sorted(with_bom - used)
info = {}
for code in products:
    root = boms_of(code)[0]
    rq = root.quantity or 1
    nested, flat = None, None
    imgs = 0
    for r in rows(root.name):
        if frappe.db.get_value('Item', r.item_code, 'image'):
            imgs += 1
        cb = frappe.get_all('BOM', filters={'name': r.bom_no, 'is_active': 1, 'docstatus': 1}, fields=['name', 'quantity']) if r.bom_no else boms_of(r.item_code)
        if cb and not nested:
            cq = cb[0].quantity or 1
            nested = {'item_code': r.item_code, 'grandchildren': {g.item_code: round((r.qty or 0) / rq * (g.qty or 0) / cq, 6) for g in rows(cb[0].name)}}
        if not cb and not flat:
            flat = r.item_code
    if frappe.db.get_value('Item', code, 'image'):
        imgs += 1
    wf = frappe.db.get_value('MES Assembly Workflow', {'finished_item': code}, ['name', 'status', 'approved_version'], as_dict=True)
    wos = [w for w in frappe.get_all('Work Order', filters={'production_item': code, 'docstatus': 1, 'status': ['in', ['Not Started', 'In Process']]}, pluck='name', order_by='name asc')
           if not frappe.db.exists('MES Workflow Binding', w)]
    info[code] = {'nested': nested, 'flat': flat, 'images': imgs, 'workflow': wf, 'wos': wos}
print('@@' + json.dumps({'products': products, 'info': info}, default=str))
""")
INFO = truth["info"]
fresh_nested = sorted([c for c in truth["products"] if INFO[c]["nested"] and not INFO[c]["workflow"]], key=lambda c: (INFO[c]["images"], c))
DATASET_B = fresh_nested[:2]
B1 = DATASET_B[0] if DATASET_B else None
B2 = DATASET_B[1] if len(DATASET_B) > 1 else None
A_ITEM = ([c for c in truth["products"] if c not in DATASET_B and INFO[c]["images"] and INFO[c]["wos"]
           and not (INFO[c]["workflow"] and INFO[c]["workflow"]["approved_version"])] or [None])[0]
IMG_ITEM = A_ITEM or ([c for c in truth["products"] if INFO[c]["images"]] or [None])[0]
NEST_ITEM = B1 or ([c for c in truth["products"] if INFO[c]["nested"]] or [None])[0]
wo_lists = {c: INFO[c]["wos"] for c in INFO}
print("datasets: B=%s A=%s images=%s nested=%s" % (DATASET_B, A_ITEM, IMG_ITEM, NEST_ITEM), flush=True)

disc = ok_call("mes_wf_discover", operator=SUP, action="products")
codes = {p["item_code"]: p for p in disc["products"]}
check("D1", "Finished products are discovered from active BOMs (every finished product, nothing else)",
      set(truth["products"]) == set(codes), "%d products found, %d expected" % (len(codes), len(truth["products"])))
comps = set()
for c in truth["products"]:
    if INFO[c]["nested"]:
        comps.add(INFO[c]["nested"]["item_code"])
    if INFO[c]["flat"]:
        comps.add(INFO[c]["flat"])
check("D2", "Sub-assemblies and raw materials are not reported as finished products", not (comps & set(codes)), sorted(comps & set(codes)))

trees = {it: ok_call("mes_wf_discover", operator=SUP, action="tree", item_code=it) for it in {x for x in DATASET_B + [NEST_ITEM, IMG_ITEM] if x}}
if NEST_ITEM:
    nest = INFO[NEST_ITEM]["nested"]
    root = trees[NEST_ITEM]["tree"]
    kids = {c["item_code"]: c for c in root["children"]}
    sub_node = kids.get(nest["item_code"])
    sub_kids = {c["item_code"]: c for c in (sub_node or {}).get("children", [])}
    check("D3", "Nested BOM is retrieved: %s expands into its own components" % (nest["item_code"],),
          bool(sub_node and sub_node["bom"]) and set(nest["grandchildren"]) == set(sub_kids), sorted(sub_kids))
    check("D4", "Quantities are multiplied down the tree (per finished unit)",
          all(abs(sub_kids.get(g, {}).get("qty_per_unit", -1) - q) < 1e-5 for g, q in nest["grandchildren"].items()),
          {g: (sub_kids.get(g, {}).get("qty_per_unit"), q) for g, q in list(nest["grandchildren"].items())[:4]})
    flat = INFO[NEST_ITEM]["flat"]
    if flat:
        check("D5", "A component without a BOM is a normal material with no children",
              kids[flat]["bom"] is None and kids[flat]["children"] == [], flat)
    else:
        skip("D5", "A component without a BOM has no children", "%s has no component without a BOM" % (NEST_ITEM,))
else:
    for cid in ("D3", "D4", "D5"):
        skip(cid, "Nested BOM retrieval", "no finished product with a nested BOM")
all_nodes = [n for t in trees.values() for n in tree_nodes(t["tree"])]
no_img = [n for n in all_nodes if not n["image"]]
if no_img:
    check("D6", "An item with no image gets no guessed image and a 'No image' flag",
          all(n["image"] is None and "No image" in n["flags"] for n in no_img), "%d nodes without image" % len(no_img))
else:
    skip("D6", "An item with no image is flagged", "every discovered node has an image")
if IMG_ITEM:
    with_img = [n for n in tree_nodes(trees[IMG_ITEM]["tree"]) if n["image"]]
    check("D7", "Images come from ERPNext Item.image, never from a name guess",
          bool(with_img) and all(n["image_source"] == "Item image field" for n in with_img), "%s: %d components with images" % (IMG_ITEM, len(with_img)))
else:
    skip("D7", "Images come from ERPNext Item.image", "no product has an image")
skip("D8", "Circular BOM references are reported without infinite recursion",
     "the sandbox has no circular BOM and this test does not write BOM master data; the cycle guard is in the prelude (mes_bom_node)")
if NEST_ITEM:
    check("D9", "BOM signature is stable for an unchanged BOM",
          ok_call("mes_wf_discover", operator=SUP, action="tree", item_code=NEST_ITEM)["bom_signature"] == trees[NEST_ITEM]["bom_signature"],
          "repeatable")
check("P1", "Shopfloor user cannot use workflow discovery", call("mes_wf_discover", operator=OP, action="products")[0] != 200, "denied")

if DATASET_B:
    trees_b = {it: trees[it]["tree"] for it in DATASET_B}
    for item in DATASET_B:
        d = ok_call("mes_wf_workflow", operator=SUP, action="generate", item_code=item)
        wf, s = d["workflow"], d["steps"]
        want = len(trees_b[item]["children"]) + len(trees_b[item]["operations"]) + 1
        check("G1-" + item, "Draft generated from the BOM of %s: one step per direct component and per BOM operation, plus a final check" % item,
              wf["status"] == "Draft" and wf["approved_version"] == 0 and wf["current_version"] == 1 and len(s) == want,
              "%d steps (expected %d), status %s" % (len(s), want, wf["status"]))
        check("G2-" + item, "Every generated step is flagged for review and none is High confidence",
              all(x["review_flag"] != "None" for x in s) and all(x["confidence"] != "High" for x in s),
              sorted({x["review_flag"] for x in s}))
        check("G3-" + item, "Components without an image are flagged Missing Image in the draft",
              any(x["review_flag"] == "Missing Image" for x in s), sum(1 for x in s if x["review_flag"] == "Missing Image"))
        check("G4-" + item, "Sub-assemblies come first and their steps list the ERPNext components to build from",
              s[0]["step_name"].startswith("Build sub-assembly") and "Build the sub-assembly from its ERPNext components" in s[0]["instructions"],
              s[0]["step_name"])
        s_r, _ = call("mes_wf_workflow", operator=SUP, action="generate", item_code=item)
        check("G5-" + item, "A second generate is refused, so an existing draft is never silently replaced", s_r != 200, "refused (%s)" % s_r)

    for item in DATASET_B:
        wf = ok_call("mes_wf_workflow", operator=SUP, action="get", finished_item=item)
        edited = [dict(x) for x in wf["steps"]]
        edited[0]["step_name"] = "Check and prepare: " + edited[0]["step_name"]
        edited.insert(1, {"step_name": "Safety check before assembly", "item_code": None, "instructions": "Confirm the work area is clear.",
                          "checklist": "Area clear\nTools present", "mandatory": 1, "source": "Admin", "confidence": "High",
                          "review_flag": "None", "scan_mode": "None"})
        s, r = call("mes_wf_workflow", operator=SUP, action="save", finished_item=item, steps=json.dumps(edited), change_note="Admin edit")
        check("E1-" + item, "Admin edits are saved as version 2 with every step stored",
              s == 200 and r["version"] == 2 and len(r["steps"]) == len(edited), r if s != 200 else (r["version"], len(r["steps"])))
        bad = edited + [{"step_name": "Bad step", "item_code": "NOT-A-REAL-ITEM-9"}]
        s2, r2 = call("mes_wf_workflow", operator=SUP, action="save", finished_item=item, steps=json.dumps(bad), change_note="bad item")
        check("E2-" + item, "A step pointing at an item that does not exist in ERPNext is rejected",
              s2 != 200 and "does not exist" in r2, r2[:120])
        g = ok_call("mes_wf_workflow", operator=SUP, action="get", finished_item=item)
        check("E3-" + item, "Version history keeps both saved versions", sorted(v["version"] for v in g["versions"]) == [1, 2],
              [(v["version"], v["status"]) for v in g["versions"]])
        check("E4-" + item, "Original steps are kept after an edit (saving deletes nothing)",
              len(g["steps"]) == len(wf["steps"]) + 1 and any(x["step_name"] == "Safety check before assembly" for x in g["steps"]),
              len(g["steps"]))

    LOCK = ([c["item_code"] for c in trees_b[B1]["children"] if not c["bom"]] or [trees_b[B1]["children"][-1]["item_code"]])[0]
    a = ok_call("mes_wf_workflow", operator=SUP, action="approve", finished_item=B1)
    check("A1", "Approval makes the saved version live; the response lists every flagged step",
          a["workflow"]["approved_version"] == 2 and a["workflow"]["status"] == "Approved" and len(a["warnings"]) >= 1,
          "approved v%s, %d warnings" % (a["workflow"]["approved_version"], len(a["warnings"])))
    ap = ok_call("mes_wf_workflow", operator=SUP, action="get", finished_item=B1)
    check("A2", "Approved steps are retrievable, each with its ERPNext image field",
          len(ap["approved_steps"]) == len(ap["steps"]) and all("image" in x for x in ap["approved_steps"]), len(ap["approved_steps"]))
    check("A3", "Generating a new draft over an approved workflow is refused",
          call("mes_wf_workflow", operator=SUP, action="generate", item_code=B1, force=1)[0] != 200, "refused")
    if B2:
        ok_call("mes_wf_workflow", operator=SUP, action="approve", finished_item=B2)

    wo_b = (wo_lists.get(B2 or "") or [None])[0]
    wo_a = (wo_lists.get(A_ITEM or "") or [None])[0]


    def open_jc(wo):
        return bench("""
    jc = frappe.get_all('Job Card', filters={'work_order': %r, 'docstatus': 0}, pluck='name', order_by='creation asc')
    print('@@' + json.dumps(jc[0] if jc else None))
    """ % (wo,))


    jb = open_jc(wo_b) if wo_b else None
    if jb:
        j = ok_call("mes_sf_job", operator=OP, job_card=jb)
        wfb = j["workflow"]
        check("J1", "Shopfloor job shows the approved workflow for its work order (dataset B)",
              wfb["status"] == "approved" and len(wfb["steps"]) > 0, "v%s, %d steps" % (wfb.get("version"), len(wfb.get("steps", []))))
        check("J2", "Employee view carries no admin-only fields (review flags, source, notes)",
              all("review_flag" not in x and "source" not in x and "review_notes" not in x for x in wfb["steps"]),
              sorted(wfb["steps"][0].keys())[:8])
        check("J3", "Exactly one step is Current", [x["status"] for x in wfb["steps"]].count("Current") == 1, wfb["current_step"])
        check("J4", "Work order is bound to the approved version", wfb["version"] == 2, wfb["version"])
        check("J5", "Material steps show the required quantity for this work order",
              any(x["required_qty"] for x in wfb["steps"] if x["item_code"]),
              [(x["item_code"], x["required_qty"]) for x in wfb["steps"] if x["item_code"]][:3])
        cur = ok_call("mes_wf_workflow", operator=SUP, action="get", finished_item=B2)
        ok_call("mes_wf_workflow", operator=SUP, action="save", finished_item=B2, steps=json.dumps(cur["steps"]),
                change_note="Version 3 for binding test")
        ok_call("mes_wf_workflow", operator=SUP, action="approve", finished_item=B2)
        j2 = ok_call("mes_sf_job", operator=OP, job_card=jb)
        check("J6", "A newer approved version does not change a work order already bound to an older one",
              j2["workflow"]["version"] == 2 and len(j2["workflow"]["steps"]) == len(wfb["steps"]), "still v%s" % (j2["workflow"]["version"],))
    else:
        skip("J1", "Shopfloor job shows the approved workflow (dataset B)", "no second dataset B product with an open work order and job card")

    ja = open_jc(wo_a) if wo_a else None
    if ja:
        jj = ok_call("mes_sf_job", operator=OP, job_card=ja)
        check("J7", "Product with no approved workflow shows status none and no steps, without error",
              jj["workflow"]["status"] == "none" and jj["workflow"]["steps"] == [], jj["workflow"]["status"])
    else:
        skip("J7", "Product with no approved workflow has no steps", "no open work order with a job card for a product without a workflow")

    check("S1", "Sync check on an unchanged BOM reports In Sync",
          ok_call("mes_wf_workflow", operator=SUP, action="sync_check", finished_item=B1)["workflows"][0]["sync_status"] == "In Sync",
          "%s In Sync" % (B1,))

    bench("""
    name = frappe.db.get_value('MES Assembly Workflow', {'finished_item': %r}, 'name')
    sig = json.loads(frappe.db.get_value('MES Assembly Workflow', name, 'approved_bom_signature'))
    sig = [[e[0], e[1], e[2] + 2.0 if (e[0] == %r and e[1] == %r) else e[2]] for e in sig]
    sig.append([%r, %r, 1.0])
    frappe.db.set_value('MES Assembly Workflow', name, 'approved_bom_signature', json.dumps(sig))
    frappe.db.commit()
    print('@@' + json.dumps(name))
    """ % (B1, B1, LOCK, B1, GHOST))
    sc = ok_call("mes_wf_workflow", operator=SUP, action="sync_check", finished_item=B1)
    wf_after = ok_call("mes_wf_workflow", operator=SUP, action="get", finished_item=B1)
    lock = [x for x in wf_after["steps"] if x["item_code"] == LOCK]
    check("S2", "A quantity change in the BOM flags the matching step for review",
          sc["workflows"][0]["sync_status"] == "Review Needed" and bool(lock) and lock[0]["review_flag"] == "Quantity Changed",
          lock[0]["review_flag"] if lock else None)
    check("S3", "A component removed from the BOM is reported and no step is added for it",
          GHOST in (wf_after["sync_notes"] or "") and "Component Removed" in (wf_after["sync_notes"] or "") and
          not any(x["item_code"] == GHOST for x in wf_after["steps"]), (wf_after["sync_notes"] or "")[:160])
    check("S4", "Approved instructions are unchanged by the sync check",
          wf_after["workflow"]["approved_version"] == 2 and len(wf_after["approved_steps"]) == len(ap["approved_steps"]),
          "approved v%s, %d steps" % (wf_after["workflow"]["approved_version"], len(wf_after["approved_steps"])))
    check("S5", "Steps and version history are not deleted by a sync",
          len(wf_after["steps"]) == len(ap["steps"]) and len(wf_after["versions"]) == 2,
          "%d steps, %d versions" % (len(wf_after["steps"]), len(wf_after["versions"])))
    ack = ok_call("mes_wf_workflow", operator=SUP, action="ack_sync", finished_item=B1)
    check("S6", "Acknowledging the BOM change returns the workflow to In Sync without regenerating instructions",
          ack["workflow"]["sync_status"] == "In Sync" and ack["workflow"]["approved_version"] == 2, ack["workflow"]["sync_status"])

    check("P2", "Shopfloor user cannot approve workflows", call("mes_wf_workflow", operator=OP, action="approve", finished_item=B1)[0] != 200,
          "denied")
else:
    for cid in ("G1", "E1", "A1", "J1", "S1", "P2"):
        skip(cid, "Workflow generation, editing, approval, binding and sync", "every discovered product already has an MES workflow")

passed = len([r for r in RESULTS if r["result"] == "PASS"])
failed = [r for r in RESULTS if r["result"] == "FAIL"]
out_dir = MES / "state"
(out_dir / "workflow-test-results.json").write_text(json.dumps(RESULTS, indent=2), encoding="utf-8")
lines = ["# Workflow test results", "", "Run %s: %d of %d checks pass." % (datetime.datetime.now().isoformat(timespec="seconds"), passed, len(RESULTS)),
         "", "| ID | Result | Criterion | Evidence |", "|---|---|---|---|"]
for r in RESULTS:
    lines.append("| %s | %s | %s | %s |" % (r["id"], r["result"], r["criterion"], str(r["evidence"]).replace("|", "/")[:200]))
(out_dir / "workflow-test-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n%d of %d passed; %d failed" % (passed, len(RESULTS), len(failed)), flush=True)
