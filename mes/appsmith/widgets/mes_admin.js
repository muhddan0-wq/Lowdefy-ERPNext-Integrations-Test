// ---- Shopfloor Admin page: supervisors review defects and invalid scans, maintenance runs machine issues ----
// Rights come from the operator's ERPNext roles and are checked again by mes_sf_admin on every call.
const A = { me: null, data: null, tab: "", timer: null, edits: {} };
const DEF_STATUS = ["Reported", "Under Review", "Accepted", "Rejected", "Rework Required", "Resolved"];
const DISPOSITIONS = ["", "Use As Is", "Replace", "Rework", "Scrap", "Return to Supplier"];
const ISS_FLOW = ["Open", "Acknowledged", "In Progress", "Resolved", "Closed"];
const ERP_DESK_FILE = ERP_PUBLIC;
const WF_SCAN = ["None", "Unit", "Quantity", "Confirm"];
const WF_FLAGS = ["None", "Missing Information", "Expert Review", "Missing Image", "Component Removed", "Component Added", "Quantity Changed", "Not In BOM"];
const WF_CONF = ["High", "Medium", "Low"];
const WF_TOGGLES = [["serial_required", "Serial scan"], ["batch_required", "Batch scan"], ["quality_inspection", "Quality inspection"], ["photo_required", "Photo required"], ["mandatory", "Mandatory"]];
const WF_KEYS = ["step_name", "item_code", "item_name", "qty", "uom", "description", "instructions", "checklist", "comments", "scan_mode", "serial_required", "batch_required", "quality_inspection", "photo_required", "mandatory", "image_override", "operation", "workstation", "source", "confidence", "review_flag", "review_notes"];
const WF = { list: null, sel: "", d: null, steps: [], bom: [], dirty: false, drag: -1 };
const DISC = { rows: null, connection: "", subs: 0 };

function adminTop() {
  const me = A.me || {};
  const tabs = [];
  if (me.maintenance || me.supervisor) tabs.push(["issues", "Machine Issues"]);
  if (me.supervisor) tabs.push(["defects", "Defect Reports"], ["scans", "Invalid Scans"], ["workflows", "Assembly Instructions"], ["discovery", "Product Discovery"]);
  return '<div class="sf-top"><span class="brand">MES · SUPERVISOR / MAINTENANCE</span><div class="who"><b>' + esc(me.name || operator()) + '</b><span class="muted">' + esc(me.role || "") + "</span></div>" +
    '<span class="spacer"></span><button class="sbtn small" data-a="refresh">&#8635; Refresh</button><a href="#" class="sbtn small ghost" data-nav="Shopfloor">Shopfloor</a></div>' +
    '<div class="tabs">' + tabs.map((t) => '<button class="sbtn' + (A.tab === t[0] ? " on" : "") + '" data-tab="' + t[0] + '">' + esc(t[1]) + countFor(t[0]) + "</button>").join("") + "</div>";
}

function countFor(tab) {
  const d = A.data || {};
  let n = 0;
  if (tab === "issues") n = (d.issues || []).filter((i) => ["Open", "Acknowledged", "In Progress"].indexOf(i.status) >= 0).length;
  if (tab === "defects") n = (d.defects || []).filter((x) => ["Reported", "Under Review", "Rework Required"].indexOf(x.status) >= 0 || (x.status === "Accepted" && !x.disposition)).length;
  if (tab === "scans") n = (d.invalid_scans || []).length;
  return n ? ' <span class="chip ' + (tab === "scans" ? "" : "bad") + '">' + n + "</span>" : "";
}

function files(list) {
  if (!list || !list.length) return "";
  return '<div class="thumbs">' + list.map((f) => '<a class="thumb" href="' + esc(ERP_DESK_FILE + encodeURI(f.file_url)) + '" title="Opens in ERPNext (sign-in needed for private files)">&#128206; ' + esc(f.file_name) + "</a>").join("") + "</div>";
}

