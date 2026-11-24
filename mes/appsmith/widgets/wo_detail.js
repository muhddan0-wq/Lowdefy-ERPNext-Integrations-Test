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
