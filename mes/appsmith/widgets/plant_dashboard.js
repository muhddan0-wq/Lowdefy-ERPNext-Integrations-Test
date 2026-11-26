// ---- Plant dashboard page (Tulip-style) ----
// Complete / plan / defects, performance, availability, quality, station status and the event feed, from
// mes_sf_dashboard. Read-only; refreshes every 30 seconds.
document.body.classList.remove("sf");
document.body.classList.add("pd");

const D = { data: null, days: 1, timer: null };
const GREEN = "#6abf3b", RED = "#e74c3c", ORANGE = "#f39a33", BLUE = "#2678c2", LINE = "#2b7bd6";

function pctClass(v) { return v === null || v === undefined ? "" : v >= 95 ? "good" : v >= 80 ? "mid" : "bad"; }
function pctTxt(v) { return v === null || v === undefined ? "–" : num(v, 1) + "%"; }
function shortWs(s) { return String(s).replace(/^P1-/, "").replace(/-0?/, ""); }

function lineChart(rows) {
  if (!rows.length) return '<div class="pd-empty">No units reported yet in this window</div>';
  const W = 700, H = 150, pad = 30, max = Math.max.apply(null, rows.map((r) => r.value)) || 1;
  const x = (i) => pad + (rows.length === 1 ? (W - pad * 2) / 2 : i * (W - pad * 2) / (rows.length - 1));
  const y = (v) => H - 20 - (v / max) * (H - 40);
  const pts = rows.map((r, i) => x(i).toFixed(1) + "," + y(r.value).toFixed(1)).join(" ");
  return '<svg viewBox="0 0 ' + W + " " + H + '"><line x1="' + pad + '" x2="' + (W - pad) + '" y1="' + (H - 20) + '" y2="' + (H - 20) + '" stroke="#c7ccd2"/>' +
    '<text x="0" y="' + (y(max) + 4) + '">' + num(max, 0) + "</text>" +
    '<polyline fill="none" stroke="' + LINE + '" stroke-width="2" points="' + pts + '"/>' +
    rows.map((r, i) => '<circle cx="' + x(i) + '" cy="' + y(r.value) + '" r="4" fill="' + LINE + '"><title>' + esc(r.label) + ": " + num(r.value, 0) + "</title></circle>" +
      '<text x="' + x(i) + '" y="' + (H - 4) + '" text-anchor="middle">' + esc(r.label.slice(-5)) + "</text>").join("") + "</svg>";
}

function stackBars(rows) {
  if (!rows.length) return '<div class="pd-empty">No stations</div>';
  const W = 320, H = 170, base = H - 28, top = 10, bw = Math.min(60, (W - 20) / rows.length - 8);
  const max = Math.max.apply(null, rows.map((r) => r.up_min + r.down_min)) || 1;
  return '<svg viewBox="0 0 ' + W + " " + H + '">' + rows.map((r, i) => {
    const x = 10 + i * ((W - 20) / rows.length) + 4;
    const hu = (r.up_min / max) * (base - top), hd = (r.down_min / max) * (base - top);
    return '<rect x="' + x + '" y="' + (base - hu - hd) + '" width="' + bw + '" height="' + hd + '" fill="' + RED + '"><title>' + esc(r.workstation) + " down " + r.down_min + " min</title></rect>" +
      '<rect x="' + x + '" y="' + (base - hu) + '" width="' + bw + '" height="' + hu + '" fill="' + (r.down_min ? ORANGE : GREEN) + '"><title>' + esc(r.workstation) + " up " + r.up_min + " min</title></rect>" +
      '<text x="' + (x + bw / 2) + '" y="' + (H - 12) + '" text-anchor="middle" style="font-size:8px">' + esc(shortWs(r.workstation)) + "</text>";
  }).join("") + "</svg>";
}

