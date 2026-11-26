// ---- Station page (Tulip-style shopfloor) ----
// One task per screen: scan your ID badge; 1 pick an order; 2 work order detail; 3 issue materials: scan every material,
// then issue; 4 build: follow the BOM steps and count units; 5 log a defect ticket.
// Andon (machine issue) is always one tap away in the header. Every rule (valid material, stock, duplicates,
// completion gate, machine down) is enforced by the mes_sf_* server scripts; this page shows and sends only.
document.body.classList.remove("sf");
document.body.classList.add("tl");

const DEFECT_REASONS = ["Physical Damage", "Incorrect Component", "Missing Component", "Manufacturing Defect", "Surface Defect", "Electrical Issue", "Mechanical Issue", "Other"];
const ANDON = [
  { status: "Experiencing Problems", label: "Problem", icon: "!", cls: "a1", types: ["Abnormal Noise", "Overheating", "Maintenance Required", "Mechanical Failure", "Electrical Failure", "Other"] },
  { status: "Stalled", label: "Stalled", icon: "&#10074;&#10074;", cls: "a2", types: ["Machine Stalled", "Mechanical Failure", "Electrical Failure", "Other"] },
  { status: "Completely Down", label: "Down", icon: "&#9940;", cls: "a3", types: ["Machine Breakdown", "Electrical Failure", "Mechanical Failure", "Safety Concern", "Other"] },
];
const STEP_RULES = [
  [/grease|lubric|oil|varnish|resin|paste|adhesive|glue/i, "Apply", "Apply an even layer of {name}. Wipe off any excess.", 6],
  [/housing|casing|case|shell|frame|base|body|enclosure/i, "Place", "Place the {name} in the fixture, {em:opening facing up}.", 0],
  [/stator|armature|rotor|motor|core/i, "Insert", "Insert the {name} into the assembly. {em:Align the tabs} so it seats flush.", 2],
  [/bearing|bushing|sleeve/i, "Press-fit", "Press-fit the {name} until it sits {em:flush} with the seat.", 2],
  [/brush|spring|pin|key/i, "Insert", "Insert the {name} into its holder. Check it moves freely.", 3],
  [/gear|pinion|spindle|shaft|clutch|hammer|piston|mechanism/i, "Fit", "Fit the {name}. {em:Check the teeth mesh} before closing.", 3],
  [/switch|pcb|board|controller|module|trigger/i, "Install", "Install the {name} and press until it clicks.", 4],
  [/enamel|magnet wire|copper wire|winding wire|coil/i, "Wind", "Wind the {name} onto the core. {em:Keep the turns tight} and even.", 3],
  [/insulation|paper|tape|film|wedge/i, "Insert", "Insert the {name} into the slots before winding.", 1],
  [/cable|wire|cord|harness|lead|plug|strain/i, "Connect", "Connect the {name}. Route it {em:clear of moving parts}.", 4],
  [/chuck|blade|guard|handle|cover|cap|grip|endbell|end bell/i, "Attach", "Attach the {name} to the assembly.", 5],
  [/screw|bolt|nut|fastener|rivet|washer|clip/i, "Secure with", "Secure the assembly with {qty} {name}. {em:Torque evenly}.", 7],
  [/label|sticker|nameplate|manual|box|carton|bag|foam|insert/i, "Pack with", "Add the {name}.", 8],
];

const S = {
  me: null, stations: [], jobs: [], issues: [], ws: "", metrics: null,
  screen: "station", prev: "orders", sel: "", d: null, search: "", step: 0, flash: null, flashTimer: null,
  scanBusy: false, camAt: null, menu: false, andon: null, ticket: null, defectRow: "", mine: null, wedge: "", wedgeAt: 0,
  emp: null, badgeBusy: false, wodet: null, pendingWo: "",
};

function sfApi(method, args) {
  return api(method, Object.assign({ employee: S.emp ? S.emp.id : "" }, args || {}));
}

function batchTodo(d) {
  return (d.materials || []).filter((m) => m.mode === "batch" && m.status !== "Verified");
}

function issueState(d) {
  const iss = d.issue;
  return { needed: iss.needed, done: !iss.needed || iss.left <= 0, started: iss.issued > 0, left: iss.left, issued: iss.issued,
    entry: iss.entries && iss.entries[0] ? iss.entries[0].name : "" };
}

function wsInfo() { return S.stations.find((s) => s.name === S.ws) || null; }
function selJob() { return S.jobs.find((j) => j.job_card === S.sel) || null; }
function initials(n) { return String(n || "?").split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((x) => x[0].toUpperCase()).join(""); }
function img(url, alt, cls) {
  if (!url) return '<div class="tl-ph ' + (cls || "") + '">No photo</div>';
  return '<img class="' + (cls || "") + '" src="' + esc(fileUrl(url)) + '" alt="' + esc(alt || "") + '" loading="lazy" data-ph="' + esc('<div class="tl-ph ' + (cls || "") + '">No photo</div>') + '">';
}
function pill(text, cls) { return '<span class="tl-pill ' + (cls || "") + '">' + esc(text) + "</span>"; }
function statusPill(s) {
  const m = { Running: "info", Paused: "warn", "Work In Progress": "info", Open: "", "Not Started": "", Completed: "ok", Verified: "ok",
    "Partially Verified": "warn", "Invalid Material": "bad", "Defective Material": "bad", Reported: "bad", "Under Review": "warn", Accepted: "info",
    Resolved: "ok", Closed: "ok", Acknowledged: "info", "In Progress": "warn", Rejected: "", "Rework Required": "warn" };
  return pill(s === "Open" ? "Not started" : s, m[s] || "");
}

// ---------- header ----------
function head() {
  const ws = wsInfo(), me = S.me || {};
  let title = "Choose your station";
  if (S.screen === "badge") title = "Scan your ID badge";
  else if (S.screen !== "station") title = S.d ? S.d.work_order.item_name : (ws ? noPrefix(ws.workstation_type) : "Shopfloor");
  return '<header class="tl-head"><div class="logo"><i>&#9670;</i>VOLTRA</div><div class="title">' + esc(title) + "</div>" +
    (ws ? '<button class="hbtn andon" data-act="andon"><b>!</b>Andon</button>' : "") +
    (ws ? '<button class="hbtn" data-act="restart"><b>&#8635;</b>Restart</button>' : "") +
    '<button class="hbtn" data-act="menu"><b>&#9776;</b>Menu</button>' +
    (S.emp ? '<button class="hbtn" data-act="sign-out" title="Next person: scan a different badge"><b>&#8634;</b>Switch</button>' : "") +
    '<div class="user"><div><span class="av">' + esc(initials(S.emp ? S.emp.name : me.name || operator())) + "</span>" + esc(S.emp ? S.emp.name : "No badge scanned") + "</div>" +
    "<div>" + (S.emp ? esc(S.emp.id) + " · " : "") + (ws ? "Station " + esc(ws.name) : '<span class="tl-muted" style="color:#c7d0e0">No station</span>') + "</div></div></header>" +
    (S.menu ? menuHtml() : "");
}

function menuHtml() {
  const me = S.me || {};
  return '<div class="tl-menu">' +
    '<button data-act="change-ws">&#8646; Change station</button>' +
    '<button data-act="mine">&#128203; My reports</button>' +
    '<button data-nav="Plant Dashboard">&#128202; Plant dashboard</button>' +
    (me.supervisor || me.maintenance ? '<button data-nav="Shopfloor Admin">&#128736; Supervisor / maintenance</button>' : "") +
    (me.supervisor ? '<button data-nav="Work Orders">&#128197; Planner: work orders</button>' : "") + "</div>";
}

function stepsBar() {
  const order = ["orders", "wo", "issue", "assembly", "defect"];
  const names = ["Order", "Work order", "Issue materials", "Build", "Defect ticket"];
  const at = order.indexOf(S.screen);
  if (at < 0) return "";
  const d = S.d && S.d.job.job_card === S.sel ? S.d : null;
  const is = d ? issueState(d) : null;
  return '<nav class="tl-steps">' + names.map((n, i) => {
    const key = order[i];
    const done = (key === "orders" && S.sel) || (key === "issue" && is && is.done) || (key === "assembly" && d && d.job.completed_qty >= d.job.qty);
    const can = key === "orders" || (d && (key !== "assembly" || (is && (is.started || !is.needed))));
    return '<button class="' + (i === at ? "on" : done ? "done" : "") + '" data-goto="' + key + '"' + (can ? "" : " disabled") + '><i>' + (done ? "&#10003;" : i + 1) + "</i>" + esc(n) + "</button>";
  }).join("") + "</nav>";
}

