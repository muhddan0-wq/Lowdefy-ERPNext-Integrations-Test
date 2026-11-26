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

## Appendix: JavaScript used in Appsmith

All JavaScript below runs in Appsmith. None of it decides anything about stock, capacity or the schedule: it only displays data and sends requests to the ERPNext API server scripts in `mes/server_scripts/`, which validate everything.

How a request flows:

1. The page's Custom Widget (`Main`) calls `MES.get()` or `MES.post()` (in `common.js`), which raises the Appsmith event `onCall` with `{id, path, body}`.
2. The `onCall` handler runs the page's REST query `Erp` on the Appsmith server. The ERPNext API key lives only in the **ERPNext** datasource header, never in the browser.
3. The answer is saved with `storeValue('mesResp_<id>')`. It flows back into the widget through its Default Model (`appsmith.store`), and the waiting promise in `common.js` resolves.

The source files are in `mes/appsmith/widgets/`, and `mes/appsmith/build_app.py` packs them into `MES-Phase1.json`. Each page widget is `common.css` + `<page>.css` for CSS and `common.js` + `<page>.js` for JS; the HTML is just `<div id="app"></div>`. This appendix is generated by `mes/appsmith/update_report_appendix.py`.

### A.1 Appsmith wiring (identical on every page)

REST query `Erp` (datasource **ERPNext**, `http://host.docker.internal:8000`, header `Authorization: token <key>:<secret>`):

| Setting | Value |
|---|---|
| Method | `POST` |
| Path | `{{this.params.path}}` |
| Body (JSON) | `{{this.params.body}}` |
| Headers | `Content-Type: application/json`, `Accept: application/json` |
| Timeout | 120 s |

Custom Widget `Main`, Default Model:

```javascript
{{ { store: appsmith.store, query: appsmith.URL.queryParams, user: appsmith.user.email } }}
```

Event `onCall`. The event context (`id`, `path`, `body`) is only in scope while the handler starts, so it is captured in an IIFE before `.then()`:

```javascript
{{ (function (rid, p, b) { return Erp.run({ path: p, body: b })
  .then(function (d) { storeValue('mesResp_' + rid, { ok: true, data: d }, false); })
  .catch(function (e) { storeValue('mesResp_' + rid, { ok: false, data: Erp.data, status: Erp.responseMeta && Erp.responseMeta.statusCode, msg: e && e.message }, false); });
})(id, path, body) }}
```

Event `onNavigate`. Page names open in the same window; full URLs (ERPNext desk links) open in a new, unsandboxed tab:

```javascript
{{ navigateTo(page, params || {}, /^https?:/.test(page) ? 'NEW_WINDOW' : 'SAME_WINDOW') }}
```

### A.2 `common.js`

Shared by every page: bridge to Appsmith/ERPNext, formatting helpers, dialogs, navigation bar, external links.

```javascript
// ---- MES common (prepended to every page widget by build_app.py) ----
// The widget never talks to ERPNext itself. It raises the Appsmith event "onCall" with
// {id, method, path, body}; the page's ErpGet/ErpPost REST queries (server-side, API key kept in the
// Appsmith datasource) run it and storeValue("mesResp_<id>", ...) the result, which flows back in
// through the widget model (appsmith.model.store).
const MES = (() => {
  const pending = {};
  const handled = new Set();
  const ERP_DESK = "http://localhost:8000/desk/";

  function uid() {
    return "r" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function decode(html) {
    const t = document.createElement("textarea");
    t.innerHTML = String(html == null ? "" : html).replace(/<[^>]*>/g, "");
    return t.value.trim();
  }

  function errText(r) {
    const d = r.data;
    try {
      if (d && d._server_messages) {
        return JSON.parse(d._server_messages)
          .map((x) => { try { return JSON.parse(x).message; } catch (e) { return x; } })
          .map(decode).filter(Boolean).join("\n");
      }
      if (d && Array.isArray(d.errors) && d.errors.length) {
        return d.errors.map((e) => decode(e.message || e.title || String(e.exception || e.type).split("\n").pop())).join("\n");
      }
      if (d && d.exception) return decode(String(d.exception).split("\n").filter(Boolean).pop());
      if (d && typeof d.message === "string") return decode(d.message);
      if (typeof d === "string" && d) return decode(d).slice(0, 400);
    } catch (e) { /* fall through */ }
    return r.msg || "Request failed" + (r.status ? " (HTTP " + r.status + ")" : "");
  }

  function deliver(model) {
    const store = (model && model.store) || {};
    Object.keys(pending).forEach((id) => {
      const r = store["mesResp_" + id];
      if (!r || handled.has(id)) return;
      handled.add(id);
      const p = pending[id];
      delete pending[id];
      if (r.ok) p.resolve(r.data);
      else p.reject(new Error(errText(r)));
    });
  }

  function request(method, path, body) {
    return new Promise((resolve, reject) => {
      const id = uid();
      pending[id] = { resolve, reject };
      appsmith.triggerEvent("onCall", { id: id, method: method, path: path, body: body || {} });
      setTimeout(() => {
        if (pending[id]) {
          delete pending[id];
          reject(new Error("No answer from ERPNext after 2 minutes"));
        }
      }, 120000);
    });
  }

  function qs(params) {
    const parts = [];
    Object.keys(params || {}).forEach((k) => {
      const v = params[k];
      if (v === undefined || v === null || v === "") return;
      parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(typeof v === "object" ? JSON.stringify(v) : v));
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  // Read calls also go as POST /api/method/<name> with a JSON body: Frappe API server scripts accept both,
  // and it keeps each Appsmith page down to ONE REST query ("Erp") with no query strings in the path.
  async function get(method, args) {
    return post(method, args);
  }

  // POST /api/method/<name> {args} -> message
  async function post(method, args) {
    const d = await request("POST", "/api/method/" + method, args || {});
    return d && d.message !== undefined ? d.message : d;
  }

  function navigate(page, params) {
    appsmith.triggerEvent("onNavigate", { page: page, params: params || {} });
  }

  function deskUrl(doctype, name) {
    return ERP_DESK + doctype.toLowerCase().replace(/ /g, "-") + "/" + encodeURIComponent(name);
  }

  return { request, get, post, qs, navigate, deliver, decode, deskUrl };
})();

// ---- small DOM / format helpers ----
const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

function esc(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function num(v, dp) {
  const n = Number(v || 0);
  return n.toLocaleString("en-MY", { maximumFractionDigits: dp == null ? 2 : dp });
}

// ERPNext returns naive local datetimes "YYYY-MM-DD HH:mm:ss" (site TZ Asia/Kuala_Lumpur); keep them naive.
function parseDT(s) {
  if (!s) return null;
  const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
}

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n) => String(n).padStart(2, "0");

function fmtDT(s, withDow) {
  const d = s instanceof Date ? s : parseDT(s);
  if (!d) return "";
  return (withDow === false ? "" : DOW[d.getDay()] + " ") + pad(d.getDate()) + " " + MON[d.getMonth()] + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
}

function fmtD(s) {
  const d = s instanceof Date ? s : parseDT(s);
  return d ? DOW[d.getDay()] + " " + pad(d.getDate()) + " " + MON[d.getMonth()] : "";
}

function isoDate(d) {
  return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
}

function isoDT(d) {
  return isoDate(d) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
}

function addDays(d, n) {
  const x = new Date(d.getTime());
  x.setDate(x.getDate() + n);
  return x;
}

function badge(status) {
  const cls = {
    "Not Started": "b-grey", "Open": "b-blue", "In Process": "b-amber", "Work In Progress": "b-amber",
    "Running": "b-amber", "Completed": "b-green", "Closed": "b-dark", "Stopped": "b-red", "Cancelled": "b-dark",
    "On Hold": "b-purple", "Paused": "b-purple", "Material Transferred": "b-cyan", "Late": "b-red", "Not started": "b-blue",
  }[status] || "b-grey";
  return '<span class="badge ' + cls + '">' + esc(status || "-") + "</span>";
}

function bar(pct, cls) {
  const p = Math.max(0, Math.min(100, Number(pct || 0)));
  return '<div class="bar ' + (cls || "") + '"><span style="width:' + p + '%"></span></div>';
}

let toastTimer;
function toast(msg, kind) {
  let t = $("#toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    document.body.appendChild(t);
  }
  t.className = "show " + (kind || "ok");
  t.textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ""; }, kind === "err" ? 9000 : 4000);
}

// Modal dialog inside the widget. Returns a Promise<boolean>.
function dialog(title, html, okLabel, opts) {
  opts = opts || {};
  return new Promise((resolve) => {
    const wrap = document.createElement("div");
    wrap.className = "modal-wrap";
    wrap.innerHTML =
      '<div class="modal"><h3>' + esc(title) + '</h3><div class="modal-body">' + html + "</div>" +
      '<div class="modal-actions">' + (opts.noCancel ? "" : '<button class="btn" data-x="0">Cancel</button>') +
      '<button class="btn ' + (opts.danger ? "danger" : "primary") + '" data-x="1">' + esc(okLabel || "OK") + "</button></div></div>";
    document.body.appendChild(wrap);
    wrap.addEventListener("click", (e) => {
      const x = e.target.getAttribute && e.target.getAttribute("data-x");
      if (x === null || x === undefined) return;
      const ok = x === "1";
      const values = {};
      $$("input,select,textarea", wrap).forEach((i) => { values[i.name] = i.value; });
      wrap.remove();
      resolve(opts.withValues ? (ok ? values : null) : ok);
    });
  });
}

function setBusy(on) {
  document.body.classList.toggle("busy", !!on);
}

function navBar(active) {
  const pages = ["Work Orders", "Work Order Detail", "New Plan", "Schedule Board", "Capacity", "Workstation Queue"];
  return '<nav class="nav"><b>MES · P1 Shah Alam</b>' + pages.map((p) =>
    '<a href="#" data-nav="' + esc(p) + '" class="' + (p === active ? "on" : "") + '">' + esc(p) + "</a>").join("") + "</nav>";
}

document.addEventListener("click", (e) => {
  // External links (ERPNext desk) must not open from inside the sandboxed widget frame: the new tab would inherit the
  // sandbox, so ERPNext could not use its login cookie and the page hangs. Hand them to Appsmith's navigateTo instead.
  const ext = e.target.closest && e.target.closest("a[href^='http']");
  if (ext) {
    e.preventDefault();
    appsmith.triggerEvent("onNavigate", { page: ext.getAttribute("href"), params: {} });
    return;
  }
  const a = e.target.closest && e.target.closest("[data-nav]");
  if (a) {
    e.preventDefault();
    MES.navigate(a.getAttribute("data-nav"), a.dataset.params ? JSON.parse(a.dataset.params) : {});
  }
});

function startPage(init) {
  let started = false;
  appsmith.onModelChange((model) => {
    MES.deliver(model);
  });
  appsmith.onReady(() => {
    MES.deliver(appsmith.model);
    if (!started) {
      started = true;
      init(appsmith.model || {});
    }
  });
}
// ---- end MES common ----
```

