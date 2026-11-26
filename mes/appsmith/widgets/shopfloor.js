// ---- Shopfloor page ----
// Flow: open job -> identify product -> review materials -> scan -> confirm -> start -> report defects or machine
// issues -> update progress -> complete. Every rule is enforced by the mes_sf_* server scripts; this page only shows
// what the backend says and sends what the operator does.
const S = {
  me: null, stations: [], jobs: [], issues: [], ws: localStorage.getItem("mes.sf.ws") || "",
  jc: null, d: null, view: "home", scanItem: "", last: null, scanBusy: false,
  form: null, stream: null, detector: null, camTimer: null, lastCode: "", lastCodeAt: 0,
};
const DEFECT_CATS = ["Physical Damage", "Incorrect Component", "Missing Component", "Manufacturing Defect", "Surface Defect", "Electrical Issue", "Mechanical Issue", "Other"];
const ISSUE_TYPES = ["Machine Stalled", "Machine Breakdown", "Mechanical Failure", "Electrical Failure", "Abnormal Noise", "Overheating", "Safety Concern", "Maintenance Required", "Other"];
const MACHINE_STATES = [["Operating Normally", "go"], ["Experiencing Problems", "warn"], ["Stalled", "warn"], ["Completely Down", "stop"]];
const SEVERITIES = ["Low", "Medium", "High", "Critical"];
const TABS = [["job", "Job"], ["steps", "Assembly Steps"], ["materials", "Material Verification"], ["scan", "Barcode Scanner"], ["defect", "Report Defect"], ["issue", "Machine Issue"], ["progress", "Production Progress"]];
const SCAN_LABEL = { None: "No scan needed", Unit: "Scan every unit", Quantity: "Scan and enter quantity", Confirm: "Confirm quantity" };

function top() {
  const me = S.me || {};
  const wsOpts = ['<option value="">All workstations</option>'].concat(S.stations.map((s) =>
    '<option value="' + esc(s.name) + '"' + (s.name === S.ws ? " selected" : "") + ">" + esc(s.name) + (s.down ? "  (DOWN)" : "") + "</option>")).join("");
  return '<div class="sf-top"><span class="brand">MES SHOPFLOOR</span>' +
    '<div class="who"><b>' + esc(me.name || operator() || "-") + '</b><span class="muted">' + esc(me.role || "") + "</span></div>" +
    '<select id="ws" aria-label="Workstation">' + wsOpts + "</select>" +
    '<span class="spacer"></span>' +
    '<button class="sbtn small" data-act="home">&#8962; My Jobs</button>' +
    '<button class="sbtn small" data-act="mine">My Reports</button>' +
    '<button class="sbtn small warn" data-act="issue-home">&#9888; Report Machine Issue</button>' +
    (me.supervisor || me.maintenance ? '<a href="#" class="sbtn small ghost" data-nav="Shopfloor Admin">Supervisor / Maintenance</a>' : "") +
    "</div>";
}

function tabs() {
  return '<div class="tabs">' + TABS.map((t) => '<button class="sbtn' + (S.view === t[0] ? " on" : "") + '" data-view="' + t[0] + '">' + esc(t[1]) + "</button>").join("") + "</div>";
}

function render() {
  stopCamera();
  let body = "";
  if (S.view === "home") body = viewHome();
  else if (S.view === "mine") body = viewMine();
  else if (S.view === "issue" && !S.d) body = viewIssue();
  else if (!S.d) body = viewHome();
  else body = tabs() + '<div class="sf-body">' + jobHeader() + ({
    job: viewJob, steps: viewSteps, materials: viewMaterials, scan: viewScan, defect: viewDefect, issue: viewIssue, progress: viewProgress,
  }[S.view] || viewJob)() + "</div>";
  $("#app").innerHTML = top() + body;
  afterRender();
}

function viewHome() {
  const ws = S.stations.find((s) => s.name === S.ws);
  let h = '<div class="sf-body">';
  if (ws && ws.down) h += '<div class="banner bad"><span class="big">&#9940;</span><div>Machine ' + esc(ws.name) + " is COMPLETELY DOWN. Jobs on it cannot start until maintenance resolves the issue.</div></div>";
  const issues = S.issues.filter((i) => !S.ws || i.workstation === S.ws);
  if (issues.length) {
    h += '<div class="panel" style="margin-bottom:14px"><h3 style="margin-top:0">Open machine issues</h3>' + issues.map((i) =>
      '<div style="display:flex;gap:10px;align-items:center;margin:6px 0">' + chipFor(i.machine_status) + chipFor(i.severity) +
      "<b>" + esc(i.workstation) + "</b> " + esc(i.issue_type) + ' <span class="muted">' + esc(i.name) + " · " + esc(i.status) + "</span></div>").join("") + "</div>";
  }
  h += "<h2>My production jobs" + (S.ws ? " · " + esc(S.ws) : "") + "</h2>";
  if (!S.ws) h += '<p class="muted">Choose your workstation at the top to see only your jobs.</p>';
  if (!S.jobs.length) h += '<div class="panel muted">No open jobs' + (S.ws ? " on " + esc(S.ws) : "") + ".</div>";
  h += '<div class="grid g2">' + S.jobs.map((j) =>
    '<div class="panel jobcard" data-job="' + esc(j.job_card) + '">' + pic(j.image, j.item_name) +
    '<div class="meta"><div class="name">' + esc(j.item_name) + "</div>" +
    '<div><span class="code">' + esc(j.item_code) + "</span> · " + esc(j.work_order) + "</div>" +
    "<div>" + esc(j.operation) + ' <span class="muted">on</span> <b>' + esc(j.workstation) + "</b></div>" +
    '<div style="display:flex;gap:8px;flex-wrap:wrap">' + jobChip(j.status) +
    '<span class="chip">' + qtyFmt(j.completed_qty) + " / " + qtyFmt(j.qty) + " made</span>" +
    '<span class="chip ' + (j.materials_verified === j.materials_total ? "ok" : "warn") + '">Materials ' + j.materials_verified + "/" + j.materials_total + "</span>" +
    (j.defective_materials ? '<span class="chip bad">Defect</span>' : "") + (j.machine_down ? '<span class="chip bad">Machine down</span>' : "") + "</div>" +
    pbar(j.completed_qty, j.qty) + "</div></div>").join("") + "</div></div>";
  return h;
}