// ---------- screens ----------
function screenStation() {
  if (S.err) return '<main class="tl-main"><div class="tl-banner bad"><b>&#9888;</b><span>' + esc(S.err) + '<br><span style="font-weight:400;font-size:16px">Your Appsmith email must also be an enabled ERPNext user with a shopfloor role (Manufacturing User, Manufacturing Manager or Maintenance).</span></span></div></main>';
  if (!S.stations.length) return '<main class="tl-main"><div class="tl-card">Loading stations&hellip;</div></main>';
  return '<main class="tl-main"><div class="tl-card"><h2>Which station are you working at?<small>Tap your station. It is remembered on this device.</small></h2>' +
    '<div class="tl-stations">' + S.stations.map((s) => {
      const st = s.down ? "down" : s.machine_status === "Stalled" ? "down" : s.machine_status === "Experiencing Problems" ? "warn" : "idle";
      return '<button class="tl-station st-' + st + '" data-ws="' + esc(s.name) + '"><b>' + esc(s.name) + "</b><span>" + esc(noPrefix(s.workstation_type)) +
        "</span><span>" + esc(s.down ? "MACHINE DOWN" : s.machine_status) + "</span></button>";
    }).join("") + "</div></div></main>";
}

function screenOrders() {
  const ws = wsInfo(), m = S.metrics && S.metrics.station, j = selJob();
  let h = '<main class="tl-main" style="grid-template-columns:minmax(380px,1fr) 1.25fr">';
  if (ws && ws.down) h += '<div class="tl-banner bad" style="grid-column:1/-1"><b>&#9940;</b>Machine ' + esc(ws.name) + " is DOWN. Orders here cannot start until maintenance resolves it.</div>";
  h += '<section class="tl-card"><h2>Select or search for orders</h2>' +
    '<div class="tl-search"><span style="font-size:22px;color:#8a95a3">&#128269;</span><input id="osearch" placeholder="Order, item or job…" value="' + esc(S.search) + '" autocomplete="off"></div>' +
    '<div class="tl-scroll"><table class="tl-table"><caption>ALL ORDERS</caption><thead><tr><th>ID (Order)</th><th>Item</th><th>Done</th><th>Due</th></tr></thead><tbody id="orows">' +
    orderRows() + "</tbody></table></div></section>";
  h += '<div style="display:grid;gap:18px;align-content:start"><section class="tl-card"><h2>Performance metrics<small>' + esc(S.ws) + " · today</small></h2>" +
    '<div class="tl-metrics">' +
    metric("Remaining due today", m ? m.remaining_due : "–") +
    metric("Completed today", m ? m.completed : "–", m && m.completed >= m.target_now ? "good" : "") +
    metric("Current target", m ? m.target_now : "–", m && m.completed < m.target_now ? "behind" : "") + "</div></section>" +
    '<section class="tl-card"><h2>Selected order</h2>' + (j ? selectedOrder(j) : '<div class="tl-muted" style="padding:30px 0;text-align:center;font-size:18px">Tap an order on the left to see it here.</div>') + "</section></div>";
  h += "</main>";
  return h;
}

function metric(l, v, cls) {
  return '<div class="tl-metric ' + (cls || "") + '"><div class="l">' + esc(l) + '</div><div class="v">' + esc(typeof v === "number" ? num(v, 0) : v) + "</div></div>";
}

function jobMatches(list, q) {
  return list.filter((j) => !q || [j.work_order, j.job_card, j.item_code, j.item_name, j.operation].join(" ").toLowerCase().indexOf(q) >= 0);
}

async function searchAllStations() {
  if (S.allBusy) return;
  if (!S.allJobs || Date.now() - S.allAt > 30000) {
    S.allBusy = true;
    try { const r = await sfApi("mes_sf_jobs", {}); S.allJobs = r.jobs; S.allAt = Date.now(); } catch (e) { toast(e.message, "err"); S.allJobs = []; }
    S.allBusy = false;
  }
  const tb = $("#orows");
  if (tb && S.screen === "orders") tb.innerHTML = orderRows();
}

function orderRows() {
  const q = S.search.trim().toLowerCase();
  const rows = jobMatches(S.jobs, q);
  if (!rows.length && q.length >= 3) {
    if (!S.allJobs || Date.now() - S.allAt > 30000) { searchAllStations(); return '<tr><td colspan="4" class="tl-muted" style="padding:24px;text-align:center">Not at this station. Searching all stations&hellip;</td></tr>'; }
    const far = jobMatches(S.allJobs, q).filter((j) => j.workstation !== S.ws);
    if (far.length) return '<tr><td colspan="4" class="tl-muted" style="padding:10px 12px">Not at ' + esc(S.ws) + ". Found at other stations: tap to switch there.</td></tr>" +
      far.map((j) => '<tr data-far="' + esc(j.job_card) + '" data-farws="' + esc(j.workstation) + '"><td><b>' + esc(j.work_order) + '</b><div class="tl-muted" style="font-size:13px">' + esc(j.job_card) + " · " + esc(j.operation) +
        "</div></td><td>" + esc(j.item_name) + "</td><td>" + pill("Station " + j.workstation, "info") + "</td><td>" + esc(fmtD(j.scheduled_start)) + "</td></tr>").join("");
  }
  if (!rows.length) return '<tr><td colspan="4" class="tl-muted" style="padding:24px;text-align:center">' + (S.jobs.length || q ? "No open order matches, at this or any other station." : "No open orders at this station.") + "</td></tr>";
  return rows.map((j) => '<tr data-row="' + esc(j.job_card) + '" class="' + (j.job_card === S.sel ? "sel" : "") + '"><td><b>' + esc(j.work_order) + '</b><div class="tl-muted" style="font-size:13px">' +
    esc(j.job_card) + " · " + esc(j.operation) + "</div></td><td>" + esc(j.item_name) + (j.status === "Running" ? " " + pill("Running", "info") : "") + "</td><td>" +
    qtyFmt(j.completed_qty || 0) + '<span class="tl-muted"> of ' + qtyFmt(j.qty) + " done</span></td><td>" + esc(fmtD(j.scheduled_start)) + "</td></tr>").join("");
}

function selectedOrder(j) {
  const ready = j.materials_verified === j.materials_total;
  return '<div style="display:grid;grid-template-columns:200px 1fr;gap:20px;align-items:center">' + img(j.image, j.item_name, "tl-photo") +
    '<div class="tl-kv"><div><div class="k">Item</div><div class="v"><b>' + esc(j.item_name) + '</b></div></div><div><div class="k">Description</div><div class="v">' + esc(j.operation) + "</div></div>" +
    '<div><div class="k">Order ID</div><div class="v">' + esc(j.work_order) + '</div></div><div><div class="k">Due date</div><div class="v">' + esc(fmtDT(j.scheduled_start)) + "</div></div>" +
    '<div><div class="k">QTY required</div><div class="v" style="font-size:26px">' + qtyFmt(j.qty) + '</div></div><div><div class="k">QTY complete</div><div class="v" style="font-size:26px">' + qtyFmt(j.completed_qty) + "</div></div>" +
    '<div class="full"><div class="k">Components</div><div class="v">' + pill(j.materials_verified + " of " + j.materials_total + " scanned", ready ? "ok" : "warn") + " " +
    (j.defective_materials ? pill("Defect open", "bad") : "") + (j.machine_down ? pill("Machine down", "bad") : "") + " " + statusPill(j.status) + "</div></div></div></div>" + orderActions();
}

function orderActions() {
  const d = S.d && S.d.job.job_card === S.sel ? S.d : null;
  if (!d) return '<div class="tl-muted" style="margin-top:14px">Loading order&hellip;</div>';
  const is = issueState(d), running = d.job.status === "Running", sm = d.summary;
  const step1 = !is.needed ? '<div class="tl-act done"><i>&#10003;</i><div><b>Materials</b><span>Consumed directly, no issue needed</span></div></div>'
    : is.done ? '<button class="tl-act done" data-goto="issue"><i>&#10003;</i><div><b>Materials issued</b><span>' + esc(is.entry) +
      (sm.outstanding ? " · " + sm.outstanding + " to scan at Build" : " · all materials scanned") + "</span></div></button>"
    : '<button class="tl-act" data-goto="issue"><i>1</i><div><b>Issue materials</b><span>' +
      (batchTodo(d).length ? "Scan " + batchTodo(d).length + " batch label" + (batchTodo(d).length === 1 ? "" : "s") + ", then issue" : "Batches scanned · tap to issue") + "</span></div></button>";
  const blocking = (d.start_blocking || []).filter((r) => !/not been issued/.test(r));
  const step2 = running ? '<button class="tl-act go" data-act="to-assembly"><i>&#9654;</i><div><b>Building</b><span>Continue on the build page</span></div></button>'
    : '<button class="tl-act go" data-act="start"' + (d.actions.start ? "" : " disabled") + '><i>2</i><div><b>Build</b><span>' +
      (d.actions.start ? "Starts the job in ERPNext and opens the build page" : !is.started ? "Issue materials first" : esc(blocking[0] || "Not available")) + "</span></div></button>";
  return '<div class="tl-acts">' + step1 + step2 + "</div>";
}

