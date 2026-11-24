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

## Install

1. Run `python mes/appsmith/build_app.py`.
2. In Appsmith (http://localhost:8081), go to Workspace, then **Create new**, then **Import**, and pick `mes/appsmith/MES-Phase1.json`.
3. When the import asks you to configure datasource **ERPNext**:
   - URL: `http://host.docker.internal:8000`
   - Header: `Authorization` = `token <key>:<secret>` of user `appsmith-mes@voltra.local` (stored in `mes/.secrets/appsmith-mes.env`, which git ignores)
4. Deploy the app. The pages are Work Orders, Work Order Detail, New Plan, Schedule Board, Capacity and Workstation Queue.

The REST query runs on the Appsmith server, so the key never reaches the browser.

## Server side

- Install or update the scripts: `.\mes\setup\install-server-scripts.ps1` (it backs up the site first).
- Create the API user: `mes/setup/create_api_user.py` (see the header comment in the file).
- Run the REST checks: `bash mes/setup/verify_api.sh all`.
