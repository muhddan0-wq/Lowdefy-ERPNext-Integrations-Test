# MES in a box: site template

Seeds an ERPNext v16 site with a complete, schedulable manufacturing setup for a demo
power-tools maker, **Voltra Power Tools Sdn Bhd**, at plant **P1 Shah Alam**.

## Files

| File | What it holds | Shared across sites? |
|---|---|---|
| `products.yaml` | UOMs, cost components, processes, operations, suppliers, raw materials (with buy prices), sub-assemblies, finished goods (with sell prices), BOMs and routings | Yes |
| `sites/p1-shah-alam.yaml` | Company, calendar (shifts, weekly off, public holidays), workstations per process, demo production plan | One file per site |
| `seed_mes.py` | Loader. Runs inside the Frappe bench, is idempotent and only creates what is missing | — |
| `run-seed.ps1` | Copies the files into the bench container and runs the loader | — |

## Run

```powershell
.\mes\run-seed.ps1                       # masters + BOMs + demo plan (work orders, job cards)
.\mes\run-seed.ps1 -NoPlan               # masters + BOMs only
.\mes\run-seed.ps1 -ResetPlan            # delete this company's demo plan, work orders, job cards and re-plan
.\mes\run-seed.ps1 -Site p2-penang       # seed another site file
```

At the end the loader prints costs and a **schedule conflict check** (any workstation booked over its capacity).

## What gets created (site P1)

- **Products**: 3 finished goods, 14 sub-assemblies and 42 raw materials, with 17 BOMs (multi-level: raw material → armature/stator → motor → finished good).

  | Finished good | Sell price (MYR) | BOM cost (MYR) |
  |---|---|---|
  | FG-DRL-800 13mm Electric Drill 800W | 289 | 176.34 |
  | FG-RH-800 SDS-Plus Rotary Hammer Drill 800W | 529 | 233.18 |
  | FG-CS-1400 185mm Circular Saw 1400W | 459 | 245.71 |

  The 800W motor, armature, stator and 10A harness are shared by the drill and the rotary hammer.
- **Plant**: Plant Floor `P1 Shah Alam Plant`, warehouses `P1 Stores / P1 Work In Progress / P1 Finished Goods`, and 12 workstations across 8 site-scoped workstation types. Each type's hour rate is built from Labour, Electricity, Depreciation, Maintenance and Consumables.
- **Calendar**: two shifts (08:00–12:00, 13:00–17:00), Saturday and Sunday off, and Malaysian public holidays for 2026–2027.
- **Finite capacity**: capacity planning is on, overtime and holiday production are off, and the look-ahead is 60 days. Job cards are slotted into real workstation hours, and the oven runs 20 units in parallel.
- **Demo plan**: a Production Plan for 40 drills, 25 hammers and 30 saws, giving 17 work orders and 32 job cards. Sub-assembly work orders are scheduled before the products that consume them.

## Adding a second site

1. Copy `sites/p1-shah-alam.yaml` to e.g. `sites/p2-penang.yaml`.
2. Change `code` (e.g. `P2`), `name`, the workstation list and the calendar.
3. Choose a company:
   - **Same company**: keep the same `company` block. The site gets its own warehouses, plant floor, workstation types and site-specific BOMs. The first site's BOMs stay the default, so pick the P2 BOM on P2 work orders.
   - **Separate company** (cleaner accounting): give it a new `name`/`abbr`.
4. Run `.\mes\run-seed.ps1 -Site p2-penang`.

Workstation types are prefixed with the site code on purpose. ERPNext assigns job cards to *any* workstation of the requested type, so shared types would let P1 jobs land on P2 machines.

## Ready for machine data later (not built yet)

Operators currently use job cards (start, pause, complete, enter quantities). The data model already has the hooks a machine gateway would need:

- **Workstation codes** (`P1-IMM-01`, …) are the stable machine IDs.
- **Workstation `status`** (Production / Off / Idle / Problem / Maintenance / Setup) is shown on the Plant Floor page.
- **Downtime Entry** (workstation, from/to, stop reason).
- **Job Card time logs and completed quantity.**

Later, a gateway (Node-RED is already running at `:1880`) reads PLC or sensor signals and writes these through the ERPNext REST API. The ERP side does not need to change.

## Known limits

- ERPNext's built-in capacity planner is simple: first-free-slot, per workstation, in order of submission. It does not optimise sequence or changeovers, and it can double-book a workstation when two job cards spill into the same next shift. Separate work orders for the same sub-assembly triggered this, which is why the demo plan combines sub-assembly demand. The conflict check in the report catches any recurrence. A real finite scheduler (sequence optimisation, drag-and-drop Gantt) would be a custom layer on top.
- The demo has no opening stock, so job cards can be started but material transfers will need stock (a Material Receipt) first.