function screenBadge() {
  const ws = wsInfo();
  return '<main class="tl-main" style="grid-template-columns:minmax(320px,640px);justify-content:center"><section class="tl-card" style="text-align:center;padding:36px">' +
    '<div style="font-size:64px;line-height:1">&#129706;</div><h2 style="justify-content:center;margin-top:10px">Scan your ID badge<small>Station ' + esc(ws ? ws.name : S.ws) + "</small></h2>" +
    '<p class="tl-muted" style="font-size:17px">ERPNext records your name on every scan, issue, unit and report you make here.</p>' +
    '<div class="tl-scanbar"><input id="badgein" placeholder="Scan badge, or type Employee ID / full name" autocomplete="off" spellcheck="false"' + (S.badgeBusy ? " disabled" : "") + ">" +
    '<button class="tl-btn primary" data-act="badge-enter"' + (S.badgeBusy ? " disabled" : "") + ">Sign in</button></div>" +
    '<div class="tl-muted" style="font-size:14px">For example <b>HR-EMP-00001</b> or <b>Aiman Hakimi</b>.</div></section></main>';
}

function screenIssue() {
  const d = S.d, is = issueState(d), w = d.work_order;
  const batch = d.materials.filter((m) => m.mode === "batch"), later = d.materials.filter((m) => m.mode !== "batch");
  const todo = batchTodo(d), ok = !todo.length;
  const bDone = batch.length - todo.length;
  const left = '<section class="tl-card tl-items" style="max-height:none"><h2>1 · Scan the batch labels<small>' + bDone + " of " + batch.length + " scanned</small></h2>" +
    scanBar("Scan batch label", true) +
    '<div class="tl-item-list">' + (batch.length ? batch.map(itemRow).join("") : '<div class="tl-muted" style="padding:14px">This order has no batch-tracked materials.</div>') + "</div>" +
    (later.length ? '<h2 style="margin-top:18px">Scanned later at Build<small>' + later.filter((m) => m.status === "Verified").length + " of " + later.length + " done</small></h2>" +
      '<div class="tl-muted" style="margin:-4px 0 8px">Per-unit sub-assemblies and plain items. Scan them on the Build page before counting finished units.</div>' +
      '<div class="tl-item-list" style="opacity:.75">' + later.map(itemRow).join("") + "</div>" : "") + "</section>";
  let act;
  if (!is.needed) act = '<div class="tl-banner ok"><b>&#10003;</b><span>This order consumes materials directly. No issue is needed.</span></div>';
  else if (is.done) act = '<div class="tl-banner ok"><b>&#10003;</b><span>Materials issued in ERPNext: <b>' + esc(is.entry) + "</b></span></div>";
  else act = '<button class="tl-btn big green" style="width:100%" data-act="issue"' + (ok && !S.busyIssue ? "" : " disabled") + ">&#10004; 2 · Issue materials for " + qtyFmt(is.left) + " units</button>" +
    '<div class="tl-muted" style="margin-top:8px">' + (ok ? "Batch labels scanned. Issuing moves this order's materials from stores to the line in ERPNext, taking exactly the scanned batches." :
      "Scan the " + todo.length + " batch label" + (todo.length === 1 ? "" : "s") + " still open in the list first.") + "</div>";
  const running = d.job.status === "Running";
  const next = is.started || !is.needed ? '<button class="tl-btn big primary" style="width:100%;margin-top:14px" data-act="' + (running ? "to-assembly" : "start") + '"' +
    (running || d.actions.start ? "" : " disabled") + ">&#9654; 3 · " + (running ? "Continue building" : "Start building") + "</button>" : "";
  const right = '<section class="tl-card tl-issue-side" style="display:grid;gap:14px;align-content:start"><div class="tl-making">' + img(w.image, w.item_name) +
    '<div><span class="tl-muted">Issuing for</span><b>' + esc(w.item_name) + "</b><span>" + esc(w.name) + " · " + qtyFmt(w.qty) + " units</span></div></div>" +
    '<div class="tl-counter"><div class="h">Batch labels scanned</div><div class="v">' + bDone + '</div><div class="r"><b>' + batch.length + "</b>Required</div></div>" +
    '<div class="tl-muted">Scanning as <b style="color:#1b2430">' + esc(S.emp ? S.emp.name : "") + "</b></div>" + act + next + "</section>";
  return '<main class="tl-main" style="grid-template-columns:1.4fr minmax(300px,1fr)">' + left + right + "</main>" +
    '<button class="tl-back" data-act="to-orders">&larr; Orders</button>';
}

function screenWo() {
  const x = S.wodet;
  if (!x || x.header.name !== S.d.work_order.name) return '<main class="tl-main"><section class="tl-card">Loading work order&hellip;</section></main>';
  const h = x.header;
  const kv = (k, v) => '<div><div class="k">' + esc(k) + '</div><div class="v">' + v + "</div></div>";
  const pct = (a, b) => (b ? Math.min(100, 100 * (a || 0) / b) : 0).toFixed(1);
  const bar = (p, c) => '<div style="height:10px;background:#e7eaee;border-radius:5px;overflow:hidden"><span style="display:block;height:100%;width:' + p + "%;background:" + c + '"></span></div>';
  return '<main class="tl-main" style="grid-template-columns:1fr;align-content:start"><section class="tl-card"><h2>' + esc(h.name) + " · " + esc(h.item_name) +
    '<small><a href="' + esc(MES.deskUrl("Work Order", h.name)) + '" target="_blank" rel="noopener">Open in ERPNext &#8599;</a></small></h2>' +
    '<div class="tl-kv" style="grid-template-columns:repeat(4,1fr)">' + kv("Status", statusPill(h.status) + (h.late ? " " + pill("Late", "bad") : "")) + kv("Qty to make", qtyFmt(h.qty)) +
    kv("Produced", qtyFmt(h.produced_qty)) + kv("Materials issued for", qtyFmt(h.transferred_qty)) +
    kv("Planned start", esc(fmtDT(h.planned_start_date))) + kv("Planned end", esc(fmtDT(h.planned_end_date))) + kv("BOM", esc(h.bom_no)) +
    kv("Warehouses", esc((h.source_warehouse || "") + " → " + (h.wip_warehouse || "") + " → " + (h.fg_warehouse || ""))) + "</div>" +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:14px"><div><div class="tl-muted">Produced ' + qtyFmt(h.produced_qty) + " of " + qtyFmt(h.qty) + "</div>" + bar(pct(h.produced_qty, h.qty), "#2e9e5b") +
    '</div><div><div class="tl-muted">Materials issued for ' + qtyFmt(h.transferred_qty) + " of " + qtyFmt(h.qty) + "</div>" + bar(pct(h.transferred_qty, h.qty), "#2f6fd6") + "</div></div></section>" +
    '<section class="tl-card"><h2>Operations</h2><table class="tl-table"><thead><tr><th>#</th><th>Operation</th><th>Station</th><th>Job</th><th>Status</th><th>Scheduled</th><th>Actual</th></tr></thead><tbody>' +
    x.operations.map((o) => "<tr" + (o.job_card === S.sel ? ' class="sel"' : "") + "><td>" + o.idx + "</td><td>" + esc(o.operation) + "</td><td>" + esc(o.workstation || "-") + "</td><td>" + esc(o.job_card || "-") +
      "</td><td>" + statusPill(o.job_card_status || o.op_status) + "</td><td>" + esc(fmtDT(o.scheduled_start)) + "</td><td>" + esc(o.actual_start ? fmtDT(o.actual_start) + " → " + (fmtDT(o.actual_end) || "…") : "-") + "</td></tr>").join("") +
    "</tbody></table></section>" +
    '<section class="tl-card"><h2>Materials</h2><table class="tl-table"><thead><tr><th>Item</th><th>Required</th><th>Issued</th><th>Consumed</th><th>In stores</th><th>Short</th></tr></thead><tbody>' +
    x.materials.map((m) => "<tr><td><b>" + esc(m.item_code) + '</b><div class="tl-muted" style="font-size:13px">' + esc(m.item_name) + "</div></td><td>" + qtyFmt(m.required_qty) + "</td><td>" + qtyFmt(m.transferred_qty) +
      "</td><td>" + qtyFmt(m.consumed_qty) + "</td><td>" + qtyFmt(m.in_stock) + '</td><td style="color:' + (m.short > 0 ? "#d33a2c" : "inherit") + '">' + (m.short > 0 ? qtyFmt(m.short) : "–") + "</td></tr>").join("") +
    "</tbody></table></section></main>" +
    '<button class="tl-back" data-act="to-orders">&larr; Orders</button>';
}

async function loadWo() {
  if (!S.d) return;
  try { S.wodet = await MES.get("mes_work_order_detail", { work_order: S.d.work_order.name }); } catch (e) { toast(e.message, "err"); }
  if (S.screen === "wo") render();
}

function lastScans(code) {
  return (S.d.scans || []).filter((s) => s.item_code === code);
}

function scanBar(ph, compact) {
  return '<div class="tl-scanbar"><input id="scanin" placeholder="' + esc(ph) + '" autocomplete="off" autocapitalize="characters" spellcheck="false">' +
    '<button class="tl-btn primary" data-act="scan-enter"' + (S.scanBusy ? " disabled" : "") + ">Enter</button>" +
    '<label class="tl-btn" style="cursor:pointer">&#128444; Read photo<input type="file" accept="image/*" capture="environment" id="scanphoto" hidden></label></div>' +
    '<div class="tl-muted" style="font-size:' + (compact ? 12 : 14) + 'px;margin:-4px 0 10px">' + (compact ? "USB scanner, <b>Camera scan</b> button above, or photo. QR and barcodes."
      : "USB scanner: just scan. Camera: tap <b>Camera scan</b> above this screen. QR codes and barcodes both work.") + "</div>";
}

