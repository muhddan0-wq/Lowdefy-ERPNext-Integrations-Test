"""Make the Copilot Demo data demo-quality.

- Pays off demo sales invoices except three, so the overdue queue stays small.
- Replaces the draft delivery note the first seed attempt left behind.

Run: python scripts/settle_demo_invoices.py
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPANY = "Copilot Demo"
CURRENCY = "MYR"
KEEP_UNPAID = 3


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


def call(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=HEADERS, method="POST" if data else "GET")
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
        raise RuntimeError(f"{path} -> {exc.code}: {str(message)[:500]}") from None


def get_list(doctype, fields, filters, limit=500, order_by=None):
    params = {
        "doctype": doctype,
        "fields": json.dumps(fields),
        "filters": json.dumps(filters),
        "limit_page_length": limit,
    }
    if order_by:
        params["order_by"] = order_by
    return call("/api/method/frappe.client.get_list?" + urllib.parse.urlencode(params))["message"]


def settle(customer, invoices, accounts):
    references = [
        {"reference_doctype": "Sales Invoice", "reference_name": inv["name"], "allocated_amount": inv["outstanding_amount"]}
        for inv in invoices
    ]
    total = sum(inv["outstanding_amount"] for inv in invoices)
    doc = {
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "company": COMPANY,
        "posting_date": datetime.date.today().isoformat(),
        "party_type": "Customer",
        "party": customer,
        "paid_from": accounts["receivable"],
        "paid_to": accounts["cash"],
        "paid_amount": total,
        "received_amount": total,
        "reference_no": f"CPD-SETTLE-{customer.replace(' ', '-')[:20]}",
        "reference_date": datetime.date.today().isoformat(),
        "references": references,
    }
    created = call("/api/method/frappe.client.insert", {"doc": json.dumps(doc)})["message"]
    call("/api/method/frappe.client.submit", {"doc": json.dumps(created)})
    return total


def main():
    accounts = {"receivable": f"Debtors - CPD", "cash": f"Cash - CPD"}

    # Remove the draft delivery note the first seed attempt left behind.
    drafts = get_list(
        "Delivery Note",
        ["name"],
        [["Delivery Note", "company", "=", COMPANY], ["Delivery Note", "docstatus", "=", 0]],
    )
    for dn in drafts:
        call("/api/method/frappe.client.delete", {"doctype": "Delivery Note", "name": dn["name"]})
        print(f"deleted leftover draft delivery note {dn['name']}")

    open_invoices = get_list(
        "Sales Invoice",
        ["name", "customer", "outstanding_amount", "posting_date"],
        [
            ["Sales Invoice", "company", "=", COMPANY],
            ["Sales Invoice", "docstatus", "=", 1],
            ["Sales Invoice", "outstanding_amount", ">", 0],
        ],
        limit=1000,
        order_by="posting_date asc",
    )
    print(f"{len(open_invoices)} unpaid demo invoices")

    keep = open_invoices[:KEEP_UNPAID]
    keep_names = {inv["name"] for inv in keep}
    to_pay = [inv for inv in open_invoices if inv["name"] not in keep_names]

    by_customer = {}
    for inv in to_pay:
        by_customer.setdefault(inv["customer"], []).append(inv)

    for customer, invoices in by_customer.items():
        total = settle(customer, invoices, accounts)
        print(f"settled {len(invoices)} invoices for {customer} (MYR {total:.2f})")

    if len(keep) < KEEP_UNPAID:
        print(f"WARNING: only {len(keep)} invoices left unpaid.", file=sys.stderr)

    # A delivery note that has not been invoiced, dated today to avoid
    # backdating stock movements.
    existing = get_list(
        "Delivery Note",
        ["name"],
        [
            ["Delivery Note", "company", "=", COMPANY],
            ["Delivery Note", "docstatus", "=", 1],
            ["Delivery Note", "per_billed", "<", 100],
        ],
    )
    if not existing:
        bins = get_list(
            "Bin",
            ["warehouse"],
            [["Bin", "item_code", "=", "CPD-TEA-500G"], ["Bin", "actual_qty", ">", 0]],
        )
        if not bins:
            raise RuntimeError("No stock bin for CPD-TEA-500G - run the seeder first.")
        warehouse = bins[0]["warehouse"]
        doc = {
            "doctype": "Delivery Note",
            "company": COMPANY,
            "customer": "Copilot Demo Hotel",
            "posting_date": datetime.date.today().isoformat(),
            "currency": CURRENCY,
            "conversion_rate": 1,
            "items": [{"item_code": "CPD-TEA-500G", "qty": 3, "rate": 22.0, "warehouse": warehouse}],
        }
        created = call("/api/method/frappe.client.insert", {"doc": json.dumps(doc)})["message"]
        call("/api/method/frappe.client.submit", {"doc": json.dumps(created)})
        print(f"created uninvoiced delivery note {created['name']}")

    print("Settlement complete.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"SETTLE FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

