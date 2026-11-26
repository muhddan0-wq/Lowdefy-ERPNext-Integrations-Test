// ---- MES common (prepended to every page widget by build_app.py) ----
// The widget never talks to ERPNext itself. It raises the Appsmith event "onCall" with
// {id, method, path, body}; the page's ErpGet/ErpPost REST queries (server-side, API key kept in the
// Appsmith datasource) run it and storeValue("mesResp_<id>", ...) the result, which flows back in
// through the widget model (appsmith.model.store).
const MES = (() => {
  const pending = {};
  const handled = new Set();
  const ERP_DESK = "__ERP_PUBLIC_URL__/desk/";

  function uid() {
    return "r" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function decode(html) {
    const t = document.createElement("textarea");
    t.innerHTML = String(html == null ? "" : html).replace(/<[^>]*>/g, "");
    return t.value.trim();
  }

  function errText(r) {
    const d = r.data;
    try {
      if (d && d._server_messages) {
        return JSON.parse(d._server_messages)
          .map((x) => { try { return JSON.parse(x).message; } catch (e) { return x; } })
          .map(decode).filter(Boolean).join("\n");
      }
      if (d && Array.isArray(d.errors) && d.errors.length) {
        return d.errors.map((e) => decode(e.message || e.title || String(e.exception || e.type).split("\n").pop())).join("\n");
      }
      if (d && d.exception) return decode(String(d.exception).split("\n").filter(Boolean).pop());
      if (d && typeof d.message === "string") return decode(d.message);
      if (typeof d === "string" && d) return decode(d).slice(0, 400);
    } catch (e) { /* fall through */ }
    return r.msg || "Request failed" + (r.status ? " (HTTP " + r.status + ")" : "");
  }

  function deliver(model) {
    const store = (model && model.store) || {};
    Object.keys(pending).forEach((id) => {
      const r = store["mesResp_" + id];
      if (!r || handled.has(id)) return;
      handled.add(id);
      const p = pending[id];
      delete pending[id];
      if (r.ok) p.resolve(r.data);
      else p.reject(new Error(errText(r)));
    });
  }

  function request(method, path, body) {
    return new Promise((resolve, reject) => {
      const id = uid();
      pending[id] = { resolve, reject };
      appsmith.triggerEvent("onCall", { id: id, method: method, path: path, body: body || {} });
      setTimeout(() => {
        if (pending[id]) {
          delete pending[id];
          reject(new Error("No answer from ERPNext after 2 minutes"));
        }
      }, 120000);
    });
  }

  function qs(params) {
    const parts = [];
    Object.keys(params || {}).forEach((k) => {
      const v = params[k];
      if (v === undefined || v === null || v === "") return;
      parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(typeof v === "object" ? JSON.stringify(v) : v));
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  // Read calls also go as POST /api/method/<name> with a JSON body: Frappe API server scripts accept both,
  // and it keeps each Appsmith page down to ONE REST query ("Erp") with no query strings in the path.
  async function get(method, args) {
    return post(method, args);
  }

  // POST /api/method/<name> {args} -> message
  async function post(method, args) {
    const d = await request("POST", "/api/method/" + method, args || {});
    return d && d.message !== undefined ? d.message : d;
  }

  function navigate(page, params) {
    appsmith.triggerEvent("onNavigate", { page: page, params: params || {} });
  }

  function deskUrl(doctype, name) {
    return ERP_DESK + doctype.toLowerCase().replace(/ /g, "-") + "/" + encodeURIComponent(name);
  }

  return { request, get, post, qs, navigate, deliver, decode, deskUrl };
})();

// ---- small DOM / format helpers ----
const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

function esc(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function num(v, dp) {
  const n = Number(v || 0);
  return n.toLocaleString("en-MY", { maximumFractionDigits: dp == null ? 2 : dp });
}

// ERPNext returns naive local datetimes "YYYY-MM-DD HH:mm:ss" (site TZ Asia/Kuala_Lumpur); keep them naive.
function parseDT(s) {
  if (!s) return null;
  const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
}

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n) => String(n).padStart(2, "0");

function fmtDT(s, withDow) {
  const d = s instanceof Date ? s : parseDT(s);
  if (!d) return "";
  return (withDow === false ? "" : DOW[d.getDay()] + " ") + pad(d.getDate()) + " " + MON[d.getMonth()] + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
}

function fmtD(s) {
  const d = s instanceof Date ? s : parseDT(s);
  return d ? DOW[d.getDay()] + " " + pad(d.getDate()) + " " + MON[d.getMonth()] : "";
}

function isoDate(d) {
  return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
}

function isoDT(d) {
  return isoDate(d) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
}

function addDays(d, n) {
  const x = new Date(d.getTime());
  x.setDate(x.getDate() + n);
  return x;
}

function badge(status) {
  const cls = {
    "Not Started": "b-grey", "Open": "b-blue", "In Process": "b-amber", "Work In Progress": "b-amber",
    "Running": "b-amber", "Completed": "b-green", "Closed": "b-dark", "Stopped": "b-red", "Cancelled": "b-dark",
    "On Hold": "b-purple", "Paused": "b-purple", "Material Transferred": "b-cyan", "Late": "b-red", "Not started": "b-blue",
  }[status] || "b-grey";
  return '<span class="badge ' + cls + '">' + esc(status || "-") + "</span>";
}

function bar(pct, cls) {
  const p = Math.max(0, Math.min(100, Number(pct || 0)));
  return '<div class="bar ' + (cls || "") + '"><span style="width:' + p + '%"></span></div>';
}

let toastTimer;
function toast(msg, kind) {
  let t = $("#toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    document.body.appendChild(t);
  }
  t.className = "show " + (kind || "ok");
  t.textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ""; }, kind === "err" ? 9000 : 4000);
}

// Modal dialog inside the widget. Returns a Promise<boolean>.
function dialog(title, html, okLabel, opts) {
  opts = opts || {};
  return new Promise((resolve) => {
    const wrap = document.createElement("div");
    wrap.className = "modal-wrap";
    wrap.innerHTML =
      '<div class="modal"><h3>' + esc(title) + '</h3><div class="modal-body">' + html + "</div>" +
      '<div class="modal-actions">' + (opts.noCancel ? "" : '<button class="btn" data-x="0">Cancel</button>') +
      '<button class="btn ' + (opts.danger ? "danger" : "primary") + '" data-x="1">' + esc(okLabel || "OK") + "</button></div></div>";
    document.body.appendChild(wrap);
    wrap.addEventListener("click", (e) => {
      const x = e.target.getAttribute && e.target.getAttribute("data-x");
      if (x === null || x === undefined) return;
      const ok = x === "1";
      const values = {};
      $$("input,select,textarea", wrap).forEach((i) => { values[i.name] = i.value; });
      wrap.remove();
      resolve(opts.withValues ? (ok ? values : null) : ok);
    });
  });
}

function setBusy(on) {
  document.body.classList.toggle("busy", !!on);
}

const SITE_PREFIX = "__SITE_PREFIX__";
function noPrefix(s) {
  s = String(s || "");
  return SITE_PREFIX && s.indexOf(SITE_PREFIX) === 0 ? s.slice(SITE_PREFIX.length) : s;
}

function navBar(active) {
  const pages = ["Work Orders", "New Plan", "Schedule Board", "Capacity", "Workstation Queue", "Shopfloor", "Plant Dashboard", "Shopfloor Admin"];
  return '<nav class="nav"><b>MES · __PLANT_NAME__</b>' + pages.map((p) =>
    '<a href="#" data-nav="' + esc(p) + '" class="' + (p === active ? "on" : "") + '">' + esc(p) + "</a>").join("") + "</nav>";
}

document.addEventListener("click", (e) => {
  // External links (ERPNext desk) must not open from inside the sandboxed widget frame: the new tab would inherit the
  // sandbox, so ERPNext could not use its login cookie and the page hangs. Hand them to Appsmith's navigateTo instead.
  const ext = e.target.closest && e.target.closest("a[href^='http']");
  if (ext) {
    e.preventDefault();
    appsmith.triggerEvent("onNavigate", { page: ext.getAttribute("href"), params: {} });
    return;
  }
  const a = e.target.closest && e.target.closest("[data-nav]");
  if (a) {
    e.preventDefault();
    MES.navigate(a.getAttribute("data-nav"), a.dataset.params ? JSON.parse(a.dataset.params) : {});
  }
});

function startPage(init) {
  let started = false;
  appsmith.onModelChange((model) => {
    MES.deliver(model);
  });
  appsmith.onReady(() => {
    MES.deliver(appsmith.model);
    if (!started) {
      started = true;
      init(appsmith.model || {});
    }
  });
}
// ---- end MES common ----