function itemRow(m) {
  const mine = lastScans(m.item_code);
  const last = mine[0];
  const ok = m.status === "Verified";
  const bad = !ok && (m.status === "Invalid Material" || m.status === "Defective Material");
  const valid = mine.filter((x) => x.result === "Valid");
  const lot = valid.length ? (valid[0].unit_id || valid[0].scanned_value) : "";
  const avail = (m.issued_qty || 0) + (m.in_stock || 0);
  const enough = ok || avail + 1e-9 >= m.remaining_qty;
  const why = (last && last.result !== "Valid" && last.reason) || (m.status === "Defective Material" ? "Defect reported: waiting for supervisor" : m.status);
  const sub = ok ? "&#10003; Verified" + (lot ? " · " + esc(lot) : "") : bad ? "&#10008; " + esc(why) :
    m.mode === "unit" ? "Scan each unit · " + m.units_scanned + " of " + qtyFmt(m.required_qty) : m.mode === "batch" ? "Scan its batch label · " + qtyFmt(m.verified_qty) + " of " + qtyFmt(m.required_qty) : m.mode === "confirm" ? "Scan its barcode, or weigh and confirm" : "Scan its barcode";
  let act = "";
  if (!ok && m.mode === "confirm") {
    act = '<div class="tl-item-q"><input type="number" step="any" min="0" data-cq="' + esc(m.item_code) + '" value="' + esc(m.remaining_qty) + '"><span>' + esc(m.uom) +
      '</span><button class="tl-btn green" data-confirm="' + esc(m.item_code) + '">Confirm</button></div>';
  }
  return '<div class="tl-item ' + (ok ? "ok" : bad ? "bad" : "") + '">' + img(m.image, m.item_name) + '<div class="tx"><b>' + esc(m.item_name) + '</b><span class="code">' +
    esc(m.item_code) + " · " + qtyFmt(m.per_unit) + " " + esc(m.uom) + " per unit</span>" + '<span class="st">' + sub + "</span>" +
    (enough ? "" : '<span class="st" style="color:#d33a2c">&#9888; Only ' + qtyFmt(avail) + " available</span>") + act + "</div>" +
    '<span class="tl-check ' + (ok ? "ok" : bad ? "bad" : "") + '">' + (ok ? "&#10003;" : bad ? "&#10005;" : "") + "</span></div>";
}

// ---------- build steps ----------
function buildSteps() {
  const d = S.d, qtyJob = d.job.qty || d.work_order.qty || 1;
  const steps = d.materials.map((m, i) => {
    const rule = STEP_RULES.find((r) => r[0].test(m.item_name + " " + m.item_code)) || [null, "Attach", "Attach the {name} to the assembly.", 5];
    const per = m.per_unit || (m.required_qty / qtyJob);
    const perTxt = qtyFmt(Math.round(per * 1000) / 1000) + " " + (m.uom || "");
    const shortName = m.item_name.replace(/\s*\(.*?\)\s*/g, " ").trim();
    const hint = rule[2].replace("{name}", shortName).replace("{qty}", perTxt).replace(/\{em:([^}]+)\}/g, "<em>$1</em>");
    return { order: rule[3] * 100 + i, verb: rule[1], name: shortName, title: rule[1] + " " + shortName, hint: hint, per: perTxt, image: m.image, code: m.item_code };
  }).sort((a, b) => a.order - b.order);
  steps.push({ verb: "Inspect", title: "Inspect and test the unit", name: d.work_order.item_name, hint: "Check the finished <em>" + esc(d.work_order.item_name) + "</em> runs and looks right. Log a defect if anything is wrong.", per: "", image: d.work_order.image, code: d.work_order.item_code, last: true });
  return steps;
}

function stepKey() { return "mes.tl.step." + S.sel; }

function screenAssembly() {
  const d = S.d, j = d.job, steps = buildSteps();
  if (S.step >= steps.length) S.step = steps.length - 1;
  const st = steps[S.step];
  const running = j.status === "Running";
  const s = d.summary, allOk = s.outstanding === 0;
  const canCount = Math.max(0, Math.min(j.remaining_qty, (s.buildable || 0) - (j.completed_qty || 0)));
  const w = d.work_order;
  const left = '<section class="tl-card tl-items"><div class="tl-making">' + img(w.image, w.item_name) + '<div><span class="tl-muted">Making</span><b>' + esc(w.item_name) +
    "</b><span>" + esc(w.name) + " · " + esc(j.operation) + "</span></div></div>" +
    '<h2>Materials<small>' + s.materials_verified + " of " + s.materials_total + " scanned</small></h2>" + (allOk ? "" : scanBar("Scan item barcode / serial", true)) +
    '<div class="tl-item-list">' + d.materials.map(itemRow).join("") + "</div></section>";
  let center = '<section class="tl-card" style="display:flex;flex-direction:column">';
  if (!allOk) center += '<div class="tl-banner ' + (canCount > 0 ? "ok" : "warn") + '" style="margin-bottom:12px;font-size:16px"><b>' + (canCount > 0 ? "&#10003;" : "&#9646;&#9646;") + "</b><span>" +
    (canCount > 0 ? "Parts scanned for " + qtyFmt(s.buildable) + " unit" + (s.buildable === 1 ? "" : "s") + ": you can count " + qtyFmt(canCount) + " more. Scan the next set on the left as you build."
      : "Scan one more set of parts on the left (one of each material) to count the next unit.") + "</span></div>";
  if (!running) center += '<div class="tl-banner warn" style="margin-bottom:12px"><b>&#10074;&#10074;</b><span style="flex:1">Production is not running on this order.</span><button class="tl-btn green" data-act="resume">&#9654; Start / resume</button></div>';
  center += '<h1 class="tl-step-title">Step ' + (S.step + 1) + ": " + esc(st.title) + "</h1>" +
    '<p class="tl-step-hint">' + st.hint + (st.per ? ' <span class="tl-muted">· uses ' + esc(st.per) + " per unit</span>" : "") + "</p>" +
    '<div class="tl-step-img">' + (st.image ? '<img src="' + esc(fileUrl(st.image)) + '" alt="">' : '<div class="tl-ph" style="width:100%;height:100%">No photo for ' + esc(st.code) + "</div>") + "</div>" +
    '<div class="tl-seq-h">Work sequence<small>Tap a step to open it</small></div><div class="tl-seq">' + steps.map((x, i) =>
      '<button data-step="' + i + '" class="' + (i === S.step ? "on" : i < S.step ? "done" : "") + '"><span class="n">' + (i < S.step ? "&#10003;" : i + 1) + '</span><span class="t">' + esc(x.title) + "</span>" +
      (x.image ? '<img src="' + esc(fileUrl(x.image)) + '" alt="">' : "") + "</button>").join("") + "</div>" +
    '<div style="display:flex;gap:10px;margin-top:14px"><button class="tl-btn big" data-act="step-prev"' + (S.step ? "" : " disabled") + ">&#9664; Previous</button>" +
    (st.last ? '<button class="tl-btn big green" style="flex:1" data-act="unit-done"' + (running && canCount > 0 ? "" : " disabled") + ">&#10004; Unit complete (+1)</button>"
      : '<button class="tl-btn big primary" style="flex:1" data-act="step-next">Next step &#9654;</button>') + "</div></section>";
  const defects = d.defects || [];
  const right = '<section class="tl-card" style="display:grid;gap:14px;align-content:start"><h2 style="margin:0">Assembly progress</h2>' +
    '<div class="tl-muted">Lot: <b style="color:#1b2430">' + esc(j.job_card) + "</b></div>" +
    '<div class="tl-counter"><div class="h">Completed counter</div><div class="v">' + qtyFmt(j.completed_qty) + '</div><div class="r"><b>' + qtyFmt(j.qty) + "</b>Required</div></div>" +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><button class="tl-btn grey big" data-act="add-one"' + (running && canCount > 0 ? "" : " disabled") + ">+ 1</button>" +
    '<button class="tl-btn grey big" data-act="add-all"' + (running && canCount > 0 ? "" : " disabled") + ">+ All</button></div>" +
    '<div class="tl-mini-list"><div class="h">Defects</div><div class="b">' + (defects.length ? defects.map((x) => "<div><b>" + esc(x.unit_id || x.item_code) + "</b> " + esc(x.category) + " " + statusPill(x.status) + "</div>").join("") : '<span class="tl-muted">None logged</span>') + "</div></div>" +
    '<button class="tl-btn grey big" data-act="to-defect">&#8856; Log defect</button>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><button class="tl-btn" data-act="pause"' + (running ? "" : " disabled") + ">&#10074;&#10074; Pause</button>" +
    '<button class="tl-btn green" data-act="complete"' + (d.actions.complete && j.completed_qty > 0 ? "" : " disabled") + ">&#10004; Finish order</button></div></section>";
  const pct = j.qty ? Math.min(100, 100 * j.completed_qty / j.qty) : 0;
  return '<main class="tl-main" style="grid-template-columns:340px 1fr 240px">' + left + center + right + "</main>" +
    '<button class="tl-back" data-act="to-orders">&larr; Orders</button>' +
    '<div class="tl-progress"><span style="width:' + pct.toFixed(1) + '%"></span></div>';
}

