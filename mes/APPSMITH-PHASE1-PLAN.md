# Phase 1 plan: Work Orders and Finite Scheduling in Appsmith

**Scope:** the two MES core functions that ERPNext already provides: **work order management** and **scheduling**. Appsmith is the screen layer, and ERPNext stays the engine that holds the data and the logic.

**Out of scope for phase 1:** OEE, downtime, quality, recipes and machine sensors. These come later and reuse the same connection.

**Demo data already in place:** company *Voltra Power Tools Sdn Bhd*, plant *P1 Shah Alam* (12 workstations with shifts and holidays), 17 BOMs, and a forward plan of 17 work orders and 32 scheduled job cards.

---

## 1. How the pieces fit

```
 Planner / Supervisor / Operator  (browser or tablet on the factory Wi-Fi)
                 |
                 v
        Appsmith  (screens only, Docker on this PC, port 8081)
                 |   REST calls, server-side, using an API key
                 v
        ERPNext  (http://localhost:8000)
          - Work Orders, Job Cards, Production Plan
          - Finite capacity planning (shifts, holidays, workstation capacity)
          - Small "MES API" server scripts for validated scheduling actions
```

**The rule for every screen:** Appsmith never decides anything about stock, costs or capacity. It asks ERPNext and shows the answer. Anything that changes the schedule goes through an ERPNext API that validates first.

---

## 2. Setup

| Step | What | Done when |
|---|---|---|
| S1 | Run Appsmith Community Edition in Docker:<br>`docker run -d --name appsmith -p 8081:80 -v appsmith-stacks:/appsmith-stacks --restart unless-stopped appsmith/appsmith-ce`<br>Port 80 is already used on this PC, so Appsmith uses 8081. | `http://localhost:8081` opens and an admin account is created |
| S2 | Create a dedicated ERPNext user `appsmith-mes@local.test` with Manufacturing User, Manufacturing Manager and Stock User roles. Add a User Permission restricting it to Company = Voltra. Generate its API key and secret. Never use Administrator. | The key can read a Voltra Work Order and cannot see SHRDC records |
| S3 | In Appsmith, add a REST API datasource "ERPNext" with base URL `http://host.docker.internal:8000` and header `Authorization: token <key>:<secret>`. Inside the container, `localhost` means Appsmith itself, so it can't be used here. | A test query `GET /api/resource/Workstation` returns the 12 P1 workstations |
| S4 | Turn on Appsmith's "Use same-origin" defaults and keep every ERPNext call server-side (Appsmith's default for REST datasources). | The key never appears in browser network calls |

---

## 3. ERPNext services Appsmith will use

All of these already exist in ERPNext v16 (checked on this instance).

### Work orders

| Need | ERPNext call |
|---|---|
| List work orders (filter by status, item, date) | `GET /api/resource/Work Order?filters=[["company","=","Voltra Power Tools Sdn Bhd"]]&fields=[...]` |
| One work order with operations and materials | `GET /api/resource/Work Order/{name}` (includes `operations` and `required_items`) |
| Plan from demand (multi-level, with sub-assemblies) | New `mes_create_plan` API (section 4), which wraps Production Plan → sub-assemblies → work orders |
| Create a single work order | `POST /api/resource/Work Order`, then submit (`PUT … {"docstatus": 1}`) |
| Stop / resume | `POST /api/method/erpnext.manufacturing.doctype.work_order.work_order.stop_unstop` `{work_order, status}` |
| Close | `POST /api/method/erpnext.manufacturing.doctype.work_order.work_order.close_work_order` |
| Issue materials / finish | `POST …work_order.make_stock_entry` `{work_order_id, purpose: "Material Transfer for Manufacture" or "Manufacture", qty}`, then insert and submit the returned entry |
| Stock check for components | `GET /api/resource/Bin?filters=[["warehouse","=","P1 Stores - VPT"]]` |

### Scheduling and job cards

