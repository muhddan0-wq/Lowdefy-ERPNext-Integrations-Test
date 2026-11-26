"""Build the Appsmith import file mes/appsmith/MES-Phase1.json from mes/appsmith/widgets/.

Each page = one Custom Widget ("Main") + one REST query ("Erp", POST, datasource "ERPNext").
The widget raises "onCall" {id, path, body}; the page runs Erp with those params and stores the result
under appsmith.store["mesResp_<id>"], which flows back into the widget through its model.
The datasource carries no credentials in this file: set the Authorization header in Appsmith after import.

Format follows Appsmith v2.7.2's own import compiler (clientSchemaVersion 2, serverSchemaVersion 12, DSL 95).
Run: python mes/appsmith/build_app.py
"""
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import site_config  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
W = HERE / "widgets"
OUT = HERE / "MES-Phase1.json"
APP_NAME = "MES Phase 1"
DATASOURCE = "ERPNext"
SITE = site_config.load()
DATASOURCE_URL = SITE["erp"]["datasource_url"]
ERP_PUBLIC_URL = SITE["erp"]["public_url"]
DSL_VERSION = 95
GRID = 64

PAGES = [  # (page name, widget file stem, widget height in rows of 10px)
    ("Shopfloor", "station", 84),
    ("Plant Dashboard", "plant_dashboard", 110),
    ("Shopfloor Admin", "mes_admin", 130),
    ("Work Orders", "work_orders", 90),
    ("New Plan", "new_plan", 90),
    ("Schedule Board", "schedule_board", 80),
    ("Capacity", "capacity", 90),
    ("Workstation Queue", "queue", 110),
]

# Event handlers. Custom-widget event context ({id, path, body} / {page, params}) is in scope by name.
# The event context is only in scope while the handler starts, not inside .then(): capture it in an IIFE.
ON_CALL = (
    "{{ (function (rid, p, b) { if (!/^\\/api\\/method\\/mes_[a-z_]+$/.test(p)) { storeValue('mesResp_' + rid, "
    "{ ok: false, data: null, msg: 'Blocked: only MES API methods may be called' }, false); return; } "
    "return Erp.run({ path: p, body: b })"
    ".then(function (d) { storeValue('mesResp_' + rid, { ok: true, data: d }, false); })"
    ".catch(function (e) { storeValue('mesResp_' + rid, { ok: false, data: Erp.data, "
    "status: Erp.responseMeta && Erp.responseMeta.statusCode, msg: e && e.message }, false); }); })(id, path, body) }}"
)
# Page names open in the same window; full URLs (ERPNext desk links) open in a new, unsandboxed tab.
ON_NAVIGATE = "{{ navigateTo(page, params || {}, /^https?:/.test(page) ? 'NEW_WINDOW' : 'SAME_WINDOW') }}"
ON_PREF = "{{ /^sfPref_[A-Za-z0-9_]+$/.test(key) ? storeValue(key, value, true) : null }}"
DEFAULT_MODEL = "{{ { store: appsmith.store, query: appsmith.URL.queryParams, user: appsmith.user.email } }}"


def gid(*parts):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


TOKENS = {
    "__ERP_PUBLIC_URL__": ERP_PUBLIC_URL,
    "__PLANT_NAME__": SITE["plant_floor"],
    "__PLANT_CODE__": SITE["code"],
    "__SITE_PREFIX__": SITE["site_prefix"],
    "__COMPANY__": SITE["company"]["name"],
    "__BRAND__": SITE.get("brand") or SITE["company"]["name"].split()[0].upper(),
}


def read(name):
    p = W / name
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    for k, v in TOKENS.items():
        text = text.replace(k, json.dumps(str(v))[1:-1])
    return text


SHARED_JS = {"shopfloor": ["sf_base"], "mes_admin": ["sf_base"], "station": ["sf_base", "vendor_jsqr"], "plant_dashboard": ["sf_base"]}
SHARED_CSS = {"shopfloor": ["sf_base"], "mes_admin": ["sf_base"]}
SCANNER_ROWS = 6
SCANNER_PAGES = {"station"}
ON_CODE = "{{ storeValue('sfCam', { code: CamScan.value, at: Date.now() }, false) }}"