// ---------- defect ticket ----------
function stationItems() {
  const d = S.d, rows = [];
  d.materials.forEach((m) => {
    const valid = lastScans(m.item_code).filter((x) => x.result === "Valid" || x.result === "Defective");
    const units = valid.filter((x) => x.unit_id);
    if (units.length) units.forEach((u) => rows.push({ key: m.item_code + "::" + u.unit_id, item_code: m.item_code, item_name: m.item_name, image: m.image, lot: u.unit_id, uom: m.uom, mode: m.mode_label, unit: true, flagged: u.result === "Defective" }));
    else rows.push({ key: m.item_code + "::", item_code: m.item_code, item_name: m.item_name, image: m.image, lot: valid.length ? valid[0].scanned_value : "", uom: m.uom, mode: m.mode_label, unit: false });
  });
  const w = d.work_order;
  rows.push({ key: w.item_code + "::fg", item_code: w.item_code, item_name: w.item_name, image: w.image, lot: d.job.job_card + "-" + (Math.round(d.job.completed_qty || 0) + 1), uom: "Nos", mode: "Finished product (current unit)", unit: false, fg: true });
  return rows;
}

function screenDefect() {
  const rows = stationItems();
  const r = rows.find((x) => x.key === S.defectRow);
  let h = '<main class="tl-main" style="grid-template-columns:1.15fr 1fr"><section class="tl-card"><h2>Select the defective item</h2>' + scanBar("Scan the serial / lot barcode of the bad item") +
    '<div class="tl-scroll" style="max-height:calc(100vh - 360px)"><table class="tl-table"><thead><tr><th>Photo</th><th>Material ID (Lot)</th><th>Item</th><th>Description</th></tr></thead><tbody>' +
    rows.map((x) => '<tr data-drow="' + esc(x.key) + '" class="' + (x.key === S.defectRow ? "sel" : "") + '"><td>' + img(x.image, x.item_name, "thumb") + '</td><td style="font-family:ui-monospace,Consolas,monospace">' +
      esc(x.lot || "—") + (x.flagged ? " " + pill("Flagged", "bad") : "") + "</td><td>" + esc(x.item_code) + "</td><td>" + esc(x.item_name) + (x.fg ? '<div class="tl-muted" style="font-size:13px">Finished product</div>' : "") + "</td></tr>").join("") +
    "</tbody></table></div></section>";
  h += '<section class="tl-card tl-ticket">' + (S.ticket ? ticketDone() : r ? ticketForm(r) : '<div class="tl-muted" style="text-align:center;padding:60px 10px;font-size:19px">&#8592; Tap the item that has a problem,<br>or scan its serial / lot barcode.</div>') + "</section></main>";
  h += '<button class="tl-back" data-act="defect-back">&larr; Previous</button>';
  return h;
}

function ticketForm(r) {
  const f = S.form;
  return '<div class="head"><h3>Defect Ticket</h3><div class="item">' + esc(r.item_name) + "</div></div>" +
    '<div class="top"><div class="tl-kv"><div><div class="k">Description</div><div class="v">' + esc(r.item_name) + '</div></div><div><div class="k">Type</div><div class="v">' + esc(r.mode) + "</div></div>" +
    '<div><div class="k">Unit of measure</div><div class="v">' + esc(r.uom) + '</div></div><div><div class="k">Item code</div><div class="v">' + esc(r.item_code) + "</div></div></div>" + img(r.image, r.item_name) + "</div>" +
    '<div class="row2"><div><label for="flot">Material ID (Lot)</label><input id="flot" value="' + esc(f.lot) + '" autocomplete="off"></div>' +
    '<div><label for="freason">Defect reason</label><select id="freason"><option value="">Select an option</option>' + DEFECT_REASONS.map((c) => '<option' + (f.category === c ? " selected" : "") + ">" + esc(c) + "</option>").join("") + "</select></div></div>" +
    '<div class="row2"><div><label for="fqty">Quantity</label><div class="tl-qty"><button class="tl-btn" data-act="qty-minus">&minus;</button><input id="fqty" type="number" min="1" step="1" value="' + esc(f.qty) + '"' + (r.unit ? " disabled" : "") + '><button class="tl-btn" data-act="qty-plus"' + (r.unit ? " disabled" : "") + ">+</button></div></div>" +
    '<div><label>Photo / file (optional)</label><div style="display:flex;gap:8px"><label class="tl-btn" style="cursor:pointer;flex:1">&#128247; Photo<input type="file" accept="image/*" capture="environment" data-attach="1" hidden></label>' +
    '<label class="tl-btn" style="cursor:pointer;flex:1">&#128206; File<input type="file" multiple data-attach="1" hidden></label></div></div></div>' +
    '<div class="tl-files">' + f.files.map((x, i) => '<div class="f">' + (/^data:image\//.test(x.data) ? '<img src="' + x.data + '" alt="">' : esc(x.file_name.slice(0, 14))) + '<button data-unattach="' + i + '">&#10005;</button></div>').join("") + "</div>" +
    '<div style="margin-top:12px"><label for="fdesc">Comment</label><textarea id="fdesc" placeholder="What is wrong? (optional)">' + esc(f.description) + "</textarea></div>" +
    '<button class="tl-btn red big" style="width:100%;margin-top:14px" data-act="send-defect"' + (f.sending ? " disabled" : "") + ">&#8856; Submit defect ticket</button>";
}

function ticketDone() {
  const t = S.ticket;
  return '<div class="head"><h3>Defect Ticket</h3><div class="item">' + esc(t.item_name) + "</div></div>" +
    '<div class="tl-banner ok"><b>&#10003;</b><span>Ticket <b style="font-size:20px">' + esc(t.id) + "</b> sent to the supervisor." + (t.flagged ? " That unit no longer counts as verified." : "") + "</span></div>" +
    '<div class="tl-kv" style="margin-top:14px"><div><div class="k">Material ID (Lot)</div><div class="v">' + esc(t.lot || "—") + '</div></div><div><div class="k">Reason</div><div class="v">' + esc(t.category) + "</div></div>" +
    '<div><div class="k">Quantity</div><div class="v">' + qtyFmt(t.qty) + '</div></div><div><div class="k">Item</div><div class="v">' + esc(t.item_code) + "</div></div></div>" +
    '<div class="tl-barcode">' + code128Svg(t.id) + "<div>" + esc(t.id) + "</div></div>" +
    '<div style="display:flex;gap:10px;margin-top:16px"><button class="tl-btn big" style="flex:1" data-act="new-ticket">Log another</button><button class="tl-btn big primary" style="flex:1" data-act="defect-back">Back to work</button></div>';
}

// ---------- my reports ----------
function screenMine() {
  const m = S.mine || { defects: [], issues: [] };
  const list = (rows, kind) => rows.length ? '<table class="tl-table"><thead><tr><th>Ticket</th><th>' + (kind === "d" ? "Item / reason" : "Machine / issue") + "</th><th>Status</th><th>When</th></tr></thead><tbody>" +
    rows.map((x) => "<tr><td><b>" + esc(x.name) + "</b></td><td>" + (kind === "d" ? esc(x.item_code) + (x.unit_id ? " · " + esc(x.unit_id) : "") + '<div class="tl-muted">' + esc(x.category) + "</div>"
      : esc(x.workstation) + '<div class="tl-muted">' + esc(x.issue_type) + " · " + esc(x.machine_status) + "</div>") + "</td><td>" + statusPill(x.status) +
      (x.disposition ? " " + pill(x.disposition, "info") : "") + "</td><td>" + esc(fmtWhen(x.creation)) + "</td></tr>").join("") + "</tbody></table>" : '<div class="tl-muted">None yet.</div>';
  return '<main class="tl-main" style="grid-template-columns:1fr 1fr"><section class="tl-card"><h2>My defect tickets</h2>' + list(m.defects || [], "d") +
    '</section><section class="tl-card"><h2>My machine issues</h2>' + list(m.issues || [], "i") + "</section></main>" +
    '<button class="tl-back" data-act="to-orders">&larr; Orders</button>';
}

// ---------- andon ----------
function andonHtml() {
  const a = S.andon, ws = wsInfo();
  if (!a) return "";
  const sel = ANDON.find((x) => x.status === a.status);
  const open = S.issues.filter((i) => i.workstation === S.ws);
  return '<div class="tl-modal"><div class="in"><h2>Andon · ' + esc(S.ws) + '</h2><div class="sub">' + esc(ws ? ws.workstation_type : "") + ". Maintenance is notified the moment you send.</div>" +
    '<div class="tl-andon">' + ANDON.map((x) => '<button class="' + x.cls + (a.status === x.status ? " sel" : "") + '" data-andon="' + esc(x.status) + '"><b>' + x.icon + "</b>Machine " + esc(x.label.toLowerCase()) + "</button>").join("") + "</div>" +
    (sel ? '<div style="font-weight:600">What is wrong?</div><div class="tl-chips">' + sel.types.map((t) => '<button class="' + (a.type === t ? "sel" : "") + '" data-atype="' + esc(t) + '">' + esc(t) + "</button>").join("") + "</div>" +
      '<textarea id="anote" style="width:100%;min-height:70px" placeholder="Anything maintenance should know? (optional)">' + esc(a.note) + "</textarea>" +
      '<div class="tl-files">' + a.files.map((x, i) => '<div class="f">' + (/^data:image\//.test(x.data) ? '<img src="' + x.data + '" alt="">' : esc(x.file_name.slice(0, 14))) + '<button data-aunattach="' + i + '">&#10005;</button></div>').join("") + "</div>" : "") +
    '<div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">' + (sel ? '<label class="tl-btn" style="cursor:pointer">&#128247; Add photo<input type="file" accept="image/*" capture="environment" data-aattach="1" hidden></label>' : "") +
    '<span style="flex:1"></span><button class="tl-btn big" data-act="andon-close">Cancel</button><button class="tl-btn big red" data-act="andon-send"' + (sel && a.type && !a.sending ? "" : " disabled") + ">Send to maintenance</button></div>" +
    (open.length ? '<h3 style="margin:20px 0 8px">Open issues on this machine</h3>' + open.map((i) => '<div style="display:flex;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid #eef0f2"><b>' + esc(i.name) + "</b>" +
      esc(i.issue_type) + " " + statusPill(i.status) + " " + pill(i.machine_status, i.machine_status === "Completely Down" || i.machine_status === "Stalled" ? "bad" : "warn") + '<span class="tl-muted" style="margin-left:auto">' + esc(fmtWhen(i.creation)) + "</span></div>").join("") : "") +
    "</div></div>";
}

// ---------- render ----------
function render() {
  let body = "";
  if (!S.ws && S.screen !== "mine") S.screen = "station";
  if (S.ws && !S.emp && S.screen !== "station") { if (S.screen !== "badge") S.screenAfterBadge = S.screen; S.screen = "badge"; }
  if (["assembly", "defect", "issue", "wo"].indexOf(S.screen) >= 0 && !S.d) S.screen = "orders";
  if (S.screen === "station") body = screenStation();
  else if (S.screen === "badge") body = screenBadge();
  else if (S.screen === "orders") body = screenOrders();
  else if (S.screen === "issue") body = screenIssue();
  else if (S.screen === "wo") body = screenWo();
  else if (S.screen === "assembly") body = screenAssembly();
  else if (S.screen === "defect") body = screenDefect();
  else if (S.screen === "mine") body = screenMine();
  $("#app").innerHTML = head() + stepsBar() + body + andonHtml() + flashHtml();
  afterRender();
}

function flashHtml() {
  const f = S.flash;
  if (!f) return "";
  return '<div class="tl-flash ' + (f.ok ? "ok" : "bad") + '">' + (f.image ? '<img src="' + esc(fileUrl(f.image)) + '" alt="">' : "") + "<div><b>" + esc(f.title) + "</b>" + esc(f.text || "") + "</div></div>";
}

function flash(ok, title, text, image) {
  S.flash = { ok: ok, title: title, text: text, image: image };
  clearTimeout(S.flashTimer);
  S.flashTimer = setTimeout(() => { S.flash = null; const el = $(".tl-flash"); if (el) el.remove(); }, ok ? 2200 : 5000);
}

function afterRender() {
  const si = $("#scanin");
  if (si && !S.andon) {
    si.focus();
    si.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); const v = si.value; si.value = ""; handleScan(v); } });
  }
  const bi = $("#badgein");
  if (bi && !S.andon) {
    bi.focus();
    bi.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); const v = bi.value; bi.value = ""; signIn(v); } });
  }
  const os = $("#osearch");
  if (os) os.addEventListener("input", () => { S.search = os.value; const tb = $("#orows"); if (tb) tb.innerHTML = orderRows(); });
  const sp = $("#scanphoto");
  if (sp) sp.onchange = () => readPhoto(sp.files[0]);
  $$("input[data-attach]").forEach((inp) => {
    inp.onchange = async () => {
      try { keepForm(); const got = await readFiles(inp.files, 10); S.form.files = S.form.files.concat(got).slice(0, 6); render(); } catch (e) { toast(e.message, "err"); }
    };
  });
  $$("input[data-aattach]").forEach((inp) => {
    inp.onchange = async () => {
      try { keepAndon(); const got = await readFiles(inp.files, 10); S.andon.files = S.andon.files.concat(got).slice(0, 4); render(); } catch (e) { toast(e.message, "err"); }
    };
  });
}