### A.3 `work_orders.js`

Page Work Orders (M1): KPI tiles and filterable table.

```javascript
// Page: Work Orders (M1) — KPI tiles + filterable table. Data: mes_work_orders.
const S = { status: "All", item: "", search: "", hist: false, sort: "planned_start_date", dir: 1, data: null };

async function load() {
  setBusy(true);
  try {
    S.data = await MES.get("mes_work_orders", { status: S.status, item: S.item, search: S.search, include_history: S.hist ? 1 : 0 });
    render();
  } catch (e) {
    toast(e.message, "err");
  } finally {
    setBusy(false);
  }
}

function kpiTile(key, label, value, cls) {
  return '<div class="kpi ' + cls + (S.status === key ? " sel" : "") + '" data-status="' + esc(key) + '"><div class="v">' + num(value, 0) +
    '</div><div class="l">' + esc(label) + "</div></div>";
}

function render() {
  const d = S.data || { kpi: {}, rows: [] };
  const k = d.kpi || {};
  // full item list from the server (does not shrink when a status/item filter is applied)
  const items = d.items || Array.from(new Set((d.rows || []).map((r) => r.production_item))).sort();
  const rows = (d.rows || []).slice().sort((a, b) => {
    const x = a[S.sort], y = b[S.sort];
    return (x > y ? 1 : x < y ? -1 : 0) * S.dir;
  });
  const th = (key, label, cls) => '<th class="sort ' + (cls || "") + '" data-sort="' + key + '">' + esc(label) + (S.sort === key ? (S.dir > 0 ? " ▲" : " ▼") : "") + "</th>";
  $("#app").innerHTML =
    navBar("Work Orders") +
    '<div class="row" style="justify-content:space-between"><h2>Work Orders <span class="spin"></span></h2>' +
    '<span class="muted small">As of ' + esc(fmtDT(d.as_of)) + " · company Voltra Power Tools Sdn Bhd</span></div>" +
    '<div class="kpis">' +
    kpiTile("Not Started", "Not Started", k.not_started, "k-grey") +
    kpiTile("In Process", "In Process", k.in_process, "k-amber") +
    kpiTile("Completed", "Completed", k.completed, "k-green") +
    kpiTile("Late", "Late (past planned end)", k.late, "k-red") +
    kpiTile("All", "All work orders" + (k.stopped ? " · " + k.stopped + " stopped" : ""), k.total, "k-blue") +
    "</div>" +
    '<div class="row" style="margin-bottom:10px">' +
    '<label class="f">Status<select id="f-status">' + ["All", "Not Started", "In Process", "Completed", "Stopped", "Closed", "Late"].map((s) =>
      "<option" + (s === S.status ? " selected" : "") + ">" + s + "</option>").join("") + "</select></label>" +
    '<label class="f">Item<select id="f-item"><option value="">All items</option>' + items.map((i) =>
      '<option' + (i === S.item ? " selected" : "") + ">" + esc(i) + "</option>").join("") + "</select></label>" +
    '<label class="f grow">Search<input id="f-search" placeholder="Work order, item code or name" value="' + esc(S.search) + '"></label>' +
    '<label class="f"><span>&nbsp;</span><span><input type="checkbox" id="f-hist" ' + (S.hist ? "checked" : "") + '> include simulated history</span></label>' +
    '<button class="btn" id="b-refresh">Refresh</button></div>' +
    (rows.length ? '<table class="t"><thead><tr>' + th("name", "Work order") + th("production_item", "Item") + th("qty", "Qty", "n") +
      th("produced_qty", "Produced", "n") + th("progress_pct", "Progress") + th("planned_start_date", "Planned start") +
      th("planned_end_date", "Planned end") + th("status", "Status") + th("production_plan", "Plan") + "</tr></thead><tbody>" +
      rows.map((r) => '<tr class="click" data-wo="' + esc(r.name) + '"><td><b>' + esc(r.name) + "</b></td><td>" + esc(r.production_item) +
        '<div class="muted small">' + esc(r.item_name) + '</div></td><td class="n">' + num(r.qty, 0) + '</td><td class="n">' + num(r.produced_qty, 0) +
        "</td><td>" + bar(r.progress_pct) + '<span class="muted small">' + num(r.progress_pct, 0) + "%</span></td><td>" + esc(fmtDT(r.planned_start_date)) +
        "</td><td>" + esc(fmtDT(r.planned_end_date)) + "</td><td>" + badge(r.status) + (r.late ? " " + badge("Late") : "") +
        '</td><td class="small">' + esc(r.production_plan || "") + (r.plan_tag ? '<div class="muted">' + esc(r.plan_tag) + "</div>" : "") + "</td></tr>").join("") +
      "</tbody></table>" : '<div class="card empty">No work orders match these filters.</div>') +
    '<p class="muted small">' + rows.length + " work order(s). Click a row for detail.</p>";
}

document.addEventListener("click", (e) => {
  const tile = e.target.closest(".kpi");
  if (tile) { S.status = tile.dataset.status; load(); return; }
  const th = e.target.closest("th.sort");
  if (th) {
    const key = th.dataset.sort;
    S.dir = S.sort === key ? -S.dir : 1;
    S.sort = key;
    render();
    return;
  }
  const tr = e.target.closest("tr[data-wo]");
  if (tr) { MES.navigate("Work Order Detail", { wo: tr.dataset.wo }); return; }
  if (e.target.id === "b-refresh") load();
});

document.addEventListener("change", (e) => {
  if (e.target.id === "f-status") { S.status = e.target.value; load(); }
  if (e.target.id === "f-item") { S.item = e.target.value; load(); }
  if (e.target.id === "f-hist") { S.hist = e.target.checked; load(); }
});

let searchTimer;
document.addEventListener("input", (e) => {
  if (e.target.id === "f-search") {
    clearTimeout(searchTimer);
    S.search = e.target.value;
    searchTimer = setTimeout(async () => {
      await load();
      const i = $("#f-search");
      if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
    }, 400);
  }
});

startPage(() => { render(); load(); });
```

