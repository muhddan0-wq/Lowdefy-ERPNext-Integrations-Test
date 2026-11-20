# 3-Minute Demo Script

A non-technical walkthrough of ERPNext Copilot.

---

**0:00 — Open the app (30s)**

- Open http://localhost:3010.
- "This is **ERPNext Copilot**. It sits on top of our ERP system and tells us
  *what needs attention* and *what to buy* — without us hunting through ERPNext."

---

**0:30 — Exceptions Inbox (60s)**

- Click **Exceptions**.
- "This is the **Exceptions Inbox** — a prioritised to-do list of problems:
  stale draft sales orders, invoices that are overdue, deliveries not yet billed,
  and orders at risk because we don't have enough stock."
- Point at a row: "Each row is one issue. One click and we can act on it — but
  the app always asks for confirmation first, and records who did what."
- Switch the **Company** dropdown to `SHRDC` and back to `Copilot Demo` to show
  it works per company.

---

**1:30 — Purchasing Assistant (60s)**

- Click **Purchasing**.
- "This is the **Purchasing Assistant**. It looks at how fast each item is
  selling and compares that with what we have in stock, to suggest what to
  reorder."
- Point at a supplier group: "Suggestions are grouped by **supplier**, so we can
  place one order per supplier instead of many."
- Click **Create draft PO** on one supplier: "It only creates a **draft**
  Purchase Order — nothing is submitted. A real buyer reviews it in ERPNext
  before it goes anywhere."

---

**2:30 — Audit Log & Settings (30s)**

- Click **Audit Log**: "Everything we just did is written down here — who did it,
  what they did, and whether it worked. Nothing happens silently."
- Click **Settings**: "These are the rules the app uses — how many days of sales
  to look at, lead time, safety stock. We can tune them here without touching any
  code."

---

**3:00 — Wrap up**

- "In short: ERPNext Copilot turns a busy ERP into a short, prioritised list of
  decisions — what to fix and what to buy — with an audit trail for every action."
