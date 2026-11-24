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

HERE = pathlib.Path(__file__).resolve().parent
W = HERE / "widgets"
OUT = HERE / "MES-Phase1.json"
APP_NAME = "MES Phase 1"
DATASOURCE = "ERPNext"
DATASOURCE_URL = "http://host.docker.internal:8000"
DSL_VERSION = 95
GRID = 64

PAGES = [  # (page name, widget file stem, widget height in rows of 10px)
    ("Work Orders", "work_orders", 90),
    ("Work Order Detail", "wo_detail", 110),
    ("New Plan", "new_plan", 90),
    ("Schedule Board", "schedule_board", 80),
    ("Capacity", "capacity", 90),
    ("Workstation Queue", "queue", 110),
]

# Event handlers. Custom-widget event context ({id, path, body} / {page, params}) is in scope by name.
# The event context is only in scope while the handler starts, not inside .then(): capture it in an IIFE.
ON_CALL = (
    "{{ (function (rid, p, b) { return Erp.run({ path: p, body: b })"
    ".then(function (d) { storeValue('mesResp_' + rid, { ok: true, data: d }, false); })"
    ".catch(function (e) { storeValue('mesResp_' + rid, { ok: false, data: Erp.data, "
    "status: Erp.responseMeta && Erp.responseMeta.statusCode, msg: e && e.message }, false); }); })(id, path, body) }}"
)
ON_NAVIGATE = "{{ navigateTo(page, params || {}, 'SAME_WINDOW') }}"
DEFAULT_MODEL = "{{ { store: appsmith.store, query: appsmith.URL.queryParams, user: appsmith.user.email } }}"


def gid(*parts):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def read(name):
    p = W / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def widget_src(stem):
    css = read("common.css") + "\n" + read(f"{stem}.css")
    js = read("common.js") + "\n" + read(f"{stem}.js")
    html = '<div id="app"></div>\n'
    return {"html": html, "css": css, "js": js}


def custom_widget(page, stem, rows):
    src = widget_src(stem)
    top, left, cols = 0, 0, GRID
    return {
        "widgetName": "Main",
        "type": "CUSTOM_WIDGET",
        "version": 1,
        "widgetId": gid(page, "Main"),
        "parentId": "0",
        "renderMode": "CANVAS",
        "isVisible": True,
        "isLoading": False,
        "events": ["onCall", "onNavigate"],
        "onCall": ON_CALL,
        "onNavigate": ON_NAVIGATE,
        "defaultModel": DEFAULT_MODEL,
        "srcDoc": src,
        "uncompiledSrcDoc": src,
        "theme": "{{appsmith.theme}}",
        "dynamicBindingPathList": [{"key": "theme"}, {"key": "defaultModel"}],
        "dynamicTriggerPathList": [{"key": "onCall"}, {"key": "onNavigate"}],
        "dynamicPropertyPathList": [{"key": "onCall"}, {"key": "onNavigate"}],
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
        "children": [custom_widget(page, stem, rows)],
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