| Need | ERPNext call |
|---|---|
| Automatic finite schedule | Already happens when a work order is **submitted**: ERPNext creates one job card per operation and slots it into workstation working hours, holidays and capacity (Manufacturing Settings: capacity planning on, overtime off, 60-day horizon) |
| Schedule board data | Query report `MES Schedule Board`, via `POST /api/method/frappe.desk.query_report.run {report_name}` |
| Workstations, shifts, holidays | `GET /api/resource/Workstation/{name}` (`working_hours`, `holiday_list`, `production_capacity`) |
| Job card actions (phase 1b) | `POST /api/v2/document/Job Card/{name}/method/start_timer` (also `pause_job`, `resume_job`, `complete_job_card`), all whitelisted |

---

## 4. Small ERPNext additions (server scripts)

ERPNext covers the core, but Appsmith needs a few validated "one-call" actions. These go in as **API Server Scripts**: server scripts are already enabled on this site, so no custom app is needed. Each one checks the caller's role before doing anything.

| API | What it does | Why it's needed |
|---|---|---|
| `mes_create_plan` | Input: list of {finished good, qty, start date}. Creates a Production Plan with sub-assemblies, submits it, makes the work orders, sets the P1 warehouses, and submits them in BOM order (sub-assemblies first). Each parent starts when its children finish. Returns work orders and planned dates. | Turns the 6-step ERPNext flow into one button. The logic already exists in `mes/seed_mes.py` (`demo_plan`) |
| `mes_reschedule_job_card` | Moves a job card to a new start time or workstation. **Validates** that the workstation type matches, the time falls inside working hours, it's not a holiday, it doesn't exceed workstation capacity, and it isn't before the previous operation ends. It then rewrites the scheduled time blocks. | Needed for drag-and-drop on the Gantt |
| `mes_schedule_conflicts` | Returns every workstation slot booked over capacity. This is the check in `seed_mes.py` (`schedule_conflicts`), moved server-side. | ERPNext's own planner can double-book in edge cases, so the board shows a warning banner |
| `mes_workstation_load` | Scheduled minutes ÷ available minutes per workstation per day. | Feeds the capacity heat-map |

**Existing script to replace:** this site already has an API server script `planner_shift_job_card`, added on 11 Nov by Administrator. It moves job card time blocks with direct database writes and does **no** checks for overlap, shifts or capacity. It isn't tied to any screen; it's just an API. No project in this folder calls it, but the ERPNext project on `F:\ERPNEXT\erpnextcomp_demo` might.

Phase 1 redoes it properly as `mes_reschedule_job_card`, called by the Appsmith Gantt. The validation stays in ERPNext rather than in Appsmith's JavaScript, so no screen (Appsmith, ERPNext desk or a future Node-RED flow) can save an invalid schedule. Leave the old script in place until it's confirmed unused, then disable it.

---

## 5. Appsmith screens

| # | Page | Users | Contents | Calls |
|---|---|---|---|---|
| 1 | **Work Orders** | Planner, supervisor | KPI tiles (Not Started / In Process / Completed / Late), filterable table (item, qty, produced, planned start and end, status), row click opens detail | Work Order list |
| 2 | **Work Order Detail** | Planner, supervisor | Header and progress bar. Operations table (operation, workstation, scheduled start and end, job card status). Materials table (required, transferred, in stock, short). Buttons: Stop/Resume, Close, Issue Materials, Finish | WO get, Bin, `stop_unstop`, `close_work_order`, `make_stock_entry` |
| 3 | **New Plan** | Planner | Pick finished goods, quantities and a start date. Preview the sub-assemblies and quantities that will be made, then press Create plan. Shows the resulting work orders and finish date. | `mes_create_plan` |
| 4 | **Schedule Board** | Planner, supervisor | Gantt: one row per workstation, one bar per job card, coloured by status. Date range and workstation-type filters. Conflict banner. Drag a bar to reschedule (with a confirm dialog) and see ERPNext's validation message if it's refused. | `MES Schedule Board`, `mes_schedule_conflicts`, `mes_reschedule_job_card` |
| 5 | **Capacity** | Planner | Heat-map table of workstations × days with load %, with red above 100% | `mes_workstation_load` |
| 6 | **Workstation Queue** (phase 1b) | Operator | Choose a workstation and see today's job cards in order, with work instructions. Start / Pause / Complete with good qty. | Job card list, `start_timer` / `pause_job` / `complete_job_card` |

