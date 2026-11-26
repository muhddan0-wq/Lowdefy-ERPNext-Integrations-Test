"""Phase 7: OEE and MES dashboards (query reports, number cards, charts, workspace)."""

import json

import frappe

from mes_common import company_of, phase, run

JOB_LOGS = """
    select date(tl.from_time) as day, jc.workstation, jc.operation, jc.production_item,
        tl.time_in_mins as run_mins,
        tl.completed_qty as good_qty,
        ifnull(tl.custom_rejected_qty, 0) as rejected_qty,
        (tl.completed_qty + ifnull(tl.custom_rejected_qty, 0)) * ifnull(bo.custom_ideal_cycle_time, 0) as ideal_mins
    from `tabJob Card Time Log` tl
    join `tabJob Card` jc on jc.name = tl.parent
    left join `tabBOM Operation` bo on bo.parent = jc.bom_no and bo.operation = jc.operation
    where jc.company = '{company}' and jc.docstatus = 1 and tl.to_time is not null
"""

DOWNTIME = """
    select date(de.from_time) as day, de.workstation,
        timestampdiff(second, de.from_time, de.to_time) / 60 as down_mins, de.stop_reason
    from `tabDowntime Entry` de
    where de.workstation like '{site}-%%'
"""


def oee_by_ws_day(company, site):
    return f"""select
    x.day as "Date:Date:100",
    x.workstation as "Workstation:Link/Workstation:110",
    round(x.run_mins, 1) as "Run Mins:Float:90",
    round(x.down_mins, 1) as "Downtime Mins:Float:110",
    round(x.ideal_mins, 1) as "Ideal Mins:Float:90",
    x.total_qty as "Total Qty:Float:80",
    x.good_qty as "Good Qty:Float:80",
    round(100 * x.run_mins / (x.run_mins + x.down_mins), 1) as "Availability:Percent:100",
    round(100 * x.ideal_mins / x.run_mins, 1) as "Performance:Percent:100",
    round(100 * x.good_qty / x.total_qty, 1) as "Quality:Percent:90",
    round(100 * (x.run_mins / (x.run_mins + x.down_mins)) * (x.ideal_mins / x.run_mins) * (x.good_qty / x.total_qty), 1) as "OEE:Percent:90"
from (
    select l.day, l.workstation,
        sum(l.run_mins) as run_mins,
        ifnull((select sum(d.down_mins) from ({DOWNTIME.format(site=site)}) d where d.day = l.day and d.workstation = l.workstation), 0) as down_mins,
        sum(l.ideal_mins) as ideal_mins,
        sum(l.good_qty + l.rejected_qty) as total_qty,
        sum(l.good_qty) as good_qty
    from ({JOB_LOGS.format(company=company)}) l
    group by l.day, l.workstation
) x
where x.run_mins > 0 and x.total_qty > 0
order by x.day desc, x.workstation"""


def oee_trend(company, site):
    return f"""select
    x.day as "Date:Date:100",
    round(100 * x.run_mins / (x.run_mins + x.down_mins), 1) as "Availability:Percent:100",
    round(100 * x.ideal_mins / x.run_mins, 1) as "Performance:Percent:100",
    round(100 * x.good_qty / x.total_qty, 1) as "Quality:Percent:90",
    round(100 * (x.run_mins / (x.run_mins + x.down_mins)) * (x.ideal_mins / x.run_mins) * (x.good_qty / x.total_qty), 1) as "OEE:Percent:90"
from (
    select l.day,
        sum(l.run_mins) as run_mins,
        ifnull((select sum(d.down_mins) from ({DOWNTIME.format(site=site)}) d where d.day = l.day), 0) as down_mins,
        sum(l.ideal_mins) as ideal_mins,
        sum(l.good_qty + l.rejected_qty) as total_qty,
        sum(l.good_qty) as good_qty
    from ({JOB_LOGS.format(company=company)}) l
    group by l.day
) x
where x.run_mins > 0
order by x.day"""