function jobHeader() {
  const d = S.d, j = d.job, w = d.work_order;
  let h = "";
  if (d.machine.down) h += '<div class="banner bad"><span class="big">&#9940; MACHINE DOWN</span><div>' + esc(j.workstation) + " is completely down (" + esc(d.machine.issue) + "). Production on this job is stopped until maintenance resolves it.</div></div>";
  h += '<div class="panel" style="display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin-bottom:14px">' + pic(w.image, w.item_name, "") +
    '<div style="flex:1;min-width:240px"><div class="muted">Making</div><div style="font-size:24px;font-weight:800">' + esc(w.item_name) + "</div>" +
    '<div><span class="code">' + esc(w.item_code) + "</span> · Work order <b>" + esc(w.name) + "</b></div>" +
    "<div>" + esc(j.operation) + " on <b>" + esc(j.workstation) + "</b> · job " + esc(j.job_card) + "</div></div>" +
    '<div class="grid g4" style="flex:2;min-width:320px">' +
    tile("Required", qtyFmt(j.qty)) + tile("Completed", qtyFmt(j.completed_qty), "ok") + tile("Remaining", qtyFmt(j.remaining_qty), j.remaining_qty ? "warn" : "ok") +
    '<div class="tile"><div class="l">Status</div><div style="margin-top:8px">' + jobChip(j.status) + "</div></div></div></div>";
  return h;
}

function jobChip(s) {
  return chipFor(s === "Open" ? "Not Started" : s);
}

function tile(l, v, cls) {
  return '<div class="tile ' + (cls || "") + '"><div class="l">' + esc(l) + '</div><div class="v">' + esc(v) + "</div></div>";
}

function blockingPanel(title) {
  const b = S.d.blocking || [];
  if (!b.length) return '<div class="banner ok"><span class="big">&#10003;</span><div>All checks passed: materials verified, no open defects, machine available.</div></div>';
  return '<div class="banner warn" style="align-items:flex-start"><span class="big">!</span><div><div>' + esc(title) + '</div><ul class="list-reasons" style="font-weight:500;font-size:16px">' +
    b.map((r) => "<li>" + esc(r) + "</li>").join("") + "</ul></div></div>";
}

function viewJob() {
  const d = S.d, s = d.summary, a = d.actions;
  let h = blockingPanel("Before production can start or complete:");
  h += '<div class="grid g3" style="margin-bottom:14px">' +
    actBtn("start", "&#9654;", "Start Production", "go", a.start) +
    actBtn("v-materials", "&#9776;", "Confirm Materials", "blue", true) +
    actBtn("v-scan", "&#9646;&#9646;&#9646;", "Scan Material", "blue", true) +
    actBtn("v-defect", "&#9888;", "Report Defect", "warn", true) +
    actBtn("v-issue", "&#128295;", "Report Machine Issue", "stop", true) +
    actBtn("v-progress", "&#128200;", "View Production Progress", "", true) +
    actBtn("v-complete", "&#10004;", "Complete Production", "go", a.complete) + "</div>";
  h += '<div class="grid g4">' + tile("Materials verified", s.materials_verified + " / " + s.materials_total, s.outstanding ? "warn" : "ok") +
    tile("Outstanding", s.outstanding, s.outstanding ? "warn" : "ok") + tile("Invalid scans", s.invalid_scans, s.invalid_scans ? "bad" : "") +
    tile("Defective", s.defective, s.defective ? "bad" : "") + tile("Machine", d.machine.down ? "DOWN" : "OK", d.machine.down ? "bad" : "ok") + "</div>";
  h += "<h3>Required materials</h3>" + materialRows(false);
  return h;
}

function actBtn(act, ico, label, cls, enabled) {
  return '<button class="sbtn ' + cls + '" style="min-height:84px;font-size:19px' + (enabled ? "" : ";opacity:.55") + '" data-act="' + act + '"' +
    (enabled ? "" : ' data-blocked="1" aria-disabled="true"') + '><span class="ico">' + ico + "</span>" + esc(label) + "</button>";
}