function bars(rows, color, unit) {
  if (!rows.length) return '<div class="pd-empty">Nothing recorded in this window</div>';
  const W = 320, H = 170, base = H - 22, top = 14, n = rows.length, bw = Math.min(70, (W - 20) / n - 10);
  const max = Math.max.apply(null, rows.map((r) => r.value)) || 1;
  return '<svg viewBox="0 0 ' + W + " " + H + '">' + rows.map((r, i) => {
    const x = 10 + i * ((W - 20) / n) + 5, h = (r.value / max) * (base - top);
    return '<rect x="' + x + '" y="' + (base - h) + '" width="' + bw + '" height="' + h + '" fill="' + color + '"><title>' + esc(r.label) + ": " + num(r.value, 1) + (unit || "") + "</title></rect>" +
      '<text x="' + (x + bw / 2) + '" y="' + (base - h - 3) + '" text-anchor="middle">' + num(r.value, r.value < 10 ? 1 : 0) + "</text>" +
      '<text x="' + (x + bw / 2) + '" y="' + (H - 6) + '" text-anchor="middle">' + esc(shortWs(r.label).slice(0, 14)) + "</text>";
  }).join("") + "</svg>";
}

function pareto(rows, unit) {
  if (!rows.length) return '<div class="pd-empty">Nothing recorded in this window</div>';
  const W = 320, H = 170, base = H - 22, top = 14, n = rows.length, slot = (W - 40) / n, bw = Math.min(70, slot - 10);
  const max = Math.max.apply(null, rows.map((r) => r.value)) || 1;
  const cx = (i) => 10 + i * slot + 5 + bw / 2;
  const cy = (p) => base - (p / 100) * (base - top);
  return '<svg viewBox="0 0 ' + W + " " + H + '">' + rows.map((r, i) => {
    const h = (r.value / max) * (base - top);
    return '<rect x="' + (cx(i) - bw / 2) + '" y="' + (base - h) + '" width="' + bw + '" height="' + h + '" fill="' + BLUE + '"><title>' + esc(r.label) + ": " + num(r.value, 1) + (unit || "") + "</title></rect>" +
      '<text x="' + cx(i) + '" y="' + (H - 6) + '" text-anchor="middle">' + esc(r.label.length > 12 ? r.label.slice(0, 11) + "…" : r.label) + "</text>";
  }).join("") +
    '<polyline fill="none" stroke="' + ORANGE + '" stroke-width="2" points="' + rows.map((r, i) => cx(i) + "," + cy(r.cum_pct)).join(" ") + '"/>' +
    rows.map((r, i) => '<circle cx="' + cx(i) + '" cy="' + cy(r.cum_pct) + '" r="4" fill="' + ORANGE + '"/>').join("") +
    '<text x="' + (W - 30) + '" y="' + (cy(100) + 4) + '">100%</text><text x="' + (W - 30) + '" y="' + (cy(50) + 4) + '">50%</text></svg>';
}

