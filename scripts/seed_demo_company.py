"""Seed a separate 'Copilot Demo' company in ERPNext for the purchasing demo.

Idempotent: re-running only creates what is missing. Nothing outside the
Copilot Demo company is touched. Run:  python scripts/seed_demo_company.py
"""

import datetime
import json
import os
import random
import sys
import urllib.error
import urllib.parse
import urllib.request

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPANY = "Copilot Demo"
ABBR = "CPD"
CURRENCY = "MYR"
random.seed(20261102)


def read_env(path):
    env = {}
    with open(path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key] = value
    return env


ENV = read_env(os.path.join(APP_ROOT, ".env"))
BASE = ENV["ERPNEXT_URL"].rstrip("/")
HEADERS = {
    "Authorization": ENV["ERPNEXT_AUTH_HEADER"],
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def call(path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, headers=HEADERS, method=method or ("POST" if data else "GET")
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            parsed = json.loads(body)
            message = parsed.get("exception") or parsed.get("_server_messages") or body
        except json.JSONDecodeError:
            message = body
        raise RuntimeError(f"{path} -> {exc.code}: {str(message)[:600]}") from None


def exists(doctype, name):
    res = call(
        "/api/method/frappe.client.get_list?"
        + urllib.parse.urlencode(
            {
                "doctype": doctype,
                "filters": json.dumps([[doctype, "name", "=", name]]),
                "fields": json.dumps(["name"]),
                "limit_page_length": 1,
            }
        )
    )
    return bool(res.get("message"))


def insert(doc):
    return call("/api/method/frappe.client.insert", {"doc": json.dumps(doc)})["message"]


def submit(doc):
    created = insert(doc)
    call("/api/method/frappe.client.submit", {"doc": json.dumps(created)})
    return created


def ensure_company():
    if not exists("Company", COMPANY):
        insert(
            {
                "doctype": "Company",
                "company_name": COMPANY,
                "abbr": ABBR,
                "default_currency": CURRENCY,
                "country": "Malaysia",
                "chart_of_accounts": "Standard",
                "create_chart_of_accounts_based_on": "Standard Template",
            }
        )
        print(f"created company {COMPANY}")
    else:
        print(f"company {COMPANY} already exists")
    warehouses = call(
        "/api/method/frappe.client.get_list?"
        + urllib.parse.urlencode(
            {
                "doctype": "Warehouse",
                "filters": json.dumps([["Warehouse", "company", "=", COMPANY]]),
                "fields": json.dumps(["name", "is_group"]),
                "limit_page_length": 50,
            }
        )
    )["message"]
    leaf = [w["name"] for w in warehouses if not w["is_group"]]
    default = next((w for w in leaf if w.startswith("Stores")), leaf[0] if leaf else None)
    if not default:
        raise RuntimeError("No warehouse was created for the demo company.")
    return default


ITEMS = [
    ("CPD-COFFEE-1KG", "Copilot Demo Arabica Beans 1kg", 34.0, 6, 10, 20),
    ("CPD-TEA-500G", "Copilot Demo Green Tea 500g", 22.0, 4, 7, 15),
    ("CPD-CUP-12", "Copilot Demo Paper Cups (12 pack)", 9.5, 10, 10, 40),
    ("CPD-SYRUP-VAN", "Copilot Demo Vanilla Syrup 750ml", 18.0, 5, 14, 12),
    ("CPD-MILK-1L", "Copilot Demo Oat Milk 1L", 12.5, 8, 2, 24),
    ("CPD-CHOC-1KG", "Copilot Demo Cocoa Powder 1kg", 41.0, 3, 21, 8),
    ("CPD-LID-100", "Copilot Demo Cup Lids (100 pack)", 7.0, 6, 10, 30),
    ("CPD-NAPKIN-500", "Copilot Demo Napkins (500 pack)", 5.5, 12, 5, 50),
]

SUPPLIERS = [
    ("Copilot Demo Roasters", "Demo Goods"),
    ("Copilot Demo Packaging", "Demo Goods"),
    ("Copilot Demo Dairy Co", "Demo Goods"),
]

SUPPLIER_MAP = {
    "CPD-COFFEE-1KG": "Copilot Demo Roasters",
    "CPD-TEA-500G": "Copilot Demo Roasters",
    "CPD-CHOC-1KG": "Copilot Demo Roasters",
    "CPD-SYRUP-VAN": "Copilot Demo Roasters",
    "CPD-CUP-12": "Copilot Demo Packaging",
    "CPD-LID-100": "Copilot Demo Packaging",
    "CPD-NAPKIN-500": "Copilot Demo Packaging",
    "CPD-MILK-1L": "Copilot Demo Dairy Co",
}

CUSTOMERS = [
    "Copilot Demo Cafe",
    "Copilot Demo Bistro",
    "Copilot Demo Hotel",
    "Copilot Demo Office Pantry",
]

VELOCITY = {
    "CPD-COFFEE-1KG": 1.6,
    "CPD-TEA-500G": 0.9,
    "CPD-CUP-12": 3.4,
    "CPD-SYRUP-VAN": 0.55,
    "CPD-MILK-1L": 2.2,
    "CPD-CHOC-1KG": 0.3,
    "CPD-LID-100": 2.8,
    "CPD-NAPKIN-500": 1.1,
}

OPENING_STOCK = {
    "CPD-COFFEE-1KG": 26,
    "CPD-TEA-500G": 30,
    "CPD-CUP-12": 62,
    "CPD-SYRUP-VAN": 9,
    "CPD-MILK-1L": 18,
    "CPD-CHOC-1KG": 4,
    "CPD-LID-100": 80,
    "CPD-NAPKIN-500": 120,
}


def ensure_items():
    created = []
    for code, name, rate, safety, lead, min_order in ITEMS:
        if exists("Item", code):
            continue
        insert(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": name,
                "item_group": "Products",
                "stock_uom": "Nos",
                "is_stock_item": 1,
                "is_sales_item": 1,
                "is_purchase_item": 1,
                "standard_rate": rate,
                "last_purchase_rate": rate,
                "safety_stock": safety,
                "lead_time_days": lead,
                "min_order_qty": min_order,
                "description": "Seeded by erpnext-copilot for the purchasing demo.",
            }
        )
        created.append(code)
    print(f"items created: {len(created)}")


def ensure_suppliers():
    for name, group in SUPPLIERS:
        if not exists("Supplier", name):
            insert(
                {
                    "doctype": "Supplier",
                    "supplier_name": name,
                    "supplier_group": group,
                    "supplier_type": "Company",
                    "country": "Malaysia",
                }
            )
    print("suppliers ready")


def ensure_item_suppliers():
    for code, supplier in SUPPLIER_MAP.items():
        res = call(
            "/api/method/frappe.client.get_list?"
            + urllib.parse.urlencode(
                {
                    "doctype": "Item Supplier",
                    "filters": json.dumps(
                        [["Item Supplier", "parent", "=", code], ["Item Supplier", "supplier", "=", supplier]]
                    ),
                    "fields": json.dumps(["name"]),
                    "limit_page_length": 1,
                }
            )
        )["message"]
        if res:
            continue
        call(
            "/api/method/frappe.client.set_value",
            {
                "doctype": "Item",
                "name": code,
                "fieldname": "supplier_items",
                "value": [{"supplier": supplier, "supplier_part_no": f"{code}-{supplier.split()[-1]}"}],
            },
        )
    print("default suppliers linked")


def ensure_customers():
    for name in CUSTOMERS:
        if not exists("Customer", name):
            insert(
                {
                    "doctype": "Customer",
                    "customer_name": name,
                    "customer_type": "Company",
                    "customer_group": "Individual",
                    "territory": "Rest Of The World",
                }
            )
    print("customers ready")


def opening_stock(warehouse):
    marker = f"Copilot Demo opening stock - {COMPANY}"
    count = call(
        "/api/method/frappe.client.get_count?"
        + urllib.parse.urlencode(
            {
                "doctype": "Bin",
                "filters": json.dumps([["Bin", "warehouse", "=", warehouse], ["Bin", "actual_qty", ">", 0]]),
            }
        )
    )["message"]
    if count:
        print("opening stock already posted")
        return
    items = []
    for code, qty in OPENING_STOCK.items():
        rate = next(i[2] for i in ITEMS if i[0] == code)
        items.append({"item_code": code, "qty": qty, "t_warehouse": warehouse, "basic_rate": rate})
    submit(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": COMPANY,
            "remarks": marker,
            "posting_date": (datetime.date.today() - datetime.timedelta(days=91)).isoformat(),
            "set_posting_time": 1,
            "items": items,
        }
    )
    print("opening stock posted")