function keepForm() {
  const f = S.form;
  if (!f) return;
  const v = (id) => { const el = $(id); return el ? el.value : null; };
  if (v("#flot") !== null) f.lot = v("#flot");
  if (v("#freason") !== null) f.category = v("#freason");
  if (v("#fqty") !== null) f.qty = v("#fqty");
  if (v("#fdesc") !== null) f.description = v("#fdesc");
}

function keepAndon() {
  const el = $("#anote");
  if (S.andon && el) S.andon.note = el.value;
}

// ---------- data ----------
async function loadJobs() {
  setBusy(true);
  try {
    const want = S.pendingWo;
    let r = await sfApi("mes_sf_jobs", { workstation: S.ws, work_order: want });
    if (want) {
      S.pendingWo = "";
      const first = (r.wo_jobs || [])[0];
      if (!first) toast(want + " has no open job at any station", "err");
      else {
        if (first.workstation !== S.ws) { S.ws = first.workstation; PREFS.set("mes.sf.ws", S.ws); r = await sfApi("mes_sf_jobs", { workstation: S.ws }); }
        S.sel = first.job_card; S.d = null;
        S.openAfter = true;
      }
    }
    S.me = r.operator; S.stations = r.workstations; S.jobs = r.jobs; S.issues = r.issues; S.err = "";
    if (S.ws && !wsInfo()) { S.ws = ""; PREFS.set("mes.sf.ws", null); }
    if (S.sel && !selJob()) S.sel = "";
    if (S.ws) {
      sfApi("mes_sf_dashboard", { workstation: S.ws }).then((m) => { S.metrics = m; if (S.screen === "orders") render(); }).catch(() => {});
    }
  } catch (e) {
    toast(e.message, "err");
    if (!S.stations.length) { S.err = e.message; S.screen = "station"; }
  } finally { setBusy(false); render(); }
  if (S.openAfter && S.sel) {
    S.openAfter = false;
    try {
      const d = await loadJob(S.sel);
      const is = issueState(d);
      S.screen = !is.done ? "issue" : "orders";
    } catch (e) { toast(e.message, "err"); }
    render();
  }
}

async function signIn(code) {
  code = String(code || "").trim();
  if (!code || S.badgeBusy) return;
  S.badgeBusy = true; render();
  try {
    const r = await api("mes_sf_badge", { employee: code });
    S.emp = r.employee;
    PREFS.set("mes.sf.emp", JSON.stringify(S.emp));
    beep(true); flash(true, "✔ Signed in", S.emp.name + " · " + S.emp.id);
    S.screen = S.d && S.screenAfterBadge ? S.screenAfterBadge : "orders";
    S.screenAfterBadge = "";
  } catch (e) { beep(false); flash(false, "✘ Badge not accepted", e.message); }
  S.badgeBusy = false; render();
}

async function goTo(key) {
  if (key !== "orders" && !S.d) return;
  if (key === "orders") { S.screen = "orders"; return render(); }
  if (key === "assembly") { S.screen = "assembly"; S.step = Number(PREFS.get(stepKey()) || 0); return render(); }
  if (key === "defect") { S.prev = S.screen; S.screen = "defect"; S.ticket = null; S.defectRow = ""; S.form = null; return render(); }
  S.screen = key; render();
  if (key === "wo") loadWo();
}

async function loadJob(jc) {
  const r = await sfApi("mes_sf_job", { job_card: jc });
  S.d = r; S.me = r.operator; S.sel = jc;
  return r;
}

// ---------- scanning ----------
function handleScan(raw) {
  const code = String(raw || "").trim();
  if (!code) return;
  if (S.andon) return;
  if (S.screen === "badge") return signIn(code);
  if (S.screen === "issue") return submitScan(code);
  if (S.screen === "assembly") {
    if (S.d && S.d.summary.outstanding > 0) return submitScan(code);
    beep(false); toast("Every material is already scanned for this order. To report a bad part, use Log defect.", "err");
    return;
  }
  if (S.screen === "defect") return pickDefectByCode(code);
  if (S.screen === "orders") {
    const j = S.jobs.find((x) => x.job_card === code || x.work_order === code);
    if (j) { S.sel = j.job_card; beep(true); S.d = null; render(); loadJob(j.job_card).then(render, (e) => toast(e.message, "err")); return; }
    if (/^MFG-WO-/i.test(code)) { S.pendingWo = code.toUpperCase(); return loadJobs(); }
    if (S.d && S.d.job.job_card === S.sel) { S.screen = "issue"; render(); return submitScan(code); }
    beep(false); toast(code + " is not an order at this station. Pick the order first, then scan its materials on Issue materials.", "err");
    return;
  }
  toast("Scanned " + code + ". Scanning is used on the Issue materials, Build and Defect screens.", "err");
}