function viewIssues() {
  const d = A.data, me = A.me;
  const rows = d.issues || [];
  const users = d.maintenance_users || [];
  if (!rows.length) return '<div class="panel muted">No machine issues reported.</div>';
  return '<div class="grid g2">' + rows.map((i) => {
    const done = i.status === "Closed";
    const next = ISS_FLOW.slice(ISS_FLOW.indexOf(i.status) + 1);
    const canMove = me.maintenance || (me.supervisor && i.status === "Open");
    return '<div class="panel" style="border-left:6px solid ' + ({ Critical: "#ef4444", High: "#f59e0b", Medium: "#3b82f6", Low: "#64748b" }[i.severity] || "#64748b") + '">' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><b style="font-size:19px">' + esc(i.workstation) + "</b>" + chipFor(i.severity) + chipFor(i.machine_status) + chipFor(i.status) +
      '<span class="muted">' + esc(i.name) + "</span></div>" +
      '<div style="font-size:18px;font-weight:700;margin-top:6px">' + esc(i.issue_type) + "</div><div>" + esc(i.description) + "</div>" +
      '<div class="muted" style="font-size:14px;margin-top:4px">Reported by ' + esc(i.reported_by_name || "") + " · " + esc(fmtWhen(i.creation)) +
      (i.work_order ? " · " + esc(i.work_order) + (i.job_card ? " / " + esc(i.job_card) : "") : "") +
      (i.acknowledged_by ? " · acknowledged by " + esc(i.acknowledged_by) : "") + (i.resolved_by ? " · resolved by " + esc(i.resolved_by) + " " + esc(fmtWhen(i.resolved_on)) : "") + "</div>" +
      (i.resolution_notes ? '<div class="tile" style="margin-top:8px;white-space:pre-line">' + esc(i.resolution_notes) + "</div>" : "") + files(i.files) +
      (done || !canMove ? "" :
        '<div style="margin-top:12px;display:flex;flex-direction:column;gap:8px">' +
        (me.maintenance ? '<select data-assign="' + esc(i.name) + '"><option value="">Assigned to: ' + esc(i.assigned_to || "nobody") + "</option>" + users.map((u) => '<option value="' + esc(u) + '">' + esc(u) + "</option>").join("") + "</select>" : "") +
        (me.maintenance ? '<textarea data-notes="' + esc(i.name) + '" placeholder="Work done / resolution notes" style="min-height:70px">' + esc(A.edits[i.name] || "") + "</textarea>" : "") +
        '<div class="choices">' + next.filter((s) => me.maintenance || s === "Acknowledged").map((s) =>
          '<button class="sbtn small ' + (s === "Resolved" || s === "Closed" ? "go" : "blue") + '" data-istatus="' + esc(s) + '" data-iname="' + esc(i.name) + '">' + esc(s === "Acknowledged" ? "Acknowledge" : s === "In Progress" ? "Start work" : s) + "</button>").join("") +
        (me.maintenance ? '<button class="sbtn small" data-istatus="" data-iname="' + esc(i.name) + '">Save notes / assignee</button>' : "") + "</div></div>") +
      "</div>";
  }).join("") + "</div>";
}

function viewDefects() {
  const rows = A.data.defects || [];
  if (!rows.length) return '<div class="panel muted">No defect reports.</div>';
  return '<div class="grid g2">' + rows.map((x) => '<div class="panel"><div style="display:flex;gap:14px">' + pic(x.image, x.item_name, "sm") + '<div style="flex:1">' +
    '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><b>' + esc(x.name) + "</b>" + chipFor(x.status) + (x.disposition ? '<span class="chip info">' + esc(x.disposition) + "</span>" : "") +
    '<span class="chip">' + esc(x.category) + "</span></div>" +
    '<div style="font-weight:700;margin-top:4px">' + esc(x.item_name) + ' <span class="code">' + esc(x.item_code) + "</span></div>" +
    "<div>" + (x.unit_id ? "Unit " + esc(x.unit_id) : "Qty " + qtyFmt(x.qty_affected)) + (x.work_order ? " · " + esc(x.work_order) : "") + "</div>" +
    '<div class="muted">' + esc(x.description) + "</div>" +
    '<div class="muted" style="font-size:14px">' + esc(x.reported_by_name || "") + " · " + esc(fmtWhen(x.creation)) + (x.reviewed_by ? " · reviewed by " + esc(x.reviewed_by) : "") + "</div>" +
    (x.resolution_comments ? '<div class="tile" style="margin-top:6px;white-space:pre-line">' + esc(x.resolution_comments) + "</div>" : "") + files(x.files) + "</div></div>" +
    '<div class="grid g3" style="margin-top:12px;gap:8px">' +
    '<select data-dstatus="' + esc(x.name) + '">' + DEF_STATUS.map((s) => '<option' + (s === x.status ? " selected" : "") + ">" + esc(s) + "</option>").join("") + "</select>" +
    '<select data-ddisp="' + esc(x.name) + '">' + DISPOSITIONS.map((s) => '<option value="' + esc(s) + '"' + (s === (x.disposition || "") ? " selected" : "") + ">" + esc(s || "No disposition") + "</option>").join("") + "</select>" +
    '<button class="sbtn small go" data-dsave="' + esc(x.name) + '">Save decision</button></div>' +
    '<textarea data-dcom="' + esc(x.name) + '" placeholder="Decision comments" style="min-height:60px;margin-top:8px"></textarea></div>').join("") + "</div>";
}

function viewScans() {
  const rows = A.data.invalid_scans || [];
  if (!rows.length) return '<div class="panel muted">No invalid scans.</div>';
  return '<div class="panel"><table class="sf-t"><tr><th>When</th><th>Work order</th><th>Scanned</th><th>Item</th><th>Reason</th><th>By</th></tr>' + rows.map((s) =>
    "<tr><td>" + esc(fmtWhen(s.creation)) + "</td><td>" + esc(s.work_order) + '</td><td class="code">' + esc(s.scanned_value) + '</td><td class="code">' + esc(s.item_code || "") +
    "</td><td>" + esc(s.reason) + "</td><td>" + esc(s.operator_name || "") + "</td></tr>").join("") + "</table></div>";
}