### A.4 `wo_detail.js`

Page Work Order Detail (M1 + M4): header, operations, materials, Stop/Resume/Issue/Finish/Close.

```javascript
// Page: Work Order Detail (M1 read + M4 actions). Data: mes_work_order_detail; actions: mes_work_order_action.
const S = { wo: "", d: null, list: [] };

async function load() {
  if (!S.wo) return renderPicker();
  setBusy(true);
  try {
    S.d = await MES.get("mes_work_order_detail", { work_order: S.wo });
    render();
  } catch (e) {
    S.d = null;
    render();
    toast(e.message, "err");
  } finally {
    setBusy(false);
  }
}

async function renderPicker() {
  $("#app").innerHTML = navBar("Work Order Detail") + '<h2>Work Order Detail</h2><div class="card"><div class="row">' +
    '<label class="f grow">Work order<select id="pick"><option value="">Loading…</option></select></label>' +
    '<button class="btn primary" id="b-open">Open</button></div></div>';
  try {
    const m = await MES.get("mes_work_orders", {});
    S.list = m.rows || [];
    $("#pick").innerHTML = '<option value="">Choose…</option>' + S.list.map((r) =>
      '<option value="' + esc(r.name) + '">' + esc(r.name + " · " + r.production_item + " × " + r.qty + " · " + r.status) + "</option>").join("");
  } catch (e) {
    toast(e.message, "err");
  }
}

function kv(k, v) {
  return '<div class="kv"><div class="k">' + esc(k) + '</div><div class="v">' + v + "</div></div>";
}

function render() {
  const d = S.d;
  if (!d) {
    $("#app").innerHTML = navBar("Work Order Detail") + '<h2>Work Order ' + esc(S.wo) + '</h2><div class="card empty">Could not load this work order.</div>';
    return;
  }
  const h = d.header, a = d.actions;
  const transferPct = h.qty ? (100 * (h.transferred_qty || 0)) / h.qty : 0;
  $("#app").innerHTML =
    navBar("Work Order Detail") +
    '<div class="row" style="justify-content:space-between"><h2>' + esc(h.name) + " · " + esc(h.production_item) + ' <span class="spin"></span></h2>' +
    '<div class="row"><a class="lnk" href="#" data-nav="Work Orders">← All work orders</a>' +
    '<a class="lnk" target="_blank" rel="noopener" href="' + MES.deskUrl("Work Order", h.name) + '">Open in ERPNext ↗</a></div></div>' +
    '<div class="card"><div class="grid2">' +
    kv("Item", esc(h.item_name)) + kv("Status", badge(h.status) + (h.late ? " " + badge("Late") : "")) +
    kv("Qty to make", num(h.qty, 0)) + kv("Produced", num(h.produced_qty, 0)) +
    kv("Planned start", esc(fmtDT(h.planned_start_date))) + kv("Planned end", esc(fmtDT(h.planned_end_date))) +
    kv("Actual start", esc(fmtDT(h.actual_start_date) || "-")) + kv("Actual end", esc(fmtDT(h.actual_end_date) || "-")) +
    kv("BOM", esc(h.bom_no)) + kv("Production plan", esc(h.production_plan || "-")) +
    kv("Source / WIP", esc((h.source_warehouse || "") + " → " + (h.wip_warehouse || ""))) + kv("Target", esc(h.fg_warehouse || "")) +
    "</div>" +
    '<div class="row" style="margin-top:12px"><div class="grow"><div class="small muted">Produced ' + num(h.produced_qty, 0) + " / " + num(h.qty, 0) +
    " (" + num(h.progress_pct, 0) + "%)</div>" + bar(h.progress_pct, "lg") + "</div>" +
    '<div class="grow"><div class="small muted">Materials issued for ' + num(h.transferred_qty, 0) + " / " + num(h.qty, 0) + "</div>" + bar(transferPct, "lg blue") + "</div></div>" +
    '<div class="row" style="margin-top:12px">' +
    '<button class="btn" data-act="stop" ' + (a.stop ? "" : "disabled") + ">Stop</button>" +
    '<button class="btn" data-act="resume" ' + (a.resume ? "" : "disabled") + ">Resume</button>" +
    '<button class="btn primary" data-act="issue" ' + (a.issue ? "" : "disabled") + ">Issue materials…</button>" +
    '<button class="btn primary" data-act="finish" ' + (a.finish ? "" : "disabled") + ">Finish (manufacture)…</button>" +
    '<button class="btn danger" data-act="close" ' + (a.close ? "" : "disabled") + ">Close…</button>" +
    '<span class="muted small">Every action is validated by ERPNext.</span></div><div id="msg"></div></div>' +
    "<h3>Operations</h3>" +
    '<table class="t"><thead><tr><th>#</th><th>Operation</th><th>Workstation</th><th class="n">Mins</th><th>Job card</th><th>Status</th>' +
    "<th>Scheduled start</th><th>Scheduled end</th><th>Actual</th></tr></thead><tbody>" +
    d.operations.map((o) => "<tr><td>" + o.idx + "</td><td>" + esc(o.operation) + '<div class="muted small">' + esc(o.workstation_type) + "</div></td><td>" +
      esc(o.workstation || "-") + '</td><td class="n">' + num(o.time_in_mins, 0) + "</td><td>" +
      (o.job_card ? '<a class="lnk" target="_blank" rel="noopener" href="' + MES.deskUrl("Job Card", o.job_card) + '">' + esc(o.job_card) + "</a>" : "-") +
      "</td><td>" + badge(o.job_card_status || o.op_status) + "</td><td>" + esc(fmtDT(o.scheduled_start)) + "</td><td>" + esc(fmtDT(o.scheduled_end)) +
      '</td><td class="small">' + esc(o.actual_start ? fmtDT(o.actual_start) + " → " + (fmtDT(o.actual_end) || "…") : "-") + "</td></tr>").join("") +
    "</tbody></table>" +
    "<h3>Materials</h3>" +
    '<table class="t"><thead><tr><th>Item</th><th>Source</th><th class="n">Required</th><th class="n">Transferred</th><th class="n">Consumed</th>' +
    '<th class="n">In stock</th><th class="n">Short</th></tr></thead><tbody>' +
    d.materials.map((m) => "<tr><td><b>" + esc(m.item_code) + '</b><div class="muted small">' + esc(m.item_name) + '</div></td><td class="small">' +
      esc(m.source_warehouse) + '</td><td class="n">' + num(m.required_qty) + '</td><td class="n">' + num(m.transferred_qty) + '</td><td class="n">' +
      num(m.consumed_qty) + '</td><td class="n">' + num(m.in_stock) + '</td><td class="n ' + (m.short > 0 ? "red" : "") + '">' + (m.short > 0 ? num(m.short) : "–") + "</td></tr>").join("") +
    "</tbody></table>" +
    '<p class="muted small">In stock = actual qty in the source warehouse. Short = still to transfer minus in stock.</p>';
}

async function doAction(act) {
  const h = S.d.header, a = S.d.actions;
  let qty = 0;
  if (act === "issue" || act === "finish") {
    const max = act === "issue" ? a.max_issue_qty : a.max_finish_qty;
    const v = await dialog(act === "issue" ? "Issue materials" : "Finish (manufacture)",
      (act === "issue"
        ? "Creates and submits a <b>Material Transfer for Manufacture</b> stock entry from " + esc(h.source_warehouse) + " to " + esc(h.wip_warehouse) + "."
        : "Creates and submits a <b>Manufacture</b> stock entry into " + esc(h.fg_warehouse) + ". ERPNext requires the job cards for this quantity to be completed.") +
      '<br><br><label class="f">Quantity (max ' + num(max) + ')<input name="qty" type="number" min="1" max="' + max + '" value="' + max + '"></label>',
      act === "issue" ? "Issue" : "Finish", { withValues: true });
    if (!v) return;
    qty = Number(v.qty);
  } else {
    const text = {
      stop: "Stop work order " + h.name + "? Job cards cannot be worked on while it is stopped.",
      resume: "Resume work order " + h.name + "?",
      close: "Close work order " + h.name + "? A closed work order cannot be reopened, and no more stock entries can be made against it.",
    }[act];
    if (!(await dialog(act[0].toUpperCase() + act.slice(1) + " work order", esc(text), act[0].toUpperCase() + act.slice(1), { danger: act === "close" }))) return;
  }
  setBusy(true);
  try {
    const r = await MES.post("mes_work_order_action", { work_order: h.name, action: act, qty: qty });
    const se = r.stock_entry ? ' Stock entry <a class="lnk" target="_blank" rel="noopener" href="' + MES.deskUrl("Stock Entry", r.stock_entry) + '">' + esc(r.stock_entry) + "</a> submitted." : "";
    await load();
    $("#msg").innerHTML = '<div class="banner ok">' + esc(act) + " done: " + esc(r.before) + " → " + esc(r.status) + "." + se + "</div>";
  } catch (e) {
    $("#msg").innerHTML = '<div class="banner err">ERPNext refused: ' + esc(e.message) + "</div>";
  } finally {
    setBusy(false);
  }
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-act]");
  if (b && !b.disabled) { doAction(b.dataset.act); return; }
  if (e.target.id === "b-open") {
    const v = $("#pick").value;
    if (v) MES.navigate("Work Order Detail", { wo: v });
  }
});

startPage((model) => {
  S.wo = ((model.query || {}).wo || "").trim();
  load();
  // navigateTo() to this same page with another ?wo= does not reload the widget: follow the URL param
  appsmith.onModelChange((m) => {
    const w = (((m || {}).query || {}).wo || "").trim();
    if (w && w !== S.wo) { S.wo = w; load(); }
  });
});
```

