# POST /api/method/mes_wf_workflow  {operator, action, ...}   supervisor only
#   list                                  every MES assembly workflow with its status and sync state
#   get        {finished_item}            working steps, version history, approved steps, live BOM changes since approval
#   generate   {item_code, force?}        build a Draft from the ERPNext BOM (never overwrites an approved workflow)
#   save       {finished_item, steps, change_note?}   store the steps as a new version (history is kept)
#   approve    {finished_item, version?}  make a saved version the one shopfloor employees see
#   archive    {finished_item}
#   sync_check {finished_item?}           compare live BOMs with the approved baseline; flag, never delete
#   ack_sync   {finished_item}            accept the current BOM as the new baseline (instructions unchanged)
who = M["operator"](M, "supervisor")
action = (M["arg"](M, "action") or "").lower()
now = frappe.utils.now_datetime()
STEP_FIELDS = ["step_name", "item_code", "qty", "uom", "description", "instructions", "checklist", "comments", "scan_mode",
               "serial_required", "batch_required", "quality_inspection", "photo_required", "mandatory", "image_override",
               "operation", "workstation", "source", "confidence", "review_flag", "review_notes"]
META = frappe.get_meta("MES Assembly Step")
SCAN_MODES = META.get_field("scan_mode").options.split("\n")
REVIEW_FLAGS = META.get_field("review_flag").options.split("\n")
CONFIDENCE = META.get_field("confidence").options.split("\n")
SOURCES = META.get_field("source").options.split("\n")


def wf_for(item):
    name = M["workflow_for"](M, item)
    if not name:
        return None
    return frappe.get_doc("MES Assembly Workflow", name)


def wf_require(item):
    if not item:
        frappe.throw("Choose a finished product first")
    doc = wf_for(item)
    if not doc:
        frappe.throw("No assembly workflow exists for %s yet: generate a draft first" % (item,))
    return doc


def wf_tree(item):
    if not frappe.db.exists("Item", item):
        frappe.throw("Item %s not found in ERPNext" % (item,))
    root = M["bom_tree"](M, item)
    if not root["bom"]:
        frappe.throw("%s has no active submitted BOM in ERPNext" % (item,))
    return root


def wf_whole(uom):
    return bool(frappe.db.get_value("UOM", uom, "must_be_whole_number")) if uom else False


def wf_mk_step(c, whole_cache, n):
    sub = bool(c["bom"])
    kids = [k for k in c["children"] if not k["cycle"]]
    flags = []
    notes = []
    if c["cycle"]:
        flags.append("Missing Information")
        notes.append("Circular BOM reference: not expanded")
    if not c["exists"]:
        flags.append("Missing Information")
        notes.append("Item not found in ERPNext")
    if c["disabled"]:
        flags.append("Missing Information")
        notes.append("Item is disabled in ERPNext")
    if not c["image"]:
        flags.append("Missing Image")
        notes.append("No image in ERPNext: upload one for this item")
    if c["bom_candidates"] > 1:
        flags.append("Missing Information")
        notes.append("Several active BOMs: confirm which one applies")
    if c["has_serial_no"]:
        scan = "Unit"
    else:
        if c["uom"] not in whole_cache:
            whole_cache[c["uom"]] = wf_whole(c["uom"])
        scan = "Quantity" if whole_cache[c["uom"]] else "Confirm"
    lines = ["Retrieve %s %s of %s (%s)." % (frappe.utils.flt(c["qty_per_unit"], 4), c["uom"] or "", c["item_name"], c["item_code"])]
    if sub:
        if kids:
            lines.append("Build the sub-assembly from its ERPNext components: %s." % (", ".join(k["item_name"] for k in kids),))
        else:
            lines.append("Its ERPNext BOM lists no components: an administrator must describe the build.")
    lines.append("Confirm the item code %s on the label or barcode." % (c["item_code"],))
    if c["has_serial_no"]:
        lines.append("Scan the serial number of every unit used.")
    lines.append("Inspect %s for visible damage." % (c["item_name"],))
    if sub:
        lines.append("Complete the sub-assembly build according to the approved assembly procedure.")
    else:
        lines.append("Fit %s according to the approved assembly procedure." % (c["item_name"],))
    notes.append("Orientation, torque, wiring, lubrication, safety and test tolerances are not in ERPNext: expert review required")
    flags.append("Expert Review")
    rank = ["Missing Information", "Missing Image", "Expert Review"]
    flag = "None"
    for r in rank:
        if flag == "None" and r in flags:
            flag = r
    return {"step_name": ("Build sub-assembly: " if sub else "Prepare: ") + c["item_name"], "item_code": c["item_code"],
            "qty": c["qty_per_unit"], "uom": c["uom"], "description": "Use %s x %s per finished unit." % (
                frappe.utils.flt(c["qty_per_unit"], 4), c["item_code"]),
            "instructions": "\n".join(lines), "checklist": "Item code confirmed\nQuantity matches the BOM\nNo visible damage",
            "comments": "", "scan_mode": scan, "serial_required": int(c["has_serial_no"] or 0),
            "batch_required": int(c["has_batch_no"] or 0), "quality_inspection": 0, "photo_required": 0, "mandatory": 1,
            "image_override": None, "operation": c["operation"] or "", "workstation": None, "source": "ERPNext BOM",
            "confidence": "Medium", "review_flag": flag, "review_notes": "; ".join(notes)}


