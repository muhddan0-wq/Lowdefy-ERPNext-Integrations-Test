# MES portability scope: connecting a new ERPNext site

Goal: point the MES server scripts, Appsmith pages and install scripts at a different ERPNext site (another company, plant, item catalogue and containers) without editing code.

Status: phases 1 and 2 done (see below). The sections after that are the original scope. Figures come from a read-only search of `mes/` on 2026-11-25.

**Phase 1 (config layer) done.** Site values now live in `mes/sites/p1-shah-alam.yaml` and are read by `mes/site_config.py`:
- `server_scripts/_prelude.py` takes its site values from a `@@SITE@@` marker; `setup/install_server_scripts.py` renders them from the YAML (argv[2]) and `setup/install-server-scripts.ps1` copies the YAML and loader into the bench (`-SiteConfig` to override). Rendered values equal the old literals, and all 20 `mes_*.py` scripts compile with the rendered prelude.
- `appsmith/build_app.py` takes the datasource URL from `erp.datasource_url`; `widgets/common.js` and `sf_base.js` use a `__ERP_PUBLIC_URL__` token filled from `erp.public_url`; `deploy_appsmith.py` (default `--url`), `dev_harness.py` and `update_report_appendix.py` read the same config.
- Still hard-coded, for phase 2 and later: `setup/install-shopfloor.ps1` container and site, `create_sector_roles.py`, `create_api_user.py`, the test and seed scripts, `mes_analytics.py` report titles, and "P1"/"Voltra" wording in `mes_*` messages and comments.

**Phase 2 (install split) done, 2026-11-26.** `setup/install-mes.ps1 -SiteConfig <yaml>` is the generic install. It loads no demo data; `run-seed.ps1` remains the optional Voltra sample.
- The site YAML now also holds `erp.container`, `sector_roles` (role to Workstation Type), `api_user` (email, roles), `test_users` and `test_account_domain`. `site_config.py` fills in defaults and prints any value for PowerShell (`python site_config.py <yaml> erp.container`).
- Install steps run in this order: `check_site.py` (read-only), backup, shopfloor DocTypes, server scripts, sector roles, API user. `-Only check|doctypes|scripts|roles|apiuser` runs a single step. The check fails the install, before the backup or any write, when the company, plant floor, warehouses or API-user roles are missing. It warns about missing workstations, `site_prefix` BOM operations, sector Workstation Types, `Tracked Item` and `server_script_enabled`. Newly generated API keys go to `mes/.secrets/appsmith-mes.env`, and the copied install files are removed from the bench even when a step fails.
- `create_sector_roles.py`, `create_api_user.py` and `install_shopfloor.py --test-users` read the YAML, and `create_test_function_accounts.py` takes `FRAPPE_SITE`/`TEST_DOMAIN`. `install-shopfloor.ps1` and `install-server-scripts.ps1` are thin wrappers over `install-mes.ps1`, so their container and site also come from the YAML.
- Verified: `-Only check` passes 20/20 on this sandbox. A YAML with a wrong company and plant floor is blocked (2 blocking) before the backup. Config values equal the old literals. A full `all` run on 2026-11-26 made a backup (`20261126_100218-frontend`). It reported 7 DocTypes unchanged, 20 server scripts updated, the 9 roles already present, and the API user unchanged, with its keys not rotated. Afterwards the API user got HTTP 200 from `mes_work_orders`, `mes_schedule_board`, `mes_workstation_load`, `mes_sf_dashboard`, `mes_wf_discover` and `mes_sf_jobs`.
- Left for later phases: `test_shopfloor.py`/`test_workflow.py` container and SKUs (phase 3), `run-seed.ps1`/`run-mes.ps1`/`import-item-images.ps1` defaults (sample data), `mes_analytics.py` titles and "P1"/"Voltra" wording, and the Appsmith datasource credential created at deploy (phase 4).

## 1. Hard-coded site identity (blocking)

These values are baked into the server scripts that run inside ERPNext. A new site fails or silently filters out its own data on the first call.