### A.5 `new_plan.js`

Page New Plan (M3): finished goods, preview, create plan.

```javascript
// Page: New Plan (M3). Data/actions: mes_create_plan (list_items=1 | preview=1 | create).
const S = { items: [], lines: [], nextDay: "", preview: null, result: null };

function renderLines() {
  return S.lines.map((l, i) =>
    '<div class="row" style="margin-bottom:6px" data-line="' + i + '">' +
    '<label class="f grow">Finished good<select data-f="item">' + S.items.map((it) =>
      '<option value="' + esc(it.item) + '"' + (it.item === l.item ? " selected" : "") + ">" + esc(it.item + " · " + it.item_name) + "</option>").join("") + "</select></label>" +
    '<label class="f">Quantity<input data-f="qty" type="number" min="1" step="1" value="' + esc(l.qty) + '"></label>' +
    '<label class="f">Start date<input data-f="start" type="date" value="' + esc(l.start) + '"></label>' +
    '<button class="btn" data-del="' + i + '" ' + (S.lines.length < 2 ? "disabled" : "") + ">Remove</button></div>").join("");
}

function render() {
  const p = S.preview, r = S.result;
  $("#app").innerHTML =
    navBar("New Plan") +
    '<h2>New production plan <span class="spin"></span></h2>' +
    '<div class="card"><p class="muted small" style="margin-top:0">ERPNext creates a Production Plan with all sub-assemblies (combined), makes the work orders, ' +
    "sets the P1 warehouses and submits them sub-assemblies first, each parent starting when its children finish. Job cards are slotted into " +
    "workstation shifts by ERPNext's capacity planner.</p>" +
    '<div id="lines">' + renderLines() + "</div>" +
    '<div class="row"><button class="btn" id="b-add">+ Add finished good</button><span class="grow"></span>' +
    '<button class="btn" id="b-preview">Preview sub-assemblies</button><button class="btn primary" id="b-create">Create plan…</button></div></div>' +
    (p ? "<h3>Preview: " + p.work_orders_expected + " work orders will be created</h3>" +
      '<table class="t"><thead><tr><th>Item</th><th>Name</th><th>Level</th><th class="n">Qty</th><th>Used in</th><th>BOM</th></tr></thead><tbody>' +
      p.finished_goods.map((f) => "<tr><td><b>" + esc(f.item) + "</b></td><td>" + esc(f.item_name) + '</td><td>Finished good</td><td class="n">' + num(f.qty, 0) +
        '</td><td class="muted">starts ' + esc(fmtDT(f.start)) + "</td><td>" + esc(f.bom) + "</td></tr>").join("") +
      p.sub_assemblies.map((s) => "<tr><td>" + esc(s.item) + "</td><td>" + esc(s.item_name) + "</td><td>Sub-assembly L" + s.level + '</td><td class="n">' +
        num(s.qty) + "</td><td>" + esc((s.used_in || []).join(", ")) + "</td><td>" + esc(s.bom) + "</td></tr>").join("") +
      "</tbody></table>" + '<p class="muted small">Build order: ' + esc(p.build_order.join(" → ")) + "</p>" : "") +
    (r ? '<h3>Created ' + esc(r.production_plan) + "</h3>" +
      '<div class="banner ' + (r.conflicts.count || r.blocks_outside_shift.length ? "err" : "ok") + '">' + r.work_orders.length + " work orders, " + r.job_cards +
      " job cards (" + r.blocks + " scheduled blocks) from " + esc(fmtDT(r.start)) + " to " + esc(fmtDT(r.end)) + ". Blocks outside shifts: " +
      r.blocks_outside_shift.length + ". Capacity conflicts: " + r.conflicts.count + ".</div>" +
      '<table class="t"><thead><tr><th>Work order</th><th>Item</th><th class="n">Qty</th><th>Planned start</th><th>Planned end</th></tr></thead><tbody>' +
      r.work_orders.map((w) => '<tr class="click" data-wo="' + esc(w.name) + '"><td><b>' + esc(w.name) + "</b></td><td>" + esc(w.item) + '<div class="muted small">' +
        esc(w.item_name) + '</div></td><td class="n">' + num(w.qty, 0) + "</td><td>" + esc(fmtDT(w.planned_start_date)) + "</td><td>" + esc(fmtDT(w.planned_end_date)) +
        "</td></tr>").join("") + "</tbody></table>" +
      '<p><a class="lnk" href="#" data-nav="Schedule Board">Open the Schedule Board →</a></p>' : "");
}

function readLines() {
  return S.lines.map((l) => ({ item: l.item, qty: Number(l.qty), start: l.start }));
}

async function preview() {
  setBusy(true);
  try {
    S.preview = await MES.post("mes_create_plan", { items: readLines(), preview: 1 });
    S.result = null;
    render();
  } catch (e) {
    toast(e.message, "err");
  } finally {
    setBusy(false);
  }
}

async function create() {
  const lines = readLines();
  const ok = await dialog("Create production plan",
    "This creates and submits a Production Plan and its work orders in ERPNext for:<ul>" +
    lines.map((l) => "<li><b>" + esc(l.qty) + " × " + esc(l.item) + "</b> from " + esc(l.start) + "</li>").join("") + "</ul>", "Create plan");
  if (!ok) return;
  setBusy(true);
  try {
    S.result = await MES.post("mes_create_plan", { items: lines });
    S.preview = null;
    render();
    toast("Created " + S.result.production_plan + " with " + S.result.work_orders.length + " work orders");
  } catch (e) {
    toast(e.message, "err");
  } finally {
    setBusy(false);
  }
}

document.addEventListener("click", (e) => {
  if (e.target.id === "b-add") {
    const used = S.lines.map((l) => l.item);
    const next = S.items.find((it) => used.indexOf(it.item) < 0) || S.items[0];
    S.lines.push({ item: next ? next.item : "", qty: 10, start: S.nextDay });
    render();
  } else if (e.target.dataset.del !== undefined) {
    S.lines.splice(Number(e.target.dataset.del), 1);
    render();
  } else if (e.target.id === "b-preview") preview();
  else if (e.target.id === "b-create") create();
  else {
    const tr = e.target.closest("tr[data-wo]");
    if (tr) MES.navigate("Work Order Detail", { wo: tr.dataset.wo });
  }
});

document.addEventListener("change", (e) => {
  const row = e.target.closest("[data-line]");
  if (row && e.target.dataset.f) {
    S.lines[Number(row.dataset.line)][e.target.dataset.f] = e.target.value;
    S.preview = null;
  }
});

startPage(async () => {
  render();
  setBusy(true);
  try {
    const m = await MES.get("mes_create_plan", { list_items: 1 });
    S.items = m.items || [];
    S.nextDay = m.next_working_day;
    S.lines = [{ item: (S.items.find((i) => i.item === "FG-DRL-800") || S.items[0] || {}).item, qty: 10, start: S.nextDay }];
    render();
  } catch (e) {
    toast(e.message, "err");
  } finally {
    setBusy(false);
  }
});
```