function renderAdmin() {
  let body = "";
  if (A.tab === "workflows") body = viewWorkflows();
  else if (A.tab === "discovery") body = viewDiscovery();
  else if (!A.data) body = '<div class="panel muted">Loading…</div>';
  else if (A.tab === "defects") body = viewDefects();
  else if (A.tab === "scans") body = viewScans();
  else body = viewIssues();
  $("#app").innerHTML = adminTop() + '<div class="sf-body">' + body + "</div>";
}

function wfBlank() {
  return { step_name: "", item_code: "", item_name: "", qty: null, uom: "", description: "", instructions: "", checklist: "", comments: "",
    scan_mode: "None", serial_required: 0, batch_required: 0, quality_inspection: 0, photo_required: 0, mandatory: 1,
    image_override: "", operation: "", workstation: "", source: "Admin", confidence: "High", review_flag: "None", review_notes: "" };
}

function wfFromRow(row) {
  const o = wfBlank();
  WF_KEYS.forEach((k) => { if (row[k] !== undefined && row[k] !== null) o[k] = row[k]; });
  return o;
}

function wfPayload() {
  return WF.steps.map((s) => {
    const o = {};
    WF_KEYS.forEach((k) => { o[k] = s[k]; });
    o.item_code = s.item_code || null;
    o.image_override = s.image_override || null;
    o.qty = s.qty === "" || s.qty === null || s.qty === undefined ? null : Number(s.qty);
    WF_TOGGLES.forEach((t) => { o[t[0]] = s[t[0]] ? 1 : 0; });
    return o;
  });
}

function bomItems(root) {
  const seen = {};
  const walk = (n) => {
    if (n.item_code && !seen[n.item_code]) seen[n.item_code] = { item_code: n.item_code, item_name: n.item_name, image: n.image };
    (n.children || []).forEach(walk);
  };
  if (root) walk(root);
  return Object.keys(seen).map((k) => seen[k]);
}

function wfBomOf(code) {
  return WF.bom.filter((b) => b.item_code === code)[0] || null;
}

function wfItemLabel(s) {
  const b = wfBomOf(s.item_code);
  if (b) return b.item_name;
  return s.item_code ? "Not in this product's BOM" : "No item: a non-material step";
}

function wfImage(s) {
  const b = wfBomOf(s.item_code);
  const url = s.image_override || (b ? b.image : null);
  return pic(url, s.item_name || s.item_code || "", "sm") + '<div class="muted small">' + (s.image_override ? "Reference override" : url ? "Item image" : "No image") + "</div>";
}

function wfStatus(w) {
  if (w.status === "Archived") return '<span class="chip">Archived</span>';
  if (!w.approved_version) return '<span class="chip info">Draft v' + w.current_version + "</span>";
  return '<span class="chip ok">Approved v' + w.approved_version + "</span>" +
    (w.current_version > w.approved_version ? ' <span class="chip warn">Newer draft v' + w.current_version + "</span>" : "");
}

function wfOptions(list, cur) {
  return list.map((o) => '<option' + (o === cur ? " selected" : "") + ">" + esc(o) + "</option>").join("");
}

function viewWorkflows() {
  if (!WF.list) return '<div class="panel muted">Loading…</div>';
  const rows = WF.list.length ? WF.list.map((w) => '<button class="wf-row' + (w.finished_item === WF.sel ? " on" : "") + '" data-wfopen="' + esc(w.finished_item) + '">' +
    "<b>" + esc(w.finished_item) + '</b><span class="muted">' + esc(w.item_name || "") + '</span><div class="wf-chips">' + wfStatus(w) +
    (w.sync_status === "Review Needed" ? ' <span class="chip bad">BOM changed</span>' : "") + "</div></button>").join("")
    : '<div class="panel muted">No assembly instructions yet. Generate a draft from Product Discovery.</div>';
  return '<div class="wf-layout"><div class="wf-list"><h3 style="margin-top:0">Products</h3>' + rows + "</div><div>" +
    (WF.d ? wfEditor() : '<div class="panel muted">Choose a product to review and edit its assembly instructions.</div>') + "</div></div>";
}

