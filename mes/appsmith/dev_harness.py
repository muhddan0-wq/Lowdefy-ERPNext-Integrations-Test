"""Local test harness for the MES Appsmith widgets (development only).

Serves http://127.0.0.1:8099/?page=<widget> which renders a widget exactly as the Appsmith Custom Widget
would (common + page CSS/JS) with a mock `appsmith` object. "onCall" events are proxied server-side to
ERPNext with the appsmith-mes API key from mes/.secrets/appsmith-mes.env, so the key never reaches the
browser — same contract as the real ErpGet/ErpPost Appsmith queries.

Run:  python mes/appsmith/dev_harness.py
"""
import http.server
import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
W = HERE / "widgets"
ERP = "http://localhost:8000"
env = dict(l.split("=", 1) for l in (HERE.parent / ".secrets" / "appsmith-mes.env").read_text().split() if "=" in l)
AUTH = f"token {env['ERP_API_KEY']}:{env['ERP_API_SECRET']}"

MOCK = r"""
<script>
(function () {
  const subs = [];
  let readyFn = null;
  const params = Object.fromEntries(new URLSearchParams(location.search));
  const model = { store: {}, query: params, user: "harness" };
  window.appsmith = {
    model, ui: { width: innerWidth, height: innerHeight }, theme: {}, mode: "DEPLOYED",
    onModelChange(fn) { subs.push(fn); fn(window.appsmith.model); },
    onUiChange() {}, onThemeChange() {},
    onReady(fn) { readyFn = fn; setTimeout(() => readyFn && readyFn(), 0); },
    updateModel(o) { Object.assign(window.appsmith.model, o); },
    triggerEvent(name, ctx) {
      if (name === "onNavigate") {
        const map = { "Work Orders": "work_orders", "Work Order Detail": "wo_detail", "New Plan": "new_plan",
          "Schedule Board": "schedule_board", "Capacity": "capacity", "Workstation Queue": "queue" };
        const q = new URLSearchParams(Object.assign({ page: map[ctx.page] }, ctx.params || {}));
        location.search = q.toString();
        return;
      }
      if (name !== "onCall") return;
      fetch("/proxy", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(ctx) })
        .then((r) => r.json())
        .then((res) => {
          const m = Object.assign({}, window.appsmith.model);
          m.store = Object.assign({}, m.store, { ["mesResp_" + ctx.id]: Object.assign({ id: ctx.id }, res) });
          window.appsmith.model = m;
          subs.forEach((fn) => fn(m));
        });
    },
  };
  document.documentElement.style.setProperty("--appsmith-ui-height", innerHeight);
  document.documentElement.style.setProperty("--appsmith-ui-width", innerWidth);
})();
</script>
"""


def page_html(name):
    css = (W / "common.css").read_text(encoding="utf-8")
    if (W / f"{name}.css").exists():
        css += "\n" + (W / f"{name}.css").read_text(encoding="utf-8")
    js = (W / "common.js").read_text(encoding="utf-8") + "\n" + (W / f"{name}.js").read_text(encoding="utf-8")
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{MOCK}<div id='app'></div><script type='module'>{js}</script></body></html>"


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        name = (q.get("page") or ["work_orders"])[0]
        if not (W / f"{name}.js").exists():
            return self._send(404, "unknown page", "text/plain")
        self._send(200, page_html(name), "text/html; charset=utf-8")

    def do_POST(self):
        ctx = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        path = ctx.get("path", "")
        if not path.startswith("/api/"):
            return self._send(400, json.dumps({"ok": False, "msg": "bad path"}))
        method = "POST" if ctx.get("method") == "POST" else "GET"
        data = json.dumps(ctx.get("body") or {}).encode() if method == "POST" else None
        req = urllib.request.Request(ERP + path, data=data, method=method,
                                     headers={"Authorization": AUTH, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out = {"ok": True, "data": json.loads(r.read() or b"{}")}
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                body = json.loads(raw)
            except Exception:
                body = raw.decode("utf-8", "replace")
            out = {"ok": False, "data": body, "status": e.code}
        self._send(200, json.dumps(out))


if __name__ == "__main__":
    print("MES widget harness on http://127.0.0.1:8099/?page=work_orders")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8099), H).serve_forever()
