# 2. Lowdefy basics (learned from this app)

Lowdefy builds web apps from **YAML config** instead of React code. You describe what is on the page, where the data comes from and what happens when someone clicks. Lowdefy turns that into a Next.js app. This project uses **Lowdefy 7.1.0**.

Every example below is copied from this repo, so you can open the file and see it in context.

## The mental model in one picture

```
lowdefy.yaml ── app settings, plugins, connections, theme, list of pages
   │
   └─ pages/*.yaml ── one file per page
        ├─ requests:  "how to fetch or send data" (uses a connection)
        ├─ events:    "what to do when the page loads" (onInit / onInitAsync)
        └─ blocks:    "what is on screen" (a tree of components)
              └─ each block can have its own events (onClick, onChange, ...)
                    └─ each event is a list of actions (SetState, Request, Link, ...)

state ── the page's memory. Inputs write to it; everything else reads it.
operators ── the _something: keys that compute values (_state, _request, _if, ...)
```

Six words to learn: **block, state, request, connection, event/action, operator**.

## 1. `lowdefy.yaml`: the app root

```yaml
lowdefy: 7.1.0
name: ERPNext Copilot
plugins:                          # which component/connection packages to load
  - name: '@lowdefy/blocks-antd'  # buttons, cards, tables, inputs (Ant Design)
  - name: '@lowdefy/blocks-echarts'
  - name: '@lowdefy/connection-axios-http'   # lets requests call HTTP APIs
connections:                      # servers the app may call (server-side only)
  - id: copilot
    type: AxiosHttp
    properties:
      baseURL:
        _secret: COPILOT_API_URL  # read from .env as LOWDEFY_SECRET_COPILOT_API_URL
theme:                            # colours for every Ant Design component
  darkMode: dark
  antd:
    token:
      colorPrimary: "#2DD4BF"
pages:
  - _ref: pages/overview.yaml     # _ref pulls another YAML file in
```

- **Plugins** are npm packages that provide block types (`Button`, `Table`, ...) and connection types (`AxiosHttp`).
- **Connections** run on the Lowdefy **server**, never in the browser. That is why secrets are safe there.
- **`_secret: NAME`** reads the environment variable `LOWDEFY_SECRET_NAME`.
- **`_ref`** splits config across files. The menu is shared the same way: every page uses `_ref: menus/main.yaml`.

## 2. A page and its blocks

```yaml
id: inventory                 # URL becomes /inventory
type: PageSidebarLayout       # page shell: sidebar menu + header + content
properties:
  title: Inventory
  menu:
    links:
      _ref: menus/main.yaml
blocks:
- id: page_box
  type: Box                   # a plain container (like a <div>)
  blocks:
  - id: page_title
    type: Title
    properties:
      content: Inventory
      level: 3
```

Every block has an `id` (unique on the page) and a `type`. `properties` configure it. Container blocks hold children under `blocks:`.

The block types this app uses most: `Box` (102×), `Card` (77×), `Statistic` (53×), `Button`, `Markdown`, `Table`, `Title`, `Selector` (dropdown), `Tag`, `NumberInput`, `Alert`, `Tabs`, `Drawer`, `EChart`, `QRCode`, `DangerousHtml` (raw HTML, used to embed the 3D floor iframe).

## 3. State: the page's memory

Each page has a **state** object. Input blocks write their value into state under their own `id` automatically. Other blocks read state with `_state`.

```yaml
events:
  onInit:                     # runs before the page renders
  - id: inv_state
    type: SetState            # action: put values into state
    params:
      fSearch: ""
      fWarehouse: ""
```

```yaml
visible:
  _state: tSubmit             # only show this block when tSubmit is true
```

## 4. Requests: getting data

A request says which connection to use and what to send. It does **not** run by itself; an event triggers it.

```yaml
requests:
- id: inventory_req
  type: AxiosHttp
  connectionId: copilot       # the connection from lowdefy.yaml
  payload:                    # values sent from the browser to the server
    search:
      _state: fSearch
  properties:                 # evaluated on the server
    url: /inventory           # → http://127.0.0.1:4010/inventory
    params:
      search:
        _payload: search      # read what the browser sent
```

**Why `payload` and then `_payload`?** `properties` are evaluated on the server, which can't see browser state. So you pass browser values through `payload`, and the server picks them up with `_payload`. It is the most common beginner confusion in Lowdefy.

Read the response anywhere with `_request`:

```yaml
data:
  _request: inventory_req.data.rows   # AxiosHttp puts the response body in .data
```

A **POST** works the same way: put the JSON body in `properties.data` and set `method: post` (see `transfer_req` in `pages/movements.yaml`).