### A.6 `schedule_board.js`

Page Schedule Board (M2 + M5): Gantt coloured by product line or status, hover card, drag-and-drop rescheduling.

```javascript
// Page: Schedule Board (M2 read + M5 drag-and-drop). Data: mes_schedule_board; moves: mes_reschedule_job_card.
// Self-contained SVG-free Gantt (no CDN): one lane per workstation, x axis = each day's 07:00-18:00 window.
const DAY_START = 7, DAY_END = 18, ROW_H = 42, LABEL_W = 170, SNAP_MIN = 5;
const MOVABLE = ["Open", "Material Transferred"];
const COLORS = {
  "Open": "#3b82f6", "Material Transferred": "#06b6d4", "Work In Progress": "#f59e0b", "On Hold": "#a855f7",
  "Paused": "#a855f7", "Completed": "#10b981", "Submitted": "#10b981",
};
// Product lines, from the item code suffix (P1 naming: FG-DRL-800, SA-HSG-RH, SA-ARM-S = 800W motor parts, ...)
const FAMILIES = [
  { key: "DRL", label: "Drill", color: "#2563eb", test: (c) => /-DRL\b/.test(c) },
  { key: "RH", label: "Rotary Hammer", color: "#7c3aed", test: (c) => /-RH\b/.test(c) },
  { key: "CS", label: "Circular Saw", color: "#0f766e", test: (c) => /-CS\b/.test(c) },
  { key: "S", label: "800W motor parts (Drill + Hammer)", color: "#c2410c", test: (c) => /-S$/.test(c) },
  { key: "L", label: "1400W motor parts (Saw)", color: "#be185d", test: (c) => /-L$/.test(c) },
];
const family = (code) => FAMILIES.find((f) => f.test(code || "")) || { key: "?", label: "Other", color: "#6b7280" };
const shortCode = (code) => String(code || "").replace(/^(SA|FG)-/, "");
const S = { from: isoDate(new Date()), days: 7, type: "", zoom: 40, colorBy: "product", d: null, drag: null };

const dayW = () => (DAY_END - DAY_START) * S.zoom;
const fromDate = () => parseDT(S.from);

function timeToX(dt) {
  const d = dt instanceof Date ? dt : parseDT(dt);
  const day = Math.floor((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - fromDate()) / 86400000);
  let h = d.getHours() + d.getMinutes() / 60;
  h = Math.max(DAY_START, Math.min(DAY_END, h));
  return day * dayW() + (h - DAY_START) * S.zoom;
}

function xToTime(x) {
  const day = Math.floor(x / dayW());
  let mins = ((x - day * dayW()) / S.zoom + DAY_START) * 60;
  mins = Math.round(mins / SNAP_MIN) * SNAP_MIN;
  const d = addDays(fromDate(), day);
  d.setHours(0, mins, 0, 0);
  return d;
}

async function load() {
  setBusy(true);
  try {
    S.d = await MES.get("mes_schedule_board", {
      from_date: S.from, to_date: isoDate(addDays(fromDate(), S.days - 1)), workstation_type: S.type,
    });
    render();
  } catch (e) {
    toast(e.message, "err");
  } finally {
    setBusy(false);
  }
}

function jobInfo(jc) {
  const blocks = S.d.items.filter((i) => i.job_card === jc).sort((a, b) => (a.start > b.start ? 1 : -1));
  return { blocks, first: blocks[0], start: blocks[0] && blocks[0].start, end: blocks.length && blocks[blocks.length - 1].end };
}

function render() {
  const d = S.d || { groups: [], items: [], conflicts: { count: 0, job_cards: [] }, workstation_types: [] };
  const conflictSet = new Set(d.conflicts.job_cards || []);
  const totalW = S.days * dayW();
  const now = new Date();
  let header = "", shade = "";
  for (let i = 0; i < S.days; i++) {
    const day = addDays(fromDate(), i);
    const wk = day.getDay() === 0 || day.getDay() === 6;
    header += '<div class="g-day' + (wk ? " wk" : "") + '" style="left:' + i * dayW() + "px;width:" + dayW() + 'px">' + fmtD(day) +
      '<span class="g-hrs">' + [8, 12, 13, 17].map((h) => '<i style="left:' + (h - DAY_START) * S.zoom + 'px">' + h + "</i>").join("") + "</span></div>";
    // non-working bands: before 08:00, lunch 12-13, after 17:00 (from the P1 shift calendar), whole weekend days
    shade += wk ? '<div class="g-off" style="left:' + i * dayW() + "px;width:" + dayW() + 'px"></div>'
      : [[7, 8], [12, 13], [17, 18]].map((b) => '<div class="g-off" style="left:' + (i * dayW() + (b[0] - DAY_START) * S.zoom) + "px;width:" + (b[1] - b[0]) * S.zoom + 'px"></div>').join("") +
        '<div class="g-sep" style="left:' + i * dayW() + 'px"></div>';
  }
  const nowX = now >= fromDate() && now < addDays(fromDate(), S.days) ? timeToX(now) : -1;
  const lanes = d.groups.map((g, gi) => {
    const bars = d.items.filter((it) => it.group === g.id).map((it) => {
      const x = timeToX(it.start), w = Math.max(4, timeToX(it.end) - x);
      const movable = MOVABLE.indexOf(it.status) >= 0;
      const fill = S.colorBy === "status" ? COLORS[it.status] || "#6b7280" : family(it.item).color;
      const st = it.status === "Completed" ? " st-done" : it.status === "Work In Progress" ? " st-wip" : (it.status === "On Hold" || it.status === "Paused") ? " st-hold" : "";
      // shrink the label to fit: "ARM-S ×65" -> "ARM-S" -> "" (about 7px per character); the hover card has everything
      const tick = it.status === "Completed" ? "✓ " : "";
      const full = tick + shortCode(it.item) + " ×" + num(it.qty, 0), codeOnly = tick + shortCode(it.item);
      const fits = (t) => t.length * 7 + 12 <= w;
      const label = fits(full) ? full : fits(codeOnly) ? codeOnly : "";
      return '<div class="g-bar' + (movable ? " mv" : "") + st + (conflictSet.has(it.job_card) ? " cf" : "") + '" data-jc="' + esc(it.job_card) + '" data-id="' + esc(it.id) +
        '" style="left:' + x + "px;width:" + w + "px;background:" + fill + '">' + esc(label) + "</div>";
    }).join("");
    return '<div class="g-row" data-row="' + gi + '" style="top:' + gi * ROW_H + "px;height:" + ROW_H + 'px"><div class="g-label"><b>' + esc(g.id) + "</b><span>" +
      esc(g.workstation_type.replace(/^P1 /, "")) + (g.capacity > 1 ? " · cap " + g.capacity : "") + '</span></div><div class="g-lane" style="width:' + totalW + 'px">' + bars + "</div></div>";
  }).join("");

  $("#app").innerHTML =
    navBar("Schedule Board") +
    '<div class="row" style="margin-bottom:6px">' +
    '<h2 style="margin:0 12px 0 0">Schedule Board <span class="spin"></span></h2>' +
    '<label class="f">From<input type="date" id="f-from" value="' + esc(S.from) + '"></label>' +
    '<label class="f">Days<select id="f-days">' + [7, 14, 21, 30, 45, 60].map((n) => "<option" + (n === S.days ? " selected" : "") + ">" + n + "</option>").join("") + "</select></label>" +
    '<label class="f">Workstation type<select id="f-type"><option value="">All types</option>' + (d.workstation_types || []).map((t) =>
      "<option" + (t === S.type ? " selected" : "") + ">" + esc(t) + "</option>").join("") + "</select></label>" +
    '<label class="f">Zoom<select id="f-zoom">' + [[12, "S"], [24, "M"], [40, "L"], [64, "XL"]].map((z) =>
      '<option value="' + z[0] + '"' + (z[0] === S.zoom ? " selected" : "") + ">" + z[1] + "</option>").join("") + "</select></label>" +
    '<label class="f">Colour by<select id="f-color"><option value="product"' + (S.colorBy === "product" ? " selected" : "") + ">Product line</option>" +
    '<option value="status"' + (S.colorBy === "status" ? " selected" : "") + ">Job status</option></select></label>" +
    '<button class="btn" id="b-refresh">Refresh</button></div>' +
    '<div class="g-legend small">' + (S.colorBy === "status"
      ? ["Open", "Work In Progress", "On Hold", "Completed"].map((k) => '<span><i style="background:' + COLORS[k] + '"></i>' + k + "</span>").join("")
      : FAMILIES.map((f) => '<span><i style="background:' + f.color + '"></i>' + esc(f.label) + "</span>").join("") +
        '<span class="muted">✓ completed · striped = in progress · dashed = on hold</span>') +
    '<span class="muted">Bar label = item code without SA-/FG- and quantity, e.g. "ARM-S ×65". Hover a bar for details.</span></div>' +
    (d.conflicts.count
      ? '<div class="banner err">⚠ ' + d.conflicts.count + " capacity conflict slot(s): " + esc(d.conflicts.job_cards.join(", ")) + " (outlined red)</div>"
      : '<div class="banner ok">No capacity conflicts · ' + d.job_card_count + " job cards, " + d.items.length + " scheduled blocks in view</div>") +
    '<div class="g-wrap" id="gwrap"><div class="g-inner" style="width:' + (totalW + LABEL_W) + "px;height:" + (d.groups.length * ROW_H + 40) + 'px">' +
    '<div class="g-head" style="width:' + (totalW + LABEL_W) + 'px"><div class="g-corner">Workstation</div><div class="g-days" style="width:' + totalW + 'px">' + header + "</div></div>" +
    '<div class="g-body" style="height:' + d.groups.length * ROW_H + 'px"><div class="g-shade" style="left:' + LABEL_W + "px;width:" + totalW + 'px">' + shade +
    (nowX >= 0 ? '<div class="g-now" style="left:' + nowX + 'px"></div>' : "") + "</div>" + lanes + "</div></div></div>" +
    '<p class="muted small">Drag an open job card along its row (or to another workstation of the same type). ERPNext checks shift, holiday, capacity and ' +
    "operation order first and refuses invalid moves; you confirm valid ones. Click a bar for details.</p>" +
    '<div id="g-tip" class="g-tip"></div>';
}

// ---- hover card ----
document.addEventListener("pointerover", (e) => {
  const tip = $("#g-tip");
  if (!tip) return;
  const bar = e.target.closest && e.target.closest(".g-bar");
  if (!bar || S.drag) { tip.style.display = "none"; return; }
  const it = S.d.items.find((i) => i.id === bar.dataset.id);
  if (!it) return;
  const info = jobInfo(it.job_card), fam = family(it.item);
  tip.innerHTML = '<div class="t1"><i style="background:' + fam.color + '"></i>' + esc(it.item) + " × " + num(it.qty, 0) + "</div>" +
    '<div class="t2">' + esc(it.item_name || "") + "</div><table>" +
    [["Operation", it.operation], ["Job card", it.job_card + " · " + it.status], ["Work order", it.work_order + (it.plan ? " · " + it.plan : "")],
      ["Product line", fam.label], ["This block", fmtDT(it.start) + " → " + fmtDT(it.end).slice(-5)],
      ["Whole job", fmtDT(info.start) + " → " + fmtDT(info.end) + (info.blocks.length > 1 ? " (" + info.blocks.length + " blocks)" : "")],
      ["Done", num(it.completed_qty, 0) + " of " + num(it.qty, 0)]].map((r) => "<tr><td>" + esc(r[0]) + "</td><td>" + esc(r[1]) + "</td></tr>").join("") +
    '</table><div class="t3">' + (MOVABLE.indexOf(it.status) >= 0 ? "Drag to reschedule · click for options" : "Started or finished: cannot be moved") + "</div>";
  tip.style.display = "block";
});
document.addEventListener("pointermove", (e) => {
  const tip = $("#g-tip");
  if (!tip || tip.style.display !== "block") return;
  if (S.drag) { tip.style.display = "none"; return; }
  const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
  const y = e.clientY + 16 + tip.offsetHeight > innerHeight ? e.clientY - tip.offsetHeight - 10 : e.clientY + 16;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
});

// ---- drag & drop ----
document.addEventListener("pointerdown", (e) => {
  const bar = e.target.closest(".g-bar");
  if (!bar || e.button > 0) return;
  const jc = bar.dataset.jc;
  const info = jobInfo(jc);
  const row = bar.closest(".g-row");
  S.drag = {
    jc, info, bar, x0: e.clientX, y0: e.clientY, row0: Number(row.dataset.row), moved: false,
    movable: bar.classList.contains("mv"), els: $$('.g-bar[data-jc="' + CSS.escape(jc) + '"]'),
  };
  S.drag.els.forEach((el) => { el.dataset.left = el.style.left; });
  bar.setPointerCapture(e.pointerId);
  e.preventDefault();
});

document.addEventListener("pointermove", (e) => {
  const g = S.drag;
  if (!g) return;
  const dx = e.clientX - g.x0, dy = e.clientY - g.y0;
  if (!g.moved && Math.abs(dx) + Math.abs(dy) < 4) return;
  g.moved = true;
  if (!g.movable) return;
  const rows = Math.round(dy / ROW_H);
  g.dx = dx;
  g.rowTo = Math.max(0, Math.min(S.d.groups.length - 1, g.row0 + rows));
  g.els.forEach((el) => {
    el.classList.add("ghost");
    el.style.left = parseFloat(el.dataset.left) + dx + "px";
    el.style.transform = "translateY(" + (g.rowTo - g.row0) * ROW_H + "px)";
  });
  const t = xToTime(timeToX(g.info.start) + dx);
  g.bar.setAttribute("data-tip", fmtDT(t) + (g.rowTo !== g.row0 ? " · " + S.d.groups[g.rowTo].id : ""));
});

document.addEventListener("pointerup", async (e) => {
  const g = S.drag;
  if (!g) return;
  S.drag = null;
  g.els.forEach((el) => { el.classList.remove("ghost"); el.style.left = el.dataset.left; el.style.transform = ""; });
  g.bar.removeAttribute("data-tip");
  if (!g.moved) return showDetails(g.jc);
  if (!g.movable) return toast(g.jc + " has started or finished (" + g.info.first.status + "); only open job cards can be moved.", "err");
  const newStart = xToTime(timeToX(g.info.start) + g.dx);
  const ws = S.d.groups[g.rowTo].id;
  const body = { job_card: g.jc, new_start: isoDT(newStart) };
  if (ws !== g.info.first.group) body.workstation = ws;
  setBusy(true);
  let check;
  try {
    check = await MES.post("mes_reschedule_job_card", Object.assign({ dry_run: 1 }, body));
  } catch (err) {
    setBusy(false);
    return dialog("Move refused by ERPNext", '<div class="banner err">' + esc(err.message) + "</div>", "OK", { noCancel: true });
  }
  setBusy(false);
  const f = g.info.first;
  const ok = await dialog("Reschedule " + g.jc + "?",
    "<b>" + esc(f.operation) + "</b> · " + esc(f.work_order) + " · " + esc(f.item) + " × " + esc(f.qty) + "<br><br>" +
    "From: " + esc(f.group + " · " + fmtDT(g.info.start) + " → " + fmtDT(g.info.end)) + "<br>" +
    "To: <b>" + esc(check.workstation + " · " + fmtDT(check.start) + " → " + fmtDT(check.end)) + "</b><br>" +
    '<span class="muted small">' + check.blocks.length + " block(s): " + check.blocks.map((b) => esc(fmtDT(b.from_time, false) + "–" + fmtDT(b.to_time, false).slice(-5))).join(", ") + "</span>",
    "Save move");
  if (!ok) return;
  setBusy(true);
  try {
    const r = await MES.post("mes_reschedule_job_card", body);
    toast("Saved: " + r.job_card + " now " + r.workstation + " " + fmtDT(r.start) + " → " + fmtDT(r.end));
    await load();
  } catch (err) {
    dialog("Move refused by ERPNext", '<div class="banner err">' + esc(err.message) + "</div>", "OK", { noCancel: true });
  } finally {
    setBusy(false);
  }
});

async function showDetails(jc) {
  const info = jobInfo(jc), f = info.first;
  const go = await dialog(jc + " · " + f.operation,
    '<div class="grid2">' +
    [["Work order", f.work_order], ["Item", f.item + " · " + (f.item_name || "")], ["Workstation", f.group + " (" + f.workstation_type + ")"], ["Status", f.status],
      ["Qty", num(f.qty, 0) + " (done " + num(f.completed_qty, 0) + ")"], ["Scheduled", fmtDT(info.start) + " → " + fmtDT(info.end)]].map((p) =>
      '<div class="kv"><div class="k">' + esc(p[0]) + '</div><div class="v">' + esc(p[1]) + "</div></div>").join("") + "</div>" +
    '<p class="muted small">' + info.blocks.length + " scheduled block(s). " + (MOVABLE.indexOf(f.status) >= 0 ? "Drag the bar to reschedule." : "Started/finished jobs cannot be moved.") + "</p>",
    "Open work order");
  if (go) MES.navigate("Work Order Detail", { wo: f.work_order });
}

document.addEventListener("change", (e) => {
  if (e.target.id === "f-from") S.from = e.target.value || isoDate(new Date());
  if (e.target.id === "f-days") S.days = Number(e.target.value);
  if (e.target.id === "f-type") S.type = e.target.value;
  if (e.target.id === "f-zoom") { S.zoom = Number(e.target.value); return render(); }
  if (e.target.id === "f-color") { S.colorBy = e.target.value; return render(); }
  if (["f-from", "f-days", "f-type"].indexOf(e.target.id) >= 0) load();
});
document.addEventListener("click", (e) => { if (e.target.id === "b-refresh") load(); });

startPage(() => { render(); load(); });
```