| Where | Value | Used for |
|---|---|---|
| `server_scripts/_prelude.py` lines 5-10 | `COMPANY` "Voltra Power Tools Sdn Bhd" | Every query and create (work orders, job cards, stock entries, plans) |
| `_prelude.py` | `PLANT_FLOOR` "P1 Shah Alam Plant" | Workstation filter in 8+ scripts (`mes_sf_jobs`, `mes_sf_dashboard`, `mes_workstation_queue`, `mes_schedule_board`, `mes_workstation_load`, `mes_sf_machine_issue`, `mes_reschedule_job_card`, `mes_create_plan`) |
| `_prelude.py` | `SITE_PREFIX` "P1 " | Which BOM operations count as this site (`mes_site_bom` in `mes_create_plan`) |
| `_prelude.py` | `WH` stores / wip / fg "P1 ... - VPT" | Stock source, WIP and FG warehouses for plans and issues |
| `_prelude.py` | `HORIZON_DAYS` 60, shift/calendar rules | Planning window and calendar (partly derived from Workstation data, so lower risk) |
| `_prelude.py` | `UNIT_DOCTYPE` "Tracked Item" | Serial/unit tracking. Assumes a custom DocType exists on the target |
| `server_scripts/mes_create_plan.py`, `mes_work_orders.py`, `mes_schedule_board.py`, `mes_schedule_conflicts.py`, `mes_workstation_load.py`, `mes_work_order_detail.py` | Comments and messages naming "P1" and "Voltra"; filters on the company | Mostly cosmetic, but the message text is shown to operators |
| `mes_analytics.py` line 220 | Report title "MES Dashboard - P1 Shah Alam Plant" | ERPNext report headers |
| `mes_analytics.py`, `mes_modules.py` | Report and workspace names | Install-time, one-off |

Fix: move these into one per-site configuration record (a JSON or DocType "MES Site Settings") read by `_prelude.py`. Every script already reads through `M[...]`, so the change is mostly centralised. Estimated effort: small to medium, about a day of careful work plus re-running the full suites.

## 2. Install and setup scripts (blocking for a new site)

| File | Assumption |
|---|---|
| `setup/install-server-scripts.ps1`, `install-shopfloor.ps1` | Container `comp_demo-bench-1`, site `frontend`, and the Docker-based bench layout |
| `setup/create_sector_roles.py` lines 15-22 | Eight workstation-to-role mappings with "P1 ..." workstation names |
| `setup/create_api_user.py` line 8 | Company name hard-coded |
| `setup/create_test_function_accounts.py`, `install_shopfloor.py --test-users` | Test users `op1`, `sup1`, `maint1` at `@voltra.local` |
| `seed_mes.py`, `products.yaml` (286 lines), `run-seed.ps1`, `run-mes.ps1` | The whole demo: items, BOMs, workstations, capacities, plans. Demo only, not needed on a real site, but the install should not depend on it |
| `setup/item_images.yaml` (48 lines), `import-item-images.ps1`, `import_item_images.py` | Maps Voltra item codes to image files. Needs per-site content |

Fix: make the Docker container and site parameters explicit in one config file, and split "install MES" (generic) from "load demo data" (site-specific, optional). Medium effort.

## 3. Appsmith layer (blocking for a real deployment)

| File | Assumption |
|---|---|
| `appsmith/build_app.py` line 20 | `DATASOURCE_URL` = `http://host.docker.internal:8000` |
| `appsmith/widgets/common.js` line 9, `sf_base.js` line 3 | `http://localhost:8000` used for ERPNext desk links and public files |
| `appsmith/deploy_appsmith.py` line 119 | Appsmith at `http://localhost:8081` |
| `appsmith/dev_harness.py` | ERPNext at localhost:8000; reads `mes/.secrets/appsmith-mes.env` |
| `appsmith/update_report_appendix.py` line 52 | Hard-coded datasource URL in the report text |
| `appsmith/widgets/*.js` | Page names and the ERPNext base URL are read from the widget, not from a setting |

