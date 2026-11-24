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