### A.7 `capacity.js`

Page Capacity (M2): workstation x day heat-map.

```javascript
// Page: Capacity (M2). Heat-map workstation x day from mes_workstation_load. Red above 100 %.
const S = { from: isoDate(new Date()), days: 14, type: "", d: null, types: [] };

async function load() {
  setBusy(true);
  try {
    const to = isoDate(addDays(parseDT(S.from), S.days - 1));
    S.d = await MES.get("mes_workstation_load", { from_date: S.from, to_date: to, workstation_type: S.type });
    if (!S.types.length) S.types = Array.from(new Set(S.d.rows.map((r) => r.workstation_type))).sort();
    render();
  } catch (e) {
    toast(e.message, "err");
  } finally {
    setBusy(false);
  }
}

function cellStyle(c) {
  if (c.holiday) return "background:#f3f4f6;color:#9ca3af";
  if (c.load_pct === null) return "";
  const p = c.load_pct;
  if (p > 100) return "background:#dc2626;color:#fff;font-weight:700";
  if (p >= 85) return "background:#f59e0b;color:#111";
  if (p >= 50) return "background:#fde68a";
  if (p > 0) return "background:#d1fae5";
  return "";
}

function render() {
  const d = S.d || { days: [], rows: [] };
  $("#app").innerHTML =
    navBar("Capacity") +
    '<h2>Capacity load <span class="spin"></span></h2>' +
    '<div class="row" style="margin-bottom:10px">' +
    '<label class="f">From<input type="date" id="f-from" value="' + esc(S.from) + '"></label>' +
    '<label class="f">Days<select id="f-days">' + [7, 14, 21, 30, 45, 60].map((n) => "<option" + (n === S.days ? " selected" : "") + ">" + n + "</option>").join("") + "</select></label>" +
    '<label class="f">Workstation type<select id="f-type"><option value="">All types</option>' + S.types.map((t) =>
      "<option" + (t === S.type ? " selected" : "") + ">" + esc(t) + "</option>").join("") + "</select></label>" +
    '<button class="btn" id="b-refresh">Refresh</button>' +
    '<span class="small muted">Load = scheduled job-card minutes ÷ (shift minutes × capacity). Grey = weekend/holiday. ' +
    '<span class="badge" style="background:#d1fae5">&lt;50%</span> <span class="badge" style="background:#fde68a">50–85%</span> ' +
    '<span class="badge" style="background:#f59e0b">85–100%</span> <span class="badge" style="background:#dc2626;color:#fff">&gt;100%</span></span></div>' +
    '<div class="banner info small"><b>Where these numbers come from (all ERPNext, via the mes_workstation_load API):</b> ' +
    "<b>available</b> = the workstation's shift hours (Workstation → Working Hours, 08:00–12:00 + 13:00–17:00 = 480 min) × its Production Capacity " +
    "(the oven runs 20 jobs at once), and 0 on days in its Holiday List (weekends + Malaysian public holidays). " +
    "<b>Scheduled</b> = the Job Card scheduled time blocks that ERPNext's capacity planner booked when each work order was submitted " +
    "(or that were moved on the Schedule Board). <b>Load %</b> = scheduled ÷ available. Hover a cell for the minutes.</div>" +
    '<div style="overflow:auto"><table class="t" style="width:auto"><thead><tr><th>Workstation</th><th class="n">Cap.</th>' +
    d.days.map((day) => {
      const dt = parseDT(day);
      return '<th class="n" style="min-width:58px">' + DOW[dt.getDay()] + "<br>" + pad(dt.getDate()) + " " + MON[dt.getMonth()] + "</th>";
    }).join("") + '<th class="n">Avg</th></tr></thead><tbody>' +
    d.rows.map((r) => {
      const working = r.cells.filter((c) => c.available_mins > 0);
      const avg = working.length ? working.reduce((s, c) => s + c.scheduled_mins, 0) / working.reduce((s, c) => s + c.available_mins, 0) * 100 : 0;
      return "<tr><td><b>" + esc(r.workstation) + '</b><div class="muted small">' + esc(r.workstation_type) + '</div></td><td class="n">' + r.capacity + "</td>" +
        r.cells.map((c) => '<td class="n" style="' + cellStyle(c) + '" title="' + esc(c.date + ": " + num(c.scheduled_mins, 0) + " of " + num(c.available_mins, 0) +
          " min" + (c.holiday ? " · " + c.holiday : "")) + '">' + (c.holiday ? "–" : c.load_pct === null ? "" : num(c.load_pct, 0) + "%") + "</td>").join("") +
        '<td class="n"><b>' + num(avg, 0) + "%</b></td></tr>";
    }).join("") + "</tbody></table></div>";
}

document.addEventListener("change", (e) => {
  if (e.target.id === "f-from") S.from = e.target.value || isoDate(new Date());
  if (e.target.id === "f-days") S.days = Number(e.target.value);
  if (e.target.id === "f-type") S.type = e.target.value;
  if (["f-from", "f-days", "f-type"].indexOf(e.target.id) >= 0) load();
});
document.addEventListener("click", (e) => { if (e.target.id === "b-refresh") load(); });

startPage(() => { render(); load(); });
```