function wfEditor() {
  const d = WF.d, w = d.workflow;
  const approved = !!w.approved_version;
  const archived = w.status === "Archived";
  const synced = w.sync_status !== "Review Needed" && !(d.sync_diff || []).length;
  return '<h2 style="margin-top:0">' + esc(w.finished_item) + " · " + esc(w.item_name || "") + "</h2>" +
    '<div class="muted small">BOM ' + esc(w.bom || "-") + " · " + esc(w.status) + "</div>" +
    '<div class="wf-tiles" style="margin-top:10px">' +
    '<div class="tile ' + (approved ? "ok" : "warn") + '"><div class="l">Approved (shopfloor uses this)</div><div class="v">' + (approved ? "v" + w.approved_version : "Not approved") + "</div>" +
    (approved ? '<div class="muted small">by ' + esc(w.approved_by || "") + " · " + esc(fmtWhen(w.approved_on)) + "</div>" : "") + "</div>" +
    '<div class="tile info"><div class="l">Working (latest saved)</div><div class="v">v' + w.current_version + "</div>" +
    '<div class="muted small">' + w.step_count + " step(s) · " + (w.flagged_steps || 0) + " flagged</div></div>" +
    '<div class="tile ' + (synced ? "ok" : "bad") + '"><div class="l">ERPNext BOM</div><div class="v">' + (synced ? "In sync" : "Changed") + "</div>" +
    '<div class="muted small">' + (approved ? "Compared with the approved BOM" : "Nothing approved yet") + "</div></div></div>" +
    (synced ? "" : wfSyncPanel(d)) +
    '<div class="wf-toolbar"><button class="sbtn small" data-wfa="add"' + (archived ? " disabled" : "") + ">+ Add step</button>" +
    (d.approved_steps ? '<button class="sbtn small" data-wfa="revert">Load approved version</button>' : "") +
    '<input id="wfnote" class="wf-note" placeholder="Change note for this version">' +
    '<button class="sbtn small go" data-wfa="save"' + (archived ? " disabled" : "") + ">Save as new version</button>" +
    '<button class="sbtn small blue" id="wfapprove" data-wfa="approve"' + (archived || WF.dirty ? " disabled" : "") + ">Approve v" + w.current_version + "</button></div>" +
    '<div id="wfdirty" class="banner warn"' + (WF.dirty ? "" : ' style="display:none"') + ">Unsaved changes: save a new version before approving.</div>" +
    '<datalist id="wfItems">' + WF.bom.map((b) => '<option value="' + esc(b.item_code) + '">' + esc(b.item_name) + "</option>").join("") + "</datalist>" +
    '<h3>Steps</h3>' + (WF.steps.length ? WF.steps.map((s, i) => wfStepCard(s, i)).join("") : '<div class="panel muted">No steps yet.</div>') +
    '<h3>Version history</h3><table class="sf-t"><tr><th>Version</th><th>Status</th><th>Steps</th><th>Change note</th><th>Saved</th><th>Approved</th></tr>' +
    (d.versions || []).map((v) => "<tr><td><b>v" + v.version + '</b></td><td><span class="chip' + (v.status === "Approved" ? " ok" : "") + '">' + esc(v.status) + "</span></td><td>" + v.step_count + "</td><td>" + esc(v.change_note || "") +
      "</td><td>" + esc(v.saved_by || "") + " · " + esc(fmtWhen(v.saved_on)) + "</td><td>" + (v.approved_by ? esc(v.approved_by) + " · " + esc(fmtWhen(v.approved_on)) : "") + "</td></tr>").join("") + "</table>" +
    (d.generation_notes ? '<details style="margin-top:14px"><summary class="muted">Generation notes</summary><div class="tile" style="white-space:pre-line;margin-top:8px">' + esc(d.generation_notes) + "</div></details>" : "");
}

function wfSyncPanel(d) {
  const rows = d.sync_diff || [];
  return '<div class="panel wf-sync"><h3 style="margin-top:0">ERPNext BOM changed since approval</h3>' +
    (rows.length ? '<table class="sf-t"><tr><th>Change</th><th>Item</th><th>Under</th><th>Was</th><th>Now</th></tr>' + rows.map((r) =>
      "<tr><td>" + esc(r.kind) + '</td><td class="code">' + esc(r.item_code) + "</td><td>" + esc(r.parent) + "</td><td>" + esc(r.was == null ? "-" : r.was) + "</td><td>" + esc(r.now == null ? "-" : r.now) + "</td></tr>").join("") + "</table>"
      : '<div class="muted">No differences are visible now.</div>') +
    '<div class="muted small" style="margin:8px 0">The approved instructions are unchanged. Review the flagged steps and save a new version if needed. Then acknowledge the change.</div>' +
    (d.workflow.approved_version ? '<button class="sbtn small warn" data-wfa="ack">Acknowledge BOM change</button>' : "") + "</div>";
}

