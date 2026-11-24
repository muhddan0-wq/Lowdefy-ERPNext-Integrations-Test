// Page: Workstation Queue (M6, operators / tablet). Data: mes_workstation_queue.
// Actions use ERPNext's own whitelisted Job Card methods via /api/v2/document/Job Card/{name}/method/...
const S = { ws: "", date: isoDate(new Date()), stations: [], d: null };
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
  if (j.state === "Not started") btns.push('<button class="btn big primary" data-do="start">▶ Start</button>');
  if (j.state === "Running") btns.push('<button class="btn big" data-do="pause">❚❚ Pause</button>');
  if (j.state === "Paused") btns.push('<button class="btn big primary" data-do="resume">▶ Resume</button>');
  if (j.state === "Running" || j.state === "Paused") btns.push('<button class="btn big" style="background:#065f46;color:#fff;border-color:#065f46" data-do="complete">✔ Complete</button>');
  return '<div class="job card ' + (j.state === "Completed" ? "done" : "") + '" data-jc="' + esc(j.job_card) + '" data-left="' + left + '">' +
    '<div class="row" style="justify-content:space-between;align-items:center"><div><div class="jt">' + esc(j.operation) + "</div>" +
    '<div class="muted">' + esc(j.job_card) + " · " + esc(j.work_order) + "</div></div><div>" + badge(j.state) + (j.overdue ? " " + badge("Late") : "") + "</div></div>" +
    '<div class="grid2" style="margin:8px 0"><div class="kv"><div class="k">Item</div><div class="v">' + esc(j.item) + " · " + esc(j.item_name) + "</div></div>" +
    '<div class="kv"><div class="k">Quantity</div><div class="v">' + num(j.completed_qty, 0) + " / " + num(j.qty, 0) + "</div></div>" +
    '<div class="kv"><div class="k">Scheduled</div><div class="v">' + esc(fmtDT(j.scheduled_start)) + " → " + esc(fmtDT(j.scheduled_end)) + "</div></div></div>" +
    instructions(j.work_instructions) + '<div class="row" style="margin-top:10px">' + btns.join("") + "</div></div>";
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
    toast(jc + ": " + what + " recorded in ERPNext");
  } catch (e) {
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