## 5. Events and actions: making things happen

An event is a list of **actions** that run in order. If one fails, the rest stop.

```yaml
events:
  onRowClick:                 # a Table event
  - id: row_select
    type: SetState
    params:
      selectedCode:
        _event: row.code      # _event = data that came with the event
  - id: row_fetch
    type: Request             # run a request
    params: item_req
  - id: row_open
    type: CallMethod          # call a method on another block
    params:
      blockId: item_drawer
      method: toggleOpen      # opens the side drawer
```

Events used in this app: `onInit` (before render), `onInitAsync` (after render; good for slow fetches), `onClick`, `onChange`, `onPressEnter`, `onRowClick`.

Actions used: `SetState`, `Request`, `CallMethod`, `Link` (navigate or open a URL).

## 6. Operators: logic inside YAML

Any key starting with `_` is an **operator**. It gets replaced by a computed value.

| Operator | What it does | Example in this repo |
|---|---|---|
| `_state` | read page state | `_state: fSearch` |
| `_request` | read a request's response | `_request: orders_req.data.data` |
| `_payload` | read the payload (server side) | `_payload: search` |
| `_event` | read event data | `_event: row.code` |
| `_secret` | read an env secret (server side) | `_secret: ERP_TOKEN` |
| `_ref` | include another file | `_ref: menus/main.yaml` |
| `_if` | if/else | button title: "Create and submit" vs "Create draft" |
| `_if_none` | fall back when the value is null | `_if_none: [ _request: x, [] ]` |
| `_eq`, `_ne`, `_gt`, `_not`, `_and`, `_or` | comparisons and logic | disable a button until fields are filled |
| `_string.concat` | join strings | `'token ' + secret` header |
| `_array.length`, `_array.filter` | array helpers | count orders with a given status |
| `_function` + `__args` | an inline function (note the **double** underscore inside) | filter callback |
| `_url_query`, `_location` | read the URL | the scanner returning `?code=...` |

A real combination (from `pages/orders.yaml`), counting orders with status "Draft":

```yaml
value:
  _array.length:
    _array.filter:
      on:
        _request: orders_req.data.data
      callback:
        _function:
          __eq:
          - __args: 0.status
          - Draft
```

A disabled-until-valid button (from `pages/movements.yaml`):

```yaml
disabled:
  _or:
  - _not:
      _state: tItem
  - _and:
    - _state: tSubmit
    - _not:
        _state: tConfirm
```

## 7. Tables

```yaml
type: Table
properties:
  rowKey: code
  pagination: true
  pageSize: 25
  toolbar: { search: true, sort: true, export: true }
  columns:
  - key: code
    title: Item code
    pinned: start
  - key: available
    title: Available
    type: number
  data:
    _request: inventory_req.data.rows
```

## 8. Styling (Lowdefy 7 gotchas found while building this)

- The global design system lives in `public/styles.css`. Lowdefy 7 loads it automatically. Utility classes like `kpi kpi-mint`, `page-hero` and `section-title` are defined there. Tailwind classes also work.
- `class: "x"` (a plain string) lands on the **outer wrapper** of a block. To style the block itself, use `class: { .element: "x" }`.
- A `Box` wraps its children in an extra `.lf-row` element. `styles.css` sets `:is(.grid,.flex) > .lf-row { display: contents }`, which makes Tailwind `grid`/`flex` on the parent work as expected.
- In YAML, an unquoted value containing ` #` is cut off as a comment (for example inline CSS `#2C2D38`). Use quotes or a `|-` block for HTML/CSS strings.
- `DangerousHtml` strips `<iframe>` unless you allow it (`DOMPurifyOptions.ADD_TAGS: [iframe]`). See `pages/floor.yaml`.
- Menu icon colours come from `#nav_<page>_icon` rules in `styles.css`. A new menu link needs a line there.

## 9. Recipe: add a new page

1. Create `pages/suppliers.yaml` with `id: suppliers`, `type: PageSidebarLayout`, and the same `properties` block as another page (copy `pages/floor.yaml`'s top part).
2. Add a request that calls the helper, for example `url: /suppliers` (that endpoint already exists).
3. In `events.onInitAsync`, run the request.
4. Add a `Table` block with `data: { _request: suppliers_req.data }`.
5. Register it in `lowdefy.yaml` under `pages:` with `- _ref: pages/suppliers.yaml`.
6. Add a `MenuLink` to `menus/main.yaml`.

Lowdefy dev picks it up without a restart.

## Where to read more

- Official docs: https://docs.lowdefy.com
- Every page in `pages/` here is a working example. `floor.yaml` (86 lines) is the smallest; `inventory.yaml` shows request → table → drawer.