def downtime_pareto(site):
    return f"""select
    p.stop_reason as "Stop Reason:Data:220",
    p.events as "Events:Int:70",
    round(p.mins, 1) as "Downtime Mins:Float:110",
    round(100 * sum(p.mins) over (order by p.mins desc rows unbounded preceding) / sum(p.mins) over (), 1) as "Cumulative:Percent:100"
from (
    select ifnull(d.stop_reason, 'Unspecified') as stop_reason, count(*) as events, sum(d.down_mins) as mins
    from ({DOWNTIME.format(site=site)}) d group by d.stop_reason
) p
order by p.mins desc"""


def output_vs_plan(company):
    return f"""select
    wo.production_item as "Item:Link/Item:120",
    i.item_name as "Item Name:Data:220",
    sum(wo.qty) as "Planned Qty:Float:100",
    sum(wo.produced_qty) as "Produced Qty:Float:100",
    round(100 * sum(wo.produced_qty) / sum(wo.qty), 1) as "Attainment:Percent:100"
from `tabWork Order` wo
join `tabItem` i on i.name = wo.production_item
join `tabProduction Plan` pp on pp.name = wo.production_plan
where wo.company = '{company}' and wo.docstatus = 1 and pp.custom_mes_tag like 'history-%%'
group by wo.production_item, i.item_name
order by wo.production_item"""


def scrap_rate(company):
    return f"""select
    jc.operation as "Operation:Link/Operation:200",
    sum(tl.completed_qty + ifnull(tl.custom_rejected_qty, 0)) as "Total Qty:Float:90",
    sum(ifnull(tl.custom_rejected_qty, 0)) as "Rejected Qty:Float:100",
    round(100 * sum(ifnull(tl.custom_rejected_qty, 0)) / sum(tl.completed_qty + ifnull(tl.custom_rejected_qty, 0)), 2) as "Scrap Rate:Percent:100"
from `tabJob Card Time Log` tl
join `tabJob Card` jc on jc.name = tl.parent
where jc.company = '{company}' and jc.docstatus = 1
group by jc.operation
order by 4 desc"""


def schedule_board(company):
    return f"""select
    s.from_time as "Start:Datetime:150",
    s.to_time as "End:Datetime:150",
    jc.workstation as "Workstation:Link/Workstation:110",
    jc.name as "Job Card:Link/Job Card:120",
    jc.work_order as "Work Order:Link/Work Order:150",
    jc.production_item as "Item:Link/Item:110",
    jc.operation as "Operation:Link/Operation:180",
    jc.for_quantity as "Qty:Float:60",
    jc.status as "Status:Data:110"
from `tabJob Card Scheduled Time` s
join `tabJob Card` jc on jc.name = s.parent
where jc.company = '{company}' and jc.docstatus = 0
order by s.from_time, jc.workstation"""


def reports(company, site):
    return {
        "MES OEE by Workstation Day": ("Job Card", oee_by_ws_day(company, site)),
        "MES OEE Daily Trend": ("Job Card", oee_trend(company, site)),
        "MES Downtime Pareto": ("Downtime Entry", downtime_pareto(site)),
        "MES Output vs Plan": ("Work Order", output_vs_plan(company)),
        "MES Scrap Rate by Operation": ("Job Card", scrap_rate(company)),
        "MES Schedule Board": ("Job Card", schedule_board(company)),
    }


def upsert_report(name, ref_doctype, query):
    if frappe.db.exists("Report", name):
        doc = frappe.get_doc("Report", name)
        doc.query = query
        doc.ref_doctype = ref_doctype
        doc.save()
        return
    frappe.get_doc({
        "doctype": "Report",
        "report_name": name,
        "ref_doctype": ref_doctype,
        "report_type": "Query Report",
        "is_standard": "No",
        "module": "Manufacturing",
        "query": query,
        "roles": [{"role": r} for r in ("Manufacturing Manager", "Manufacturing User", "System Manager")],
    }).insert()