def widget_src(stem):
    css = "\n".join(read(f"{p}.css") for p in ["common"] + SHARED_CSS.get(stem, []) + [stem])
    js = "\n".join(read(f"{p}.js") for p in ["common"] + SHARED_JS.get(stem, []) + [stem])
    html = '<div id="app"></div>\n'
    return {"html": html, "css": css, "js": js}


def code_scanner(page):
    return {
        "widgetName": "CamScan",
        "type": "CODE_SCANNER_WIDGET",
        "version": 1,
        "widgetId": gid(page, "CamScan"),
        "parentId": "0",
        "renderMode": "CANVAS",
        "label": "Camera scan (QR / barcode)",
        "scannerLayout": "CLICK_TO_SCAN",
        "isDefaultClickDisabled": True,
        "isRequired": False,
        "isDisabled": False,
        "isVisible": True,
        "isLoading": False,
        "animateLoading": True,
        "placement": "CENTER",
        "iconName": "camera",
        "iconAlign": "left",
        "buttonColor": "#14213d",
        "borderRadius": "4px",
        "boxShadow": "none",
        "onCodeDetected": ON_CODE,
        "dynamicTriggerPathList": [{"key": "onCodeDetected"}],
        "dynamicBindingPathList": [],
        "topRow": 0,
        "bottomRow": SCANNER_ROWS,
        "leftColumn": GRID - 18,
        "rightColumn": GRID,
        "mobileTopRow": 0,
        "mobileBottomRow": SCANNER_ROWS,
        "mobileLeftColumn": GRID - 18,
        "mobileRightColumn": GRID,
        "parentColumnSpace": 10,
        "parentRowSpace": 10,
        "key": gid(page, "CamScan", "key"),
    }


def custom_widget(page, stem, rows, top=0):
    src = widget_src(stem)
    left, cols = 0, GRID
    return {
        "widgetName": "Main",
        "type": "CUSTOM_WIDGET",
        "version": 1,
        "widgetId": gid(page, "Main"),
        "parentId": "0",
        "renderMode": "CANVAS",
        "isVisible": True,
        "isLoading": False,
        "events": ["onCall", "onNavigate", "onPref"],
        "onCall": ON_CALL,
        "onNavigate": ON_NAVIGATE,
        "onPref": ON_PREF,
        "defaultModel": DEFAULT_MODEL,
        "srcDoc": src,
        "uncompiledSrcDoc": src,
        "theme": "{{appsmith.theme}}",
        "dynamicBindingPathList": [{"key": "theme"}, {"key": "defaultModel"}],
        "dynamicTriggerPathList": [{"key": "onCall"}, {"key": "onNavigate"}, {"key": "onPref"}],
        "dynamicPropertyPathList": [{"key": "onCall"}, {"key": "onNavigate"}, {"key": "onPref"}],
        "borderColor": "#E0DEDE",
        "borderWidth": "0",
        "borderRadius": "0px",
        "boxShadow": "none",
        "backgroundColor": "#f6f7f9",
        "dynamicHeight": "FIXED",
        "topRow": top,
        "bottomRow": top + rows,
        "leftColumn": left,
        "rightColumn": left + cols,
        "mobileTopRow": top,
        "mobileBottomRow": top + rows,
        "mobileLeftColumn": left,
        "mobileRightColumn": left + cols,
        "parentColumnSpace": 10,
        "parentRowSpace": 10,
        "key": gid(page, "Main", "key"),
    }


def page_dsl(page, stem, rows):
    top = SCANNER_ROWS if stem in SCANNER_PAGES else 0
    children = ([code_scanner(page)] if top else []) + [custom_widget(page, stem, rows, top)]
    rows = rows + top
    return {
        "widgetName": "MainContainer",
        "type": "CANVAS_WIDGET",
        "version": DSL_VERSION,
        "widgetId": "0",
        "backgroundColor": "none",
        "snapColumns": GRID,
        "parentColumnSpace": 1,
        "parentRowSpace": 1,
        "leftColumn": 0,
        "rightColumn": GRID * 10,
        "topRow": 0,
        "bottomRow": (rows + 2) * 10,
        "minHeight": (rows + 2) * 10,
        "containerStyle": "none",
        "detachFromLayout": True,
        "canExtend": True,
        "dynamicBindingPathList": [],
        "dynamicTriggerPathList": [],
        "children": children,
    }