function materialRows(withActions) {
  return '<div class="grid" style="gap:10px">' + S.d.materials.map((m) => {
    let act = "";
    if (withActions && m.status !== "Verified") {
      if (m.mode === "confirm") {
        act = '<div style="display:flex;gap:8px;align-items:center"><input type="number" step="any" min="0" inputmode="decimal" data-cq="' + esc(m.item_code) + '" value="' + esc(m.remaining_qty) + '">' +
          '<span class="muted">' + esc(m.uom) + '</span><button class="sbtn go small" data-confirm="' + esc(m.item_code) + '">Confirm qty</button></div>';
      } else {
        act = '<button class="sbtn blue small" data-scanfor="' + esc(m.item_code) + '">&#9646;&#9646; Scan</button>';
      }
    }
    return '<div class="mat">' + pic(m.image, m.item_name, "sm") + '<div class="info"><div style="font-weight:800;font-size:17px">' + esc(m.item_name) + "</div>" +
      '<div><span class="code">' + esc(m.item_code) + '</span> · <span class="muted">' + esc(m.mode_label) + "</span></div>" +
      '<div class="nums"><span>Required <b>' + qtyFmt(m.required_qty) + "</b> " + esc(m.uom) + "</span><span>Confirmed <b>" + qtyFmt(m.verified_qty) + "</b></span>" +
      (m.mode === "unit" ? "<span>Units scanned <b>" + m.units_scanned + "</b></span>" : "") +
      "<span>Remaining <b>" + qtyFmt(m.remaining_qty) + "</b></span><span>In stock <b>" + qtyFmt(m.in_stock) + "</b></span>" +
      (m.invalid_scans ? '<span style="color:#ff8a8a">Invalid scans <b>' + m.invalid_scans + "</b></span>" : "") +
      (m.defective_units || m.held_qty ? '<span style="color:#ff8a8a">Defective <b>' + (m.defective_units || qtyFmt(m.held_qty)) + "</b></span>" : "") + "</div>" +
      '<div style="margin-top:6px">' + pbar(m.verified_qty, m.required_qty) + "</div></div>" +
      '<div style="display:flex;flex-direction:column;gap:8px;align-items:flex-end">' + chipFor(m.status) + act + "</div></div>";
  }).join("") + "</div>";
}

function viewSteps() {
  const w = S.d.workflow || { status: "none", steps: [] };
  if (w.status !== "approved" || !w.steps || !w.steps.length) {
    return '<div class="panel muted" style="padding:28px;text-align:center;font-size:18px">No approved assembly instructions for ' + esc(S.d.work_order.item_name) +
      ' yet. A supervisor has to approve them in Shopfloor Admin.</div>';
  }
  const done = w.steps.filter((x) => x.status === "Complete" || x.status === "Not Required").length;
  return '<div class="grid g4" style="margin-bottom:14px">' + tile("Instructions", "version " + w.version) +
    tile("Steps done", done + " / " + w.steps.length, done === w.steps.length ? "ok" : "") +
    tile("Current step", w.current_step ? "Step " + w.current_step : "All done", w.current_step ? "warn" : "ok") + "</div>" +
    '<div class="grid" style="gap:12px">' + w.steps.map((x) => stepCard(x)).join("") + "</div>";
}

function stepChip(st) {
  const cls = { Current: "info", Complete: "ok", "Awaiting sign-off": "warn" }[st] || "";
  return '<span class="chip ' + cls + '">' + esc(st) + "</span>";
}

function stepCard(x) {
  const cur = x.status === "Current" || x.status === "Awaiting sign-off";
  const finished = x.status === "Complete" || x.status === "Not Required";
  const m = x.item_code ? (S.d.materials || []).filter((mm) => mm.item_code === x.item_code)[0] : null;
  const reqs = [];
  if (x.serial_required) reqs.push("Serial number scan");
  if (x.batch_required) reqs.push("Batch scan");
  if (x.quality_inspection) reqs.push("Quality inspection");
  if (x.photo_required) reqs.push("Photo required");
  let act = "";
  if (x.item_code && !finished && m && m.status !== "Verified") {
    act = m.mode === "confirm" ? '<button class="sbtn blue small" data-view="materials">Confirm quantity</button>'
      : '<button class="sbtn blue small" data-scanfor="' + esc(x.item_code) + '">&#9646;&#9646; Scan material</button>';
  }
  const qty = x.item_code ? '<span>Required <b>' + qtyFmt(x.required_qty) + "</b> " + esc(x.uom || "") + "</span>" +
    '<span>Verified <b>' + qtyFmt(x.verified_qty) + "</b></span>" : "";
  return '<div class="stp' + (x.status === "Current" ? " cur" : "") + (finished ? " done" : "") + '">' + pic(x.image, x.item_name || x.step_name, "lg") +
    '<div class="stp-main"><div class="stp-head"><span class="stp-no">' + esc(x.step_no) + '</span><span class="stp-name">' + esc(x.step_name) + "</span>" + stepChip(x.status) + "</div>" +
    (x.description ? '<div class="muted">' + esc(x.description) + "</div>" : "") +
    (x.item_code ? '<div><span class="code">' + esc(x.item_code) + "</span> · " + esc(x.item_name || "") + "</div>" : "") +
    '<div class="stp-req">' + qty + "<span>" + esc(SCAN_LABEL[x.scan_mode] || x.scan_mode) + "</span>" + reqs.map((r) => "<span><b>" + esc(r) + "</b></span>").join("") + "</div>" +
    (x.instructions && x.instructions.length ? '<ol class="stp-ins">' + x.instructions.map((t) => "<li>" + esc(t) + "</li>").join("") + "</ol>" : "") +
    (x.checklist && x.checklist.length ? '<ul class="stp-chk">' + x.checklist.map((t) => "<li>&#9744; " + esc(t) + "</li>").join("") + "</ul>" : "") +
    (x.comments ? '<div class="muted">' + esc(x.comments) + "</div>" : "") +
    (act ? '<div class="stp-acts">' + act + "</div>" : "") + "</div></div>";
}

function viewMaterials() {
  const s = S.d.summary;
  return '<div class="banner ' + (s.outstanding ? "warn" : "ok") + '"><span class="big">' + s.materials_verified + "/" + s.materials_total + "</span><div>" +
    (s.outstanding ? "materials verified. Scan each item (every unit where marked) or confirm bulk quantities. Tapping cannot confirm scanned items." : "All materials verified.") + "</div></div>" +
    materialRows(true);
}

function expectedMaterial() {
  return S.d.materials.find((m) => m.item_code === S.scanItem) || null;
}

