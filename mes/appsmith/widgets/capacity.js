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