def upsert(doctype, name, payload):
    if frappe.db.exists(doctype, name):
        doc = frappe.get_doc(doctype, name)
        doc.update(payload)
        doc.save()
        return doc.name
    doc = frappe.get_doc({"doctype": doctype, **payload})
    doc.insert()
    return doc.name


def number_cards(site):
    cards = {
        "MES Avg Daily OEE": {"type": "Report", "report_name": "MES OEE Daily Trend", "report_field": "oee", "report_function": "Average", "color": "#2490EF"},
        "MES Avg Availability": {"type": "Report", "report_name": "MES OEE Daily Trend", "report_field": "availability", "report_function": "Average", "color": "#29CD42"},
        "MES Avg Performance": {"type": "Report", "report_name": "MES OEE Daily Trend", "report_field": "performance", "report_function": "Average", "color": "#ECAD4B"},
        "MES Avg Quality": {"type": "Report", "report_name": "MES OEE Daily Trend", "report_field": "quality", "report_function": "Average", "color": "#7575FF"},
        "MES Downtime Minutes": {"type": "Report", "report_name": "MES Downtime Pareto", "report_field": "downtime_mins", "report_function": "Sum", "color": "#E24C4C"},
        "MES Open Job Cards": {
            "type": "Document Type", "document_type": "Job Card", "function": "Count", "color": "#5E64FF",
            "filters_json": json.dumps([["Job Card", "workstation", "like", f"{site}-%", False], ["Job Card", "docstatus", "=", 0, False]]),
        },
    }
    for label, spec in cards.items():
        upsert("Number Card", label, {"label": label, "is_public": 1, "module": "Manufacturing", "is_standard": 0, "filters_json": spec.pop("filters_json", "{}"), **spec})
    return list(cards)


def charts():
    specs = {
        "MES OEE Trend": {"report_name": "MES OEE Daily Trend", "x_field": "date", "type": "Line", "y": [("oee", "#2490EF"), ("availability", "#29CD42"), ("performance", "#ECAD4B")]},
        "MES Downtime Pareto": {"report_name": "MES Downtime Pareto", "x_field": "stop_reason", "type": "Bar", "y": [("downtime_mins", "#E24C4C")]},
        "MES Output vs Plan": {"report_name": "MES Output vs Plan", "x_field": "item", "type": "Bar", "y": [("planned_qty", "#B8C2CC"), ("produced_qty", "#2490EF")]},
        "MES Scrap Rate": {"report_name": "MES Scrap Rate by Operation", "x_field": "operation", "type": "Bar", "y": [("scrap_rate", "#FF8C00")]},
    }
    for name, spec in specs.items():
        upsert("Dashboard Chart", name, {
            "chart_name": name,
            "chart_type": "Report",
            "report_name": spec["report_name"],
            "use_report_chart": 0,
            "x_field": spec["x_field"],
            "type": spec["type"],
            "y_axis": [{"y_field": f, "color": c} for f, c in spec["y"]],
            "filters_json": "{}",
            "is_public": 1,
            "module": "Manufacturing",
            "is_standard": 0,
            "timeseries": 0,
        })
    return list(specs)


