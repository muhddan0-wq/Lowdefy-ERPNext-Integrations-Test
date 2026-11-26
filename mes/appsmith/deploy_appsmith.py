"""Put the shopfloor pages into an EXISTING Appsmith application (default: "My first application").

Unlike importing MES-Phase1.json (which creates a new app), this adds or updates pages in place through the
Appsmith REST API, signed in as you:
  - backs up the whole app first (Appsmith export) to mes/state/appsmith-backup-<time>.json
  - creates each page if missing, otherwise replaces only that page's layout
  - makes sure each page has the "Erp" REST query on your existing "ERPNext" datasource
  - publishes the app

Pages touched by default: Shopfloor, Plant Dashboard, Shopfloor Admin. Planner pages are left alone unless you
pass --all (that refreshes their widgets too, e.g. to get the new nav links).

Usage (from the repo root):
  python mes/appsmith/deploy_appsmith.py                       # asks for your Appsmith email and password
  python mes/appsmith/deploy_appsmith.py --make-default        # also make Shopfloor the app's home page
  python mes/appsmith/deploy_appsmith.py --app "My first application" --all
Env vars APPSMITH_EMAIL / APPSMITH_PASSWORD are used if set. Nothing is stored.
"""
import argparse
import getpass
import http.cookiejar
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import build_app

HERE = pathlib.Path(__file__).resolve().parent
STATE = HERE.parent / "state"
SHOPFLOOR_PAGES = ["Shopfloor", "Plant Dashboard", "Shopfloor Admin"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Appsmith:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect)

    def call(self, method, path, body=None, form=None, raw=False):
        headers = {"X-Requested-By": "Appsmith", "Accept": "application/json"}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.op.open(req, timeout=120) as r:
                payload = r.read()
                status, location = r.status, r.headers.get("Location", "")
        except urllib.error.HTTPError as e:
            payload = e.read()
            status, location = e.code, e.headers.get("Location", "")
        if raw:
            return status, location, payload
        try:
            doc = json.loads(payload or b"{}")
        except ValueError:
            raise SystemExit(f"{method} {path}: HTTP {status}, not JSON: {payload[:200]!r}")
        meta = doc.get("responseMeta") or {}
        if status >= 400 or meta.get("success") is False:
            err = (meta.get("error") or {}).get("message") or doc.get("message") or payload[:300]
            raise SystemExit(f"{method} {path}: HTTP {status}: {err}")
        return doc.get("data")

    def login(self, email, password):
        status, location, _ = self.call("POST", "/api/v1/login", form={"username": email, "password": password}, raw=True)
        if status not in (200, 302) or "error" in location:
            raise SystemExit("Appsmith sign-in failed: check the email and password")
        me = self.call("GET", "/api/v1/users/me")
        if not me or me.get("email") in (None, "anonymousUser"):
            raise SystemExit("Appsmith sign-in did not stick (no session)")
        return me


def as_list(x, *keys):
    if isinstance(x, list):
        return x
    for k in keys:
        if isinstance(x, dict) and isinstance(x.get(k), list):
            return x[k]
    return []


