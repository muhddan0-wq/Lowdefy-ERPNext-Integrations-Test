// ---- Shopfloor base (shared by the Shopfloor and Shopfloor Admin pages) ----
// ERPNext public files (item photos) load straight from ERPNext; private attachments open in ERPNext desk.
const ERP_PUBLIC = "__ERP_PUBLIC_URL__";
document.body.classList.add("sf");

function operator() {
  const m = appsmith.model || {};
  return m.user || "";
}

function api(method, args) {
  return MES.post(method, Object.assign({ operator: operator() }, args || {}));
}

// Appsmith runs widgets in a sandboxed frame without same-origin, where localStorage throws. Preferences then live in
// memory and are saved through the widget's "onPref" event (Appsmith storeValue, persisted), read back from the model.
const PREFS = (() => {
  let ls = null;
  try { ls = window.localStorage; ls.getItem("x"); } catch (e) { ls = null; }
  const mem = {};
  return {
    get(k) {
      if (ls) return ls.getItem(k);
      if (k in mem) return mem[k];
      const st = (appsmith.model && appsmith.model.store) || {};
      const v = st["sfPref_" + k.replace(/[^a-zA-Z0-9]/g, "_")];
      return v === undefined || v === null ? null : String(v);
    },
    set(k, v) {
      if (ls) { if (v === null) ls.removeItem(k); else ls.setItem(k, v); return; }
      mem[k] = v;
      appsmith.triggerEvent("onPref", { key: "sfPref_" + k.replace(/[^a-zA-Z0-9]/g, "_"), value: v });
    },
  };
})();

function reqId() {
  return "w" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
}

function fileUrl(u) {
  if (!u) return "";
  return /^https?:/.test(u) ? u : ERP_PUBLIC + encodeURI(u);
}

function pic(url, alt, size) {
  const cls = "pic" + (size ? " " + size : "");
  const ph = '<div class="' + cls + ' ph"><span>&#128247;</span>No photo</div>';
  if (!url) return ph;
  return '<img class="' + cls + '" src="' + esc(fileUrl(url)) + '" alt="' + esc(alt || "") + '" loading="lazy" data-ph="' + esc(ph) + '">';
}

document.addEventListener("error", (e) => {
  const t = e.target;
  if (t && t.tagName === "IMG" && t.dataset && t.dataset.ph) {
    const d = document.createElement("div");
    d.innerHTML = t.dataset.ph;
    t.replaceWith(d.firstChild);
  }
}, true);

function chipFor(status) {
  const map = {
    "Verified": "ok", "Valid": "ok", "Resolved": "ok", "Closed": "ok", "Completed": "ok", "Operating Normally": "ok", "Accepted": "info",
    "Partially Verified": "warn", "Awaiting Scan": "info", "Running": "info", "Work In Progress": "info", "Acknowledged": "info",
    "In Progress": "warn", "Under Review": "warn", "Rework Required": "warn", "Experiencing Problems": "warn", "High": "warn", "Medium": "info",
    "Invalid Material": "bad", "Defective Material": "bad", "Invalid": "bad", "Defective": "bad", "Reported": "bad", "Open": "bad",
    "Stalled": "bad", "Completely Down": "bad", "Critical": "bad", "Rejected": "", "Voided": "", "Low": "",
  };
  return '<span class="chip ' + (map[status] || "") + '">' + esc(status || "-") + "</span>";
}

function pbar(done, total) {
  const p = total ? Math.max(0, Math.min(100, 100 * done / total)) : 0;
  return '<div class="prog"><span style="width:' + p.toFixed(1) + '%"></span></div>';
}

let audioCtx = null;
function beep(ok) {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const notes = ok ? [880, 1320] : [220, 180];
    notes.forEach((f, i) => {
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      o.type = ok ? "sine" : "square";
      o.frequency.value = f;
      g.gain.value = 0.08;
      o.connect(g); g.connect(audioCtx.destination);
      const t = audioCtx.currentTime + i * 0.16;
      o.start(t); o.stop(t + 0.14);
    });
  } catch (e) { /* audio is optional */ }
}

function readFiles(fileList, maxMb) {
  const limit = (maxMb || 10) * 1024 * 1024;
  return Promise.all(Array.from(fileList || []).map((f) => new Promise((resolve, reject) => {
    if (f.size > limit) { reject(new Error(f.name + " is larger than " + (maxMb || 10) + " MB")); return; }
    const r = new FileReader();
    r.onload = () => resolve({ file_name: f.name || "photo.jpg", data: String(r.result), type: f.type || "", size: f.size });
    r.onerror = () => reject(new Error("Could not read " + f.name));
    r.readAsDataURL(f);
  })));
}

function fmtWhen(s) {
  return fmtDT(s, false);
}

function qtyFmt(v) {
  return num(v, 3);
}
// ---- end shopfloor base ----