### A.8 `queue.js`

Page Workstation Queue (M6): operator Start/Pause/Resume/Complete, waiting-for-previous-operation check.

```javascript
// Page: Workstation Queue (M6, operators / tablet). Data: mes_workstation_queue.
// Actions use ERPNext's own whitelisted Job Card methods via /api/v2/document/Job Card/{name}/method/...
const S = { ws: "", date: isoDate(new Date()), stations: [], d: null, err: {}, ok: {} };
const V2 = (jc, m) => "/api/v2/document/Job%20Card/" + encodeURIComponent(jc) + "/method/" + m;
const NO_EMPLOYEE = [{ employee: "" }]; // time logs without an employee (the API user has no Employee access)

async function loadStations() {
  const m = await MES.post("mes_workstation_queue", {}); // no workstation -> list of P1 workstations
  S.stations = m.stations || [];
}

async function load() {
  if (!S.ws) return render();
  setBusy(true);
  try {
    S.d = await MES.get("mes_workstation_queue", { workstation: S.ws, date: S.date });
    render();
  } catch (e) {
    toast(e.message, "err");
  } finally {
    setBusy(false);
  }
}

function instructions(html) {
  if (!html) return "";
  // DOMParser builds an inert document (no scripts/handlers run); we only read its text back
  const text = new DOMParser().parseFromString(String(html).replace(/<(br|\/p|\/li|\/div|\/h\d)[^>]*>/gi, "\n"), "text/html").body.textContent || "";
  return '<div class="instr">' + esc(text.trim()).replace(/\n+/g, "<br>") + "</div>";
}

function jobCard(j) {
  const left = Math.max(0, (j.qty || 0) - (j.completed_qty || 0));
  const btns = [];
  const waiting = j.waiting_for || [];
  if (j.state === "Not started") {
    btns.push('<button class="btn big primary" data-do="start"' + (waiting.length ? " disabled" : "") + ">▶ Start</button>");
  }
  if (j.state === "Running") btns.push('<button class="btn big" data-do="pause">❚❚ Pause</button>');
  if (j.state === "Paused") btns.push('<button class="btn big primary" data-do="resume">▶ Resume</button>');
  if (j.state === "Running" || j.state === "Paused") btns.push('<button class="btn big" style="background:#065f46;color:#fff;border-color:#065f46" data-do="complete">✔ Complete</button>');
  return '<div class="job card ' + (j.state === "Completed" ? "done" : "") + '" data-jc="' + esc(j.job_card) + '" data-left="' + left + '">' +
    '<div class="row" style="justify-content:space-between;align-items:center"><div><div class="jt">' + esc(j.operation) + "</div>" +
    '<div class="muted">' + esc(j.job_card) + " · " + esc(j.work_order) + "</div></div><div>" + badge(j.state) + (j.overdue ? " " + badge("Late") : "") + "</div></div>" +
    '<div class="grid2" style="margin:8px 0"><div class="kv"><div class="k">Item</div><div class="v">' + esc(j.item) + " · " + esc(j.item_name) + "</div></div>" +
    '<div class="kv"><div class="k">Quantity</div><div class="v">' + num(j.completed_qty, 0) + " / " + num(j.qty, 0) + "</div></div>" +
    '<div class="kv"><div class="k">Scheduled</div><div class="v">' + esc(fmtDT(j.scheduled_start)) + " → " + esc(fmtDT(j.scheduled_end)) + "</div></div></div>" +
    (waiting.length ? '<div class="banner info">⏳ Waiting for the previous operation: ' + waiting.map((w) =>
      "<b>" + esc(w.operation) + "</b> (" + esc(w.job_card) + ", " + esc(w.status) + ")").join(", ") +
      ". ERPNext only lets this job start once it is completed.</div>" : "") +
    instructions(j.work_instructions) + '<div class="row" style="margin-top:10px">' + btns.join("") + "</div>" +
    (S.err[j.job_card] ? '<div class="banner err">ERPNext refused: ' + esc(S.err[j.job_card]) + "</div>" : "") +
    (S.ok[j.job_card] ? '<div class="banner ok">' + esc(S.ok[j.job_card]) + "</div>" : "") + "</div>";
}

function render() {
  const d = S.d;
  $("#app").innerHTML =
    navBar("Workstation Queue") +
    '<div class="row" style="justify-content:space-between"><h2>Workstation Queue <span class="spin"></span></h2>' +
    '<div class="row"><label class="f">Date<input type="date" id="f-date" value="' + esc(S.date) + '"></label><button class="btn" id="b-refresh">Refresh</button></div></div>' +
    '<div class="ws-grid">' + S.stations.map((w) =>
      '<button class="btn ws ' + (w.name === S.ws ? "primary" : "") + '" data-ws="' + esc(w.name) + '"><b>' + esc(w.name) + "</b><br><small>" +
      esc(w.workstation_type.replace(/^P1 /, "")) + "</small></button>").join("") + "</div>" +
    (!S.ws ? '<div class="card empty">Choose your workstation.</div>'
      : !d ? "" : (d.jobs.length
        ? '<p class="muted">' + d.jobs.filter((j) => j.state !== "Completed").length + " open job(s) on " + esc(d.workstation) + " up to " + esc(fmtD(d.date)) +
          " (overdue first, then by schedule)</p>" + d.jobs.map(jobCard).join("")
        : '<div class="card empty">No jobs scheduled on ' + esc(S.ws) + " up to " + esc(fmtD(S.date)) + ". Pick a later date to see upcoming work.</div>"));
}

async function act(jc, what, left) {
  const now = isoDT(new Date());
  delete S.err[jc];
  delete S.ok[jc];
  try {
    if (what === "start") await MES.request("POST", V2(jc, "start_timer"), { start_time: now, employees: NO_EMPLOYEE });
    if (what === "pause") await MES.request("POST", V2(jc, "pause_job"), { end_time: now });
    if (what === "resume") await MES.request("POST", V2(jc, "resume_job"), { start_time: now, employees: NO_EMPLOYEE });
    if (what === "complete") {
      const v = await dialog("Complete " + jc, '<label class="f">Good quantity<input name="qty" type="number" min="0" value="' + left + '"></label>' +
        '<p class="muted small">Closes the running time log, records the quantity and submits the job card in ERPNext.</p>', "Complete", { withValues: true });
      if (!v) return;
      const job = S.d.jobs.find((j) => j.job_card === jc);
      if (job && job.state === "Paused") await MES.request("POST", V2(jc, "resume_job"), { start_time: now, employees: NO_EMPLOYEE });
      await MES.request("POST", V2(jc, "complete_job_card"), { qty: Number(v.qty), end_time: isoDT(new Date()), auto_submit: 1 });
    }
    S.ok[jc] = { start: "Started", pause: "Paused", resume: "Resumed", complete: "Completed and submitted" }[what] + " in ERPNext at " + now.slice(11, 16) + ".";
    toast(jc + ": " + what + " recorded in ERPNext");
  } catch (e) {
    S.err[jc] = e.message || "Request failed";  // shown on the job card itself, not only as a toast
    toast(jc + ": " + e.message, "err");
  }
  await load();
}

document.addEventListener("click", (e) => {
  const w = e.target.closest("[data-ws]");
  if (w) { S.ws = w.dataset.ws; S.d = null; load(); return; }
  const b = e.target.closest("[data-do]");
  if (b) {
    const card = b.closest("[data-jc]");
    b.disabled = true;
    act(card.dataset.jc, b.dataset.do, card.dataset.left);
    return;
  }
  if (e.target.id === "b-refresh") load();
});
document.addEventListener("change", (e) => { if (e.target.id === "f-date") { S.date = e.target.value || isoDate(new Date()); load(); } });

startPage(async (model) => {
  const q = model.query || {};
  if (q.workstation) S.ws = q.workstation;
  if (q.date) S.date = q.date;
  render();
  try { await loadStations(); } catch (e) { toast(e.message, "err"); }
  load();
  setInterval(() => { if (S.ws && !document.querySelector(".modal-wrap")) load(); }, 60000);
});
```
