"""Phase 8: MES modules on top of the core - recipe management, digital quality
inspection, SPC, work instructions, kitting / BOM-to-inventory, ISO 9001."""

import os
import random

import frappe
from frappe.utils import get_datetime, getdate

from erpnext.manufacturing.doctype.work_order.work_order import create_pick_list

from mes_common import company_of, ensure, phase, run, warehouses

SEED = 4242

MODULE_LINKS = [
    ("Recipe Management", "MES Recipe", "DocType", "MES Recipe"),
    ("Recipe Management", "MES Deviation", "DocType", "MES Deviation"),
    ("Recipe Management", "BOM (versions)", "DocType", "BOM"),
    ("Quality & SPC", "Quality Inspection", "DocType", "Quality Inspection"),
    ("Quality & SPC", "Inspection Templates", "DocType", "Quality Inspection Template"),
    ("Quality & SPC", "SPC X-bar R: Motor Current", "Report", "MES SPC X-bar R Motor Current"),
    ("Quality & SPC", "Inspection Pass Rate", "Report", "MES Inspection Pass Rate"),
    ("Work Instructions & Documents", "Operations (instructions)", "DocType", "Operation"),
    ("Work Instructions & Documents", "Quality Procedures", "DocType", "Quality Procedure"),
    ("Kitting & Inventory", "Pick List (kits)", "DocType", "Pick List"),
    ("Kitting & Inventory", "Kitting Status", "Report", "MES Kitting Status"),
    ("Kitting & Inventory", "BOM vs Actual Consumption", "Report", "MES BOM vs Actual Consumption"),
    ("ISO 9001", "Quality Goal", "DocType", "Quality Goal"),
    ("ISO 9001", "Non Conformance", "DocType", "Non Conformance"),
    ("ISO 9001", "Quality Action", "DocType", "Quality Action"),
]

