# MES Phase 1: build report (24 Nov 2026)

The engine is ERPNext v16 (site `frontend`, company Voltra Power Tools Sdn Bhd only). The screens are Appsmith CE v2.7.2 at http://localhost:8081, app **MES Phase 1**.
All validation happens in ERPNext API server scripts. Appsmith only shows the results and calls ERPNext through one REST query per page, `Erp`, which runs on the Appsmith server and uses the dedicated API key.

## Verification (checked through the ERPNext REST API with the `appsmith-mes` key)

| Milestone | Expected | Actual |
|---|---|---|
| M0 Setup | `GET /api/resource/Workstation` returns the 12 P1 workstations; the key can't read SHRDC | The P1 plant-floor filter returns 12. `Company/SHRDC` returns 403, SHRDC work orders return 0 rows, and the only company visible is Voltra. Appsmith → ERPNext returns HTTP 200 |
| M1 Work Orders pages | All 17 forward WOs with correct status and detail | `mes_work_orders?plan=MFG-PP-2026-00001` returns 17, all Not Started. The detail of MFG-WO-2026-00036 shows 3 operations with job cards, workstations and times, plus 10 materials with stock and shortages (for example SA-HSG-DRL short 30) |
| M2 Schedule Board + Capacity | Gantt shows all 32 job cards on the right workstations and times; 0 conflicts | `mes_schedule_board` returns 32 forward job cards (history plans are hidden) and 0 conflicts. `mes_workstation_load` covers 12 workstations, maximum 100% |
| M3 New Plan | 10 × FG-DRL-800 creates the sub-assembly and drill WOs inside shifts with 0 conflicts | MFG-PP-2026-00005 created 7 WOs (6 sub-assemblies + FG) and 13 job cards. 0 blocks fall outside shifts and there are 0 conflicts. The drill starts at 11:50 when the motor sub-assembly finishes |
| M4 WO actions | Each action works and shows in ERPNext | On MFG-WO-2026-00109: stop, resume, issue 10 (MAT-STE-2026-00043), finish 10 (MAT-STE-2026-00044), then status Completed. MFG-WO-2026-00108 was closed. Invalid stops and over-quantity requests are refused |
| M5 Validated rescheduling | A valid move saves; invalid moves are refused clearly | PO-JOB00204 moved to 2 Dec 16:50 and was split into 16:50–17:00 and 3 Dec 08:00–08:10; the WO plan was updated; 0 conflicts. Refused with clear messages: 07:00 and 12:30 (outside shift), Saturday, overlap with PO-JOB00092, before the previous operation, before a sub-assembly finishes, after the next operation starts, wrong workstation type, in the past |
| M6 Workstation Queue | An operator completes a job card and the Gantt bar changes | PO-JOB00200: start_timer, pause_job, resume_job, then complete_job_card (qty 10, auto-submit) through `/api/v2/document/Job Card/...`. The board then shows Completed |

### Inside Appsmith (checked in Preview, confirmed in the ERPNext access log)

| Page | Result |
|---|---|
| Work Orders | KPI tiles (22 Not Started, 1 Completed, 24 total) and the table load; clicking a row opens Work Order Detail `?wo=…` |
| Work Order Detail | `mes_work_order_detail` returns 200 |
| New Plan | `mes_create_plan` (item list and preview) returns 200 |
| Schedule Board | 45 job cards and 0 conflicts. Dragging into the past is refused ("…is in the past"), and `mes_reschedule_job_card` returns 417, ERPNext's validation error |
| Capacity | `mes_workstation_load` returns 200 |
| Workstation Queue | The station list loads; selecting P1-PCK-01 runs the queue query (200) |

The fix needed after import: the Custom Widget event context (`id`, `path`, `body`) is only in scope while the handler starts, not inside `.then()`. Each page's `onCall` now captures these values in an IIFE. This is fixed in `build_app.py`, in the regenerated `MES-Phase1.json`, and on all 6 pages of the live app, which has been deployed.

## Everything created (for rollback)