def sales_invoice_history():
    marker_count = call(
        "/api/method/frappe.client.get_count?"
        + urllib.parse.urlencode(
            {
                "doctype": "Sales Invoice",
                "filters": json.dumps(
                    [["Sales Invoice", "company", "=", COMPANY], ["Sales Invoice", "docstatus", "=", 1]]
                ),
            }
        )
    )["message"]
    if marker_count >= 40:
        print(f"sales history already present ({marker_count} invoices)")
        return

    today = datetime.date.today()
    codes = list(VELOCITY.keys())
    invoice_no = 0
    for day_offset in range(90, -1, -1):
        posting = today - datetime.timedelta(days=day_offset)
        if posting.weekday() == 6:
            continue
        for code in codes:
            expected = VELOCITY[code]
            qty = 0
            while random.random() < expected:
                qty += 1
                if qty > 4:
                    break
            if qty == 0:
                continue
            invoice_no += 1
            rate = next(i[2] for i in ITEMS if i[0] == code)
            customer = random.choice(CUSTOMERS)
            due = posting + datetime.timedelta(days=30)
            submit(
                {
                    "doctype": "Sales Invoice",
                    "company": COMPANY,
                    "customer": customer,
                    "posting_date": posting.isoformat(),
                    "due_date": due.isoformat(),
                    "set_posting_time": 1,
                    "currency": CURRENCY,
                    "conversion_rate": 1,
                    "items": [{"item_code": code, "qty": qty, "rate": rate}],
                }
            )
    print(f"created {invoice_no} demo sales invoices over 90 days")


