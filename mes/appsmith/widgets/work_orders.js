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
  const items = Array.from(new Set((d.rows || []).map((r) => r.production_item))).sort();
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