function wfStepCard(s, i) {
  const n = WF.steps.length;
  const flagged = s.review_flag && s.review_flag !== "None";
  const note = (v) => esc(v == null ? "" : v);
  return '<div class="wf-step' + (flagged ? " flagged" : "") + '" data-i="' + i + '">' +
    '<div class="wf-head"><span class="wf-handle" title="Drag to reorder">&#8942;&#8942;</span><span class="wf-no">' + (i + 1) + "</span>" +
    '<input class="wf-name" data-wf="step_name" data-i="' + i + '" value="' + note(s.step_name) + '" placeholder="Step name">' +
    (flagged ? '<span class="chip warn">' + esc(s.review_flag) + "</span>" : "") + '<span class="muted small">' + esc(s.source || "") + "</span>" +
    '<div class="wf-acts">' +
    '<button class="sbtn small" data-wfa="up" data-i="' + i + '"' + (i === 0 ? " disabled" : "") + ">&#8593;</button>" +
    '<button class="sbtn small" data-wfa="down" data-i="' + i + '"' + (i === n - 1 ? " disabled" : "") + ">&#8595;</button>" +
    '<button class="sbtn small" data-wfa="dup" data-i="' + i + '">Duplicate</button>' +
    '<button class="sbtn small stop" data-wfa="del" data-i="' + i + '">Delete</button></div></div>' +
    '<div class="wf-grid">' +
    '<label class="wf-lbl">Associated item<input list="wfItems" data-wf="item_code" data-i="' + i + '" value="' + note(s.item_code) + '" placeholder="None (no material)">' +
    '<span class="muted small" id="wfiname' + i + '">' + esc(wfItemLabel(s)) + "</span></label>" +
    '<label class="wf-lbl">Quantity per finished unit<input type="number" step="any" min="0" data-wf="qty" data-i="' + i + '" value="' + note(s.qty) + '"></label>' +
    '<label class="wf-lbl">UOM<input data-wf="uom" data-i="' + i + '" value="' + note(s.uom) + '"></label>' +
    '<label class="wf-lbl">Scan mode<select data-wf="scan_mode" data-i="' + i + '">' + wfOptions(WF_SCAN, s.scan_mode) + "</select></label>" +
    '<label class="wf-lbl">Review flag<select data-wf="review_flag" data-i="' + i + '">' + wfOptions(WF_FLAGS, s.review_flag || "None") + "</select></label>" +
    '<label class="wf-lbl">Confidence<select data-wf="confidence" data-i="' + i + '">' + wfOptions(WF_CONF, s.confidence) + "</select></label>" +
    '<label class="wf-lbl">Operation<input data-wf="operation" data-i="' + i + '" value="' + note(s.operation) + '"></label>' +
    '<label class="wf-lbl">Workstation<input data-wf="workstation" data-i="' + i + '" value="' + note(s.workstation) + '"></label>' +
    '<div class="wf-lbl"><span>Reference image</span><div class="wf-img" id="wfimg' + i + '">' + wfImage(s) + "</div>" +
    '<input data-wf="image_override" data-i="' + i + '" value="' + note(s.image_override) + '" placeholder="ERPNext file path (blank = item image)">' +
    '<button class="sbtn small" data-wfa="clearimg" data-i="' + i + '">Use item image</button></div>' +
    '<div class="wf-chks wf-wide">' + WF_TOGGLES.map((t) => '<label><input type="checkbox" data-wf="' + t[0] + '" data-i="' + i + '"' + (s[t[0]] ? " checked" : "") + "> " + esc(t[1]) + "</label>").join("") + "</div>" +
    '<label class="wf-lbl wf-wide">Description<textarea rows="2" data-wf="description" data-i="' + i + '">' + note(s.description) + "</textarea></label>" +
    '<label class="wf-lbl wf-wide">Instructions (one line per instruction)<textarea rows="4" data-wf="instructions" data-i="' + i + '">' + note(s.instructions) + "</textarea></label>" +
    '<label class="wf-lbl">Checklist (one item per line)<textarea rows="3" data-wf="checklist" data-i="' + i + '">' + note(s.checklist) + "</textarea></label>" +
    '<label class="wf-lbl">Comments<textarea rows="3" data-wf="comments" data-i="' + i + '">' + note(s.comments) + "</textarea></label>" +
    '<label class="wf-lbl wf-wide">Review notes<textarea rows="2" data-wf="review_notes" data-i="' + i + '">' + note(s.review_notes) + "</textarea></label>" +
    "</div></div>";
}

function viewDiscovery() {
  if (!DISC.rows) return '<div class="panel muted">Loading products from ERPNext…</div>';
  const head = '<div class="wf-toolbar"><span class="muted">' + DISC.rows.length + " finished product(s) in " + esc(DISC.connection || "ERPNext") + " · " + DISC.subs +
    ' sub-assembly item(s) are not listed</span><span style="flex:1"></span><button class="sbtn small blue" data-wfa="syncall">Check ERPNext BOM changes</button>' +
    '<button class="sbtn small" data-wfa="discrefresh">Refresh</button></div>';
  if (!DISC.rows.length) return head + '<div class="panel muted">No finished products: no active, submitted BOM is left unused by other BOMs.</div>';
  return head + '<div class="grid g2">' + DISC.rows.map((p) => discCard(p)).join("") + "</div>";
}