def wf_build(root):
    whole = {}
    children = root["children"]
    subs = [c for c in children if c["bom"] and not c["cycle"]]
    rest = [c for c in children if c not in subs]
    steps = [wf_mk_step(c, whole, 0) for c in subs + rest]
    for op in root["operations"]:
        steps.append({"step_name": "Operation: %s" % (op.operation,), "item_code": None, "qty": None, "uom": None,
                      "description": "ERPNext operation at %s, standard time %s min." % (op.workstation or "no workstation", frappe.utils.flt(op.time_in_mins, 1)),
                      "instructions": "Carry out the operation %s at %s.\nThe ERPNext operation does not describe the procedure: add the approved steps here." % (op.operation, op.workstation or "the assigned workstation"),
                      "checklist": "", "comments": "", "scan_mode": "None", "serial_required": 0, "batch_required": 0,
                      "quality_inspection": 0, "photo_required": 0, "mandatory": 1, "image_override": None,
                      "operation": op.operation, "workstation": op.workstation or None, "source": "ERPNext Operation",
                      "confidence": "Low", "review_flag": "Expert Review",
                      "review_notes": "Procedure not defined in ERPNext"})
    steps.append({"step_name": "Final check of %s" % (root["item_name"],), "item_code": None, "qty": None, "uom": None,
                  "description": "Finished-product check before the work order is completed.",
                  "instructions": "Compare the finished unit with the approved product specification. The specification is not held in ERPNext.",
                  "checklist": "Finished product code matches the work order\nQuantity matches the work order\nNo visible damage",
                  "comments": "", "scan_mode": "None", "serial_required": 0, "batch_required": 0, "quality_inspection": 1,
                  "photo_required": 0, "mandatory": 1, "image_override": None, "operation": "", "workstation": None,
                  "source": "AI Draft", "confidence": "Low", "review_flag": "Expert Review",
                  "review_notes": "Acceptance criteria are not in ERPNext"})
    for i in range(len(steps)):
        s = steps[i]
        s["step_no"] = i + 1
        s["review_flag"] = s["review_flag"] if s["review_flag"] in REVIEW_FLAGS else "None"
    return steps


def wf_notes(root, steps):
    summ = M["tree_summary"](M, root)
    lines = ["Generated from ERPNext BOM %s: %d components (%d sub-assemblies, %d raw materials), depth %d." % (
        root["bom"], summ["components"], summ["sub_assemblies"], summ["raw_materials"], summ["max_depth"])]
    if summ["missing_images"]:
        lines.append("%d component(s) have no image." % (summ["missing_images"],))
    if summ["cycles"]:
        lines.append("%d circular BOM reference(s) were not expanded." % (summ["cycles"],))
    if summ["ambiguous_boms"]:
        lines.append("%d item(s) have several active BOMs: the default was used." % (summ["ambiguous_boms"],))
    if not root["operations"]:
        lines.append("ERPNext has no operations on this BOM: the sequence is a draft.")
    lines.append("This is a generated draft, not a verified engineering procedure. Every assembly step needs expert review before approval.")
    return "\n".join(lines)


