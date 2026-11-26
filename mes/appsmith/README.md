# MES Phase 1: Appsmith app

Appsmith is only the screen layer. Every read and every change goes to ERPNext through the API server
scripts in `mes/server_scripts/`, which hold all the validation.

## Files

| File | What it is |
|---|---|
| `widgets/common.js`, `common.css` | Shared bridge and styles. The widget raises `onCall`, the page's `Erp` REST query runs server-side, and the result comes back through the widget model |
| `widgets/<page>.js/.css` | One Custom Widget per page: `work_orders`, `wo_detail`, `new_plan`, `schedule_board` (Gantt with drag and drop), `capacity`, `queue` |
| `build_app.py` | Builds `MES-Phase1.json`, the Appsmith import file. The file carries no credentials |
| `dev_harness.py` | Local test page (http://127.0.0.1:8099/?page=schedule_board) that runs the widgets with a mock `appsmith` object. It proxies calls to ERPNext and adds the API key on the server side, so the key never reaches the browser. Development only |

## Station screen (Tulip-style) and plant dashboard

- **Shopfloor** page = `widgets/station.*`: pick station, then 1 Order (metrics + order list), 2 Components (scan each BOM item;
  photo, stock availability and a green check per item), 3 Build (one step per BOM item, "Insert X / Wind Y", unit counter),
  4 Defect ticket (pick or scan the bad item's lot or serial, reason, quantity, photo; ticket shows a Code 128 barcode).
  Andon (machine issue) is always in the header.
- Scanning: USB scanners work anywhere on the screen. **Camera** uses Appsmith's native Code Scanner widget (`CamScan`,
  top right of the page), because Appsmith's Custom Widget iframe is not allowed to use the camera. "Read photo" decodes
  QR codes inside the widget with jsQR (`widgets/vendor_jsqr.js`, the same decoder as the Lowdefy app).
- **Plant Dashboard** page = `widgets/plant_dashboard.*` backed by `mes_sf_dashboard`.

### Put the pages into your existing Appsmith app

```powershell
python mes/appsmith/deploy_appsmith.py --make-default
```

It signs in as you (asks for your Appsmith email and password), backs up the app to `mes/state/appsmith-backup-*.json`,
adds or updates Shopfloor, Plant Dashboard and Shopfloor Admin in "My first application", and publishes it.

## Shopfloor pages (classic)

**Shopfloor** (default page) and **Shopfloor Admin** are built from `widgets/sf_base.*`, `shopfloor.js` and
`mes_admin.js`, and backed by the `mes_sf_*` server scripts. The operator is the Appsmith user's email, which must be
an enabled ERPNext user; their ERPNext roles decide what they may do. Set up the backend with
`.\mes\setup\install-shopfloor.ps1`. The full description is in `mes/SHOPFLOOR-REPORT.md`.

The `Erp` query only runs `/api/method/mes_*` paths. Dev harness: `?page=shopfloor&as=op1@local.test`.

## Install

1. Run `python mes/appsmith/build_app.py`.
2. In Appsmith (http://localhost:8081), go to Workspace, then **Create new**, then **Import**, and pick `mes/appsmith/MES-Phase1.json`.
3. When the import asks you to configure datasource **ERPNext**:
   - URL: `http://host.docker.internal:8000`
   - Header: `Authorization` = `token <key>:<secret>` of user `appsmith-mes@local.test` (stored in `mes/.secrets/appsmith-mes.env`, which git ignores)
4. Deploy the app. The pages are Work Orders, Work Order Detail, New Plan, Schedule Board, Capacity and Workstation Queue.

The REST query runs on the Appsmith server, so the key never reaches the browser.

## Server side

- Install or update the scripts: `.\mes\setup\install-server-scripts.ps1` (it backs up the site first).
- Create the API user: `mes/setup/create_api_user.py` (see the header comment in the file).
- Run the REST checks: `bash mes/setup/verify_api.sh all`.