function discCard(p) {
  const w = p.workflow, s = p.summary;
  const approved = w && w.approved_version;
  let btns = "";
  if (approved) btns = '<button class="sbtn small" disabled title="Approved instructions are never regenerated">Approved: edit a new version</button>';
  else if (w) btns = '<button class="sbtn small warn" data-gen="' + esc(p.item_code) + '" data-force="1">Regenerate draft</button>';
  else btns = '<button class="sbtn small go" data-gen="' + esc(p.item_code) + '" data-force="0">Generate Draft</button>';
  if (w) btns += '<button class="sbtn small blue" data-wfopen="' + esc(p.item_code) + '">Open editor</button>';
  return '<div class="panel wf-disc">' + pic(p.image, p.item_name, "") + '<div class="wf-disc-body">' +
    '<div style="font-size:20px;font-weight:800">' + esc(p.item_name) + "</div>" +
    '<div><span class="code">' + esc(p.item_code) + '</span> · BOM <span class="code">' + esc(p.bom) + "</span>" + (p.bom_candidates > 1 ? ' <span class="chip warn">' + p.bom_candidates + " active BOMs</span>" : "") + "</div>" +
    '<div class="muted">' + s.components + " components · " + s.sub_assemblies + " sub-assemblies · " + s.raw_materials + " raw materials · depth " + s.max_depth + " · " + s.missing_images + " without image</div>" +
    '<div class="wf-chips">' + (w ? wfStatus(w) : '<span class="chip">No workflow</span>') + (p.flag_count ? ' <span class="chip warn">' + p.flag_count + " flag(s) in BOM</span>" : "") +
    (w && w.sync_status === "Review Needed" ? ' <span class="chip bad">BOM changed</span>' : "") + "</div>" +
    '<div class="wf-toolbar" style="margin:6px 0 0">' + btns + "</div></div></div>";
}

async function wfRun(fn, label) {
  setBusy(true);
  let out = null;
  try {
    out = await fn();
    if (label) toast(label(out), "ok");
  } catch (e) {
    toast(e.message, "err");
  }
  setBusy(false);
  renderAdmin();
  return out;
}

async function wfListFetch() {
  WF.list = ((await api("mes_wf_workflow", { action: "list" })) || {}).workflows || [];
}

async function wfFetch(item) {
  const got = await api("mes_wf_workflow", { action: "get", finished_item: item });
  const tree = await api("mes_wf_discover", { action: "tree", item_code: item });
  await wfListFetch();
  WF.sel = item;
  WF.d = got;
  WF.steps = (got.steps || []).map(wfFromRow);
  WF.bom = bomItems(tree.tree);
  WF.dirty = false;
  WF.drag = -1;
}

async function wfBoot() {
  return wfRun(() => wfListFetch());
}

async function wfLeave() {
  if (!WF.dirty) return true;
  return dialog("Discard unsaved changes?", "<p>The working copy of " + esc(WF.sel) + " has changes that were not saved as a version. They will be lost.</p>", "Discard", { danger: true });
}

async function wfOpen(item) {
  if (!(await wfLeave())) return;
  return wfRun(() => wfFetch(item));
}

function wfMarkDirty() {
  WF.dirty = true;
  const b = $("#wfdirty");
  if (b) b.style.display = "";
  const ap = $("#wfapprove");
  if (ap) ap.disabled = true;
}

function wfSet(i, f, el) {
  const s = WF.steps[i];
  if (!s) return;
  if (f === "qty") s.qty = el.value === "" ? null : Number(el.value);
  else if (el.type === "checkbox") s[f] = el.checked ? 1 : 0;
  else s[f] = el.value;
  if (f === "item_code") {
    s.item_code = String(s.item_code || "").trim();
    const b = wfBomOf(s.item_code);
    s.item_name = b ? b.item_name : "";
  }
  if (f === "item_code" || f === "image_override") {
    const img = $("#wfimg" + i);
    if (img) img.innerHTML = wfImage(s);
    const nm = $("#wfiname" + i);
    if (nm) nm.textContent = wfItemLabel(s);
  }
  wfMarkDirty();
}

function wfMove(from, to) {
  if (from === to || to < 0 || to >= WF.steps.length) return;
  const x = WF.steps.splice(from, 1)[0];
  WF.steps.splice(to, 0, x);
  wfMarkDirty();
  renderAdmin();
}

async function wfSave() {
  if (WF.steps.some((s) => !String(s.step_name || "").trim())) return toast("Every step needs a name", "err");
  const note = ($("#wfnote") || {}).value || "";
  const sel = WF.sel;
  return wfRun(async () => {
    const r = await api("mes_wf_workflow", { action: "save", finished_item: sel, steps: JSON.stringify(wfPayload()), change_note: note });
    await wfFetch(sel);
    return r;
  }, (r) => "Saved as version " + r.version);
}