function viewScan() {
  const m = expectedMaterial();
  const open = S.d.materials.filter((x) => x.status !== "Verified" && x.mode !== "confirm");
  const r = S.last;
  let res = '<div class="result idle">Scan a barcode, unit label or serial number</div>';
  if (r) {
    res = '<div class="result ' + (r.ok ? "ok" : "bad") + '">' + pic(r.image, r.item_name) + '<div style="flex:1"><div class="head">' + (r.ok ? "&#10004; MATERIAL VERIFIED" : "&#10008; REJECTED") + "</div>" +
      (r.ok ? "" : '<div style="font-size:19px;font-weight:700;margin-top:6px">' + esc(r.reason) + "</div>") +
      "<dl>" + (r.item_code ? "<dt>Item</dt><dd>" + esc(r.item_name || "") + "</dd><dt>Item code</dt><dd class=\"code\">" + esc(r.item_code) + "</dd>" : "") +
      (r.unit_id ? "<dt>Unit / serial</dt><dd class=\"code\">" + esc(r.unit_id) + (r.serial_no && r.serial_no !== r.unit_id ? " (" + esc(r.serial_no) + ")" : "") + "</dd>" : "") +
      (r.ok ? "<dt>Quantity</dt><dd>" + qtyFmt(r.qty) + "</dd>" : "") + "<dt>Scanned</dt><dd class=\"code\">" + esc(r.value || "") + "</dd>" +
      "<dt>Status</dt><dd>" + (r.ok ? "Valid" : "Invalid · not counted") + "</dd></dl></div></div>";
  }
  const needQty = !m || m.mode !== "unit";
  return '<div class="grid g2"><div>' +
    '<div class="formrow"><label>Expected material</label><div class="choices">' +
    '<button class="sbtn' + (S.scanItem ? "" : " sel") + '" data-pick="">Any required material</button>' +
    open.map((x) => '<button class="sbtn' + (S.scanItem === x.item_code ? " sel" : "") + '" data-pick="' + esc(x.item_code) + '">' + esc(x.item_code) + "</button>").join("") + "</div></div>" +
    (m ? '<div class="mat" style="margin-bottom:14px">' + pic(m.image, m.item_name) + '<div class="info"><div style="font-weight:800;font-size:19px">' + esc(m.item_name) +
      '</div><div class="code">' + esc(m.item_code) + '</div><div class="nums"><span>Expected <b>' + qtyFmt(m.required_qty) + "</b></span><span>Scanned <b>" +
      qtyFmt(m.mode === "unit" ? m.units_scanned : m.verified_qty) + "</b></span><span>Remaining <b>" + qtyFmt(m.remaining_qty) + "</b></span></div>" +
      '<div class="muted" style="margin-top:4px">' + esc(m.mode_label) + "</div></div></div>" : "") +
    '<div class="formrow"><label for="scanin">Scan or type code (USB scanner works here)</label>' +
    '<input id="scanin" class="scanin" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="Waiting for scan…"></div>' +
    (needQty ? '<div class="formrow"><label for="scanqty">Quantity being used (not needed for unit labels)</label><input id="scanqty" type="number" min="0" step="any" inputmode="decimal" value="' +
      esc(m && m.mode === "batch" ? m.remaining_qty : m && m.mode !== "unit" ? Math.min(m.remaining_qty, 1) || "" : 1) + '"></div>' : "") +
    '<button class="sbtn go" style="width:100%" data-act="submit-scan"' + (S.scanBusy ? " disabled" : "") + ">Submit scan</button>" +
    '<h3>Camera</h3><div class="cam" id="cam"><span>Camera off</span></div>' +
    '<div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap"><button class="sbtn blue small" data-act="cam-on">&#128247; Start camera scan</button>' +
    '<button class="sbtn small" data-act="cam-off">Stop camera</button>' +
    '<label class="sbtn small" style="cursor:pointer">&#128444; Scan from photo<input type="file" accept="image/*" capture="environment" id="scanphoto" hidden></label></div>' +
    '<div id="camnote" class="muted" style="margin-top:8px"></div>' +
    "</div><div><h3 style=\"margin-top:0\">Latest scan</h3>" + res +
    "<h3>Recent scans on this work order</h3>" + scanHistory() + "</div></div>";
}

function scanHistory() {
  const rows = S.d.scans || [];
  if (!rows.length) return '<div class="muted">No scans yet.</div>';
  return '<table class="sf-t"><tr><th>When</th><th>Item</th><th>Unit / qty</th><th>Result</th></tr>' + rows.slice(0, 12).map((s) =>
    "<tr><td>" + esc(fmtWhen(s.creation)) + '</td><td class="code">' + esc(s.item_code || s.scanned_value) + "</td><td>" + esc(s.unit_id || qtyFmt(s.qty)) + "</td><td>" + chipFor(s.result) +
    (s.result === "Invalid" ? '<div class="muted" style="font-size:13px">' + esc(s.reason) + "</div>" : "") + "</td></tr>").join("") + "</table>";
}

function newForm(kind) {
  const d = S.d;
  S.form = {
    kind: kind, rid: reqId(), files: [], sending: false,
    item_code: kind === "defect" ? (S.scanItem || "") : "", unit_id: "", qty: 1, category: "", description: "",
    workstation: d ? d.job.workstation : (S.ws || ""), issue_type: "", machine_status: "", severity: "Medium",
  };
}