def wf_clean(raw, n, codes):
    d = {k: raw.get(k) for k in STEP_FIELDS}
    d["step_no"] = n
    d["step_name"] = (d["step_name"] or "").strip()
    if not d["step_name"]:
        frappe.throw("Step %d needs a name" % (n,))
    if d["item_code"]:
        if not frappe.db.exists("Item", d["item_code"]):
            frappe.throw("Step %d: item %s does not exist in ERPNext" % (n, d["item_code"]))
        if d["item_code"] not in codes:
            d["review_flag"] = "Not In BOM"
            d["review_notes"] = "Item %s is not in the BOM of this product" % (d["item_code"],)
    d["qty"] = frappe.utils.flt(d["qty"]) if d["qty"] not in (None, "") else None
    d["scan_mode"] = d["scan_mode"] if d["scan_mode"] in SCAN_MODES else "None"
    d["review_flag"] = d["review_flag"] if d["review_flag"] in REVIEW_FLAGS else "None"
    d["confidence"] = d["confidence"] if d["confidence"] in CONFIDENCE else "High"
    d["source"] = d["source"] if d["source"] in SOURCES else "Admin"
    for k in ("serial_required", "batch_required", "quality_inspection", "photo_required"):
        d[k] = 1 if d[k] in (1, "1", True) else 0
    d["mandatory"] = 0 if d["mandatory"] in (0, "0", False) else 1
    return d


def wf_codes(root):
    return {r[0]["item_code"] for r in M["walk"](M, root, [])}


def wf_snapshot(steps):
    keep = ["step_no", "step_name", "item_code", "item_name", "qty", "uom", "description", "instructions", "checklist", "comments",
            "scan_mode", "serial_required", "batch_required", "quality_inspection", "photo_required", "mandatory",
            "image_override", "operation", "workstation", "source", "confidence", "review_flag", "review_notes"]
    out = []
    for s in steps:
        row = {k: s.get(k) for k in keep}
        if row.get("item_code"):
            row["item_name"] = frappe.db.get_value("Item", row["item_code"], "item_name")
        out.append(row)
    return out


def wf_add_version(doc, steps, note, by):
    ver = (doc.current_version or 0) + 1
    doc.steps = []
    for s in steps:
        doc.append("steps", s)
    snap = wf_snapshot(steps)
    doc.append("versions", {"version": ver, "status": "Draft", "step_count": len(snap), "change_note": note or "",
                            "saved_by": by["user"], "saved_on": now, "snapshot": json.dumps(snap)})
    doc.current_version = ver
    return ver


def wf_row(doc, ver):
    for v in doc.versions:
        if v.version == ver:
            return v
    frappe.throw("Version %s not found" % (ver,))


def wf_steps_out(doc):
    return [{k: s.get(k) for k in ["step_no", "step_name", "item_code", "item_name", "qty", "uom", "description", "instructions",
                                   "checklist", "comments", "scan_mode", "serial_required", "batch_required", "quality_inspection",
                                   "photo_required", "mandatory", "image_override", "operation", "workstation", "source",
                                   "confidence", "review_flag", "review_notes"]} for s in doc.steps]


def wf_item_image(code):
    if not code:
        return None
    facts = M["item_facts"](M, code)
    return facts.image if facts else None


def wf_summary(doc):
    return {"name": doc.name, "finished_item": doc.finished_item, "item_name": doc.item_name, "bom": doc.bom, "status": doc.status,
            "sync_status": doc.sync_status, "current_version": doc.current_version, "approved_version": doc.approved_version,
            "source": doc.source, "step_count": len(doc.steps), "flagged_steps": len([s for s in doc.steps if s.review_flag not in ("None", "")]),
            "approved_on": doc.approved_on, "approved_by": doc.approved_by, "modified": doc.modified}