**Gantt in Appsmith:** Appsmith has no built-in Gantt widget. Use Appsmith's **Custom Widget** (HTML/JS inside the app) with an open-source timeline library such as *vis-timeline* or *frappe-gantt*. The widget receives the schedule rows as input and emits an event when a bar is dropped, which triggers `mes_reschedule_job_card`.

---

## 6. How finite scheduling works in phase 1

| Level | What | Who does it | Phase |
|---|---|---|---|
| 1. Automatic slotting | On work order submit, each operation is placed in the first free slot on a workstation of the right type, respecting shifts (08:00–12:00, 13:00–17:00), weekends, Malaysian holidays and capacity. Sub-assemblies are scheduled before the products that need them. | ERPNext (native) | **1** (already working) |
| 2. Visibility | Gantt, capacity heat-map, conflict banner | Appsmith + ERPNext APIs | **1** |
| 3. Manual rescheduling | Drag and drop with server-side validation | Appsmith + `mes_reschedule_job_card` | **1** |
| 4. Rule-based re-sequencing | Re-order by due date or priority. "Reschedule from now" when jobs run late. A frozen window (for example, no changes within 2 days). | New ERPNext API | Later |
| 5. Optimisation | Minimise changeovers, balance load across parallel workstations | Custom scheduler | Later |

ERPNext's native scheduler takes the first free slot in the order work orders are submitted. It doesn't optimise the sequence and doesn't push later jobs back when one overruns. Levels 2 and 3 cover this for phase 1 by making the schedule visible and editable, and Level 4 is the natural next step.

---

## 7. Build order

| Milestone | Deliverable | Done when |
|---|---|---|
| M0 | Setup S1–S4 | Appsmith reaches ERPNext with the dedicated key |
| M1 | Pages 1 and 2, read-only | All 17 forward work orders are listed with correct status, and the detail page shows the operations and materials |
| M2 | Page 4 read-only, plus Page 5 | The Gantt shows all 32 job cards on the correct workstations and times, and the conflict check returns 0 |
| M3 | `mes_create_plan` + Page 3 | Creating a plan for 10 drills produces the sub-assembly and drill work orders, scheduled within shifts with no conflicts |
| M4 | Work order actions on Page 2 | Stop/Resume and Close work. Issue and Finish post stock entries visible in ERPNext |
| M5 | `mes_reschedule_job_card` + drag-and-drop | A valid move is saved. An invalid move (outside a shift, overlap, or before the previous operation) is refused with a clear message |
| M6 (1b) | Page 6 Workstation Queue | An operator can start and complete a job card from a tablet, and the Gantt bar changes status |

Each milestone is checked in ERPNext through the REST API, not just on the Appsmith screen.

---

## 8. Security and housekeeping

- A dedicated API user restricted to Voltra, with no Administrator key in Appsmith.
- Every server script checks `frappe.get_roles()` for Manufacturing User or Manager, and validates every input.
- Appsmith login for planners and operators, with per-page access by role (Appsmith workspace roles).
- Back up the ERPNext site before deploying the server scripts. Keep the scripts in this repo (`mes/server_scripts/`) so they can be reinstalled on another site.

---

## 9. Open points

- **Time zone:** check the ERPNext system time zone and keep Appsmith in Asia/Kuala_Lumpur, so Gantt times match job cards.
- **Licence:** Appsmith Community Edition is free and self-hosted. Granular role-based access per page is stronger in the paid edition, so check this if it matters.
- **History data:** the W45–W47 simulated history (for OEE later) is still waiting on the W45 reset you approved. Phase 1 doesn't need it, because it uses the forward plan.