function scannedAs(r, value) {
  const id = r.unit_id ? "Unit " + r.unit_id : r.batch_no ? "Batch " + r.batch_no : "";
  if (!id) return value;
  return value && value !== r.unit_id && value !== r.batch_no ? id + " (label " + value + ")" : id;
}

async function submitScan(value) {
  if (S.scanBusy || !S.d) return;
  S.scanBusy = true;
  const m = S.d.materials.find((x) => x.item_code === value);
  const q = m ? $('input[data-cq="' + value + '"]') : null;
  try {
    const r = await sfApi("mes_sf_scan", { job_card: S.sel, value: value, qty: q ? q.value : "", qty_mode: "remaining", request_id: reqId() });
    beep(r.ok);
    if (r.ok) flash(true, "✔ " + (r.item_name || r.item_code) + " verified", scannedAs(r, value) + (r.unit_id ? "" : " · Qty " + qtyFmt(r.qty)), r.image);
    else flash(false, "✘ Invalid: not counted", (r.unit_id || r.batch_no ? scannedAs(r, value) + " · " + (r.item_code || "") + ". " : "") + (r.reason || ""), r.image);
    await loadJob(S.sel);
  } catch (e) {
    beep(false); flash(false, "✘ Scan failed", e.message);
  } finally { S.scanBusy = false; render(); }
}

async function confirmQty(code) {
  const el = $('input[data-cq="' + code + '"]');
  if (!el) return;
  return submitScanQty(code, el.value);
}

async function submitScanQty(code, qty) {
  S.scanBusy = true;
  try {
    const r = await sfApi("mes_sf_scan", { job_card: S.sel, value: code, qty: qty, request_id: reqId() });
    beep(r.ok);
    if (r.ok) flash(true, "✔ " + (r.item_name || code) + " confirmed", qtyFmt(r.qty), r.image); else flash(false, "✘ Not confirmed", r.reason || "");
    await loadJob(S.sel);
  } catch (e) { beep(false); flash(false, "✘ Not confirmed", e.message); } finally { S.scanBusy = false; render(); }
}

function pickDefectByCode(code) {
  const rows = stationItems();
  const c = code.toLowerCase();
  let r = rows.find((x) => x.lot && x.lot.toLowerCase() === c) || rows.find((x) => x.item_code.toLowerCase() === c);
  if (!r) {
    const sc = (S.d.scans || []).find((x) => [x.scanned_value, x.serial_no, x.barcode, x.batch_no].some((v) => (v || "").toLowerCase() === c));
    if (sc) r = rows.find((x) => x.item_code === sc.item_code && (!sc.unit_id || x.lot === sc.unit_id));
  }
  if (!r) { beep(false); flash(false, "✘ Not at this station", code + " was not scanned into this order. Tap the item instead."); return render(); }
  beep(true);
  selectDefectRow(r.key, r.unit ? r.lot : code);
}

function selectDefectRow(key, lot) {
  const r = stationItems().find((x) => x.key === key);
  if (!r) return;
  S.defectRow = key; S.ticket = null;
  S.form = { rid: reqId(), lot: lot !== undefined ? lot : r.lot, category: "", qty: 1, description: "", files: [], sending: false };
  render();
}

function photoToCanvas(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => {
      const scale = Math.min(1, 1600 / Math.max(im.width, im.height));
      const c = document.createElement("canvas");
      c.width = Math.round(im.width * scale); c.height = Math.round(im.height * scale);
      c.getContext("2d").drawImage(im, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c);
    };
    im.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Could not open the photo")); };
    im.src = url;
  });
}

async function readPhoto(file) {
  if (!file) return;
  try {
    const canvas = await photoToCanvas(file);
    let code = null;
    if ("BarcodeDetector" in window) {
      try { const found = await new BarcodeDetector().detect(canvas); if (found.length) code = found[0].rawValue; } catch (e) { code = null; }
    }
    if (!code && typeof jsQR === "function") {
      const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height);
      const res = jsQR(data.data, data.width, data.height, { inversionAttempts: "attemptBoth" });
      if (res && res.data) code = res.data;
    }
    if (!code) { beep(false); flash(false, "✘ No code found", "No QR code or barcode was readable in that photo. Try closer, flatter and well lit."); return render(); }
    handleScan(code);
  } catch (e) { toast(e.message, "err"); }
}

function watchCamera(model) {
  const cam = model && model.store && model.store.sfCam;
  if (!cam || !cam.at || cam.at === S.camAt) return;
  S.camAt = cam.at;
  handleScan(cam.code);
}

document.addEventListener("keydown", (e) => {
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
  const now = Date.now();
  if (e.key === "Enter") {
    if (S.wedge.length >= 3 && now - S.wedgeAt < 300) { const v = S.wedge; S.wedge = ""; e.preventDefault(); handleScan(v); }
    S.wedge = "";
    return;
  }
  if (e.key.length !== 1) return;
  if (now - S.wedgeAt > 300) S.wedge = "";
  S.wedge += e.key; S.wedgeAt = now;
});

// ---------- production ----------
async function progress(action, qty) {
  setBusy(true);
  try {
    const r = await sfApi("mes_sf_progress", { job_card: S.sel, action: action, qty: qty || 0 });
    if (r.ok) {
      beep(true);
      if (action === "complete") flash(true, "✔ Order finished", "Job " + S.sel + " submitted in ERPNext with " + qtyFmt(r.completed_qty) + " good units");
      else if (action === "report") flash(true, "✔ +" + qtyFmt(qty) + " complete", qtyFmt(r.completed_qty) + " of " + qtyFmt(r.qty) + " done");
      else if (action === "start") flash(true, "▶ Production started", S.sel);
    } else {
      beep(false); flash(false, "✘ Not allowed yet", (r.blocking || []).slice(0, 3).join(" · "));
    }
    await loadJob(S.sel);
    return r;
  } catch (e) { beep(false); flash(false, "✘ " + action + " failed", e.message); return null; } finally { setBusy(false); render(); }
}

async function issueMaterials() {
  const d = S.d;
  const ok = await dialog("Issue materials", "<p>Create and submit a <b>Material Transfer for Manufacture</b> in ERPNext for <b>" + esc(d.work_order.name) +
    "</b>, moving the materials for " + qtyFmt(d.issue.left) + " units from stores to work in progress?</p>", "Issue materials");
  if (!ok) return;
  S.busyIssue = true; setBusy(true); render();
  try {
    const r = await sfApi("mes_sf_issue", { job_card: S.sel });
    if (r.ok && r.stock_entry) { beep(true); flash(true, "\u2714 Materials issued", r.stock_entry + " submitted in ERPNext" + ((r.batches || []).length ? " \u00b7 batches " + r.batches.map((b) => b.batch_no + " \u00d7" + qtyFmt(b.qty)).join(", ") : "")); }
    else if (r.ok) { flash(true, "\u2714 Nothing to issue", r.message || ""); }
    else if ((r.scans_needed || []).length) { beep(false); flash(false, "\u2718 Scan the batch labels first", r.scans_needed.slice(0, 3).join(" \u00b7 ")); }
    else if ((r.batch_scans_needed || []).length) { beep(false); flash(false, "\u2718 Scan batch labels first", r.batch_scans_needed.slice(0, 3).join(" \u00b7 ")); }
    else { beep(false); flash(false, "\u2718 Not enough stock", (r.shortages || []).slice(0, 3).join(" · ")); }
    await loadJob(S.sel);
  } catch (e) { beep(false); flash(false, "\u2718 Issue failed", e.message); }
  S.busyIssue = false; setBusy(false); render();
}

async function startJob() {
  const d = S.d;
  if (d.job.status !== "Running") {
    const r = await progress("start");
    if (!r || !r.ok) return;
  }
  S.screen = "assembly";
  S.step = Number(PREFS.get(stepKey()) || 0);
  render();
}

async function unitDone(n) {
  const r = await progress("report", n);
  if (r && r.ok) { S.step = 0; PREFS.set(stepKey(), "0"); render(); }
}

async function finishOrder() {
  const j = S.d.job;
  const ok = await dialog("Finish order", "<p>Submit job <b>" + esc(j.job_card) + "</b> in ERPNext with <b>" + qtyFmt(j.completed_qty) + "</b> of " + qtyFmt(j.qty) +
    " good units?</p><p>This cannot be undone from the shopfloor.</p>", "Finish order");
  if (!ok) return;
  const r = await progress("complete", 0);
  if (r && r.ok) { PREFS.set(stepKey(), null); S.d = null; S.sel = ""; S.screen = "orders"; await loadJobs(); }
}

