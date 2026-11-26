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
      esc(noPrefix(g.workstation_type)) + (g.capacity > 1 ? " · cap " + g.capacity : "") + '</span></div><div class="g-lane" style="width:' + totalW + 'px">' + bars + "</div></div>";
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
  if (go) MES.navigate("Shopfloor", { wo: f.work_order });
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