Fix: pass the ERPNext base URL in from the Appsmith datasource or a page setting, and generate links from it. Small effort for the URLs. Also check that the Appsmith datasource credential is created per site, not copied.

## 4. Data and content assumptions (blocking for the operators)

- **Item codes:** the widgets and tests refer to FG-DRL-800, FG-RH-800, FG-CABINET-01, FG-BENCH-01, SA-HARN-S, RM-CHUCK-13 and similar. The assembly discovery feature (`mes_wf_discover`) is already dynamic, so it works on any BOM. The older shopfloor screens and tests are not.
- **Tracked units:** the shopfloor and unit scans need tracked-unit stock (`Tracked Item`). A new site needs its own units or a different scan mode.
- **Images:** item images come from ERPNext `Item.image`. Missing images show a placeholder, so this is cosmetic.
- **Operators:** each person needs an enabled ERPNext user, and the MES roles from `create_sector_roles.py`. Those role names map to P1 workstations, so the mapping must be rewritten for each site.

## 5. Tests (blocking for sign-off)

- `setup/test_shopfloor.py` and `test_workflow.py` hard-code SKUs, work-order names, the container and the operator emails. They cannot run on another site without edits.
- Current state: `test_shopfloor.py` is not green (44/54 at the last run, with the material-issue gate and fixture changes). It is blocked on tracked-unit stock, which is itself a data issue.
- Fix: parameterise the fixture selection (find a finished product with a BOM, a fresh work order with a job card, and enough tracked units) instead of naming SKUs. Medium to large effort, and it needs a stable fixture generator.

## 6. Recommended phases

1. **Config layer (small to medium):** one MES site config. Read it in `_prelude.py`, `build_app.py`, `deploy_appsmith.py` and the install scripts. No behaviour change on the current site.
2. **Install split (medium):** generic MES install versus demo seed. Role mapping and API-user creation read from config.
3. **Parameterised tests (medium to large):** fixtures discovered at run time, so the suite proves portability instead of this site's data.
4. **Appsmith datasource per site (small):** URLs from config, credential created during deploy.
5. **Pilot on a second site (medium):** run install, seed-free setup and the parameterised suite on a clean ERPNext before calling it portable.

## 7. Open questions

- Is the target a different company on this same ERPNext, or a separate server? The scope is the same, but the install and backup steps differ.
- Which per-site values must be decided by the customer (plant floor name, warehouse names, role mapping, workstation list)?
- Who owns the tracked-unit concept on a real site: is it a custom DocType the customer already has, or something this project must install?

## 8. Goal: MES in a box

The stated goal is a ready-made MES that connects to an ERPNext site and works, not a Voltra build that someone else has to adapt. That changes the scope:

- **Voltra becomes a sample dataset**, not the product. The demo seed (`seed_mes.py`, `products.yaml`, `item_images.yaml`) moves out of the install path and ships as an optional sample.
- **Connection is a guided step**, not a code edit: site URL, company, plant floor, warehouses, workstation list and role mapping are entered once, validated against the site, and stored in the MES site config.
- **Install must be one command** against any ERPNext site: DocTypes, server scripts, roles, API user, Appsmith datasource, pages. Each step must check its preconditions and report what is missing.
- **Discovery is the default:** finished products, BOMs, workstations and operations are read from the connected site, as the workflow discovery feature already does. Nothing is named in code.
- **Acceptance is a parameterised suite** that runs against any connected site and reports what it could and could not test, instead of a suite tied to this sandbox's SKUs.

Gaps that remain for "in a box" beyond the code work listed above: a first-run connection check and wizard, a documented list of ERPNext prerequisites (custom fields, Tracked Item or its replacement, workstation setup), and upgrade handling so a box can be updated without losing site data.

**Correction to the summary above:** I did not measure the "about 80% parameter-driven" figure, and it overstates the position. The workflow discovery code is data-driven; the shopfloor, planning and install code are not yet. Treat the effort estimates in this document as rough until the config layer is designed.

**Suggested first step:** design the site config and the connection wizard (phase 1 in section 6), since every other phase depends on it.