def secondary_scenarios(warehouse):
    today = datetime.date.today()

    draft_marker = "Copilot Demo stale draft"
    res = call(
        "/api/method/frappe.client.get_list?"
        + urllib.parse.urlencode(
            {
                "doctype": "Sales Order",
                "filters": json.dumps([["Sales Order", "company", "=", COMPANY]]),
                "fields": json.dumps(["name"]),
                "limit_page_length": 1,
            }
        )
    )["message"]
    if not res:
        for idx, (code, qty) in enumerate(
            [("CPD-COFFEE-1KG", 5), ("CPD-CUP-12", 12), ("CPD-MILK-1L", 6)]
        ):
            insert(
                {
                    "doctype": "Sales Order",
                    "company": COMPANY,
                    "customer": CUSTOMERS[idx % len(CUSTOMERS)],
                    "transaction_date": (today - datetime.timedelta(days=6 + idx)).isoformat(),
                    "delivery_date": (today + datetime.timedelta(days=3)).isoformat(),
                    "currency": CURRENCY,
                    "conversion_rate": 1,
                    "order_type": "Sales",
                    "items": [
                        {
                            "item_code": code,
                            "qty": qty,
                            "rate": next(i[2] for i in ITEMS if i[0] == code),
                            "warehouse": warehouse,
                            "delivery_date": (today + datetime.timedelta(days=3)).isoformat(),
                        }
                    ],
                    "remarks": draft_marker,
                }
            )
        print("created stale draft sales orders")

        submit(
            {
                "doctype": "Sales Order",
                "company": COMPANY,
                "customer": CUSTOMERS[0],
                "transaction_date": (today - datetime.timedelta(days=2)).isoformat(),
                "delivery_date": (today + datetime.timedelta(days=4)).isoformat(),
                "currency": CURRENCY,
                "conversion_rate": 1,
                "order_type": "Sales",
                "items": [
                    {
                        "item_code": "CPD-CHOC-1KG",
                        "qty": 60,
                        "rate": 41.0,
                        "warehouse": warehouse,
                        "delivery_date": (today + datetime.timedelta(days=4)).isoformat(),
                    }
                ],
                "remarks": "Copilot Demo stock-risk order",
            }
        )
        print("created submitted SO with a stock-risk line")

    overdue_marker = "Copilot Demo overdue"
    res = call(
        "/api/method/frappe.client.get_list?"
        + urllib.parse.urlencode(
            {
                "doctype": "Sales Invoice",
                "filters": json.dumps(
                    [
                        ["Sales Invoice", "company", "=", COMPANY],
                        ["Sales Invoice", "due_date", "<", today.isoformat()],
                        ["Sales Invoice", "outstanding_amount", ">", 0],
                    ]
                ),
                "fields": json.dumps(["name"]),
                "limit_page_length": 1,
            }
        )
    )["message"]
    if not res:
        submit(
            {
                "doctype": "Sales Invoice",
                "company": COMPANY,
                "customer": CUSTOMERS[1],
                "posting_date": (today - datetime.timedelta(days=45)).isoformat(),
                "due_date": (today - datetime.timedelta(days=15)).isoformat(),
                "set_posting_time": 1,
                "currency": CURRENCY,
                "conversion_rate": 1,
                "items": [{"item_code": "CPD-COFFEE-1KG", "qty": 4, "rate": 34.0}],
                "remarks": overdue_marker,
            }
        )
        print("created an overdue invoice")

    dn_marker = "Copilot Demo delivered not invoiced"
    res = call(
        "/api/method/frappe.client.get_list?"
        + urllib.parse.urlencode(
            {
                "doctype": "Delivery Note",
                "filters": json.dumps(
                    [["Delivery Note", "company", "=", COMPANY], ["Delivery Note", "per_billed", "<", 100]]
                ),
                "fields": json.dumps(["name"]),
                "limit_page_length": 1,
            }
        )
    )["message"]
    if not res:
        submit(
            {
                "doctype": "Delivery Note",
                "company": COMPANY,
                "customer": CUSTOMERS[2],
                "posting_date": today.isoformat(),
                "set_posting_time": 1,
                "currency": CURRENCY,
                "conversion_rate": 1,
                "items": [{"item_code": "CPD-TEA-500G", "qty": 3, "rate": 22.0, "warehouse": warehouse}],
                "remarks": dn_marker,
            }
        )
        print("created a delivery note that is not invoiced")


def main():
    warehouse = ensure_company()
    ensure_items()
    ensure_suppliers()
    ensure_item_suppliers()
    ensure_customers()
    opening_stock(warehouse)
    sales_invoice_history()
    secondary_scenarios(warehouse)
    print("Seed complete.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"SEED FAILED: {exc}", file=sys.stderr)
        sys.exit(1)