def wf_diff_live(doc):
    if not doc.approved_version or not doc.approved_bom_signature:
        return []
    root = M["bom_tree"](M, doc.finished_item)
    return M["bom_diff"](M, doc.approved_bom_signature, M["signature"](M, root))


def wf_apply_diff(doc, diff):
    for d in diff:
        if d["kind"] == "Component Added":
            continue
        flag = d["kind"]
        for s in doc.steps:
            if s.item_code == d["item_code"]:
                s.review_flag = flag
                s.review_notes = ((s.review_notes or "") + "; " if s.review_notes else "") + "%s under %s (was %s, now %s)" % (
                    flag, d["parent"], d["was"], d["now"])


def wf_sync_one(doc):
    if not doc.approved_version:
        doc.sync_status = "In Sync"
        doc.sync_notes = "Not approved yet: nothing to compare with."
        doc.save(ignore_permissions=True)
        return []
    root = M["bom_tree"](M, doc.finished_item)
    cur = M["signature"](M, root)
    diff = M["bom_diff"](M, doc.approved_bom_signature, cur)
    doc.bom = root["bom"]
    if not diff:
        doc.sync_status = "In Sync"
        doc.sync_notes = ""
    else:
        doc.sync_status = "Review Needed"
        lines = []
        for d in diff:
            lines.append("%s: %s under %s (was %s, now %s)" % (d["kind"], d["item_code"], d["parent"], d["was"], d["now"]))
        doc.sync_notes = "\n".join(lines)
        wf_apply_diff(doc, diff)
    doc.save(ignore_permissions=True)
    if diff:
        M["notify"](M, "MES workflow %s needs review: ERPNext BOM changed" % (doc.finished_item,), "MES Assembly Workflow", doc.name,
                    doc.sync_notes)
    return diff


if action == "list":
    rows = frappe.get_all("MES Assembly Workflow", fields=["name", "finished_item", "item_name", "bom", "status", "sync_status",
                                                             "current_version", "approved_version", "source", "approved_on", "modified"],
                          order_by="finished_item asc")
    out = {"ok": True, "operator": who, "workflows": rows}
elif action == "get":
    doc = wf_require(M["arg"](M, "finished_item"))
    out = {"ok": True, "operator": who, "workflow": wf_summary(doc), "generation_notes": doc.generation_notes,
           "sync_notes": doc.sync_notes, "steps": wf_steps_out(doc),
           "versions": [{"version": v.version, "status": v.status, "step_count": v.step_count, "change_note": v.change_note,
                         "saved_by": v.saved_by, "saved_on": v.saved_on, "approved_by": v.approved_by, "approved_on": v.approved_on}
                        for v in sorted(doc.versions, key=lambda v: -v.version)],
           "sync_diff": wf_diff_live(doc)}
    if doc.approved_version:
        out["approved_steps"] = json.loads(wf_row(doc, doc.approved_version).snapshot or "[]")
        for s in out["approved_steps"]:
            s["image"] = wf_item_image(s.get("item_code"))
elif action == "generate":
    code = M["arg"](M, "item_code")
    force = M["arg"](M, "force") in ("1", 1, True, "true")
    root = wf_tree(code)
    existing = wf_for(code)
    if existing and existing.approved_version:
        frappe.throw("%s already has approved instructions (version %s). Generation never replaces approved instructions: edit a new version instead."
                     % (code, existing.approved_version))
    if existing and not force:
        frappe.throw("%s already has a draft: use force to replace the unapproved draft" % (code,))
    steps = wf_build(root)
    if existing:
        doc = existing
    else:
        doc = frappe.get_doc({"doctype": "MES Assembly Workflow", "finished_item": code, "item_name": root["item_name"],
                              "bom": root["bom"], "status": "Draft", "sync_status": "In Sync", "source": "Rule Draft",
                              "approved_version": 0})
    doc.bom = root["bom"]
    doc.generated_on = now
    doc.generation_notes = wf_notes(root, steps)
    doc.sync_notes = ""
    steps_clean = [wf_clean(s, s["step_no"], wf_codes(root)) for s in steps]
    wf_add_version(doc, steps_clean, "Generated draft from ERPNext BOM %s" % (root["bom"],), who)
    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)
    out = {"ok": True, "operator": who, "workflow": wf_summary(doc), "generation_notes": doc.generation_notes,
           "steps": wf_steps_out(doc)}