def page_entry(page, stem, rows):
    dsl = page_dsl(page, stem, rows)
    slug = page.lower().replace(" ", "-")
    layout = {"dsl": dsl, "layoutOnLoadActions": [], "layoutOnLoadActionErrors": []}
    return {
        "unpublishedPage": {"name": page, "slug": slug, "layouts": [layout]},
        "publishedPage": {"name": page, "slug": slug, "layouts": [json.loads(json.dumps(layout))]},
        "gitSyncId": gid(page, "page"),
    }


def erp_action(page):
    cfg = {
        "timeoutInMillisecond": 120000,
        "paginationType": "NONE",
        "path": "{{this.params.path}}",
        "headers": [{"key": "Content-Type", "value": "application/json"}, {"key": "Accept", "value": "application/json"}],
        "autoGeneratedHeaders": [],
        "encodeParamsToggle": True,
        "queryParameters": [],
        "body": "{{this.params.body}}",
        "bodyFormData": [],
        "httpMethod": "POST",
        "httpVersion": "HTTP11",
        "pluginSpecifiedTemplates": [{"value": True}],
        "formData": {"apiContentType": "application/json"},
    }
    action = {
        "name": "Erp",
        "datasource": {"name": DATASOURCE, "pluginId": "restapi-plugin", "isAutoGenerated": False, "id": DATASOURCE, "messages": []},
        "pageId": page,
        "actionConfiguration": cfg,
        "runBehaviour": "MANUAL",
        "executeOnLoad": False,
        "dynamicBindingPathList": [{"key": "path"}, {"key": "body"}],
        "isValid": True,
        "invalids": [],
        "messages": [],
        "jsonPathKeys": ["this.params.path", "this.params.body"],
        "confirmBeforeExecute": False,
        "userSetOnLoad": True,
    }
    return {
        "id": f"{page}_Erp",
        "pluginId": "restapi-plugin",
        "pluginType": "API",
        "unpublishedAction": action,
        "publishedAction": json.loads(json.dumps(action)),
        "gitSyncId": gid(page, "Erp"),
    }


def build():
    names = [p[0] for p in PAGES]
    app_pages = [{"id": n, "isDefault": n == names[0]} for n in names]
    return {
        "clientSchemaVersion": 2,
        "serverSchemaVersion": 12,
        "artifactJsonType": "APPLICATION",
        "exportedApplication": {
            "name": APP_NAME,
            "slug": APP_NAME.lower().replace(" ", "-"),
            "color": "#D9E7FF",
            "icon": "line-chart",
            "isPublic": False,
            "unpublishedCustomJSLibs": [],
            "publishedCustomJSLibs": [],
            "pages": [dict(p) for p in app_pages],
            "publishedPages": [dict(p) for p in app_pages],
            "unpublishedApplicationDetail": {"appPositioning": {"type": "FIXED"}},
            "publishedApplicationDetail": {"appPositioning": {"type": "FIXED"}},
        },
        "pageList": [page_entry(*p) for p in PAGES],
        "actionList": [erp_action(p[0]) for p in PAGES],
        "datasourceList": [{
            "name": DATASOURCE,
            "pluginId": "restapi-plugin",
            "gitSyncId": gid("datasource", DATASOURCE),
            "datasourceConfiguration": {"url": DATASOURCE_URL},
        }],
        "actionCollectionList": [],
        "customJSLibList": [],
        "editModeTheme": {"name": "Default", "isSystemTheme": True},
        "publishedTheme": {"name": "Default", "isSystemTheme": True},
        "pageOrder": list(names),
        "publishedPageOrder": list(names),
        "unpublishedDefaultPageName": names[0],
        "publishedDefaultPageName": names[0],
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(PAGES)} pages)")