PERMS = [
    {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "print": 1},
    {"role": "Manufacturing Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "print": 1},
    {"role": "Manufacturing User", "read": 1, "write": 1, "create": 1, "report": 1, "print": 1},
    {"role": "Quality Manager", "read": 1, "write": 1, "create": 1, "report": 1, "print": 1},
]


def ensure_doctype(name, spec):
    if frappe.db.exists("DocType", name):
        return
    perms = [] if spec.get("istable") else [p for p in PERMS if frappe.db.exists("Role", p["role"])]
    doc = frappe.get_doc({"doctype": "DocType", "name": name, "module": "Manufacturing", "custom": 1, "permissions": perms, **spec})
    doc.insert()


def recipe_doctypes():
    ensure_doctype("MES Recipe Parameter", {
        "istable": 1,
        "editable_grid": 1,
        "fields": [
            {"fieldname": "parameter", "label": "Parameter", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "uom", "label": "Unit", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "target", "label": "Target", "fieldtype": "Float", "in_list_view": 1},
            {"fieldname": "min_value", "label": "Min", "fieldtype": "Float", "in_list_view": 1},
            {"fieldname": "max_value", "label": "Max", "fieldtype": "Float", "in_list_view": 1},
        ],
    })
    ensure_doctype("MES Recipe", {
        "autoname": "format:RCP-{item}-{operation}-{version}",
        "title_field": "item",
        "track_changes": 1,
        "fields": [
            {"fieldname": "item", "label": "Item", "fieldtype": "Link", "options": "Item", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1},
            {"fieldname": "operation", "label": "Operation", "fieldtype": "Link", "options": "Operation", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1},
            {"fieldname": "version", "label": "Version", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Draft\nApproved\nObsolete", "default": "Draft", "in_list_view": 1, "in_standard_filter": 1},
            {"fieldname": "cb1", "fieldtype": "Column Break"},
            {"fieldname": "bom", "label": "BOM", "fieldtype": "Link", "options": "BOM"},
            {"fieldname": "effective_from", "label": "Effective From", "fieldtype": "Date"},
            {"fieldname": "change_note", "label": "Change Note", "fieldtype": "Small Text"},
            {"fieldname": "sb1", "fieldtype": "Section Break", "label": "Process Parameters"},
            {"fieldname": "parameters", "label": "Parameters", "fieldtype": "Table", "options": "MES Recipe Parameter"},
        ],
    })
    ensure_doctype("MES Deviation", {
        "autoname": "MES-DEV-.#####",
        "title_field": "parameter",
        "fields": [
            {"fieldname": "recipe", "label": "Recipe", "fieldtype": "Link", "options": "MES Recipe", "reqd": 1, "in_list_view": 1},
            {"fieldname": "job_card", "label": "Job Card", "fieldtype": "Link", "options": "Job Card", "in_list_view": 1},
            {"fieldname": "workstation", "label": "Workstation", "fieldtype": "Link", "options": "Workstation", "in_standard_filter": 1},
            {"fieldname": "recorded_at", "label": "Recorded At", "fieldtype": "Datetime"},
            {"fieldname": "cb1", "fieldtype": "Column Break"},
            {"fieldname": "parameter", "label": "Parameter", "fieldtype": "Data", "in_list_view": 1},
            {"fieldname": "target", "label": "Target", "fieldtype": "Float"},
            {"fieldname": "min_value", "label": "Min", "fieldtype": "Float"},
            {"fieldname": "max_value", "label": "Max", "fieldtype": "Float"},
            {"fieldname": "measured", "label": "Measured", "fieldtype": "Float", "in_list_view": 1},
            {"fieldname": "sb1", "fieldtype": "Section Break"},
            {"fieldname": "severity", "label": "Severity", "fieldtype": "Select", "options": "Minor\nMajor\nCritical", "in_standard_filter": 1},
            {"fieldname": "disposition", "label": "Disposition", "fieldtype": "Select", "options": "Use As Is\nRework\nScrap\nHold"},
            {"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Open\nClosed", "default": "Open", "in_list_view": 1, "in_standard_filter": 1},
            {"fieldname": "remarks", "label": "Remarks", "fieldtype": "Small Text"},
        ],
    })


def bom_version(item, company, changes, note):
    base = frappe.db.get_value("BOM", {"item": item, "company": company, "is_default": 1, "docstatus": 1}, "name")
    for name in frappe.get_all("BOM", filters={"item": item, "company": company, "docstatus": 1, "is_default": 0}, pluck="name"):
        rows = {r.item_code: r.qty for r in frappe.get_all("BOM Item", filters={"parent": name}, fields=["item_code", "qty"])}
        if all(abs(rows.get(k, -1) - v) < 1e-9 for k, v in changes.items()):
            return name
    new = frappe.copy_doc(frappe.get_doc("BOM", base))
    new.is_default = 0
    new.is_active = 1
    new.description = note
    for row in new.items:
        if row.item_code in changes:
            row.qty = changes[row.item_code]
    new.insert()
    new.submit()
    return new.name


def recipes(P, company):
    rows = []
    for r in P["recipes"]:
        bom = frappe.db.get_value("BOM", {"item": r["item"], "company": company, "is_default": 1, "docstatus": 1}, "name")
        if r.get("bom_change"):
            bom = bom_version(r["item"], company, r["bom_change"], r.get("change_note"))
        name = f"RCP-{r['item']}-{r['operation']}-{r['version']}"
        ensure("MES Recipe", name, lambda r=r, bom=bom: {
            "doctype": "MES Recipe",
            "item": r["item"],
            "operation": r["operation"],
            "version": r["version"],
            "status": r["status"],
            "bom": bom,
            "effective_from": "2026-10-01" if r["status"] == "Approved" else "2026-12-01",
            "change_note": r.get("change_note") or "Initial released recipe",
            "parameters": [{"parameter": p, "uom": u, "target": t, "min_value": lo, "max_value": hi} for p, u, t, lo, hi in r["parameters"]],
        })
        rows.append(name)
    return rows


def deviations(company):
    if frappe.db.count("MES Deviation"):
        return frappe.db.count("MES Deviation")
    rng = random.Random(SEED)
    recipes = frappe.get_all("MES Recipe", filters={"status": "Approved"}, fields=["name", "item", "operation"])
    count = 0
    for rec in recipes:
        params = frappe.get_all("MES Recipe Parameter", filters={"parent": rec.name}, fields=["parameter", "target", "min_value", "max_value"])
        logs = frappe.db.sql(
            """select jc.name, jc.workstation, tl.from_time from `tabJob Card Time Log` tl
            join `tabJob Card` jc on jc.name = tl.parent
            where jc.company = %s and jc.docstatus = 1 and jc.production_item = %s and jc.operation = %s
            and tl.parentfield = 'time_logs' order by tl.from_time""",
            (company, rec.item, rec.operation),
            as_dict=True,
        )
        for log in logs:
            for p in params:
                band = (p.max_value - p.min_value) or max(abs(p.target) * 0.02, 1)
                measured = rng.gauss(p.target, band / 5)
                if rng.random() < 0.06:
                    measured = p.max_value + band * rng.uniform(0.05, 0.4) if rng.random() < 0.5 else p.min_value - band * rng.uniform(0.05, 0.4)
                if p.min_value <= measured <= p.max_value:
                    continue
                severity = "Major" if abs(measured - p.target) > band else "Minor"
                frappe.get_doc({
                    "doctype": "MES Deviation",
                    "recipe": rec.name,
                    "job_card": log.name,
                    "workstation": log.workstation,
                    "recorded_at": log.from_time,
                    "parameter": p.parameter,
                    "target": p.target,
                    "min_value": p.min_value,
                    "max_value": p.max_value,
                    "measured": round(measured, 2),
                    "severity": severity,
                    "disposition": "Hold" if severity == "Major" else "Use As Is",
                    "status": "Closed" if severity == "Minor" else "Open",
                    "remarks": "Recorded at first-off check" if severity == "Minor" else "Parts quarantined pending engineering review",
                }).insert()
                count += 1
    return count


def quality_templates(P):
    for name, spec in P["quality_templates"].items():
        for param, *_ in spec["parameters"]:
            ensure("Quality Inspection Parameter", param, lambda p=param: {"doctype": "Quality Inspection Parameter", "parameter": p})
        ensure("Quality Inspection Template", name, lambda name=name, spec=spec: {
            "doctype": "Quality Inspection Template",
            "quality_inspection_template_name": name,
            "item_quality_inspection_parameter": [
                {"specification": p, "numeric": 1, "min_value": lo, "max_value": hi} for p, lo, hi, _, _ in spec["parameters"]
            ],
        })
        for item in spec["items"]:
            frappe.db.set_value("Item", item, "quality_inspection_template", name, update_modified=False)


def inspections(P, company):
    if frappe.db.count("Quality Inspection", {"company": company}):
        return frappe.db.count("Quality Inspection", {"company": company})
    rng = random.Random(SEED + 1)
    count = 0
    by_item = {i: (n, s) for n, s in P["quality_templates"].items() for i in s["items"]}
    logs = frappe.db.sql(
        """select jc.name, jc.production_item, jc.operation, jc.bom_no, date(tl.from_time) day, min(tl.from_time) t
        from `tabJob Card Time Log` tl join `tabJob Card` jc on jc.name = tl.parent
        where jc.company = %s and jc.docstatus = 1 and tl.parentfield = 'time_logs'
        and jc.operation in ('Hi-Pot & Function Test', 'Motor Run Test')
        group by jc.name, date(tl.from_time) order by t""",
        company,
        as_dict=True,
    )
    for i, log in enumerate(logs):
        if log.production_item not in by_item:
            continue
        template, spec = by_item[log.production_item]
        drift = 1 + (0.02 if getdate(log.day) >= getdate("2026-11-16") and log.production_item == "SA-MOT-S" else 0)
        readings = []
        for param, lo, hi, mean, sd in spec["parameters"]:
            values = [rng.gauss(mean * drift if "Current" in param else mean, sd) for _ in range(5)]
            if rng.random() < 0.04:
                values[rng.randrange(5)] = hi + (hi - lo) * 0.08
            row = {"specification": param, "numeric": 1, "min_value": lo, "max_value": hi, "manual_inspection": 0}
            for k, v in enumerate(values, start=1):
                row[f"reading_{k}"] = f"{v:.3f}" if v < 100 else f"{v:.0f}"
            readings.append(row)
        qi = frappe.get_doc({
            "doctype": "Quality Inspection",
            "company": company,
            "inspection_type": "In Process",
            "reference_type": "Job Card",
            "reference_name": log.name,
            "item_code": log.production_item,
            "bom_no": log.bom_no,
            "sample_size": 5,
            "report_date": log.day,
            "quality_inspection_template": template,
            "inspected_by": "Administrator",
            "readings": readings,
        })
        qi.flags.ignore_links = False
        qi.insert()
        qi.submit()
        count += 1
    return count


def spc_report():
    query = """select
    s.qi as "Subgroup:Link/Quality Inspection:150",
    s.report_date as "Date:Date:100",
    round(s.xbar, 4) as "X-bar:Float:90",
    round(avg(s.xbar) over (), 4) as "Centre Line:Float:100",
    round(avg(s.xbar) over () + 0.577 * avg(s.rng) over (), 4) as "UCL:Float:90",
    round(avg(s.xbar) over () - 0.577 * avg(s.rng) over (), 4) as "LCL:Float:90",
    round(s.rng, 4) as "Range:Float:90",
    round(2.114 * avg(s.rng) over (), 4) as "Range UCL:Float:100",
    case when s.xbar > avg(s.xbar) over () + 0.577 * avg(s.rng) over ()
           or s.xbar < avg(s.xbar) over () - 0.577 * avg(s.rng) over () then 'Out of control' else 'In control' end as "Signal:Data:110"
from (
    select qi.name as qi, qi.report_date,
        (cast(r.reading_1 as decimal(12,4)) + cast(r.reading_2 as decimal(12,4)) + cast(r.reading_3 as decimal(12,4)) + cast(r.reading_4 as decimal(12,4)) + cast(r.reading_5 as decimal(12,4))) / 5 as xbar,
        greatest(cast(r.reading_1 as decimal(12,4)), cast(r.reading_2 as decimal(12,4)), cast(r.reading_3 as decimal(12,4)), cast(r.reading_4 as decimal(12,4)), cast(r.reading_5 as decimal(12,4)))
        - least(cast(r.reading_1 as decimal(12,4)), cast(r.reading_2 as decimal(12,4)), cast(r.reading_3 as decimal(12,4)), cast(r.reading_4 as decimal(12,4)), cast(r.reading_5 as decimal(12,4))) as rng
    from `tabQuality Inspection` qi
    join `tabQuality Inspection Reading` r on r.parent = qi.name
    where qi.docstatus = 1 and qi.item_code = 'SA-MOT-S' and r.specification = 'No-Load Current (A)'
) s
order by s.report_date, s.qi"""
    return query


def pass_rate_report(company):
    return f"""select
    qi.item_code as "Item:Link/Item:120",
    qi.quality_inspection_template as "Template:Link/Quality Inspection Template:220",
    count(*) as "Inspections:Int:90",
    sum(qi.status = 'Accepted') as "Accepted:Int:80",
    sum(qi.status = 'Rejected') as "Rejected:Int:80",
    round(100 * sum(qi.status = 'Accepted') / count(*), 1) as "Pass Rate:Percent:90"
from `tabQuality Inspection` qi
where qi.company = '{company}' and qi.docstatus = 1
group by qi.item_code, qi.quality_inspection_template
order by qi.item_code"""


def kitting_report(company, stores):
    return f"""select
    wo.name as "Work Order:Link/Work Order:150",
    wo.production_item as "Produces:Link/Item:110",
    wo.planned_start_date as "Planned Start:Datetime:140",
    woi.item_code as "Component:Link/Item:130",
    woi.required_qty as "Required:Float:80",
    woi.transferred_qty as "Transferred:Float:90",
    ifnull(b.actual_qty, 0) as "In Stores:Float:80",
    greatest(woi.required_qty - woi.transferred_qty - ifnull(b.actual_qty, 0), 0) as "Short:Float:70",
    case when woi.transferred_qty >= woi.required_qty then 'Kitted'
         when woi.required_qty - woi.transferred_qty <= ifnull(b.actual_qty, 0) then 'Ready to kit'
         else 'Short' end as "Kit Status:Data:100",
    ifnull((select max(pl.name) from `tabPick List` pl where pl.work_order = wo.name and pl.docstatus < 2), '') as "Pick List:Link/Pick List:150"
from `tabWork Order` wo
join `tabWork Order Item` woi on woi.parent = wo.name
left join `tabBin` b on b.item_code = woi.item_code and b.warehouse = '{stores}'
where wo.company = '{company}' and wo.docstatus = 1 and wo.status in ('Not Started', 'In Process')
    and wo.production_plan in (select name from `tabProduction Plan` where custom_mes_tag = 'forward')
order by wo.planned_start_date, wo.name, woi.idx"""


def consumption_report(company):
    return f"""select
    wo.name as "Work Order:Link/Work Order:150",
    wo.production_item as "Produced Item:Link/Item:110",
    wo.produced_qty as "Produced:Float:80",
    woi.item_code as "Component:Link/Item:130",
    round(woi.required_qty / wo.qty * wo.produced_qty, 3) as "BOM Qty for Output:Float:120",
    woi.transferred_qty as "Transferred:Float:90",
    woi.consumed_qty as "Consumed:Float:90",
    round(woi.consumed_qty - woi.required_qty / wo.qty * wo.produced_qty, 3) as "Variance:Float:80",
    round(woi.transferred_qty - woi.consumed_qty, 3) as "Left in WIP:Float:90"
from `tabWork Order` wo
join `tabWork Order Item` woi on woi.parent = wo.name
where wo.company = '{company}' and wo.docstatus = 1 and wo.produced_qty > 0
order by wo.name, woi.idx"""


def module_reports(S, company):
    from mes_analytics import upsert_report

    upsert_report("MES SPC X-bar R Motor Current", "Quality Inspection", spc_report())
    upsert_report("MES Inspection Pass Rate", "Quality Inspection", pass_rate_report(company))
    upsert_report("MES Kitting Status", "Work Order", kitting_report(company, warehouses(S)["stores"]))
    upsert_report("MES BOM vs Actual Consumption", "Work Order", consumption_report(company))


def spc_chart():
    from mes_analytics import upsert

    upsert("Dashboard Chart", "MES SPC Motor Current X-bar", {
        "chart_name": "MES SPC Motor Current X-bar",
        "chart_type": "Report",
        "report_name": "MES SPC X-bar R Motor Current",
        "use_report_chart": 0,
        "x_field": "subgroup",
        "type": "Line",
        "y_axis": [{"y_field": "x_bar", "color": "#2490EF"}, {"y_field": "ucl", "color": "#E24C4C"}, {"y_field": "centre_line", "color": "#29CD42"}, {"y_field": "lcl", "color": "#E24C4C"}],
        "filters_json": "{}",
        "is_public": 1,
        "module": "Manufacturing",
        "is_standard": 0,
        "timeseries": 0,
    })
    return "MES SPC Motor Current X-bar"


def work_instructions(P, company):
    for op, steps in P["work_instructions"].items():
        html = "<ol>" + "".join(f"<li>{s}</li>" for s in steps) + "</ol>"
        frappe.db.set_value("Operation", op, "description", html, update_modified=False)
    frappe.db.sql(
        """update `tabJob Card` jc join `tabOperation` o on o.name = jc.operation
        set jc.custom_work_instructions = o.description
        where jc.company = %s""",
        (company,),
    )


PROCEDURES = {
    "QP-MES-01 Production Execution": [
        "Release work orders from the approved Production Plan; the plan owns the schedule.",
        "Kit materials with a Pick List before the first job card starts.",
        "Operators follow the work instructions on each job card and log time, good qty and rejects.",
        "Record every stop as a Downtime Entry with a reason code.",
    ],
    "QP-MES-02 In-Process Inspection": [
        "Inspect 5 units per shift at Motor Run Test and Hi-Pot & Function Test using the linked template.",
        "Readings outside limits reject the inspection automatically.",
        "Plot motor no-load current on the X-bar/R chart and react to out-of-control signals.",
    ],
    "QP-MES-03 Control of Nonconforming Output": [
        "Red-tag and quarantine nonconforming units.",
        "Raise a Non Conformance for every rejected inspection or major recipe deviation.",
        "Decide disposition (rework, scrap, use as is) and record corrective action.",
    ],
    "QP-MES-04 Recipe Change Control": [
        "Propose a new recipe version with a change note (ECN).",
        "Create a new BOM version when material quantities change; keep the old one active until approval.",
        "Approve, set the effective date, and mark the old version obsolete.",
    ],
}


def iso_9001(company):
    for name, steps in PROCEDURES.items():
        ensure("Quality Procedure", name, lambda name=name, steps=steps: {
            "doctype": "Quality Procedure",
            "quality_procedure_name": name,
            "processes": [{"process_description": s} for s in steps],
        })
    ensure("UOM", "Percent", lambda: {"doctype": "UOM", "uom_name": "Percent"})
    ensure("Quality Goal", "MES OEE and Scrap Targets", lambda: {
        "doctype": "Quality Goal",
        "goal": "MES OEE and Scrap Targets",
        "frequency": "Monthly",
        "date": "1",
        "procedure": "QP-MES-01 Production Execution",
        "objectives": [
            {"objective": "Plant OEE (daily average)", "target": "75", "uom": "Percent"},
            {"objective": "Scrap rate across all operations", "target": "2", "uom": "Percent"},
            {"objective": "Final test first-pass yield", "target": "97", "uom": "Percent"},
        ],
    })
    ncs = 0
    for qi in frappe.get_all("Quality Inspection", filters={"company": company, "status": "Rejected", "docstatus": 1}, fields=["name", "item_code", "reference_name", "report_date"], order_by="report_date"):
        subject = f"Rejected inspection {qi.name} ({qi.item_code})"
        if frappe.db.exists("Non Conformance", {"subject": subject}):
            continue
        failed = frappe.get_all("Quality Inspection Reading", filters={"parent": qi.name, "status": "Rejected"}, pluck="specification")
        frappe.get_doc({
            "doctype": "Non Conformance",
            "subject": subject,
            "procedure": "QP-MES-03 Control of Nonconforming Output",
            "status": "Open" if getdate(qi.report_date) >= getdate("2026-11-16") else "Resolved",
            "details": f"Job card {qi.reference_name}, {qi.report_date}: out of limits on {', '.join(failed) or 'one or more readings'}.",
            "corrective_action": "Units quarantined and retested; failing unit scrapped.",
            "preventive_action": "Check test fixture calibration at shift start.",
        }).insert()
        ncs += 1
    if not frappe.db.exists("Quality Action", {"goal": "MES OEE and Scrap Targets"}):
        frappe.get_doc({
            "doctype": "Quality Action",
            "corrective_preventive": "Corrective",
            "goal": "MES OEE and Scrap Targets",
            "procedure": "QP-MES-02 In-Process Inspection",
            "status": "Open",
            "date": getdate(),
            "resolutions": [
                {"problem": "Motor no-load current drifting upward since week 47 (SPC chart)", "resolution": "Inspect brush spring pressure and bearing preload on MAS-01", "status": "Open"},
                {"problem": "Injection moulding setup downtime is the top Pareto reason", "resolution": "Introduce SMED quick-change on IMM-01/02", "status": "Open"},
            ],
        }).insert()
    return ncs


def kitting(company):
    made = 0
    wos = frappe.db.sql(
        """select wo.name, wo.qty from `tabWork Order` wo
        join `tabProduction Plan` pp on pp.name = wo.production_plan
        where wo.company = %s and wo.docstatus = 1 and pp.custom_mes_tag = 'forward'
        and wo.production_item like 'SA-%%' and wo.status = 'Not Started'
        order by wo.planned_start_date limit 6""",
        company,
        as_dict=True,
    )
    for wo in wos:
        if frappe.db.exists("Pick List", {"work_order": wo.name, "docstatus": ["<", 2]}):
            continue
        pl = create_pick_list(wo.name, for_qty=wo.qty)
        pl.insert()
        made += 1
    return made


def main(P, S):
    company = company_of(S)
    recipe_doctypes()
    frappe.db.commit()
    rec = recipes(P, company)
    quality_templates(P)
    work_instructions(P, company)
    module_reports(S, company)
    chart = spc_chart()
    frappe.db.commit()
    phase(f"P8 static: {len(rec)} recipes, {len(P['quality_templates'])} inspection templates, {len(P['work_instructions'])} work instructions, 4 module reports")
    if os.environ.get("MES_STATIC_ONLY") == "1":
        from mes_analytics import build

        build(P, S, MODULE_LINKS, extra_charts=[chart])
        phase("P8 static only: workspace refreshed")
        return
    pick = kitting(company)
    dev = deviations(company)
    qis = inspections(P, company)
    frappe.db.commit()
    ncs = iso_9001(company)
    frappe.db.commit()
    from mes_analytics import build

    build(P, S, MODULE_LINKS, extra_charts=[chart])
    phase(f"P8 data: {pick} pick lists, {dev} deviations, {qis} quality inspections, {ncs} non conformances; workspace refreshed")


if __name__ == "__main__":
    run(main)