elif action == "save":
    doc = wf_require(M["arg"](M, "finished_item"))
    raw = M["json_arg"](M, "steps") or []
    if not isinstance(raw, list) or not raw:
        frappe.throw("A workflow needs at least one step")
    root = wf_tree(doc.finished_item)
    codes = wf_codes(root)
    steps = [wf_clean(raw[i], i + 1, codes) for i in range(len(raw))]
    ver = wf_add_version(doc, steps, M["arg"](M, "change_note"), who)
    doc.save(ignore_permissions=True)
    out = {"ok": True, "operator": who, "version": ver, "workflow": wf_summary(doc), "steps": wf_steps_out(doc)}
elif action == "approve":
    doc = wf_require(M["arg"](M, "finished_item"))
    ver = int(M["arg"](M, "version") or doc.current_version or 0)
    if not ver or ver > (doc.current_version or 0):
        frappe.throw("Version %s does not exist" % (ver,))
    if doc.status == "Archived":
        frappe.throw("Archived workflows cannot be approved")
    root = wf_tree(doc.finished_item)
    for v in doc.versions:
        if v.status == "Approved":
            v.status = "Superseded"
        if v.version == ver:
            v.status = "Approved"
            v.approved_by = who["user"]
            v.approved_on = now
    doc.approved_version = ver
    doc.approved_bom_signature = M["signature"](M, root)
    doc.bom = root["bom"]
    doc.status = "Approved"
    doc.sync_status = "In Sync"
    doc.sync_notes = ""
    doc.approved_by = who["user"]
    doc.approved_on = now
    doc.save(ignore_permissions=True)
    snap = json.loads(wf_row(doc, ver).snapshot or "[]")
    out = {"ok": True, "operator": who, "workflow": wf_summary(doc), "warnings": [
        "%s: %s" % (s.get("step_name"), s.get("review_flag")) for s in snap if s.get("review_flag") not in ("None", "", None)]}
elif action == "archive":
    doc = wf_require(M["arg"](M, "finished_item"))
    doc.status = "Archived"
    doc.save(ignore_permissions=True)
    out = {"ok": True, "operator": who, "workflow": wf_summary(doc)}
elif action == "sync_check":
    item = M["arg"](M, "finished_item")
    docs = [wf_require(item)] if item else [frappe.get_doc("MES Assembly Workflow", n) for n in frappe.get_all("MES Assembly Workflow", pluck="name")]
    changes = {}
    for d in docs:
        changes[d.finished_item] = wf_sync_one(d)
    out = {"ok": True, "operator": who, "checked": len(docs),
           "changed": {k: changes[k] for k in changes if changes[k]},
           "workflows": [wf_summary(frappe.get_doc("MES Assembly Workflow", d.name)) for d in docs]}
elif action == "ack_sync":
    doc = wf_require(M["arg"](M, "finished_item"))
    if not doc.approved_version:
        frappe.throw("Nothing to acknowledge: the workflow is not approved")
    root = wf_tree(doc.finished_item)
    doc.approved_bom_signature = M["signature"](M, root)
    doc.sync_status = "In Sync"
    doc.sync_notes = "BOM change acknowledged by %s on %s: instructions were not changed" % (who["name"], now)
    doc.save(ignore_permissions=True)
    out = {"ok": True, "operator": who, "workflow": wf_summary(doc)}
else:
    frappe.throw("Unknown action %s" % (action,))

frappe.response["message"] = out