function viewDefect() {
  if (!S.form || S.form.kind !== "defect") newForm("defect");
  const f = S.form, d = S.d;
  const items = [{ item_code: d.work_order.item_code, item_name: d.work_order.item_name + " (finished product)", image: d.work_order.image }].concat(d.materials);
  let h = '<div class="grid g2"><div class="panel">' +
    '<div class="formrow"><label>Which item is defective?</label><div class="grid g2" style="gap:8px">' + items.map((m) =>
      '<button class="sbtn' + (f.item_code === m.item_code ? " sel" : "") + '" style="justify-content:flex-start" data-fitem="' + esc(m.item_code) + '">' + pic(m.image, m.item_name, "sm") +
      '<span style="text-align:left"><span class="code">' + esc(m.item_code) + '</span><br><span style="font-weight:500;font-size:15px">' + esc(m.item_name) + "</span></span></button>").join("") + "</div></div>" +
    '<div class="formrow"><label for="funit">Unit label / serial number (scan it, if the item has one)</label><input id="funit" class="scanin" value="' + esc(f.unit_id) + '" autocomplete="off"></div>' +
    '<div class="formrow"><label for="fqty">Quantity affected</label><input id="fqty" type="number" min="1" step="any" value="' + esc(f.qty) + '"></div>' +
    '<div class="formrow"><label>Defect category</label><div class="choices">' + DEFECT_CATS.map((c) =>
      '<button class="sbtn' + (f.category === c ? " sel" : "") + '" data-fcat="' + esc(c) + '">' + esc(c) + "</button>").join("") + "</div></div>" +
    '<div class="formrow"><label for="fdesc">What is wrong?</label><textarea id="fdesc" placeholder="Describe the defect">' + esc(f.description) + "</textarea></div>" +
    attachRow() +
    '<button class="sbtn warn" style="width:100%;min-height:72px;font-size:20px" data-act="send-defect"' + (f.sending ? " disabled" : "") + ">&#9888; Submit defect report</button></div>" +
    '<div><h3 style="margin-top:0">Defect reports on this work order</h3>' + defectList(d.defects) + "</div></div>";
  return h;
}