| What | Name | How to roll back |
|---|---|---|
| Site backup taken before the scripts went in | `sites/frontend/private/backups/20261124_133955-frontend-*` | `bench --site frontend restore …` |
| ERPNext user | `appsmith-mes@local.test` (Manufacturing User, Manufacturing Manager, Stock User; no password) | Disable the user |
| User Permission | Company = Voltra Power Tools Sdn Bhd for that user | Delete the permission |
| API key | Key and secret of `appsmith-mes@local.test`, stored in `mes/.secrets/appsmith-mes.env` (git-ignored) | Rotate with `create_api_user.py --new-keys`, or clear the key on the user |
| Server scripts (API) | `mes_work_orders`, `mes_work_order_detail`, `mes_work_order_action`, `mes_create_plan`, `mes_schedule_board`, `mes_schedule_conflicts`, `mes_workstation_load`, `mes_reschedule_job_card`, `mes_workstation_queue` | Disable or delete them. The source is in `mes/server_scripts/` and the installer is `mes/setup/install-server-scripts.ps1` |
| Test data | Production Plan MFG-PP-2026-00005, WOs MFG-WO-2026-00104 to 00110 (00109 Completed, 00108 Closed), stock entries MAT-STE-2026-00043/44, Tracked Items from item_tracking | Leave as demo data, or cancel. Ask first: these are submitted documents |
| Docker | Container `appsmith` (appsmith/appsmith-ce, port 8081) and volume `appsmith-stacks` | `docker rm -f appsmith; docker volume rm appsmith-stacks` |
| Appsmith | Admin account (yours), app **MES Phase 1** with 6 pages, a page query `Erp` on each, datasource **ERPNext** (URL plus Authorization header) | Delete the app and the datasource |
| Untouched | `planner_shift_job_card`, company SHRDC, the item_tracking app, history plans W45–W47 | — |

## Open the app

- Editor: http://localhost:8081, then the **MES Phase 1** app.
- To get a viewer URL for planners and operators, click **Deploy**. Tablets on the factory Wi-Fi use `http://<this-PC-IP>:8081/app/mes-phase-1/...`.

## 5-minute demo

1. **Work Orders:** show the KPI tiles; click *Late* and then *All*; search for "DRL"; click MFG-WO-2026-00036.
2. **Work Order Detail:** show the operations with job cards and times, then the materials with shortages (SA-HSG-DRL short 30). Explain that Issue is refused if stock is short, because ERPNext validates it.
3. **New Plan:** choose 5 × FG-CS-1400 and a start date; click *Preview* to show the sub-assembly tree and build order; click *Create plan* to show the new WOs with dates, 0 outside shifts and 0 conflicts.
4. **Schedule Board:** show the new saw jobs. Drag a bar onto Saturday and ERPNext refuses. Drag it onto a free slot inside a shift, confirm, and it saves and splits across shifts if needed.
5. **Capacity:** show the heat-map rising after the new plan; red means over 100%.
6. **Workstation Queue** (on a tablet): choose P1-PCK-01 → Start → Complete, then go back to the Schedule Board, where the bar is green (Completed).

## Not built, or different from the plan

- **Gantt library:** written in plain JS rather than vis-timeline or frappe-gantt, so it needs no CDN and works offline. Drag and drop, the confirm dialog and refusal messages work as specified.
- **Rescheduling bypasses one ERPNext save check:** `mes_reschedule_job_card` saves with `flags.ignore_validate`, because ERPNext's Job Card validation refuses *any* save of a later operation until the earlier ones are completed. The bypass applies only to unstarted job cards, after the API's own checks for shift, holiday, capacity, workstation type and operation order.
- **No employee on time logs:** the operator queue records time logs without an employee, because the API user has no Employee access. Add Employee read access and an employee picker when operators are set up.
- **Workstations visible to the key:** the Workstation doctype has no company field, so the key can also see the 4 non-P1 `WS-*` workstations. These are master records, not SHRDC transactions, and all MES screens filter to P1.
- **Per-page role access in Appsmith:** not configured. CE workspace roles are coarse; see Open points in the plan.
- **`planner_shift_job_card` left enabled:** it was not modified, as instructed. Disable it once it is confirmed unused.