function render() {
  const d = D.data;
  if (!d) { $("#app").innerHTML = '<div class="pd-head"><div class="logo"><i>&#9670;</i>VOLTRA</div><div class="t">Plant dashboard</div></div><div style="color:#fff;padding:20px">Loading&hellip;</div>'; return; }
  const t = d.totals;
  const plantState = t.machines_down ? "bad" : d.stations.some((s) => s.state === "warn") ? "warn" : "ok";
  const winTxt = D.days === 1 ? "today" : "last " + D.days + " days";
  const h = '<div class="pd-head"><div class="logo"><i>&#9670;</i>__BRAND__</div><div class="t">__PLANT_NAME__</div>' +
    '<button data-days="1" class="' + (D.days === 1 ? "on" : "") + '">Today</button><button data-days="7" class="' + (D.days === 7 ? "on" : "") + '">7 days</button>' +
    '<a href="#" data-nav="Shopfloor">&larr; Station screen</a><span class="clock">' + esc(fmtDT(d.now)) + "</span></div>" +
    '<div class="pd-grid"><div class="pd-col">' +
    '<div class="pd-card pd-top"><div class="plant ' + plantState + '"><div>Plant<small>' + (t.machines_down ? t.machines_down + " machine" + (t.machines_down > 1 ? "s" : "") + " down" : plantState === "warn" ? "Machine problem reported" : "All machines running") + "</small></div></div>" +
    '<div class="k"><div class="l">Complete <span>' + winTxt + '</span></div><div class="v">' + num(t.complete, 0) + "</div></div>" +
    '<div class="k"><div class="l">Plan <span>' + winTxt + '</span></div><div class="v">' + num(t.plan, 0) + "</div></div>" +
    '<div class="k"><div class="l">Defects <span>' + winTxt + '</span></div><div class="v" style="color:' + (t.defects ? "#c0392b" : "inherit") + '">' + num(t.defects, 0) + "</div></div></div>" +
    '<div class="pd-card"><h3>Performance</h3><div class="pd-row two"><div><div class="pd-big ' + pctClass(t.performance) + '">' + pctTxt(t.performance) + '</div><div class="pd-sub">' +
    num(t.complete, 0) + " done vs " + num(t.target_now, 0) + " expected by now</div></div><div class=\"pd-chart\">" + lineChart(d.hourly) + "</div></div></div>" +
    '<div class="pd-card"><h3>Availability</h3><div class="pd-row"><div><div class="pd-big ' + pctClass(t.availability) + '">' + pctTxt(t.availability) + '</div><div class="pd-sub">Shift time machines were not stalled or down</div>' +
    '<div class="pd-legend"><span><i style="background:' + GREEN + '"></i>Up</span><span><i style="background:' + RED + '"></i>Down</span></div></div>' +
    '<div class="pd-chart">' + stackBars(d.availability_by_station) + '</div><div class="pd-chart">' + pareto(d.downtime_pareto, " min") + '<div class="pd-sub" style="text-align:center">Downtime reasons (minutes)</div></div></div></div>' +
    '<div class="pd-card"><h3>Quality</h3><div class="pd-row"><div><div class="pd-big ' + pctClass(t.quality) + '">' + pctTxt(t.quality) + '</div><div class="pd-sub">Good units vs good + defective</div></div>' +
    '<div class="pd-chart">' + bars(d.defects_by_station, RED) + '<div class="pd-sub" style="text-align:center">Defects by station</div></div><div class="pd-chart">' + pareto(d.defect_pareto) +
    '<div class="pd-sub" style="text-align:center">Defect reasons</div></div></div></div>' +
    '</div><div class="pd-col"><div class="pd-card"><h3>Stations</h3><div class="pd-stations">' + d.stations.map((s) =>
      '<div class="pd-st ' + s.state + '"><b>' + esc(s.workstation) + '</b><span class="r">' + num(s.done, 0) + " / " + num(s.plan, 0) + "</span><span>" + esc(noPrefix(s.type)) + '</span><span class="r">' +
      esc(s.state === "run" ? "Running " + s.running.job_card : s.state === "idle" ? "Idle" : s.machine_status) + "</span></div>").join("") + "</div></div>" +
    '<div class="pd-card"><h3>Events</h3><div class="pd-events">' + (d.events.length ? d.events.map((e) =>
      '<div class="pd-ev"><div class="tm">' + esc(D.days === 1 ? fmtDT(e.at).slice(-5) : fmtDT(e.at, false)) + '</div><div class="ic ' + e.kind + '">' +
      ({ done: "&#10003;", start: "&#9654;", defect: "!", issue: "!", resolved: "&#10003;" }[e.kind] || "•") + "</div><div><b>" + esc(e.title) + "</b><span>" + esc(e.text) + "</span></div></div>").join("")
      : '<div class="pd-sub">No events in this window.</div>') + "</div></div></div></div>";
  $("#app").innerHTML = h;
}

async function load() {
  try {
    D.data = await api("mes_sf_dashboard", { days: D.days });
  } catch (e) {
    toast(e.message, "err");
    if (!D.data) { $("#app").innerHTML = '<div class="pd-head"><div class="logo"><i>&#9670;</i>VOLTRA</div><div class="t">Plant dashboard</div></div><div style="color:#fff;padding:20px;font-size:18px">' + esc(e.message) + "</div>"; return; }
  }
  render();
}

document.addEventListener("click", (e) => {
  const b = e.target.closest && e.target.closest("[data-days]");
  if (!b) return;
  D.days = +b.dataset.days;
  load();
});

startPage(() => {
  if (!operator() || operator() === "harness") {
    $("#app").innerHTML = '<div style="color:#fff;padding:20px">No signed-in user. Open this page while logged in to Appsmith.</div>';
    return;
  }
  render();
  load();
  D.timer = setInterval(load, 30000);
});
// ---- end Plant dashboard ----