def find_app(api, name, app_id):
    workspaces = []
    for path in ("/api/v1/workspaces/home", "/api/v1/workspaces"):
        try:
            workspaces = as_list(api.call("GET", path), "workspaces")
            if workspaces:
                break
        except SystemExit:
            continue
    for ws in workspaces:
        wid = ws.get("id") or (ws.get("workspace") or {}).get("id")
        apps = ws.get("applications")
        if apps is None:
            apps = as_list(api.call("GET", "/api/v1/applications/home?workspaceId=" + wid), "applications")
        for a in apps or []:
            if (app_id and a.get("id") == app_id) or (not app_id and a.get("name") == name):
                return a, wid
    raise SystemExit(f"Application {app_id or name!r} not found in your workspaces")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=build_app.SITE["appsmith"]["url"])
    ap.add_argument("--app", default="My first application")
    ap.add_argument("--app-id")
    ap.add_argument("--all", action="store_true", help="also refresh the six planner pages")
    ap.add_argument("--make-default", action="store_true", help="make Shopfloor the app's home page")
    ap.add_argument("--no-publish", action="store_true")
    a = ap.parse_args()

    email = os.environ.get("APPSMITH_EMAIL") or input("Appsmith email: ").strip()
    password = os.environ.get("APPSMITH_PASSWORD") or getpass.getpass("Appsmith password: ")
    api = Appsmith(a.url)
    me = api.login(email, password)
    print(f"signed in as {me.get('email')}")

    app, wid = find_app(api, a.app, a.app_id)
    app_id = app["id"]
    print(f"app {app['name']} ({app_id}), workspace {wid}")

    STATE.mkdir(exist_ok=True)
    status, _, backup = api.call("GET", f"/api/v1/applications/export/{app_id}", raw=True)
    if status != 200 or not backup:
        raise SystemExit(f"Backup export failed (HTTP {status}); nothing was changed")
    bpath = STATE / time.strftime("appsmith-backup-%Y%m%d-%H%M%S.json")
    bpath.write_bytes(backup)
    print(f"backup  {bpath}")

    ds = [d for d in as_list(api.call("GET", f"/api/v1/datasources?workspaceId={wid}")) if d.get("name") == build_app.DATASOURCE]
    if not ds:
        raise SystemExit(f"Datasource {build_app.DATASOURCE!r} not found in the workspace; create it first (see mes/appsmith/README.md)")
    ds = ds[0]

    pages = as_list(api.call("GET", f"/api/v1/pages?applicationId={app_id}&mode=EDIT"), "pages")
    by_name = {p["name"]: p for p in pages}
    actions = as_list(api.call("GET", f"/api/v1/actions?applicationId={app_id}"))
    wanted = [p for p in build_app.PAGES if p[0] in SHOPFLOOR_PAGES or a.all]

    for name, stem, rows in wanted:
        p = by_name.get(name)
        if p:
            page = api.call("GET", f"/api/v1/pages/{p['id']}")
            verb = "updated"
        else:
            blank = dict(build_app.page_dsl(name, stem, rows), children=[])
            page = api.call("POST", "/api/v1/pages", body={"name": name, "applicationId": app_id, "layouts": [{"dsl": blank}]})
            verb = "created"
        page_id = page["id"]
        layout_id = page["layouts"][0]["id"]
        erp = build_app.erp_action(name)["unpublishedAction"]
        cfg = erp["actionConfiguration"]
        mine = [x for x in actions if x.get("pageId") == page_id and x.get("name") == "Erp"]
        dsref = {"id": ds["id"], "name": ds["name"], "pluginId": ds["pluginId"]}
        if mine:
            api.call("PUT", f"/api/v1/actions/{mine[0]['id']}", body={"id": mine[0]["id"], "pageId": page_id, "datasource": dsref,
                                                                       "actionConfiguration": cfg, "executeOnLoad": False})
        else:
            api.call("POST", "/api/v1/actions", body={"name": "Erp", "pageId": page_id, "pluginId": ds["pluginId"], "pluginType": "API",
                                                       "datasource": dsref, "actionConfiguration": cfg, "executeOnLoad": False,
                                                       "dynamicBindingPathList": erp["dynamicBindingPathList"]})
        dsl = build_app.page_dsl(name, stem, rows)
        api.call("PUT", f"/api/v1/layouts/{layout_id}/pages/{page_id}?applicationId={app_id}", body={"dsl": dsl})
        print(f"{verb:8}{name}")
        by_name[name] = {"id": page_id}

    if a.make_default:
        api.call("PUT", f"/api/v1/applications/{app_id}/page/{by_name['Shopfloor']['id']}/makeDefault")
        print("default Shopfloor")
    if not a.no_publish:
        api.call("POST", f"/api/v1/applications/publish/{app_id}")
        print("published")
    print(f"open {a.url}/app/{app.get('slug', 'app')}/shopfloor-{by_name['Shopfloor']['id']}")


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    main()
