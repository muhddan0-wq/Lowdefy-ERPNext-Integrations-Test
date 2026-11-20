"""Top up Copilot Demo sales so the last 30/60/90-day windows have history.

Only fills days that have no sales invoice yet, so re-running is safe.
Run: python scripts/top_up_recent_sales.py
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
CURRENCY = "MYR"
DAYS = 34
random.seed(7)

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
RATES = {
    "CPD-COFFEE-1KG": 34.0,
    "CPD-TEA-500G": 22.0,
    "CPD-CUP-12": 9.5,
    "CPD-SYRUP-VAN": 18.0,
    "CPD-MILK-1L": 12.5,
    "CPD-CHOC-1KG": 41.0,
    "CPD-LID-100": 7.0,
    "CPD-NAPKIN-500": 5.5,
}
CUSTOMERS = ["Copilot Demo Cafe", "Copilot Demo Bistro", "Copilot Demo Hotel", "Copilot Demo Office Pantry"]


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
        raise RuntimeError(f"{path} -> {exc.code}: {str(message)[:400]}") from None


def existing_days():
    since = (datetime.date.today() - datetime.timedelta(days=DAYS)).isoformat()
    rows = call(
        "/api/method/frappe.client.get_list?"
        + urllib.parse.urlencode(
            {
                "doctype": "Sales Invoice",
                "fields": json.dumps(["posting_date"]),
                "filters": json.dumps(
                    [
                        ["Sales Invoice", "company", "=", COMPANY],
                        ["Sales Invoice", "docstatus", "=", 1],
                        ["Sales Invoice", "posting_date", ">=", since],
                    ]
                ),
                "limit_page_length": 1000,
            }
        )
    )["message"]
    return {row["posting_date"] for row in rows}


def main():
    have = existing_days()
    today = datetime.date.today()
    created = 0
    for offset in range(DAYS, -1, -1):
        day = today - datetime.timedelta(days=offset)
        if day.isoformat() in have or day.weekday() == 6:
            continue
        for item_code, expected in VELOCITY.items():
            qty = 0
            while random.random() < expected:
                qty += 1
                if qty >= 4:
                    break
            if qty == 0:
                continue
            customer = random.choice(CUSTOMERS)
            doc = {
                "doctype": "Sales Invoice",
                "company": COMPANY,
                "customer": customer,
                "posting_date": day.isoformat(),
                "due_date": (day + datetime.timedelta(days=30)).isoformat(),
                "set_posting_time": 1,
                "currency": CURRENCY,
                "conversion_rate": 1,
                "items": [{"item_code": item_code, "qty": qty, "rate": RATES[item_code]}],
            }
            created_doc = call("/api/method/frappe.client.insert", {"doc": json.dumps(doc)})["message"]
            call("/api/method/frappe.client.submit", {"doc": json.dumps(created_doc)})
            created += 1
    print(f"created {created} sales invoices for the last {DAYS} days")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"TOP-UP FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