function attachRow() {
  const f = S.form;
  return '<div class="formrow"><label>Photos and files</label><div style="display:flex;gap:10px;flex-wrap:wrap">' +
    '<label class="sbtn blue small" style="cursor:pointer">&#128247; Take photo<input type="file" accept="image/*" capture="environment" data-attach="1" hidden></label>' +
    '<label class="sbtn small" style="cursor:pointer">&#128206; Upload photo or file<input type="file" multiple data-attach="1" hidden></label></div>' +
    '<div class="thumbs">' + f.files.map((x, i) => '<div class="thumb">' + (/^data:image\//.test(x.data) ? '<img src="' + x.data + '" alt="">' : esc(x.file_name)) +
      '<button data-unattach="' + i + '" aria-label="Remove">&#10005;</button></div>').join("") + "</div></div>";
}

function defectList(rows) {
  if (!rows || !rows.length) return '<div class="muted">None.</div>';
  return '<div class="grid" style="gap:8px">' + rows.map((x) => '<div class="tile"><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><b>' + esc(x.name) + "</b>" + chipFor(x.status) +
    (x.disposition ? '<span class="chip info">' + esc(x.disposition) + "</span>" : "") + '<span class="chip">' + esc(x.category) + "</span></div>" +
    '<div style="margin-top:6px"><span class="code">' + esc(x.item_code) + "</span>" + (x.unit_id ? " · unit " + esc(x.unit_id) : " · qty " + qtyFmt(x.qty_affected)) + "</div>" +
    '<div class="muted">' + esc(x.description) + "</div>" + (x.resolution_comments ? '<div style="margin-top:4px">' + esc(x.resolution_comments) + "</div>" : "") +
    '<div class="muted" style="font-size:13px">' + esc(x.reported_by_name || "") + " · " + esc(fmtWhen(x.creation)) + ((x.files || []).length ? " · " + x.files.length + " attachment(s)" : "") + "</div></div>").join("") + "</div>";
}

function viewIssue() {
  if (!S.form || S.form.kind !== "issue") newForm("issue");
  const f = S.form;
  const wsOpts = S.stations.map((s) => '<option value="' + esc(s.name) + '"' + (s.name === f.workstation ? " selected" : "") + ">" + esc(s.name) + " · " + esc(s.workstation_type) + "</option>").join("");
  const recent = S.d ? S.d.machine_issues : S.issues.filter((i) => !f.workstation || i.workstation === f.workstation);
  return (S.d ? "" : '<div class="sf-body">') + '<div class="grid g2"><div class="panel"><h2>Report machine issue</h2>' +
    '<div class="formrow"><label for="iws">Machine / workstation</label><select id="iws"><option value="">Choose…</option>' + wsOpts + "</select></div>" +
    (S.d ? '<div class="muted" style="margin:-6px 0 12px">Linked to job ' + esc(S.d.job.job_card) + " / " + esc(S.d.work_order.name) + "</div>" : "") +
    '<div class="formrow"><label>Machine status now</label><div class="choices">' + MACHINE_STATES.map((m) =>
      '<button class="sbtn ' + (f.machine_status === m[0] ? m[1] + " sel" : "") + '" data-ims="' + esc(m[0]) + '">' + esc(m[0]) + "</button>").join("") + "</div></div>" +
    '<div class="formrow"><label>Issue type</label><div class="choices">' + ISSUE_TYPES.map((t) =>
      '<button class="sbtn' + (f.issue_type === t ? " sel" : "") + '" data-ityp="' + esc(t) + '">' + esc(t) + "</button>").join("") + "</div></div>" +
    '<div class="formrow"><label>Severity</label><div class="choices">' + SEVERITIES.map((v) =>
      '<button class="sbtn' + (f.severity === v ? " sel" : "") + '" data-isev="' + esc(v) + '">' + esc(v) + "</button>").join("") + "</div>" +
    '<div class="muted" style="font-size:14px">Stalled raises priority to High; Completely Down or Safety Concern to Critical.</div></div>' +
    '<div class="formrow"><label for="idesc">What is happening?</label><textarea id="idesc" placeholder="Describe the problem">' + esc(f.description) + "</textarea></div>" +
    attachRow() +
    '<button class="sbtn stop" style="width:100%;min-height:72px;font-size:20px" data-act="send-issue"' + (f.sending ? " disabled" : "") + ">&#128295; REPORT MACHINE ISSUE</button></div>" +
    '<div><h3 style="margin-top:0">Recent issues on ' + esc(f.workstation || "all machines") + "</h3>" + issueList(recent) + "</div></div>" + (S.d ? "" : "</div>");
}

function issueList(rows) {
  if (!rows || !rows.length) return '<div class="muted">None.</div>';
  return '<div class="grid" style="gap:8px">' + rows.map((i) => '<div class="tile"><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><b>' + esc(i.name) + "</b>" +
    chipFor(i.status) + chipFor(i.machine_status) + chipFor(i.severity) + "</div><div>" + esc(i.workstation || "") + " · " + esc(i.issue_type) + "</div>" +
    (i.description ? '<div class="muted">' + esc(i.description) + "</div>" : "") + (i.resolution_notes ? "<div>" + esc(i.resolution_notes) + "</div>" : "") +
    '<div class="muted" style="font-size:13px">' + esc(i.reported_by_name || "") + " · " + esc(fmtWhen(i.creation)) + (i.assigned_to ? " · assigned " + esc(i.assigned_to) : "") + "</div></div>").join("") + "</div>";
}

function viewProgress() {
  const d = S.d, j = d.job, a = d.actions, w = d.work_order;
  let h = '<div class="grid g4" style="margin-bottom:14px">' + tile("Target", qtyFmt(j.qty)) + tile("Completed", qtyFmt(j.completed_qty), "ok") +
    tile("Remaining", qtyFmt(j.remaining_qty), j.remaining_qty ? "warn" : "ok") + tile("Materials", d.summary.materials_verified + "/" + d.summary.materials_total, d.summary.outstanding ? "warn" : "ok") +
    tile("Defects", d.defects.length, d.summary.open_defects ? "bad" : "") + tile("Machine", d.machine.down ? "DOWN" : "OK", d.machine.down ? "bad" : "ok") + "</div>";
  h += '<div class="panel" style="margin-bottom:14px">' + pbar(j.completed_qty, j.qty) + '<div style="margin-top:8px">Current operation: <b>' + esc(j.operation) + "</b> " + jobChip(j.status) +
    (j.running_since ? ' <span class="muted">running since ' + esc(fmtWhen(j.running_since)) + "</span>" : "") + "</div></div>";
  h += blockingPanel("Completion is blocked until:");
  h += '<div class="panel"><div class="formrow"><label for="pqty">Good units made since the last report</label><input id="pqty" type="number" min="0" step="1" inputmode="numeric" value="0"></div>' +
    '<div class="grid g4">' +
    '<button class="sbtn go" data-act="start"' + (a.start ? "" : ' data-blocked="1" style="opacity:.55"') + ">&#9654; Start</button>" +
    '<button class="sbtn blue" data-act="report"' + (a.report ? "" : " disabled") + ">Report quantity</button>" +
    '<button class="sbtn warn" data-act="pause"' + (a.pause ? "" : " disabled") + ">&#10074;&#10074; Pause</button>" +
    '<button class="sbtn go" data-act="complete"' + (a.complete ? "" : ' data-blocked="1" style="opacity:.55"') + ">&#10004; Complete Production</button></div></div>";
  h += "<h3>Operations on " + esc(w.name) + '</h3><table class="sf-t"><tr><th>Operation</th><th>Status</th><th>Completed</th></tr>' +
    w.operations.map((o) => "<tr><td>" + esc(o.operation) + "</td><td>" + chipFor(o.status) + "</td><td>" + qtyFmt(o.completed_qty) + "</td></tr>").join("") + "</table>";
  h += '<h3>Time logs</h3><table class="sf-t"><tr><th>From</th><th>To</th><th>Good qty</th></tr>' + (j.time_logs.length ? j.time_logs.map((l) =>
    "<tr><td>" + esc(fmtWhen(l.from_time)) + "</td><td>" + esc(l.to_time ? fmtWhen(l.to_time) : "running") + "</td><td>" + qtyFmt(l.completed_qty) + "</td></tr>").join("") : '<tr><td colspan="3" class="muted">None yet</td></tr>') + "</table>";
  return h;
}

function viewMine() {
  const m = S.mine || { defects: [], issues: [] };
  return '<div class="sf-body"><h2>My submitted reports</h2><div class="grid g2"><div><h3 style="margin-top:0">Defects</h3>' + defectList(m.defects) +
    '</div><div><h3 style="margin-top:0">Machine issues</h3>' + issueList(m.issues) + "</div></div></div>";
}

function afterRender() {
  const ws = $("#ws");
  if (ws) ws.onchange = () => { S.ws = ws.value; localStorage.setItem("mes.sf.ws", S.ws); S.view = "home"; S.d = null; loadJobs(); };
  const si = $("#scanin");
  if (si) {
    si.focus();
    si.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submitScan(si.value); } });
  }
  const sp = $("#scanphoto");
  if (sp) sp.onchange = () => scanPhoto(sp.files[0]);
  $$("input[data-attach]").forEach((inp) => {
    inp.onchange = async () => {
      try {
        keepForm();
        const got = await readFiles(inp.files, 10);
        S.form.files = S.form.files.concat(got).slice(0, 6);
        render();
      } catch (e) { toast(e.message, "err"); }
    };
  });
  const iws = $("#iws");
  if (iws) iws.onchange = () => { keepForm(); S.form.workstation = iws.value; render(); };
}