async function wfApprove() {
  if (WF.dirty) return toast("Save a new version before approving", "err");
  const sel = WF.sel, ver = WF.d.workflow.current_version;
  const flagged = WF.steps.filter((s) => s.review_flag && s.review_flag !== "None").length;
  const ok = await dialog("Approve version " + ver + "?", "<p>Shopfloor employees will see version " + ver + " of " + esc(sel) +
    " from now on. Work orders already opened on the shopfloor keep the version they were bound to.</p>" +
    (flagged ? "<p><b>" + flagged + " step(s) are still flagged for review.</b> Approval is still allowed.</p>" : ""), "Approve");
  if (!ok) return;
  return wfRun(async () => {
    const r = await api("mes_wf_workflow", { action: "approve", finished_item: sel, version: ver });
    await wfFetch(sel);
    return r;
  }, (r) => "Version " + r.workflow.approved_version + " approved" + (r.warnings.length ? "; " + r.warnings.length + " step(s) flagged" : ""));
}

async function wfAck() {
  const sel = WF.sel;
  const ok = await dialog("Acknowledge the BOM change?", "<p>The current ERPNext BOM of " + esc(sel) +
    " becomes the new baseline. The approved instructions do not change. Flagged steps stay flagged until you review them.</p>", "Acknowledge");
  if (!ok) return;
  return wfRun(async () => {
    const r = await api("mes_wf_workflow", { action: "ack_sync", finished_item: sel });
    await wfFetch(sel);
    return r;
  }, () => "BOM change acknowledged; instructions unchanged");
}

async function wfRevert() {
  const ok = await dialog("Load the approved version?", "<p>Replaces the working copy with approved version " + WF.d.workflow.approved_version +
    ". Unsaved changes are lost.</p>", "Load", { danger: true });
  if (!ok) return;
  WF.steps = (WF.d.approved_steps || []).map(wfFromRow);
  wfMarkDirty();
  renderAdmin();
}

async function discLoad() {
  const r = await api("mes_wf_discover", { action: "products" });
  DISC.rows = r.products || [];
  DISC.connection = r.connection || "";
  DISC.subs = r.sub_assembly_items || 0;
}

function discBoot() {
  return wfRun(() => discLoad());
}

async function discGenerate(item, force) {
  if (force) {
    const ok = await dialog("Regenerate the draft for " + item + "?", "<p>The unapproved draft is replaced by a new draft built from the current ERPNext BOM. The old draft stays in version history. Approved instructions are never touched.</p>", "Regenerate", { danger: true });
    if (!ok) return;
  }
  return wfRun(async () => {
    const r = await api("mes_wf_workflow", { action: "generate", item_code: item, force: force ? 1 : 0 });
    await discLoad();
    await wfListFetch();
    return r;
  }, (r) => "Draft v" + r.workflow.current_version + " generated for " + item + " (" + r.workflow.step_count + " steps)");
}

async function wfSyncAll() {
  return wfRun(async () => {
    const r = await api("mes_wf_workflow", { action: "sync_check" });
    await discLoad();
    if (WF.sel) await wfFetch(WF.sel); else await wfListFetch();
    return r;
  }, (r) => {
    const n = Object.keys(r.changed || {}).length;
    return n ? n + " workflow(s) now show ERPNext BOM changes for review" : "No BOM changes since approval";
  });
}

async function loadAdmin() {
  setBusy(true);
  try {
    const r = await api("mes_sf_admin", { action: "overview" });
    A.me = r.operator; A.data = r;
    if (!A.tab) A.tab = A.me.maintenance && !A.me.supervisor ? "issues" : (r.defects ? "defects" : "issues");
  } catch (e) {
    $("#app").innerHTML = '<div class="sf-body"><div class="banner bad">' + esc(e.message) + "</div></div>";
    setBusy(false);
    return;
  }
  setBusy(false);
  renderAdmin();
}

async function adminCall(args, okMsg) {
  setBusy(true);
  try {
    await api("mes_sf_admin", args);
    toast(okMsg, "ok");
    return true;
  } catch (e) {
    toast(e.message, "err");
    return false;
  } finally { setBusy(false); }
}

document.addEventListener("input", (e) => {
  const n = e.target.dataset && e.target.dataset.notes;
  if (n) A.edits[n] = e.target.value;
  const d = e.target.dataset || {};
  if (d.wf && d.i !== undefined && e.target.tagName !== "SELECT" && e.target.type !== "checkbox") wfSet(+d.i, d.wf, e.target);
});

document.addEventListener("change", (e) => {
  const d = e.target.dataset || {};
  if (d.wf && d.i !== undefined && (e.target.tagName === "SELECT" || e.target.type === "checkbox")) {
    wfSet(+d.i, d.wf, e.target);
    renderAdmin();
  }
});

document.addEventListener("mousedown", (e) => {
  const card = e.target.closest && e.target.closest(".wf-handle") && e.target.closest(".wf-step");
  if (card) card.draggable = true;
});