async function sendDefect() {
  keepForm();
  const f = S.form, r = stationItems().find((x) => x.key === S.defectRow);
  if (!r) return;
  if (!f.category) return toast("Choose a defect reason", "err");
  const qty = r.unit ? 1 : Number(f.qty || 0);
  if (!(qty > 0)) return toast("Quantity must be at least 1", "err");
  f.sending = true; render();
  try {
    const desc = (f.description || "").trim() || (f.category + " on " + r.item_name + (f.lot ? " (" + f.lot + ")" : ""));
    const res = await sfApi("mes_sf_defect", { job_card: S.sel, item_code: r.item_code, unit_id: r.unit ? r.lot : "", qty_affected: qty, category: f.category,
      description: desc + (!r.unit && f.lot ? "\nLot / ID: " + f.lot : ""), files: f.files.map((x) => ({ file_name: x.file_name, data: x.data })), request_id: f.rid });
    beep(true);
    S.ticket = { id: res.defect, item_name: r.item_name, item_code: r.item_code, lot: f.lot, category: f.category, qty: qty, flagged: res.flagged_scans && res.flagged_scans.length };
    await loadJob(S.sel);
  } catch (e) { f.sending = false; beep(false); toast(e.message, "err"); }
  render();
}

async function sendAndon() {
  keepAndon();
  const a = S.andon;
  a.sending = true; render();
  try {
    const desc = (a.note || "").trim() || (a.type + " reported from the station screen");
    const jc = S.d && S.d.job.workstation === S.ws ? S.sel : "";
    const r = await sfApi("mes_sf_machine_issue", { workstation: S.ws, job_card: jc, issue_type: a.type, severity: a.status === "Experiencing Problems" ? "Medium" : "High",
      machine_status: a.status, description: desc, files: a.files.map((x) => ({ file_name: x.file_name, data: x.data })), request_id: a.rid });
    beep(true);
    S.andon = null;
    flash(true, "✔ Maintenance notified", "Issue " + r.issue + " (" + r.severity + ")");
    await loadJobs();
    if (S.sel && S.d) await loadJob(S.sel);
  } catch (e) { a.sending = false; beep(false); toast(e.message, "err"); }
  render();
}

// ---------- Code 128-B barcode (SVG) for defect ticket ids ----------
const C128 = ("212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 " +
  "221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 " +
  "231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 " +
  "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 " +
  "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 " +
  "114131 311141 411131 211412 211214 211232 2331112").split(" ");

function code128Svg(text) {
  const vals = [104];
  String(text).split("").forEach((ch) => { const c = ch.charCodeAt(0); vals.push(c >= 32 && c <= 126 ? c - 32 : 0); });
  let sum = vals[0];
  for (let i = 1; i < vals.length; i++) sum += vals[i] * i;
  vals.push(sum % 103, 106);
  let x = 10, bars = "";
  vals.forEach((v) => {
    C128[v].split("").forEach((w, i) => {
      const n = +w;
      if (i % 2 === 0) bars += '<rect x="' + x + '" y="0" width="' + n + '" height="60"/>';
      x += n;
    });
  });
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + (x + 10) + ' 60" preserveAspectRatio="none" fill="#111">' + bars + "</svg>";
}

// ---------- clicks ----------
document.addEventListener("click", async (e) => {
  const t = e.target.closest && e.target.closest("[data-act],[data-goto],[data-far],[data-ws],[data-row],[data-step],[data-drow],[data-confirm],[data-unattach],[data-andon],[data-atype],[data-aunattach]");
  if (!t) { if (S.menu && !(e.target.closest && e.target.closest(".tl-menu"))) { S.menu = false; render(); } return; }
  e.preventDefault();
  const ds = t.dataset;
  if (ds.goto) return goTo(ds.goto);
  if (ds.far) {
    S.ws = ds.farws; PREFS.set("mes.sf.ws", S.ws); S.search = ""; S.sel = ds.far; S.d = null; S.metrics = null; S.screen = "orders";
    await loadJobs();
    try { await loadJob(ds.far); } catch (err) { toast(err.message, "err"); }
    return render();
  }
  if (ds.ws) { S.ws = ds.ws; PREFS.set("mes.sf.ws", S.ws); S.screen = "orders"; S.sel = ""; S.d = null; S.metrics = null; return loadJobs(); }
  if (ds.row) {
    S.sel = ds.row; S.d = null; render();
    try { await loadJob(ds.row); } catch (err) { toast(err.message, "err"); }
    return render();
  }
  if (ds.step !== undefined) { S.step = +ds.step; PREFS.set(stepKey(), String(S.step)); return render(); }
  if (ds.drow) return selectDefectRow(ds.drow);
  if (ds.confirm) return confirmQty(ds.confirm);
  if (ds.unattach !== undefined) { keepForm(); S.form.files.splice(+ds.unattach, 1); return render(); }
  if (ds.andon) { keepAndon(); S.andon.status = ds.andon; S.andon.type = (ANDON.find((x) => x.status === ds.andon) || {}).types[0]; return render(); }
  if (ds.atype) { keepAndon(); S.andon.type = ds.atype; return render(); }
  if (ds.aunattach !== undefined) { keepAndon(); S.andon.files.splice(+ds.aunattach, 1); return render(); }
  const act = ds.act;
  if (act !== "menu") S.menu = false;
  switch (act) {
    case "menu": S.menu = !S.menu; return render();
    case "badge-enter": { const bi = $("#badgein"); return signIn(bi ? bi.value : ""); }
    case "sign-out": S.emp = null; PREFS.set("mes.sf.emp", null); S.screenAfterBadge = S.screen; S.screen = "badge"; return render();
    case "change-ws": S.ws = ""; PREFS.set("mes.sf.ws", null); S.d = null; S.sel = ""; S.screen = "station"; return render();
    case "restart": S.d = null; S.screen = "orders"; S.ticket = null; S.defectRow = ""; return loadJobs();
    case "mine":
      setBusy(true);
      try { S.mine = await sfApi("mes_sf_admin", { action: "my_reports" }); } catch (err) { toast(err.message, "err"); }
      setBusy(false); S.screen = "mine"; return render();
    case "andon": S.andon = { status: "", type: "", note: "", files: [], rid: reqId(), sending: false }; return render();
    case "andon-close": S.andon = null; return render();
    case "andon-send": return sendAndon();
    case "issue": return issueMaterials();
    case "start": return startJob();
    case "to-assembly": S.screen = "assembly"; S.step = Number(PREFS.get(stepKey()) || 0); return render();
    case "to-orders": S.screen = "orders"; return loadJobs();
    case "resume": return progress("start");
    case "scan-enter": { const si = $("#scanin"); const v = si ? si.value : ""; if (si) si.value = ""; return handleScan(v); }
    case "step-next": S.step += 1; PREFS.set(stepKey(), String(S.step)); return render();
    case "step-prev": S.step = Math.max(0, S.step - 1); PREFS.set(stepKey(), String(S.step)); return render();
    case "unit-done": case "add-one": return unitDone(1);
    case "add-all": {
      const left = Math.max(0, Math.min(S.d.job.remaining_qty, (S.d.summary.buildable || 0) - (S.d.job.completed_qty || 0)));
      if (!(left > 0)) return;
      if (!(await dialog("Complete all", "<p>Report <b>" + qtyFmt(left) + "</b> more good units on " + esc(S.sel) + "?</p>", "Report " + qtyFmt(left)))) return;
      return unitDone(left);
    }
    case "pause": return progress("pause", 0);
    case "complete": return finishOrder();
    case "to-defect": S.prev = S.screen; S.screen = "defect"; S.ticket = null; S.defectRow = ""; S.form = null; return render();
    case "defect-back": S.screen = "assembly"; S.ticket = null; return render();
    case "new-ticket": S.ticket = null; S.defectRow = ""; S.form = null; return render();
    case "send-defect": return sendDefect();
    case "qty-minus": keepForm(); S.form.qty = Math.max(1, Number(S.form.qty || 1) - 1); return render();
    case "qty-plus": keepForm(); S.form.qty = Number(S.form.qty || 0) + 1; return render();
  }
});

startPage((model) => {
  const cam0 = model && model.store && model.store.sfCam;
  S.camAt = cam0 && cam0.at ? cam0.at : 0;
  appsmith.onModelChange((m) => watchCamera(m));
  if (!operator() || operator() === "harness") {
    $("#app").innerHTML = '<main class="tl-main"><div class="tl-banner bad">No signed-in operator. Open this page while logged in to Appsmith (or add ?as=&lt;erpnext user&gt; in the dev harness).</div></main>';
    return;
  }
  S.ws = PREFS.get("mes.sf.ws") || "";
  try { S.emp = JSON.parse(PREFS.get("mes.sf.emp") || "null"); } catch (e) { S.emp = null; }
  S.pendingWo = ((model.query || {}).wo || "").trim();
  S.screen = S.ws || S.pendingWo ? "orders" : "station";
  if (S.pendingWo && !S.ws) S.ws = "_";
  appsmith.onModelChange((m) => {
    const w = (((m || {}).query || {}).wo || "").trim();
    if (w && w !== S.lastWo) { S.lastWo = w; S.pendingWo = w; S.screen = "orders"; loadJobs(); }
  });
  S.lastWo = S.pendingWo;
  loadJobs();
});
// ---- end Station page ----