function keepForm() {
  const f = S.form;
  if (!f) return;
  const v = (id) => { const el = $(id); return el ? el.value : null; };
  if (v("#funit") !== null) f.unit_id = v("#funit");
  if (v("#fqty") !== null) f.qty = v("#fqty");
  if (v("#fdesc") !== null) f.description = v("#fdesc");
  if (v("#idesc") !== null) f.description = v("#idesc");
  if (v("#iws") !== null) f.workstation = v("#iws");
}

async function loadJobs() {
  setBusy(true);
  try {
    const r = await api("mes_sf_jobs", { workstation: S.ws });
    S.me = r.operator; S.stations = r.workstations; S.jobs = r.jobs; S.issues = r.issues;
  } catch (e) {
    toast(e.message, "err");
  } finally { setBusy(false); render(); }
}

async function loadJob(jc, view) {
  setBusy(true);
  try {
    const r = await api("mes_sf_job", { job_card: jc });
    S.jc = jc; S.d = r; S.me = r.operator;
    if (view) S.view = view;
  } catch (e) {
    toast(e.message, "err");
  } finally { setBusy(false); render(); }
}

async function submitScan(value) {
  value = String(value || "").trim();
  if (!value || S.scanBusy || !S.d) return;
  const qEl = $("#scanqty");
  S.scanBusy = true;
  try {
    const r = await api("mes_sf_scan", { job_card: S.jc, value: value, qty: qEl ? qEl.value : "", request_id: reqId() });
    S.last = r;
    beep(r.ok);
    const fresh = await api("mes_sf_job", { job_card: S.jc });
    S.d = fresh;
    const m = expectedMaterial();
    if (m && m.status === "Verified") S.scanItem = "";
  } catch (e) {
    S.last = { ok: false, reason: e.message, value: value };
    beep(false);
  } finally {
    S.scanBusy = false;
    render();
  }
}

async function scanPhoto(file) {
  if (!file) return;
  const note = $("#camnote");
  if (!("BarcodeDetector" in window)) { if (note) note.textContent = "This browser cannot read barcodes from photos. Use the USB scanner or type the code."; return; }
  try {
    const det = new BarcodeDetector();
    const bmp = await createImageBitmap(file);
    const codes = await det.detect(bmp);
    if (!codes.length) { toast("No barcode found in the photo", "err"); beep(false); return; }
    submitScan(codes[0].rawValue);
  } catch (e) { toast("Could not read the photo: " + e.message, "err"); }
}

async function startCamera() {
  const note = $("#camnote"), box = $("#cam");
  const say = (t) => { if (note) note.textContent = t; };
  if (!("BarcodeDetector" in window)) { say("Live camera scanning needs a browser with barcode detection (Chrome on Android, ChromeOS or macOS). Use the USB scanner, type the code, or try Scan from photo."); return; }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { say("The camera is not available in this frame. Use the USB scanner or type the code."); return; }
  try {
    S.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    const formats = await BarcodeDetector.getSupportedFormats();
    S.detector = new BarcodeDetector({ formats: formats });
    box.innerHTML = '<video autoplay playsinline muted></video><div class="aim"></div>';
    const video = $("video", box);
    video.srcObject = S.stream;
    say("Point the camera at the barcode. Formats: " + formats.join(", "));
    S.camTimer = setInterval(async () => {
      if (!S.detector || video.readyState < 2 || S.scanBusy) return;
      try {
        const codes = await S.detector.detect(video);
        if (!codes.length) return;
        const raw = codes[0].rawValue;
        const now = Date.now();
        if (raw === S.lastCode && now - S.lastCodeAt < 2500) return;
        S.lastCode = raw; S.lastCodeAt = now;
        submitScan(raw);
      } catch (e) { /* keep scanning */ }
    }, 350);
  } catch (e) {
    say("Camera blocked or unavailable (" + e.message + "). Use the USB scanner or type the code.");
  }
}

function stopCamera() {
  if (S.camTimer) clearInterval(S.camTimer);
  S.camTimer = null;
  if (S.stream) S.stream.getTracks().forEach((t) => t.stop());
  S.stream = null; S.detector = null;
}

async function progress(action) {
  const q = $("#pqty");
  let qty = q ? q.value : 0;
  if (action === "complete") {
    const left = S.d.job.remaining_qty;
    const running = S.d.job.status === "Running";
    const v = await dialog("Complete production", (running ? '<p>Good units made since the last report:</p><input name="qty" type="number" min="0" step="1" value="' + esc(qty || 0) + '" style="width:100%">' : "") +
      "<p>Completing submits job " + esc(S.jc) + " in ERPNext with " + qtyFmt(S.d.job.completed_qty) + (running ? " + the quantity above" : "") + " of " + qtyFmt(S.d.job.qty) +
      " good units. This cannot be undone from the shopfloor." + (left ? "" : "") + "</p>", "Complete", { withValues: true });
    if (!v) return;
    qty = v.qty || 0;
  }
  setBusy(true);
  try {
    const r = await api("mes_sf_progress", { job_card: S.jc, action: action, qty: qty });
    if (r.ok) {
      toast({ start: "Production started", report: "Quantity reported", pause: "Paused", complete: "Job completed in ERPNext" }[action] + (r.blocking && r.blocking.length ? "\n" + r.blocking[0] : ""), r.blocking && r.blocking.length ? "err" : "ok");
      beep(true);
    } else {
      toast("Not allowed:\n" + (r.blocking || []).slice(0, 4).join("\n"), "err");
      beep(false);
    }
  } catch (e) { toast(e.message, "err"); beep(false); }
  setBusy(false);
  await loadJob(S.jc);
}