document.addEventListener("mouseup", () => {
  $$(".wf-step").forEach((c) => { c.draggable = false; });
});

document.addEventListener("dragstart", (e) => {
  const card = e.target.closest && e.target.closest(".wf-step");
  if (!card || !card.draggable) return;
  WF.drag = +card.dataset.i;
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", "step " + WF.drag);
});

document.addEventListener("dragover", (e) => {
  if (WF.drag < 0 || !(e.target.closest && e.target.closest(".wf-step"))) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = "move";
});

document.addEventListener("drop", (e) => {
  const card = e.target.closest && e.target.closest(".wf-step");
  if (WF.drag < 0 || !card) return;
  e.preventDefault();
  const from = WF.drag;
  WF.drag = -1;
  wfMove(from, +card.dataset.i);
});

document.addEventListener("dragend", () => {
  WF.drag = -1;
  $$(".wf-step").forEach((c) => { c.draggable = false; });
});

document.addEventListener("click", async (e) => {
  const t = e.target.closest && e.target.closest("[data-wfa],[data-wfopen],[data-gen]");
  if (!t) return;
  e.preventDefault();
  const ds = t.dataset;
  if (ds.wfopen !== undefined) { A.tab = "workflows"; return wfOpen(ds.wfopen); }
  if (ds.gen !== undefined) return discGenerate(ds.gen, ds.force === "1");
  const i = +ds.i;
  const a = ds.wfa;
  if (a === "add") { WF.steps.push(wfBlank()); wfMarkDirty(); return renderAdmin(); }
  if (a === "up") return wfMove(i, i - 1);
  if (a === "down") return wfMove(i, i + 1);
  if (a === "dup") {
    const c = Object.assign({}, WF.steps[i]);
    c.step_name = (c.step_name || "Step") + " (copy)";
    WF.steps.splice(i + 1, 0, c);
    wfMarkDirty();
    return renderAdmin();
  }
  if (a === "del") {
    const ok = await dialog("Delete step " + (i + 1) + "?", "<p>" + esc(WF.steps[i].step_name || "(unnamed)") + " is removed from the working copy. Earlier saved versions keep it.</p>", "Delete", { danger: true });
    if (!ok) return;
    WF.steps.splice(i, 1);
    wfMarkDirty();
    return renderAdmin();
  }
  if (a === "clearimg") { WF.steps[i].image_override = ""; wfMarkDirty(); return renderAdmin(); }
  if (a === "save") return wfSave();
  if (a === "approve") return wfApprove();
  if (a === "ack") return wfAck();
  if (a === "revert") return wfRevert();
  if (a === "syncall") return wfSyncAll();
  if (a === "discrefresh") return discBoot();
});

document.addEventListener("click", async (e) => {
  const t = e.target.closest && e.target.closest("[data-a],[data-tab],[data-istatus],[data-dsave]");
  if (!t) return;
  e.preventDefault();
  const ds = t.dataset;
  if (ds.tab) {
    A.tab = ds.tab;
    if (ds.tab === "workflows" && !WF.list) return wfBoot();
    if (ds.tab === "discovery" && !DISC.rows) return discBoot();
    return renderAdmin();
  }
  if (ds.a === "refresh") {
    if (A.tab === "workflows") {
      if (!(await wfLeave())) return;
      WF.dirty = false;
      return WF.sel ? wfRun(() => wfFetch(WF.sel)) : wfBoot();
    }
    if (A.tab === "discovery") return discBoot();
    return loadAdmin();
  }
  if (ds.iname !== undefined) {
    const name = ds.iname;
    const notesEl = $('textarea[data-notes="' + name + '"]');
    const asg = $('select[data-assign="' + name + '"]');
    const ok = await adminCall({ action: "issue_update", name: name, status: ds.istatus || "", notes: notesEl ? notesEl.value : "", assigned_to: asg ? asg.value : "" },
      name + (ds.istatus ? " → " + ds.istatus : " saved"));
    if (ok) delete A.edits[name];
    return loadAdmin();
  }
  if (ds.dsave) {
    const name = ds.dsave;
    await adminCall({ action: "defect_update", name: name, status: $('select[data-dstatus="' + name + '"]').value,
      disposition: $('select[data-ddisp="' + name + '"]').value, comments: $('textarea[data-dcom="' + name + '"]').value }, name + " updated");
    return loadAdmin();
  }
});

startPage(() => {
  if (!operator() || operator() === "harness") {
    $("#app").innerHTML = '<div class="sf-body"><div class="banner bad">No signed-in user. Open this page while logged in to Appsmith (or add ?as=&lt;erpnext user&gt; in the dev harness).</div></div>';
    return;
  }
  loadAdmin();
  A.timer = setInterval(() => {
    if (["issues", "defects", "scans"].indexOf(A.tab) < 0) return;
    if (!document.querySelector("textarea:focus,select:focus")) loadAdmin();
  }, 30000);
});
// ---- end Shopfloor Admin page ----