def workspace(cards, chart_names, extra_links, plant_name):
    name = "MES Dashboard"
    content = [{"id": "h1", "type": "header", "data": {"text": "<span class=\"h4\"><b>MES Dashboard - " + frappe.utils.escape_html(plant_name) + "</b></span>", "col": 12}}]
    for i, c in enumerate(cards):
        content.append({"id": f"nc{i}", "type": "number_card", "data": {"number_card_name": c, "col": 4}})
    for i, c in enumerate(chart_names):
        content.append({"id": f"ch{i}", "type": "chart", "data": {"chart_name": c, "col": 6}})
    content.append({"id": "h2", "type": "header", "data": {"text": "<span class=\"h4\"><b>Shop floor &amp; modules</b></span>", "col": 12}})
    shortcuts = [
        ("Job Card", "DocType", "Job Card", "List"),
        ("Work Order", "DocType", "Work Order", "List"),
        ("Downtime Entry", "DocType", "Downtime Entry", "List"),
        ("Plant Floor", "DocType", "Plant Floor", "List"),
        ("Schedule Board", "Report", "MES Schedule Board", ""),
        ("OEE by Workstation", "Report", "MES OEE by Workstation Day", ""),
    ]
    for i, (label, _, _, _) in enumerate(shortcuts):
        content.append({"id": f"sc{i}", "type": "shortcut", "data": {"shortcut_name": label, "col": 3}})
    groups = {}
    for group, label, link_type, link_to in extra_links:
        groups.setdefault(group, []).append((label, link_type, link_to))
    links = []
    for i, (group, rows) in enumerate(groups.items()):
        content.append({"id": f"cd{i}", "type": "card", "data": {"card_name": group, "col": 4}})
        links.append({"type": "Card Break", "label": group, "link_count": len(rows)})
        for label, link_type, link_to in rows:
            links.append({"type": "Link", "label": label, "link_type": link_type, "link_to": link_to, "is_query_report": 1 if link_type == "Report" else 0})
    payload = {
        "label": name,
        "title": name,
        "type": "Workspace",
        "module": "Manufacturing",
        "public": 1,
        "is_hidden": 0,
        "icon": "monitor",
        "content": json.dumps(content),
        "number_cards": [{"number_card_name": c, "label": c} for c in cards],
        "charts": [{"chart_name": c, "label": c} for c in chart_names],
        "shortcuts": [
            {"label": label, "type": t, "link_to": link, **({"doc_view": view} if view else {})}
            for label, t, link, view in shortcuts
        ],
        "links": links,
    }
    if frappe.db.exists("Workspace", name):
        doc = frappe.get_doc("Workspace", name)
        doc.number_cards, doc.charts, doc.shortcuts, doc.links = [], [], [], []
        doc.update(payload)
        doc.save()
    else:
        frappe.get_doc({"doctype": "Workspace", **payload}).insert()


CORE_LINKS = [
    ("MES Core Reports", "OEE by Workstation Day", "Report", "MES OEE by Workstation Day"),
    ("MES Core Reports", "OEE Daily Trend", "Report", "MES OEE Daily Trend"),
    ("MES Core Reports", "Downtime Pareto", "Report", "MES Downtime Pareto"),
    ("MES Core Reports", "Output vs Plan", "Report", "MES Output vs Plan"),
    ("MES Core Reports", "Scrap Rate by Operation", "Report", "MES Scrap Rate by Operation"),
    ("MES Core Reports", "Schedule Board", "Report", "MES Schedule Board"),
    ("Planning", "Production Plan", "DocType", "Production Plan"),
    ("Planning", "Work Order", "DocType", "Work Order"),
    ("Planning", "Workstation", "DocType", "Workstation"),
    ("Planning", "BOM", "DocType", "BOM"),
]


def build(P, S, extra_links=(), extra_charts=()):
    company = company_of(S)
    for name, (ref, query) in reports(company, S["code"]).items():
        upsert_report(name, ref, query)
    cards = number_cards(S["code"])
    chart_names = charts() + list(extra_charts)
    workspace(cards, chart_names, list(CORE_LINKS) + list(extra_links), S.get("plant_floor") or S["code"])
    frappe.db.commit()
    return cards, chart_names


def main(P, S):
    from mes_modules import MODULE_LINKS

    extra = ["MES SPC Motor Current X-bar"] if frappe.db.exists("Dashboard Chart", "MES SPC Motor Current X-bar") else []
    cards, chart_names = build(P, S, MODULE_LINKS, extra_charts=extra)
    phase(f"P7 {len(reports(company_of(S), S['code']))} reports, {len(cards)} number cards, {len(chart_names)} charts, workspace 'MES Dashboard'")


if __name__ == "__main__":
    run(main)