async function sendDefect() {
  keepForm();
  const f = S.form;
  if (!f.item_code) return toast("Choose the defective item", "err");
  if (!f.category) return toast("Choose a defect category", "err");
  if ((f.description || "").trim().length < 3) return toast("Describe the defect", "err");
  f.sending = true; render();
  try {
    const r = await api("mes_sf_defect", { job_card: S.jc, item_code: f.item_code, unit_id: f.unit_id, qty_affected: f.qty, category: f.category,
      description: f.description, files: f.files.map((x) => ({ file_name: x.file_name, data: x.data })), request_id: f.rid });
    toast("Defect " + r.defect + " reported" + (r.flagged_scans && r.flagged_scans.length ? "; that unit no longer counts as verified" : ""), "ok");
    beep(true);
    S.form = null;
    await loadJob(S.jc, "defect");
  } catch (e) { f.sending = false; toast(e.message, "err"); beep(false); render(); }
}

async function sendIssue() {
  keepForm();
  const f = S.form;
  if (!f.workstation) return toast("Choose the machine", "err");
  if (!f.machine_status) return toast("Choose the machine status", "err");
  if (!f.issue_type) return toast("Choose the issue type", "err");
  if ((f.description || "").trim().length < 3) return toast("Describe the problem", "err");
  f.sending = true; render();
  try {
    const r = await api("mes_sf_machine_issue", { workstation: f.workstation, job_card: S.d && S.d.job.workstation === f.workstation ? S.jc : "", issue_type: f.issue_type,
      severity: f.severity, machine_status: f.machine_status, description: f.description, files: f.files.map((x) => ({ file_name: x.file_name, data: x.data })), request_id: f.rid });
    toast("Issue " + r.issue + " sent (" + r.severity + "). Maintenance has been notified.", "ok");
    beep(true);
    S.form = null;
    if (S.d) await loadJob(S.jc, "issue"); else { await loadJobs(); S.view = "home"; render(); }
  } catch (e) { f.sending = false; toast(e.message, "err"); beep(false); render(); }
}

async function confirmQty(code) {
  const el = $('input[data-cq="' + code + '"]');
  if (!el) return;
  S.scanBusy = true;
  try {
    const r = await api("mes_sf_scan", { job_card: S.jc, value: code, qty: el.value, request_id: reqId() });
    beep(r.ok);
    toast(r.ok ? code + ": " + qtyFmt(r.qty) + " confirmed" : r.reason, r.ok ? "ok" : "err");
  } catch (e) { toast(e.message, "err"); beep(false); }
  S.scanBusy = false;
  await loadJob(S.jc);
}

document.addEventListener("click", async (e) => {
  const t = e.target.closest && e.target.closest("[data-act],[data-view],[data-job],[data-pick],[data-scanfor],[data-confirm],[data-fitem],[data-fcat],[data-ims],[data-ityp],[data-isev],[data-unattach]");
  if (!t) return;
  e.preventDefault();
  const ds = t.dataset;
  if (ds.job) return loadJob(ds.job, "job");
  if (ds.view) { keepForm(); S.view = ds.view; return render(); }
  if (ds.pick !== undefined) { S.scanItem = ds.pick; return render(); }
  if (ds.scanfor) { S.scanItem = ds.scanfor; S.view = "scan"; return render(); }
  if (ds.confirm) return confirmQty(ds.confirm);
  if (ds.fitem) { keepForm(); S.form.item_code = ds.fitem; return render(); }
  if (ds.fcat) { keepForm(); S.form.category = ds.fcat; return render(); }
  if (ds.ims) { keepForm(); S.form.machine_status = ds.ims; return render(); }
  if (ds.ityp) { keepForm(); S.form.issue_type = ds.ityp; return render(); }
  if (ds.isev) { keepForm(); S.form.severity = ds.isev; return render(); }
  if (ds.unattach !== undefined) { keepForm(); S.form.files.splice(+ds.unattach, 1); return render(); }
  const act = ds.act;
  if (ds.blocked && (act === "start" || act === "complete" || act === "v-complete")) {
    return toast("Not yet:\n" + (S.d.blocking.length ? S.d.blocking.slice(0, 4).join("\n") : "start production and report good units first"), "err");
  }
  if (act === "home") { S.view = "home"; S.d = null; S.form = null; return loadJobs(); }
  if (act === "mine") {
    setBusy(true);
    try { S.mine = await api("mes_sf_admin", { action: "my_reports" }); } catch (err) { toast(err.message, "err"); }
    setBusy(false); S.view = "mine"; S.d = null; return render();
  }
  if (act === "issue-home") { S.form = null; S.d = null; S.view = "issue"; return render(); }
  if (act && act.indexOf("v-") === 0) {
    S.view = act === "v-complete" ? "progress" : act.slice(2);
    return render();
  }
  if (act === "submit-scan") return submitScan(($("#scanin") || {}).value);
  if (act === "cam-on") return startCamera();
  if (act === "cam-off") { stopCamera(); const c = $("#cam"); if (c) c.innerHTML = "<span>Camera off</span>"; return; }
  if (act === "start" || act === "report" || act === "pause" || act === "complete") return progress(act);
  if (act === "send-defect") return sendDefect();
  if (act === "send-issue") return sendIssue();
});

startPage(() => {
  if (!operator() || operator() === "harness") {
    $("#app").innerHTML = '<div class="sf-body"><div class="banner bad">No signed-in operator. Open this page while logged in to Appsmith (or add ?as=&lt;erpnext user&gt; in the dev harness).</div></div>';
    return;
  }
  loadJobs();
});
// ---- end Shopfloor page ----
