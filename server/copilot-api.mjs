import http from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID, timingSafeEqual } from 'node:crypto';

const SERVER_DIR = dirname(fileURLToPath(import.meta.url));

function readEnv(file) {
  const env = {};
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const idx = trimmed.indexOf('=');
    if (idx < 1) continue;
    env[trimmed.slice(0, idx)] = trimmed.slice(idx + 1);
  }
  return env;
}

const env = readEnv(new URL('../.env', import.meta.url));
const PORT = Number(env.COPILOT_API_PORT || 4010);
const ERP_URL = (env.ERPNEXT_URL || '').replace(/\/$/, '');
const AUTH = env.ERPNEXT_AUTH_HEADER || '';
const DB_PATH = env.COPILOT_DB_PATH;
const API_KEY = env.COPILOT_API_KEY || '';
const APP_URL = (env.COPILOT_APP_URL || env.INVENTORY_APP_URL || 'http://localhost:3011').replace(/\/$/, '');

if (!ERP_URL || !AUTH) throw new Error('ERPNEXT_URL / ERPNEXT_AUTH_HEADER missing from .env');
if (!DB_PATH) throw new Error('COPILOT_DB_PATH missing from .env');
if (!API_KEY) console.warn('COPILOT_API_KEY missing from .env - all write requests will be refused.');

mkdirSync(dirname(DB_PATH), { recursive: true });
const db = new DatabaseSync(DB_PATH);
db.exec('PRAGMA journal_mode = WAL;');
db.exec('PRAGMA busy_timeout = 5000;');

function migrate() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS exceptions (
      id TEXT PRIMARY KEY,
      key TEXT NOT NULL UNIQUE,
      source TEXT NOT NULL DEFAULT 'inventory',
      category TEXT NOT NULL,
      category_key TEXT NOT NULL,
      severity TEXT NOT NULL,
      title TEXT NOT NULL,
      subtitle TEXT DEFAULT '',
      description TEXT DEFAULT '',
      why TEXT DEFAULT '',
      rule TEXT DEFAULT '',
      doctype TEXT,
      docname TEXT,
      item_code TEXT,
      warehouse TEXT,
      amount REAL,
      currency TEXT,
      action TEXT,
      action_label TEXT,
      value TEXT,
      status TEXT NOT NULL DEFAULT 'new',
      assignee TEXT,
      resolution_note TEXT,
      detected_at TEXT NOT NULL,
      last_seen_at TEXT NOT NULL,
      resolved_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_exc_status ON exceptions (status);
    CREATE INDEX IF NOT EXISTS idx_exc_source ON exceptions (source);
    CREATE TABLE IF NOT EXISTS exception_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      exception_id TEXT NOT NULL,
      ts TEXT NOT NULL,
      actor TEXT NOT NULL,
      action TEXT NOT NULL,
      note TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_exc_events ON exception_events (exception_id, ts DESC);
    CREATE TABLE IF NOT EXISTS audit_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,
      actor TEXT NOT NULL,
      role TEXT,
      action TEXT NOT NULL,
      doctype TEXT,
      docname TEXT,
      detail TEXT,
      result TEXT NOT NULL,
      message TEXT,
      correlation_id TEXT
    );
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT
    );
  `);
  const columns = db.prepare('PRAGMA table_info(exceptions)').all().map((c) => c.name);
  const wanted = {
    source: "TEXT NOT NULL DEFAULT 'inventory'",
    subtitle: "TEXT DEFAULT ''",
    amount: 'REAL',
    currency: 'TEXT',
    action: 'TEXT',
    action_label: 'TEXT',
  };
  for (const [name, type] of Object.entries(wanted)) {
    if (!columns.includes(name)) db.exec(`ALTER TABLE exceptions ADD COLUMN ${name} ${type}`);
  }
  const auditColumns = db.prepare('PRAGMA table_info(audit_log)').all().map((c) => c.name);
  if (!auditColumns.includes('role')) db.exec('ALTER TABLE audit_log ADD COLUMN role TEXT');
  if (!auditColumns.includes('correlation_id')) db.exec('ALTER TABLE audit_log ADD COLUMN correlation_id TEXT');
}
migrate();

const DEFAULT_SETTINGS = {
  company: 'SHRDC',
  default_reorder_level: 10,
  pending_transfer_days: 1,
  unusual_qty_threshold: 50,
  expiring_batch_days: 30,
  delayed_po_days: 0,
  reopen_cooldown_hours: 24,
  trend_days: 14,
  draft_so_days: 3,
  sales_window_days: 30,
  lead_time_days: 14,
  safety_stock_days: 7,
  cover_days: 30,
  exclude_warehouses: 'Goods In Transit',
  currency: 'MYR',
  floor_stores: '',
  floor_wip: '',
  floor_fg: '',
  floor_default_capacity: 1000,
  floor_fg_capacity: 5000,
  floor_max_items: 10,
  floor_max_workstations: 6,
  floor_down_statuses: 'Problem,Maintenance',
};

function getSettings() {
  const row = db.prepare("SELECT value FROM settings WHERE key = 'app'").get();
  if (!row) return { ...DEFAULT_SETTINGS };
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(row.value) };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function sanitizeSettings(patch) {
  const clean = {};
  const errors = [];
  for (const [key, value] of Object.entries(patch || {})) {
    if (!Object.hasOwn(DEFAULT_SETTINGS, key) || value === undefined || value === null) continue;
    if (typeof DEFAULT_SETTINGS[key] === 'number') {
      const n = Number(value);
      if (!Number.isFinite(n) || n < 0 || n > 1_000_000) errors.push(key);
      else clean[key] = n;
    } else {
      const v = String(value).trim();
      if (v.length > 500) errors.push(key);
      else clean[key] = v;
    }
  }
  if (errors.length) throw new ErpError(`Invalid value for: ${errors.join(', ')}.`, 400);
  return clean;
}

function saveSettings(patch) {
  const next = { ...getSettings(), ...sanitizeSettings(patch) };
  db.prepare(
    "INSERT INTO settings (key, value, updated_at) VALUES ('app', ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at"
  ).run(JSON.stringify(next), new Date().toISOString());
  return next;
}

function audit({ actor, role, action, doctype, docname, detail, result, message, correlationId }) {
  db.prepare(
    'INSERT INTO audit_log (ts, actor, role, action, doctype, docname, detail, result, message, correlation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
  ).run(
    new Date().toISOString(),
    actor || 'unknown',
    role || null,
    action,
    doctype || null,
    docname || null,
    detail ? JSON.stringify(detail) : null,
    result,
    message || null,
    correlationId || randomUUID()
  );
}

class ErpError extends Error {
  constructor(message, status = 502, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function erp(path, { method = 'GET', params, body, timeout = 30000 } = {}) {
  const url = new URL(ERP_URL + path);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null) continue;
      url.searchParams.set(k, typeof v === 'string' ? v : JSON.stringify(v));
    }
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(url, {
      method,
      headers: { Authorization: AUTH, Accept: 'application/json', 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const text = await res.text();
    let json;
    try {
      json = text ? JSON.parse(text) : {};
    } catch {
      throw new ErpError('ERPNext returned a non-JSON response.', res.status, text.slice(0, 300));
    }
    if (!res.ok) {
      let message = json?.exception || json?.message || `ERPNext responded ${res.status}`;
      if (json?._server_messages) {
        try {
          const parsed = JSON.parse(json._server_messages);
          message = (Array.isArray(parsed) ? parsed : [parsed])
            .map((m) => {
              try {
                return JSON.parse(m).message;
              } catch {
                return String(m);
              }
            })
            .join(' | ');
        } catch {
          message = json.exception || json.message || message;
        }
      }
      throw new ErpError(String(message).slice(0, 500), res.status, json);
    }
    return json;
  } catch (error) {
    if (error.name === 'AbortError') throw new ErpError('ERPNext did not respond in time.', 504);
    if (error instanceof ErpError) throw error;
    throw new ErpError(`Cannot reach ERPNext at ${ERP_URL}. Is the sandbox running?`, 503, String(error.message));
  } finally {
    clearTimeout(timer);
  }
}

const CHILD_PARENTS = {
  'Stock Entry Detail': 'Stock Entry',
  'Stock Reconciliation Item': 'Stock Reconciliation',
  'Item Supplier': 'Item',
  'Item Reorder': 'Item',
};

async function getList(doctype, { fields, filters = [], limit = 500, orderBy, start = 0 } = {}) {
  const params = { fields, limit_page_length: limit, limit_start: start };
  if (CHILD_PARENTS[doctype]) params.parent = CHILD_PARENTS[doctype];
  if (filters && filters.length) params.filters = filters;
  if (orderBy) params.order_by = orderBy;
  const res = await erp(`/api/resource/${encodeURIComponent(doctype)}`, { params });
  return res.data ?? [];
}

async function fetchDocs(doctype, names, { concurrency = 8, max = 400 } = {}) {
  const limited = names.slice(0, max);
  const out = [];
  for (let i = 0; i < limited.length; i += concurrency) {
    const batch = limited.slice(i, i + concurrency);
    const docs = await Promise.all(
      batch.map((name) =>
        erp('/api/method/frappe.client.get', { params: { doctype, name } })
          .then((r) => r.message)
          .catch(() => null)
      )
    );
    out.push(...docs.filter(Boolean));
  }
  return { docs: out, truncated: names.length > max };
}

const cache = new Map();
function cacheGet(key, ttlMs) {
  const hit = cache.get(key);
  if (!hit) return null;
  if (Date.now() - hit.at > ttlMs) {
    cache.delete(key);
    return null;
  }
  return hit.value;
}
function cacheSet(key, value) {
  cache.set(key, { at: Date.now(), value });
  if (cache.size > 60) cache.delete(cache.keys().next().value);
  return value;
}

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function round(n, p = 2) {
  const f = 10 ** p;
  return Math.round(num(n) * f) / f;
}
function isoToday() {
  return new Date().toISOString().slice(0, 10);
}
function shiftDate(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
function daysBetween(from, to = isoToday()) {
  if (!from) return null;
  const a = Date.parse(String(from).slice(0, 10));
  const b = Date.parse(String(to).slice(0, 10));
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return Math.round((b - a) / 86400000);
}

const DOC_STATUS = { 0: 'Draft', 1: 'Submitted', 2: 'Cancelled' };

const DOC_SLUGS = {
  Item: 'item',
  'Serial No': 'serial-no',
  Batch: 'batch',
  Warehouse: 'warehouse',
  'Stock Entry': 'stock-entry',
  'Purchase Order': 'purchase-order',
  'Purchase Receipt': 'purchase-receipt',
  'Stock Reconciliation': 'stock-reconciliation',
  'Delivery Note': 'delivery-note',
  'Sales Order': 'sales-order',
  'Sales Invoice': 'sales-invoice',
  'Stock Ledger Entry': 'stock-ledger-entry',
  Supplier: 'supplier',
};

function docUrl(doctype, name) {
  const slug = DOC_SLUGS[doctype];
  if (!slug || !name) return null;
  return `${ERP_URL}/app/${slug}/${encodeURIComponent(String(name))}`;
}

async function loadWarehouses() {
  return cacheGet('warehouses', 60000) ||
    cacheSet(
      'warehouses',
      await getList('Warehouse', {
        fields: ['name', 'warehouse_name', 'is_group', 'company'],
        filters: [['is_group', '=', 0], ['disabled', '=', 0]],
        limit: 200,
        orderBy: 'name asc',
      })
    );
}

async function loadItemGroups() {
  return cacheGet('groups', 120000) ||
    cacheSet(
      'groups',
      await getList('Item Group', { fields: ['name'], filters: [['is_group', '=', 0]], limit: 200, orderBy: 'name asc' })
    );
}

async function loadItems() {
  return cacheGet('items', 45000) ||
    cacheSet(
      'items',
      await getList('Item', {
        fields: [
          'name',
          'item_name',
          'item_group',
          'stock_uom',
          'is_stock_item',
          'has_serial_no',
          'has_batch_no',
          'disabled',
          'safety_stock',
          'modified',
          'image',
        ],
        limit: 2000,
        orderBy: 'name asc',
      })
    );
}

async function loadBins() {
  return cacheGet('bins', 30000) ||
    cacheSet(
      'bins',
      await getList('Bin', {
        fields: ['item_code', 'warehouse', 'actual_qty', 'reserved_qty', 'projected_qty', 'stock_value', 'valuation_rate'],
        limit: 5000,
        orderBy: 'item_code asc',
      })
    );
}

async function loadReorderLevels() {
  const cached = cacheGet('reorder', 60000);
  if (cached) return cached;
  try {
    const rows = await getList('Item Reorder', {
      fields: ['parent', 'warehouse', 'warehouse_reorder_level', 'warehouse_reorder_qty'],
      limit: 5000,
    });
    const map = {};
    for (const r of rows) {
      if (!r.parent) continue;
      map[r.parent] = map[r.parent] || {};
      map[r.parent][r.warehouse || ''] = num(r.warehouse_reorder_level);
    }
    return cacheSet('reorder', map);
  } catch {
    return cacheSet('reorder', {});
  }
}

async function loadCompanies() {
  return cacheGet('companies', 300000) ||
    cacheSet('companies', await getList('Company', { fields: ['name', 'abbr', 'default_currency'], limit: 50, orderBy: 'name asc' }));
}

function inventoryRows({ items, bins, reorder, settings, warehouseFilter }) {
  const byItem = new Map();
  for (const item of items) byItem.set(item.name, []);
  for (const bin of bins) {
    if (!byItem.has(bin.item_code)) byItem.set(bin.item_code, []);
    byItem.get(bin.item_code).push(bin);
  }
  const rows = [];
  for (const item of items) {
    const itemBins = byItem.get(item.name) || [];
    const target = itemBins.length ? itemBins : [{ warehouse: '', actual_qty: 0, reserved_qty: 0, stock_value: 0 }];
    for (const bin of target) {
      if (warehouseFilter && bin.warehouse !== warehouseFilter) continue;
      const qty = num(bin.actual_qty);
      const reorderLevel = num((reorder[item.name] || {})[bin.warehouse]);
      const effectiveReorder = reorderLevel > 0 ? reorderLevel : num(settings.default_reorder_level);
      const isStock = num(item.is_stock_item) === 1 && num(item.disabled) !== 1;
      let status = 'normal';
      let statusLabel = 'Normal';
      if (isStock) {
        if (qty <= 0) {
          status = 'out';
          statusLabel = 'Out of stock';
        } else if (effectiveReorder > 0 && qty < effectiveReorder) {
          status = 'low';
          statusLabel = 'Low stock';
        }
      } else if (num(item.disabled) === 1) {
        status = 'inactive';
        statusLabel = 'Inactive';
      } else {
        status = 'service';
        statusLabel = 'Non-stock';
      }
      rows.push({
        code: item.name,
        name: item.item_name,
        group: item.item_group,
        uom: item.stock_uom,
        warehouse: bin.warehouse,
        available: round(qty, 2),
        reorder_level: effectiveReorder,
        reorder_source: reorderLevel > 0 ? 'item' : 'default',
        status,
        status_label: statusLabel,
        stock_value: round(bin.stock_value, 2),
        has_serial: num(item.has_serial_no) === 1,
        has_batch: num(item.has_batch_no) === 1,
        last_updated: item.modified,
        is_stock: isStock,
      });
    }
  }
  return rows;
}

async function buildInventory() {
  const [items, bins, reorder, settings] = await Promise.all([
    loadItems(),
    loadBins(),
    loadReorderLevels(),
    Promise.resolve(getSettings()),
  ]);
  return inventoryRows({ items, bins, reorder, settings });
}

async function loadStockEntries(limit = 300) {
  return getList('Stock Entry', {
    fields: [
      'name',
      'stock_entry_type',
      'posting_date',
      'posting_time',
      'docstatus',
      'from_warehouse',
      'to_warehouse',
      'total_outgoing_value',
      'total_incoming_value',
      'creation',
      'owner',
    ],
    limit,
    orderBy: 'posting_date desc, creation desc',
  });
}

async function loadStockEntryItemNames(names) {
  if (!names.length) return {};
  const map = {};
  for (let i = 0; i < names.length; i += 20) {
    const chunk = names.slice(i, i + 20);
    const rows = await getList('Stock Entry Detail', {
      fields: ['parent', 'item_code', 'item_name', 'qty', 'uom', 's_warehouse', 't_warehouse', 'serial_no', 'batch_no'],
      filters: [['parent', 'in', chunk]],
      limit: 1000,
    });
    for (const r of rows) {
      map[r.parent] = map[r.parent] || [];
      map[r.parent].push(r);
    }
  }
  return map;
}

function buildMovementRows(entries, details, itemsMap) {
  const rows = [];
  for (const e of entries) {
    const lines = details[e.name] || [{}];
    for (const line of lines) {
      rows.push({
        name: e.name,
        date: e.posting_date,
        time: e.posting_time,
        type: e.stock_entry_type,
        status: DOC_STATUS[num(e.docstatus)] || 'Unknown',
        docstatus: num(e.docstatus),
        from_warehouse: e.from_warehouse || line.s_warehouse || '',
        to_warehouse: e.to_warehouse || line.t_warehouse || '',
        item_code: line.item_code || '',
        item_name: line.item_name || (itemsMap[line.item_code] || {}).item_name || '',
        qty: round(line.qty, 2),
        uom: line.uom || '',
        serials: line.serial_no || '',
        batch: line.batch_no || '',
        value: round(e.total_outgoing_value || e.total_incoming_value, 2),
      });
    }
  }
  return rows;
}

async function buildMovements({ limit = 300, search, warehouse, docstatus } = {}) {
  const [entries, items] = await Promise.all([loadStockEntries(limit), loadItems()]);
  const itemsMap = Object.fromEntries(items.map((i) => [i.name, i]));
  const details = await loadStockEntryItemNames(entries.map((e) => e.name));
  let rows = buildMovementRows(entries, details, itemsMap);
  if (search) {
    const q = String(search).toLowerCase();
    rows = rows.filter(
      (r) =>
        r.item_code.toLowerCase().includes(q) ||
        r.item_name.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q)
    );
  }
  if (warehouse) rows = rows.filter((r) => r.from_warehouse === warehouse || r.to_warehouse === warehouse);
  if (docstatus !== undefined && docstatus !== null && docstatus !== '') {
    rows = rows.filter((r) => String(r.docstatus) === String(docstatus));
  }
  return rows;
}

async function buildOverview() {
  const [rows, movements, wh, settings] = await Promise.all([
    buildInventory(),
    buildMovements({ limit: 40 }),
    loadWarehouses(),
    Promise.resolve(getSettings()),
  ]);
  const stockItems = rows.filter((r) => r.is_stock);
  const stockUnits = stockItems.reduce((a, r) => a + Math.max(r.available, 0), 0);
  const stockValue = stockItems.reduce((a, r) => a + num(r.stock_value), 0);
  const lowStock = new Set(stockItems.filter((r) => r.status === 'low').map((r) => r.code)).size;
  const outOfStock = new Set(stockItems.filter((r) => r.status === 'out').map((r) => r.code)).size;
  const active = db.prepare("SELECT severity, COUNT(*) AS n FROM exceptions WHERE status IN ('new','investigating') GROUP BY severity").all();
  const open = active.reduce((a, r) => a + r.n, 0);
  const bySev = Object.fromEntries(active.map((r) => [r.severity, r.n]));
  const bySource = Object.fromEntries(
    db
      .prepare("SELECT source, COUNT(*) AS n FROM exceptions WHERE status IN ('new','investigating') GROUP BY source")
      .all()
      .map((r) => [r.source, r.n])
  );
  const warehouses = wh.map((w) => {
    const wRows = stockItems.filter((r) => r.warehouse === w.name);
    return {
      warehouse: w.name,
      qty: round(wRows.reduce((a, r) => a + Math.max(r.available, 0), 0), 2),
      value: round(wRows.reduce((a, r) => a + num(r.stock_value), 0), 2),
      items: wRows.length,
    };
  });
  return {
    generated_at: new Date().toISOString(),
    company: settings.company,
    kpis: {
      items: new Set(stockItems.map((r) => r.code)).size,
      stock_units: round(stockUnits, 2),
      warehouses: wh.length,
      stock_value: round(stockValue, 2),
      low_stock: lowStock,
      out_of_stock: outOfStock,
      open_exceptions: open,
      critical: bySev.critical || 0,
      high: bySev.high || 0,
      inventory_exceptions: bySource.inventory || 0,
      sales_exceptions: bySource.sales || 0,
    },
    warehouse_stock: warehouses,
    severity_breakdown: ['critical', 'high', 'medium', 'low'].map((s) => ({
      severity: s,
      count: bySev[s] || 0,
    })),
    recent_movements: movements.slice(0, 8),
  };
}

async function getItemDetail(code) {
  const [items, bins, reorder, settings, wh] = await Promise.all([
    loadItems(),
    loadBins(),
    loadReorderLevels(),
    Promise.resolve(getSettings()),
    loadWarehouses(),
  ]);
  const item = items.find((i) => i.name.toLowerCase() === String(code).toLowerCase());
  if (!item) return { found: false };
  const itemBins = bins.filter((b) => b.item_code === item.name);
  const rows = inventoryRows({ items: [item], bins: itemBins, reorder, settings });
  let serials = [];
  if (num(item.has_serial_no) === 1) {
    serials = await getList('Serial No', {
      fields: ['name', 'item_code', 'status', 'warehouse', 'purchase_rate', 'modified'],
      filters: [['item_code', '=', item.name]],
      limit: 500,
      orderBy: 'name asc',
    });
  }
  let batches = [];
  if (num(item.has_batch_no) === 1) {
    batches = await getList('Batch', {
      fields: ['name', 'item', 'expiry_date', 'batch_qty', 'modified'],
      filters: [['item', '=', item.name]],
      limit: 500,
      orderBy: 'name asc',
    });
  }
  const movements = (await buildMovements({ limit: 300 })).filter((m) => m.item_code === item.name).slice(0, 25);
  const exceptions = db
    .prepare("SELECT * FROM exceptions WHERE item_code = ? AND status IN ('new','investigating') ORDER BY detected_at DESC")
    .all(item.name)
    .map(mapExceptionRow);
  return {
    found: true,
    item: {
      code: item.name,
      name: item.item_name,
      group: item.item_group,
      uom: item.stock_uom,
      is_stock: num(item.is_stock_item) === 1,
      has_serial: num(item.has_serial_no) === 1,
      has_batch: num(item.has_batch_no) === 1,
      disabled: num(item.disabled) === 1,
      modified: item.modified,
      image: item.image || null,
      url: docUrl('Item', item.name),
    },
    bins: rows.map((r) => ({
      warehouse: r.warehouse || '(no bin)',
      available: r.available,
      reorder_level: r.reorder_level,
      reorder_source: r.reorder_source,
      status: r.status,
      status_label: r.status_label,
      stock_value: r.stock_value,
    })),
    total_available: round(rows.reduce((a, r) => a + r.available, 0), 2),
    stock_value: round(rows.reduce((a, r) => a + r.stock_value, 0), 2),
    warehouses: wh.map((w) => w.name),
    serials: serials.map((s) => ({
      serial: s.name,
      status: s.status,
      warehouse: s.warehouse || '',
      modified: s.modified,
    })),
    batches: batches.map((b) => ({
      batch: b.name,
      expiry_date: b.expiry_date || '',
      qty: round(b.batch_qty, 2),
    })),
    movements,
    exceptions,
  };
}

async function getSerialDetail(code) {
  const serials = await getList('Serial No', {
    fields: ['name', 'item_code', 'status', 'warehouse', 'purchase_rate', 'modified'],
    filters: [['name', '=', code]],
    limit: 1,
  });
  if (!serials.length) return { found: false, type: 'none' };
  const s = serials[0];
  const itemDetail = await getItemDetail(s.item_code);
  return {
    found: true,
    type: 'serial',
    serial: {
      serial: s.name,
      item_code: s.item_code,
      status: s.status,
      warehouse: s.warehouse || '',
      modified: s.modified,
      purchase_rate: round(s.purchase_rate, 2),
      qr_value: s.name,
    },
    item: itemDetail.item,
    bins: itemDetail.bins,
    total_available: itemDetail.total_available,
    stock_value: itemDetail.stock_value,
    movements: itemDetail.movements.filter((m) => !m.serials || m.serials.includes(s.name)).slice(0, 20),
    exceptions: itemDetail.exceptions,
  };
}

function roleAllowed(role, allowed) {
  return allowed.includes(String(role || '').toLowerCase());
}

const WRITE_ROLES = ['administrator', 'inventory_manager'];

function requireRole(body, action, allowed = WRITE_ROLES) {
  const actor = body.actor || 'unknown';
  const role = String(body.role || '').toLowerCase();
  if (!roleAllowed(role, allowed)) {
    audit({ actor, role, action, doctype: body.doctype, docname: body.name, result: 'denied', message: 'Role not allowed.' });
    throw new ErpError('Your role is not allowed to perform this action.', 403);
  }
}

async function createTransfer(body) {
  const actor = body.actor || 'unknown';
  const role = body.role || 'employee';
  if (!roleAllowed(role, ['administrator', 'inventory_manager'])) {
    audit({ actor, role, action: 'stock_transfer', result: 'denied', message: 'Role not allowed to create transfers.' });
    throw new ErpError('Your role is not allowed to create stock transfers.', 403);
  }
  const itemCode = String(body.item_code || '').trim();
  const source = String(body.source_warehouse || '').trim();
  const target = String(body.target_warehouse || '').trim();
  const qty = num(body.qty);
  const serials = Array.isArray(body.serials)
    ? body.serials.filter(Boolean)
    : String(body.serials || '')
        .split(/[\n,]/)
        .map((x) => x.trim())
        .filter(Boolean);
  if (!itemCode || !source || !target) throw new ErpError('Item, source warehouse and target warehouse are required.', 400);
  if (source === target) throw new ErpError('Source and target warehouse must be different.', 400);
  if (!(qty > 0)) throw new ErpError('Quantity must be greater than zero.', 400);

  const items = await loadItems();
  const item = items.find((i) => i.name === itemCode);
  if (!item) throw new ErpError(`Item ${itemCode} not found in ERPNext.`, 404);
  if (num(item.has_serial_no) === 1 && !serials.length) {
    throw new ErpError(`${itemCode} is serial tracked - select the serial numbers to move.`, 400);
  }
  if (serials.length && serials.length !== qty) {
    throw new ErpError(`Quantity (${qty}) does not match the number of serial numbers selected (${serials.length}).`, 400);
  }
  const bins = await loadBins();
  const bin = bins.find((b) => b.item_code === itemCode && b.warehouse === source);
  const available = num(bin?.actual_qty);
  if (available < qty) {
    throw new ErpError(`Insufficient stock: ${available} ${item.stock_uom} available in ${source}.`, 400);
  }

  const doc = {
    doctype: 'Stock Entry',
    stock_entry_type: 'Material Transfer',
    company: getSettings().company,
    from_warehouse: source,
    to_warehouse: target,
    posting_date: isoToday(),
    items: [
      {
        item_code: itemCode,
        s_warehouse: source,
        t_warehouse: target,
        qty,
        uom: item.stock_uom,
        serial_no: serials.join('\n'),
      },
    ],
  };
  const created = await erp('/api/resource/Stock Entry', { method: 'POST', body: doc });
  const name = created.data?.name;
  let docstatus = 0;
  if (body.submit) {
    await erp('/api/method/frappe.client.submit', { method: 'POST', body: { doc: { doctype: 'Stock Entry', name } } });
    docstatus = 1;
  }
  audit({
    actor,
    role,
    action: body.submit ? 'stock_transfer_submitted' : 'stock_transfer_draft',
    doctype: 'Stock Entry',
    docname: name,
    detail: { itemCode, source, target, qty, serials },
    result: 'ok',
  });
  invalidateStock();
  return {
    ok: true,
    name,
    docstatus,
    status: docstatus === 1 ? 'Submitted' : 'Draft',
    url: docUrl('Stock Entry', name),
    message:
      docstatus === 1
        ? `Stock Entry ${name} submitted - stock moved from ${source} to ${target}.`
        : `Draft Stock Entry ${name} created. Submit it in ERPNext to move stock.`,
  };
}

async function listSerialOptions(itemCode, warehouse) {
  if (!itemCode) return [];
  const filters = [['item_code', '=', itemCode], ['status', '=', 'Active']];
  if (warehouse) filters.push(['warehouse', '=', warehouse]);
  const rows = await getList('Serial No', { fields: ['name', 'warehouse', 'status'], filters, limit: 300, orderBy: 'name asc' });
  return rows.map((r) => ({ value: r.name, label: r.name, warehouse: r.warehouse || '' }));
}

function invalidateStock() {
  for (const key of ['bins', 'items', 'reorder', 'warehouses', 'companies']) cache.delete(key);
}

function upsertException(e, settings) {
  const existing = db.prepare('SELECT * FROM exceptions WHERE key = ?').get(e.key);
  const now = new Date().toISOString();
  if (!existing) {
    const info = db
      .prepare(
        `INSERT INTO exceptions (key, source, category, category_key, severity, title, subtitle, description, why, rule, doctype, docname, item_code, warehouse, amount, currency, action, action_label, value, status, detected_at, last_seen_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)`
      )
      .run(
        e.key,
        e.source || 'inventory',
        e.category,
        e.category_key,
        e.severity,
        e.title,
        e.subtitle || '',
        e.description || '',
        e.why || '',
        e.rule || '',
        e.doctype || null,
        e.docname || null,
        e.item_code || null,
        e.warehouse || null,
        e.amount == null ? null : num(e.amount),
        e.currency || null,
        e.action || null,
        e.action_label || null,
        e.value == null ? null : JSON.stringify(e.value),
        now,
        now
      );
    const id = 'EXC-' + String(info.lastInsertRowid).padStart(4, '0');
    db.prepare('UPDATE exceptions SET id = ? WHERE rowid = ?').run(id, info.lastInsertRowid);
    db.prepare('INSERT INTO exception_events (exception_id, ts, actor, action, note) VALUES (?, ?, ?, ?, ?)').run(
      id,
      now,
      'system',
      'detected',
      'Detected by the unified exception engine.'
    );
    return { created: true, id };
  }
  if (existing.status === 'resolved' || existing.status === 'dismissed') {
    const hours = (Date.now() - Date.parse(existing.resolved_at || existing.last_seen_at)) / 3600000;
    if (hours < num(settings.reopen_cooldown_hours)) return { created: false, skipped: true, id: existing.id };
    db.prepare(
      "UPDATE exceptions SET status = 'new', detected_at = ?, last_seen_at = ?, resolved_at = NULL, resolution_note = NULL, severity = ?, subtitle = ?, description = ?, value = ?, amount = ? WHERE id = ?"
    ).run(
      now,
      now,
      e.severity,
      e.subtitle || '',
      e.description || '',
      e.value == null ? null : JSON.stringify(e.value),
      e.amount == null ? null : num(e.amount),
      existing.id
    );
    db.prepare('INSERT INTO exception_events (exception_id, ts, actor, action, note) VALUES (?, ?, ?, ?, ?)').run(
      existing.id,
      now,
      'system',
      'reopened',
      'Issue detected again after the cooldown period.'
    );
    return { created: false, reopened: true, id: existing.id };
  }
  db.prepare(
    'UPDATE exceptions SET last_seen_at = ?, severity = ?, subtitle = ?, description = ?, value = ?, amount = ? WHERE id = ?'
  ).run(
    now,
    e.severity,
    e.subtitle || '',
    e.description || '',
    e.value == null ? null : JSON.stringify(e.value),
    e.amount == null ? null : num(e.amount),
    existing.id
  );
  return { created: false, id: existing.id };
}

async function detectInventoryFindings(settings) {
  const findings = [];
  const inv = await buildInventory();
  const seenLow = new Set();
  const seenOut = new Set();
  for (const r of inv) {
    if (!r.is_stock) continue;
    if (r.status === 'out' && !seenOut.has(r.code)) {
      seenOut.add(r.code);
      findings.push({
        key: `out_of_stock:Bin:${r.code}:${r.warehouse}`,
        source: 'inventory',
        category: 'Out of Stock',
        category_key: 'out_of_stock',
        severity: 'critical',
        title: `${r.code} has no stock left`,
        subtitle: `${r.name} has ${r.available} ${r.uom} available in ${r.warehouse || 'no warehouse bin'}.`,
        description: `${r.name} has ${r.available} ${r.uom} available in ${r.warehouse || 'no warehouse bin'}.`,
        why: 'The warehouse bin quantity is zero or negative while the item is a stock item.',
        rule: `Bin.actual_qty <= 0 for item ${r.code} in ${r.warehouse}.`,
        doctype: 'Bin',
        docname: `${r.code} / ${r.warehouse}`,
        item_code: r.code,
        warehouse: r.warehouse,
        value: { available: r.available, uom: r.uom },
      });
    } else if (r.status === 'low' && !seenLow.has(r.code)) {
      seenLow.add(r.code);
      const ratio = r.reorder_level ? round((r.available / r.reorder_level) * 100, 0) : null;
      findings.push({
        key: `low_stock:Bin:${r.code}:${r.warehouse}`,
        source: 'inventory',
        category: 'Low Stock',
        category_key: 'low_stock',
        severity: ratio !== null && ratio <= 50 ? 'high' : 'medium',
        title: `${r.code} below reorder level`,
        subtitle: `${r.available} ${r.uom} available vs reorder level ${r.reorder_level} (${ratio}% of the level).`,
        description: `${r.available} ${r.uom} available vs reorder level ${r.reorder_level} (${ratio}% of the level).`,
        why: 'Available stock in the warehouse is below the configured reorder level.',
        rule: `Bin.actual_qty < ${r.reorder_source === 'item' ? 'Item Reorder.warehouse_reorder_level' : 'Settings.default_reorder_level'} (${r.reorder_level}).`,
        doctype: 'Bin',
        docname: `${r.code} / ${r.warehouse}`,
        item_code: r.code,
        warehouse: r.warehouse,
        value: { available: r.available, reorder_level: r.reorder_level, ratio },
      });
    }
  }

  const today = isoToday();
  const pos = await getList('Purchase Order', {
    fields: ['name', 'supplier', 'transaction_date', 'schedule_date', 'status', 'per_received', 'per_billed', 'grand_total', 'currency', 'docstatus'],
    filters: [['docstatus', '=', 1], ['per_received', '<', 100]],
    limit: 500,
    orderBy: 'schedule_date asc',
  });
  for (const po of pos) {
    const overdue = daysBetween(po.schedule_date, today);
    if (overdue === null || overdue <= num(settings.delayed_po_days)) continue;
    const received = num(po.per_received);
    if (['Closed', 'Completed', 'Cancelled'].includes(po.status)) continue;
    const nothingDelivered = received === 0;
    findings.push({
      key: nothingDelivered ? `delayed_delivery:Purchase Order:${po.name}:` : `overdue_po:Purchase Order:${po.name}:`,
      source: 'inventory',
      category: nothingDelivered ? 'Delayed Delivery' : 'Overdue Purchase Order',
      category_key: nothingDelivered ? 'delayed_delivery' : 'overdue_po',
      severity: overdue >= 7 ? 'critical' : overdue >= 3 ? 'high' : 'medium',
      title: nothingDelivered
        ? `${po.name} delivery is ${overdue} day(s) late with nothing received`
        : `${po.name} is ${overdue} day(s) overdue`,
      subtitle: `${po.supplier} - expected ${po.schedule_date} - ${received}% received - ${po.currency} ${round(po.grand_total, 2)}.`,
      description: `${po.supplier} - expected ${po.schedule_date} - ${received}% received - ${po.currency} ${round(po.grand_total, 2)}.`,
      why: nothingDelivered
        ? 'The scheduled delivery date has passed and no quantity has been received against this order.'
        : 'The expected delivery date has passed and the order is only partially received.',
      rule: nothingDelivered
        ? `Purchase Order.docstatus = 1 AND per_received = 0 AND schedule_date < ${today}.`
        : `Purchase Order.docstatus = 1 AND per_received > 0 AND per_received < 100 AND schedule_date < ${today}.`,
      doctype: 'Purchase Order',
      docname: po.name,
      item_code: '',
      warehouse: '',
      amount: num(po.grand_total),
      currency: po.currency || '',
      value: { supplier: po.supplier, days_overdue: overdue, per_received: received, total: round(po.grand_total, 2), currency: po.currency },
    });
  }

  const entries = await loadStockEntries(200);
  const details = await loadStockEntryItemNames(entries.map((e) => e.name));
  for (const e of entries) {
    if (num(e.docstatus) !== 0) continue;
    if (e.stock_entry_type !== 'Material Transfer') continue;
    const age = daysBetween(e.posting_date, today);
    if (age === null || age < num(settings.pending_transfer_days)) continue;
    const lines = details[e.name] || [];
    const itemList = lines.map((l) => `${l.item_code} x${round(l.qty, 2)}`).join(', ') || 'no items';
    findings.push({
      key: `pending_transfer:Stock Entry:${e.name}:`,
      source: 'inventory',
      category: 'Pending Stock Transfer',
      category_key: 'pending_transfer',
      severity: age >= 3 ? 'high' : 'medium',
      title: `${e.name} has been in draft for ${age} day(s)`,
      subtitle: `${e.from_warehouse || '?'} to ${e.to_warehouse || '?'} - ${itemList}.`,
      description: `${e.from_warehouse || '?'} to ${e.to_warehouse || '?'} - ${itemList}.`,
      why: 'A Material Transfer Stock Entry has not been submitted, so the stock never moved.',
      rule: `Stock Entry.docstatus = 0 AND stock_entry_type = 'Material Transfer' AND posting_date older than ${settings.pending_transfer_days} day(s).`,
      doctype: 'Stock Entry',
      docname: e.name,
      item_code: lines[0]?.item_code || '',
      warehouse: e.from_warehouse || '',
      value: { days_pending: age, items: itemList },
    });
  }

  const sle = await getList('Stock Ledger Entry', {
    fields: ['name', 'item_code', 'warehouse', 'actual_qty', 'qty_after_transaction', 'voucher_type', 'voucher_no', 'posting_date', 'stock_value_difference'],
    filters: [['posting_date', '>=', shiftDate(-30)]],
    limit: 2000,
    orderBy: 'posting_date desc, creation desc',
  });
  const items = await loadItems();
  const itemNames = Object.fromEntries(items.map((i) => [i.name, i.item_name]));
  const flagged = new Set();
  for (const row of sle) {
    const qty = num(row.actual_qty);
    const after = num(row.qty_after_transaction);
    const big = Math.abs(qty) >= num(settings.unusual_qty_threshold);
    const negative = after < 0;
    if (!big && !negative) continue;
    const k = `unusual_movement:${row.voucher_no}:${row.item_code}`;
    if (flagged.has(k)) continue;
    flagged.add(k);
    findings.push({
      key: k,
      source: 'inventory',
      category: 'Unusual Stock Movement',
      category_key: 'unusual_movement',
      severity: negative ? 'high' : 'medium',
      title: negative
        ? `${row.item_code} went negative in ${row.warehouse}`
        : `Large movement of ${Math.abs(qty)} ${row.item_code}`,
      subtitle: negative
        ? `${row.voucher_type} ${row.voucher_no} on ${row.posting_date} moved ${qty} and left a negative balance of ${after}.`
        : `${row.voucher_type} ${row.voucher_no} on ${row.posting_date} moved ${qty} (balance after: ${after}).`,
      description: negative
        ? `${row.voucher_type} ${row.voucher_no} on ${row.posting_date} moved ${qty} and left a negative balance of ${after}.`
        : `${row.voucher_type} ${row.voucher_no} on ${row.posting_date} moved ${qty} (balance after: ${after}).`,
      why: negative
        ? 'The stock ledger balance dropped below zero after this transaction.'
        : `The movement exceeds the configured investigation threshold of ${settings.unusual_qty_threshold} units.`,
      rule: negative
        ? 'Stock Ledger Entry.qty_after_transaction < 0.'
        : `abs(Stock Ledger Entry.actual_qty) >= ${settings.unusual_qty_threshold}.`,
      doctype: row.voucher_type || 'Stock Ledger Entry',
      docname: row.voucher_no || row.name,
      item_code: row.item_code,
      warehouse: row.warehouse,
      value: { qty, balance_after: after, posting_date: row.posting_date, item_name: itemNames[row.item_code] || '', negative },
    });
  }

  const batches = await getList('Batch', {
    fields: ['name', 'item', 'expiry_date', 'batch_qty'],
    filters: [['expiry_date', 'is', 'set']],
    limit: 1000,
  });
  for (const b of batches) {
    const left = daysBetween(today, b.expiry_date);
    if (left === null || left > num(settings.expiring_batch_days)) continue;
    findings.push({
      key: `expiring_batch:Batch:${b.name}:`,
      source: 'inventory',
      category: 'Expiring Batch',
      category_key: 'expiring_batch',
      severity: left <= 7 ? 'critical' : left <= 14 ? 'high' : 'medium',
      title: `Batch ${b.name} expires in ${left} day(s)`,
      subtitle: `${b.item} - ${round(b.batch_qty, 2)} units - expires ${b.expiry_date}.`,
      description: `${b.item} - ${round(b.batch_qty, 2)} units - expires ${b.expiry_date}.`,
      why: `The batch expiry date is within the ${settings.expiring_batch_days}-day warning window.`,
      rule: `Batch.expiry_date <= today + ${settings.expiring_batch_days} days.`,
      doctype: 'Batch',
      docname: b.name,
      item_code: b.item,
      warehouse: '',
      value: { days_left: left, qty: round(b.batch_qty, 2) },
    });
  }

  const reconciliations = await getList('Stock Reconciliation', {
    fields: ['name', 'posting_date', 'docstatus'],
    filters: [['docstatus', '=', 1]],
    limit: 200,
    orderBy: 'posting_date desc',
  });
  if (reconciliations.length) {
    const byName = Object.fromEntries(reconciliations.map((r) => [r.name, r]));
    const lines = await getList('Stock Reconciliation Item', {
      fields: ['parent', 'item_code', 'warehouse', 'qty', 'current_qty', 'difference'],
      filters: [['parent', 'in', reconciliations.map((r) => r.name)]],
      limit: 5000,
    });
    for (const line of lines) {
      const recorded = line.current_qty == null ? null : num(line.current_qty);
      const counted = num(line.qty);
      const diff = line.difference == null ? (recorded == null ? 0 : counted - recorded) : num(line.difference);
      if (!diff) continue;
      const parent = byName[line.parent];
      findings.push({
        key: `inventory_discrepancy:Stock Reconciliation:${line.parent}:${line.item_code}:${line.warehouse}`,
        source: 'inventory',
        category: 'Inventory Discrepancy',
        category_key: 'inventory_discrepancy',
        severity: Math.abs(diff) >= 20 ? 'high' : 'medium',
        title: `${line.item_code} counted ${diff > 0 ? 'above' : 'below'} system in ${line.warehouse}`,
        subtitle: `System quantity ${recorded ?? 'unknown'}, counted quantity ${counted}, difference ${diff} (${line.parent}).`,
        description: `System quantity ${recorded ?? 'unknown'}, counted quantity ${counted}, difference ${diff} (${line.parent}).`,
        why: 'The physical count recorded on a submitted Stock Reconciliation differs from the system quantity.',
        rule: 'Stock Reconciliation.docstatus = 1 AND abs(Stock Reconciliation Item.difference) > 0.',
        doctype: 'Stock Reconciliation',
        docname: line.parent,
        item_code: line.item_code,
        warehouse: line.warehouse,
        value: { recorded, counted, difference: diff, posting_date: parent ? parent.posting_date : '' },
      });
    }
  }

  return {
    findings,
    reconciliation_documents: reconciliations.length,
    note:
      reconciliations.length === 0
        ? 'Inventory discrepancy detection is wired to Stock Reconciliation, but this ERPNext site has no submitted Stock Reconciliation documents yet, so that category reports zero rather than inventing counts.'
        : null,
  };
}

async function detectSalesFindings(settings) {
  const findings = [];
  const notes = [];
  const t = isoToday();
  const draftDays = num(settings.draft_so_days);
  const cutoff = shiftDate(-draftDays);
  const companies = await loadCompanies();
  if (!companies.length) return { findings, notes: ['No companies returned - check API user permissions.'] };

  for (const company of companies.map((c) => c.name)) {
    const [draftSos, overdueSis, openDns, openSos] = await Promise.all([
      getList('Sales Order', {
        fields: ['name', 'customer', 'transaction_date', 'delivery_date', 'grand_total', 'currency', 'status'],
        filters: [['docstatus', '=', 0], ['company', '=', company], ['transaction_date', '<', cutoff]],
        limit: 300,
        orderBy: 'transaction_date asc',
      }),
      getList('Sales Invoice', {
        fields: ['name', 'customer', 'posting_date', 'due_date', 'grand_total', 'outstanding_amount', 'currency', 'status'],
        filters: [['docstatus', '=', 1], ['company', '=', company], ['outstanding_amount', '>', 0], ['due_date', '<', t]],
        limit: 300,
        orderBy: 'due_date asc',
      }),
      getList('Delivery Note', {
        fields: ['name', 'customer', 'posting_date', 'grand_total', 'per_billed', 'currency', 'status'],
        filters: [['docstatus', '=', 1], ['company', '=', company], ['per_billed', '<', 100]],
        limit: 300,
        orderBy: 'posting_date asc',
      }),
      getList('Sales Order', {
        fields: ['name', 'customer', 'transaction_date', 'delivery_date', 'grand_total', 'currency'],
        filters: [['docstatus', '=', 1], ['company', '=', company], ['per_delivered', '<', 100]],
        limit: 200,
        orderBy: 'delivery_date asc',
      }),
    ]);

    for (const so of draftSos) {
      const age = daysBetween(so.transaction_date, t);
      const subtitle = `Draft for ${age} days (threshold ${draftDays}). Value ${so.currency || ''} ${round(so.grand_total)}.`;
      findings.push({
        key: `draft_so:Sales Order:${so.name}:`,
        source: 'sales',
        category: 'Draft Sales Order',
        category_key: 'draft_so',
        severity: age >= draftDays * 2 ? 'high' : 'medium',
        title: `${so.name} - ${so.customer || 'No customer'}`,
        subtitle,
        description: subtitle,
        why: `The sales order is still a draft ${age} day(s) after its transaction date, so it cannot be delivered or invoiced.`,
        rule: `Sales Order.docstatus = 0 AND transaction_date older than ${draftDays} day(s) (company ${company}).`,
        doctype: 'Sales Order',
        docname: so.name,
        amount: num(so.grand_total),
        currency: so.currency || 'MYR',
        action: 'submit_doc',
        action_label: 'Submit order',
        value: { company, transaction_date: so.transaction_date, delivery_date: so.delivery_date, status: so.status },
      });
    }

    for (const si of overdueSis) {
      const overdue = daysBetween(si.due_date, t);
      const subtitle = `Outstanding ${si.currency || ''} ${round(si.outstanding_amount)} - ${overdue} days overdue.`;
      findings.push({
        key: `overdue_invoice:Sales Invoice:${si.name}:`,
        source: 'sales',
        category: 'Overdue Sales Invoice',
        category_key: 'overdue_invoice',
        severity: overdue >= 30 || num(si.outstanding_amount) >= 1000 ? 'high' : 'medium',
        title: `${si.name} - ${si.customer || 'No customer'}`,
        subtitle,
        description: subtitle,
        why: `The invoice due date passed ${overdue} day(s) ago and the outstanding amount is still unpaid.`,
        rule: 'Sales Invoice.docstatus = 1 AND outstanding_amount > 0 AND due_date < today.',
        doctype: 'Sales Invoice',
        docname: si.name,
        amount: num(si.outstanding_amount),
        currency: si.currency || 'MYR',
        action: 'remind',
        action_label: 'Log reminder',
        value: { company, due_date: si.due_date, posting_date: si.posting_date, grand_total: num(si.grand_total) },
      });
    }

    for (const dn of openDns) {
      const age = daysBetween(dn.posting_date, t);
      const subtitle = `Delivered ${age} days ago, ${round(dn.per_billed)}% billed. Value ${dn.currency || ''} ${round(dn.grand_total)}.`;
      findings.push({
        key: `uninvoiced_dn:Delivery Note:${dn.name}:`,
        source: 'sales',
        category: 'Uninvoiced Delivery Note',
        category_key: 'uninvoiced_dn',
        severity: age >= 7 ? 'high' : 'low',
        title: `${dn.name} - ${dn.customer || 'No customer'}`,
        subtitle,
        description: subtitle,
        why: 'The delivery note has been submitted but only partially invoiced, so revenue is unbilled.',
        rule: 'Delivery Note.docstatus = 1 AND per_billed < 100.',
        doctype: 'Delivery Note',
        docname: dn.name,
        amount: num(dn.grand_total),
        currency: dn.currency || 'MYR',
        action: 'remind',
        action_label: 'Log reminder',
        value: { company, posting_date: dn.posting_date, per_billed: num(dn.per_billed), status: dn.status },
      });
    }

    if (openSos.length > 0) {
      const { docs: soDocs, truncated } = await fetchDocs('Sales Order', openSos.map((s) => s.name), { max: 60 });
      if (truncated) notes.push(`Stock-risk scan only looked at the 60 earliest open sales orders for ${company}.`);
      const lines = [];
      for (const doc of soDocs) {
        for (const line of doc.items || []) lines.push({ ...line, parent: doc.name });
      }
      const itemCodes = [...new Set(lines.map((l) => l.item_code).filter(Boolean))];
      const bins = itemCodes.length
        ? await getList('Bin', {
            fields: ['item_code', 'warehouse', 'actual_qty', 'reserved_qty'],
            filters: [['item_code', 'in', itemCodes]],
            limit: 2000,
          })
        : [];
      const stockByItem = {};
      for (const b of bins) {
        stockByItem[b.item_code] = stockByItem[b.item_code] || { actual: 0, reserved: 0 };
        stockByItem[b.item_code].actual += num(b.actual_qty);
        stockByItem[b.item_code].reserved += num(b.reserved_qty);
      }
      const shortBySo = {};
      for (const line of lines) {
        const pending = num(line.stock_qty) - num(line.delivered_qty);
        if (pending <= 0) continue;
        const avail = (stockByItem[line.item_code]?.actual || 0) - (stockByItem[line.item_code]?.reserved || 0);
        if (avail >= pending) continue;
        shortBySo[line.parent] = shortBySo[line.parent] || [];
        shortBySo[line.parent].push({
          item_code: line.item_code,
          item_name: line.item_name,
          pending: round(pending),
          available: round(avail),
          shortfall: round(pending - avail),
        });
      }
      for (const so of openSos) {
        const short = shortBySo[so.name];
        if (!short) continue;
        const worst = [...short].sort((a, b) => b.shortfall - a.shortfall)[0];
        const totalShort = short.reduce((sum, l) => sum + l.shortfall, 0);
        const subtitle = `${short.length} line(s) short by ${round(totalShort)} units. Worst: ${worst.item_name || worst.item_code} needs ${worst.pending}, ${worst.available} available.`;
        findings.push({
          key: `stock_risk:Sales Order:${so.name}:`,
          source: 'sales',
          category: 'Order Line at Stock Risk',
          category_key: 'stock_risk',
          severity: worst.available <= 0 ? 'high' : 'medium',
          title: `${so.name} - ${so.customer || 'No customer'}`,
          subtitle,
          description: subtitle,
          why: 'Open sales order lines need more stock than is available after reservations, so delivery will be short.',
          rule: 'Sales Order.docstatus = 1 AND per_delivered < 100 AND pending quantity > available stock.',
          doctype: 'Sales Order',
          docname: so.name,
          amount: num(so.grand_total),
          currency: so.currency || 'MYR',
          action: 'open',
          action_label: 'Open order',
          value: { company, delivery_date: so.delivery_date, lines: short },
        });
      }
    }
  }

  return { findings, notes };
}

async function detectExceptions() {
  const settings = getSettings();
  const inventoryPass = await detectInventoryFindings(settings);
  const salesPass = await detectSalesFindings(settings);
  const findings = [...inventoryPass.findings, ...salesPass.findings];
  let created = 0;
  let reopened = 0;
  let refreshed = 0;
  for (const f of findings) {
    const r = upsertException(f, settings);
    if (r.created) created += 1;
    else if (r.reopened) reopened += 1;
    else refreshed += 1;
  }
  const bySource = {
    inventory: inventoryPass.findings.length,
    sales: salesPass.findings.length,
  };
  audit({
    actor: 'system',
    action: 'exception_scan',
    detail: { findings: findings.length, created, reopened, refreshed, by_source: bySource },
    result: 'ok',
  });
  const notes = [...salesPass.notes];
  if (inventoryPass.note) notes.push(inventoryPass.note);
  return {
    ok: true,
    scanned_categories: 12,
    reconciliation_documents: inventoryPass.reconciliation_documents,
    findings: findings.length,
    created,
    reopened,
    refreshed,
    by_source: bySource,
    skipped:
      inventoryPass.reconciliation_documents === 0
        ? ['inventory_discrepancy: no submitted Stock Reconciliation documents exist in ERPNext']
        : [],
    note: notes.length ? notes.join(' ') : null,
  };
}

function mapExceptionRow(row) {
  let value = null;
  try {
    value = row.value ? JSON.parse(row.value) : null;
  } catch {
    value = null;
  }
  const detected = Date.parse(row.detected_at);
  return {
    id: row.id,
    key: row.key,
    source: row.source || 'inventory',
    category: row.category,
    category_key: row.category_key,
    severity: row.severity,
    title: row.title,
    subtitle: row.subtitle || row.description || '',
    description: row.description,
    why: row.why,
    rule: row.rule,
    doctype: row.doctype,
    docname: row.docname,
    item_code: row.item_code,
    warehouse: row.warehouse,
    amount: row.amount == null ? null : round(row.amount, 2),
    currency: row.currency || '',
    action: row.action || null,
    action_label: row.action_label || null,
    value,
    status: row.status,
    assignee: row.assignee || '',
    resolution_note: row.resolution_note || '',
    detected_at: row.detected_at,
    last_seen_at: row.last_seen_at,
    resolved_at: row.resolved_at,
    age_hours: round((Date.now() - detected) / 3600000, 1),
    age_days: round((Date.now() - detected) / 86400000, 1),
    doc_url: docUrl(row.doctype, row.docname),
  };
}

function listExceptions({ status, severity, category, source }) {
  let sql = 'SELECT * FROM exceptions WHERE 1 = 1';
  const params = [];
  if (status) {
    sql += ' AND status = ?';
    params.push(status);
  }
  if (severity) {
    sql += ' AND severity = ?';
    params.push(severity);
  }
  if (category) {
    sql += ' AND category_key = ?';
    params.push(category);
  }
  if (source) {
    sql += ' AND source = ?';
    params.push(source);
  }
  sql += " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, detected_at DESC";
  const rows = db.prepare(sql).all(...params).map(mapExceptionRow);
  const counts = db.prepare('SELECT status, COUNT(*) AS n FROM exceptions GROUP BY status').all();
  const sev = db
    .prepare("SELECT severity, COUNT(*) AS n FROM exceptions WHERE status IN ('new','investigating') GROUP BY severity")
    .all();
  const byStatus = Object.fromEntries(counts.map((c) => [c.status, c.n]));
  const bySev = Object.fromEntries(sev.map((c) => [c.severity, c.n]));
  const categories = db.prepare('SELECT category, category_key, source, COUNT(*) AS n FROM exceptions GROUP BY category_key ORDER BY n DESC').all();
  return {
    generated_at: new Date().toISOString(),
    rows,
    summary: {
      total: rows.length,
      active: (byStatus.new || 0) + (byStatus.investigating || 0),
      new: byStatus.new || 0,
      investigating: byStatus.investigating || 0,
      resolved: byStatus.resolved || 0,
      dismissed: byStatus.dismissed || 0,
      critical: bySev.critical || 0,
      high: bySev.high || 0,
      medium: bySev.medium || 0,
      low: bySev.low || 0,
    },
    categories,
    category_options: [
      { label: 'All categories', value: '' },
      ...categories.map((c) => ({ label: c.category, value: c.category_key })),
    ],
    status_options: [
      { label: 'All statuses', value: '' },
      { label: 'New', value: 'new' },
      { label: 'Investigating', value: 'investigating' },
      { label: 'Resolved', value: 'resolved' },
      { label: 'Dismissed', value: 'dismissed' },
    ],
    severity_options: [
      { label: 'All severities', value: '' },
      { label: 'Critical', value: 'critical' },
      { label: 'High', value: 'high' },
      { label: 'Medium', value: 'medium' },
      { label: 'Low', value: 'low' },
    ],
    source_options: [
      { label: 'All sources', value: '' },
      { label: 'Inventory', value: 'inventory' },
      { label: 'Sales & finance', value: 'sales' },
    ],
  };
}

function getException(id) {
  const row = db.prepare('SELECT * FROM exceptions WHERE id = ?').get(id);
  if (!row) return { found: false };
  const events = db
    .prepare('SELECT ts, actor, action, note FROM exception_events WHERE exception_id = ? ORDER BY id DESC')
    .all(id);
  return { found: true, exception: mapExceptionRow(row), events };
}

function exceptionAction(body) {
  const actor = body.actor || 'unknown';
  const role = String(body.role || 'employee').toLowerCase();
  const id = body.id;
  const action = String(body.action || '');
  const allowed = ['administrator', 'inventory_manager'];
  if (!roleAllowed(role, allowed)) {
    audit({ actor, role, action: `exception_${action}`, result: 'denied', message: 'Role not allowed.' });
    throw new ErpError('Your role is not allowed to change exception status.', 403);
  }
  const row = db.prepare('SELECT * FROM exceptions WHERE id = ?').get(id);
  if (!row) throw new ErpError(`Exception ${id} not found.`, 404);
  const now = new Date().toISOString();
  const note = body.note || '';
  if (action === 'investigate') {
    db.prepare("UPDATE exceptions SET status = 'investigating', assignee = COALESCE(?, assignee) WHERE id = ?").run(body.assignee || null, id);
  } else if (action === 'assign') {
    if (!body.assignee) throw new ErpError('An assignee is required.', 400);
    db.prepare('UPDATE exceptions SET assignee = ? WHERE id = ?').run(body.assignee, id);
  } else if (action === 'resolve') {
    db.prepare("UPDATE exceptions SET status = 'resolved', resolution_note = ?, resolved_at = ? WHERE id = ?").run(note, now, id);
  } else if (action === 'dismiss') {
    db.prepare("UPDATE exceptions SET status = 'dismissed', resolution_note = ?, resolved_at = ? WHERE id = ?").run(note, now, id);
  } else if (action === 'reopen') {
    db.prepare("UPDATE exceptions SET status = 'new', resolved_at = NULL, resolution_note = NULL WHERE id = ?").run(id);
  } else {
    throw new ErpError(`Unknown action ${action}.`, 400);
  }
  db.prepare('INSERT INTO exception_events (exception_id, ts, actor, action, note) VALUES (?, ?, ?, ?, ?)').run(id, now, actor, action, note || null);
  audit({ actor, role, action: `exception_${action}`, doctype: 'Exception', docname: id, detail: { note }, result: 'ok' });
  return { ok: true, id, status: db.prepare('SELECT status FROM exceptions WHERE id = ?').get(id).status };
}

async function buildReports({ days = 30, from, to, warehouse, group } = {}) {
  const settings = getSettings();
  const windowDays = Math.abs(num(days) || 30);
  const validDate = (d) => (typeof d === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : null);
  const since = validDate(from) || shiftDate(-windowDays);
  const until = validDate(to) || isoToday();
  const [bins, entries, items, poRows] = await Promise.all([
    loadBins(),
    getList('Stock Entry', {
      fields: ['name', 'posting_date', 'stock_entry_type', 'docstatus', 'from_warehouse', 'to_warehouse'],
      filters: [['posting_date', '>=', since], ['posting_date', '<=', until]],
      limit: 2000,
      orderBy: 'posting_date asc',
    }),
    loadItems(),
    getList('Purchase Order', {
      fields: ['name', 'supplier', 'schedule_date', 'per_received', 'status', 'docstatus'],
      filters: [['docstatus', '=', 1], ['per_received', '<', 100]],
      limit: 500,
    }),
  ]);
  const itemNames = Object.fromEntries(items.map((i) => [i.name, i.item_name]));
  const itemGroups = Object.fromEntries(items.map((i) => [i.name, i.item_group]));
  const scopedItems = group ? new Set(items.filter((i) => i.item_group === group).map((i) => i.name)) : null;
  const byWarehouse = {};
  for (const b of bins) {
    if (warehouse && b.warehouse !== warehouse) continue;
    if (scopedItems && !scopedItems.has(b.item_code)) continue;
    byWarehouse[b.warehouse] = byWarehouse[b.warehouse] || { warehouse: b.warehouse, qty: 0, value: 0 };
    byWarehouse[b.warehouse].qty += Math.max(num(b.actual_qty), 0);
    byWarehouse[b.warehouse].value += num(b.stock_value);
  }
  const inScopeWarehouse = (e) => !warehouse || e.from_warehouse === warehouse || e.to_warehouse === warehouse;
  const perDay = {};
  for (const e of entries) {
    if (num(e.docstatus) === 2) continue;
    if (!inScopeWarehouse(e)) continue;
    perDay[e.posting_date] = (perDay[e.posting_date] || 0) + 1;
  }
  const dayseries = Object.entries(perDay)
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([date, count]) => ({ date, count }));

  const sle = await getList('Stock Ledger Entry', {
    fields: ['item_code', 'warehouse', 'actual_qty', 'voucher_type'],
    filters: [['posting_date', '>=', since], ['posting_date', '<=', until]],
    limit: 5000,
  });
  const perItem = {};
  for (const r of sle) {
    if (warehouse && r.warehouse !== warehouse) continue;
    if (scopedItems && !scopedItems.has(r.item_code)) continue;
    perItem[r.item_code] = (perItem[r.item_code] || 0) + Math.abs(num(r.actual_qty));
  }
  const topItems = Object.entries(perItem)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([code, qty]) => ({ code, name: itemNames[code] || code, group: itemGroups[code] || '', qty: round(qty, 2) }));

  const overdueBySupplier = {};
  for (const po of poRows) {
    const overdue = daysBetween(po.schedule_date);
    if (overdue === null || overdue <= num(settings.delayed_po_days)) continue;
    if (['Closed', 'Completed', 'Cancelled'].includes(po.status)) continue;
    overdueBySupplier[po.supplier] = overdueBySupplier[po.supplier] || { supplier: po.supplier, orders: 0, max_days: 0 };
    overdueBySupplier[po.supplier].orders += 1;
    overdueBySupplier[po.supplier].max_days = Math.max(overdueBySupplier[po.supplier].max_days, overdue);
  }

  const excByCategory = db.prepare('SELECT category, category_key, COUNT(*) AS n FROM exceptions GROUP BY category_key ORDER BY n DESC').all();
  const excByDay = db
    .prepare('SELECT substr(detected_at, 1, 10) AS day, COUNT(*) AS n FROM exceptions GROUP BY day ORDER BY day')
    .all();
  const resolved = db.prepare('SELECT detected_at, resolved_at FROM exceptions WHERE resolved_at IS NOT NULL').all();
  const avgHours = resolved.length
    ? round(resolved.reduce((a, r) => a + (Date.parse(r.resolved_at) - Date.parse(r.detected_at)) / 3600000, 0) / resolved.length, 1)
    : null;
  return {
    generated_at: new Date().toISOString(),
    window_days: windowDays,
    window: { from: since, to: until },
    filters: { warehouse: warehouse || null, group: group || null },
    stock_by_warehouse: Object.values(byWarehouse)
      .map((w) => ({ warehouse: w.warehouse, qty: round(w.qty, 2), value: round(w.value, 2) }))
      .sort((a, b) => b.value - a.value),
    movement_by_day: dayseries,
    top_moved_items: topItems,
    overdue_by_supplier: Object.values(overdueBySupplier).sort((a, b) => b.orders - a.orders),
    exceptions_by_category: excByCategory,
    exceptions_by_day: excByDay,
    avg_resolution_hours: avgHours,
    resolved_count: resolved.length,
    total_units: round(Object.values(byWarehouse).reduce((a, w) => a + w.qty, 0), 2),
    total_value: round(Object.values(byWarehouse).reduce((a, w) => a + w.value, 0), 2),
    warehouse_options: [
      { label: 'All warehouses', value: '' },
      ...[...new Set(bins.map((b) => b.warehouse))].sort().map((w) => ({ label: w, value: w })),
    ],
    group_options: [
      { label: 'All item groups', value: '' },
      ...[...new Set(items.map((i) => i.item_group))].sort().map((g) => ({ label: g, value: g })),
    ],
    chart_data: {
      warehouse_names: Object.values(byWarehouse)
        .sort((a, b) => b.value - a.value)
        .map((w) => w.warehouse),
      warehouse_values: Object.values(byWarehouse)
        .sort((a, b) => b.value - a.value)
        .map((w) => round(w.value, 2)),
      warehouse_qty: Object.values(byWarehouse)
        .sort((a, b) => b.value - a.value)
        .map((w) => round(w.qty, 2)),
      movement_dates: dayseries.map((d) => d.date),
      movement_counts: dayseries.map((d) => d.count),
      top_item_names: topItems.map((i) => `${i.code} - ${i.name}`),
      top_item_qty: topItems.map((i) => i.qty),
      overdue_suppliers: Object.values(overdueBySupplier)
        .sort((a, b) => b.orders - a.orders)
        .map((s) => s.supplier),
      overdue_orders: Object.values(overdueBySupplier)
        .sort((a, b) => b.orders - a.orders)
        .map((s) => s.orders),
      exception_categories: excByCategory.map((c) => c.category),
      exception_counts: excByCategory.map((c) => c.n),
      exception_days: excByDay.map((d) => d.day),
      exception_day_counts: excByDay.map((d) => d.n),
    },
  };
}

async function buildPurchasing(query) {
  const settings = getSettings();
  const company = query.company || settings.company;
  const windowDays = Number(query.window_days || settings.sales_window_days);
  const leadTime = Number(query.lead_time_days ?? settings.lead_time_days);
  const safetyDays = Number(query.safety_stock_days ?? settings.safety_stock_days);
  const coverDays = Number(query.cover_days ?? settings.cover_days);
  const exclude = String(query.exclude_warehouses ?? settings.exclude_warehouses ?? '')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  const start = shiftDate(-windowDays);
  const notes = [];

  const [items, bins, siNames] = await Promise.all([
    getList('Item', {
      fields: ['name', 'item_name', 'stock_uom', 'is_stock_item', 'safety_stock', 'lead_time_days', 'min_order_qty', 'disabled'],
      filters: [['is_stock_item', '=', 1], ['disabled', '=', 0]],
      limit: 2000,
    }),
    getList('Bin', { fields: ['item_code', 'warehouse', 'actual_qty', 'reserved_qty'], limit: 5000 }),
    getList('Sales Invoice', {
      fields: ['name'],
      filters: [['docstatus', '=', 1], ['company', '=', company], ['posting_date', '>=', start]],
      limit: 2000,
    }),
  ]);

  const itemCodes = new Set(items.map((i) => i.name));
  const supplierByItem = {};

  let soldByItem = {};
  if (siNames.length > 0) {
    const { docs: siDocs, truncated } = await fetchDocs('Sales Invoice', siNames.map((s) => s.name), { max: 400 });
    if (truncated) notes.push('Sales history scan used the 400 most recent invoices in the window.');
    for (const doc of siDocs) {
      for (const row of doc.items || []) {
        if (!itemCodes.has(row.item_code)) continue;
        soldByItem[row.item_code] = (soldByItem[row.item_code] || 0) + num(row.stock_qty || row.qty);
      }
    }
  }

  const openPos = await getList('Purchase Order', {
    fields: ['name'],
    filters: [['docstatus', '=', 1], ['company', '=', company], ['status', 'not in', ['Closed', 'Completed', 'Cancelled']]],
    limit: 1000,
  });
  const incomingByItem = {};
  if (openPos.length > 0) {
    const { docs: poDocs } = await fetchDocs('Purchase Order', openPos.map((p) => p.name), { max: 60 });
    for (const doc of poDocs) {
      for (const row of doc.items || []) {
        if (!itemCodes.has(row.item_code)) continue;
        const open = Math.max(0, num(row.stock_qty) - num(row.received_qty));
        incomingByItem[row.item_code] = (incomingByItem[row.item_code] || 0) + open;
      }
    }
  }

  const stockByItem = {};
  for (const bin of bins) {
    if (!itemCodes.has(bin.item_code)) continue;
    const wh = String(bin.warehouse || '').toLowerCase();
    if (exclude.some((frag) => wh.includes(frag))) continue;
    stockByItem[bin.item_code] = stockByItem[bin.item_code] || { actual: 0, reserved: 0, warehouses: [] };
    stockByItem[bin.item_code].actual += num(bin.actual_qty);
    stockByItem[bin.item_code].reserved += num(bin.reserved_qty);
    stockByItem[bin.item_code].warehouses.push(bin.warehouse);
  }

  const lines = [];
  for (const item of items) {
    const sold = soldByItem[item.name] || 0;
    const avgDaily = sold / windowDays;
    const stock = stockByItem[item.name]?.actual || 0;
    const reserved = stockByItem[item.name]?.reserved || 0;
    const incoming = incomingByItem[item.name] || 0;
    const available = stock - reserved;
    const itemSafety = num(item.safety_stock);
    const safety = Math.max(itemSafety, safetyDays * avgDaily);
    const reorderPoint = avgDaily * leadTime + safety;
    const daysLeft = avgDaily > 0 ? available / avgDaily : null;
    const minOrder = num(item.min_order_qty);

    if (avgDaily <= 0 && available >= safety) continue;

    let suggested = avgDaily * (leadTime + coverDays) + safety - available - incoming;
    if (suggested <= 0) continue;
    if (minOrder > 0) suggested = Math.max(suggested, minOrder);
    suggested = Math.ceil(suggested);

    const urgency = daysLeft === null ? 'critical' : daysLeft <= leadTime ? 'critical' : daysLeft <= leadTime + 14 ? 'soon' : 'ok';

    lines.push({
      item_code: item.name,
      item_name: item.item_name,
      uom: item.stock_uom,
      supplier: supplierByItem[item.name] || '',
      has_supplier: Boolean(supplierByItem[item.name]),
      sold_qty: round(sold, 2),
      avg_daily: round(avgDaily, 3),
      stock: round(stock, 2),
      reserved: round(reserved, 2),
      available: round(available, 2),
      incoming: round(incoming, 2),
      safety: round(safety, 2),
      reorder_point: round(reorderPoint, 2),
      days_left: daysLeft === null ? null : round(daysLeft, 1),
      lead_time_days: leadTime,
      cover_days: coverDays,
      window_days: windowDays,
      suggested_qty: suggested,
      urgency,
      warehouses: stockByItem[item.name]?.warehouses || [],
      warehouse: (stockByItem[item.name]?.warehouses || [])[0] || '',
      formula: {
        avg_daily: `${round(sold, 2)} sold / ${windowDays} days = ${round(avgDaily, 3)} per day`,
        safety: `max(item safety ${itemSafety}, ${safetyDays} days x ${round(avgDaily, 3)}/day) = ${round(safety, 2)}`,
        reorder_point: `${round(avgDaily, 3)}/day x ${leadTime} lead days + ${round(safety, 2)} safety = ${round(reorderPoint, 2)}`,
        days_left: daysLeft === null ? 'no sales in window' : `${round(available, 2)} available / ${round(avgDaily, 3)} per day = ${round(daysLeft, 1)} days`,
        suggested: `ceil(${round(avgDaily, 3)}/day x (${leadTime} lead + ${coverDays} cover) + ${round(safety, 2)} safety - ${round(available, 2)} available - ${round(incoming, 2)} incoming) = ${suggested}`,
      },
    });
  }

  const urgencyRank = { critical: 0, soon: 1, ok: 2 };

  const supplierCache = new Map();
  for (const line of lines) {
    if (supplierCache.has(line.item_code)) {
      const cached = supplierCache.get(line.item_code);
      line.supplier = cached || 'No default supplier';
      line.has_supplier = Boolean(cached);
      continue;
    }
    let supplier = '';
    try {
      const doc = await erp('/api/method/frappe.client.get', { params: { doctype: 'Item', name: line.item_code } });
      const links = doc.message?.supplier_items || [];
      supplier = links.find((l) => l.supplier)?.supplier || '';
    } catch {
      supplier = '';
    }
    supplierCache.set(line.item_code, supplier);
    line.supplier = supplier || 'No default supplier';
    line.has_supplier = Boolean(supplier);
  }

  lines.sort((a, b) => {
    const u = urgencyRank[a.urgency] - urgencyRank[b.urgency];
    if (u !== 0) return u;
    const da = a.days_left === null ? -1 : a.days_left;
    const dbv = b.days_left === null ? -1 : b.days_left;
    return da - dbv;
  });

  const groupMap = new Map();
  for (const line of lines) {
    if (!groupMap.has(line.supplier)) {
      groupMap.set(line.supplier, {
        supplier: line.supplier,
        has_supplier: line.has_supplier,
        priority: line.urgency,
        lines: [],
      });
    }
    const group = groupMap.get(line.supplier);
    group.lines.push(line);
    if (urgencyRank[line.urgency] < urgencyRank[group.priority]) group.priority = line.urgency;
  }
  const groups = [...groupMap.values()]
    .map((g) => ({
      ...g,
      line_count: g.lines.length,
      total_suggested: g.lines.reduce((a, l) => a + l.suggested_qty, 0),
    }))
    .sort((a, b) => urgencyRank[a.priority] - urgencyRank[b.priority] || b.lines.length - a.lines.length);

  if (lines.length === 0) {
    notes.push('No reorder suggestions. This company has too little sales history in the window, or stock already covers demand.');
  }
  const noSupplier = groups.find((g) => !g.has_supplier);
  if (noSupplier) notes.push(`${noSupplier.lines.length} item(s) have no default supplier and cannot be ordered automatically.`);

  return {
    generated_at: new Date().toISOString(),
    company,
    window_days: windowDays,
    lead_time_days: leadTime,
    safety_stock_days: safetyDays,
    cover_days: coverDays,
    counts: {
      critical: lines.filter((l) => l.urgency === 'critical').length,
      soon: lines.filter((l) => l.urgency === 'soon').length,
      ok: lines.filter((l) => l.urgency === 'ok').length,
      total: lines.length,
      suppliers: groups.length,
    },
    lines,
    groups,
    notes,
  };
}

async function buildSuppliers(query) {
  const settings = getSettings();
  const company = query.company || settings.company;
  const [suppliers, links, pos] = await Promise.all([
    getList('Supplier', {
      fields: ['name', 'supplier_name', 'supplier_group', 'disabled'],
      filters: [['disabled', '=', 0]],
      limit: 1000,
    }),
    getList('Item Supplier', { fields: ['supplier', 'parent'], limit: 5000 }),
    getList('Purchase Order', {
      fields: ['name', 'supplier', 'transaction_date', 'grand_total', 'currency', 'status', 'docstatus'],
      filters: [['company', '=', company], ['docstatus', '=', 1]],
      limit: 1000,
      orderBy: 'transaction_date desc',
    }),
  ]);

  const itemCountBySupplier = {};
  for (const l of links) itemCountBySupplier[l.supplier] = (itemCountBySupplier[l.supplier] || 0) + 1;

  const poBySupplier = {};
  for (const p of pos) {
    const s = poBySupplier[p.supplier] || (poBySupplier[p.supplier] = { open: 0, total: 0, last: null, currency: null });
    if (!['Closed', 'Completed', 'Cancelled'].includes(p.status)) s.open += 1;
    s.total += num(p.grand_total);
    if (!s.last || String(p.transaction_date) > String(s.last)) s.last = p.transaction_date;
    if (p.currency) s.currency = p.currency;
  }

  const rows = suppliers
    .map((s) => {
      const p = poBySupplier[s.name] || {};
      return {
        name: s.name,
        supplier_name: s.supplier_name || s.name,
        group: s.supplier_group,
        item_count: itemCountBySupplier[s.name] || 0,
        open_po_count: p.open || 0,
        last_purchase_date: p.last || null,
        total_value: round(p.total || 0),
        currency: p.currency || settings.currency || 'MYR',
      };
    })
    .sort((a, b) => b.total_value - a.total_value);

  return {
    generated_at: new Date().toISOString(),
    company,
    rows,
    counts: { total: rows.length, with_po: rows.filter((r) => r.open_po_count > 0 || r.total_value > 0).length },
  };
}

async function buildPurchaseOrders(query) {
  const settings = getSettings();
  const company = query.company || settings.company;
  const pos = await getList('Purchase Order', {
    fields: [
      'name',
      'supplier',
      'supplier_name',
      'transaction_date',
      'schedule_date',
      'grand_total',
      'currency',
      'status',
      'docstatus',
      'per_received',
      'per_billed',
    ],
    filters: [['company', '=', company], ['docstatus', 'in', [0, 1]]],
    limit: 500,
    orderBy: 'transaction_date desc',
  });

  const { docs } = await fetchDocs('Purchase Order', pos.map((p) => p.name), { max: 200 });
  const byName = {};
  for (const d of docs) {
    let o = 0;
    let r = 0;
    const items = [];
    for (const it of d.items || []) {
      const qty = num(it.qty);
      const recv = num(it.received_qty);
      o += qty;
      r += recv;
      items.push({
        item_code: it.item_code,
        item_name: it.item_name,
        qty: round(qty),
        received_qty: round(recv),
        outstanding: round(Math.max(0, qty - recv)),
        uom: it.uom,
        warehouse: it.warehouse,
        rate: round(num(it.rate)),
        schedule_date: it.schedule_date || null,
      });
    }
    byName[d.name] = {
      ordered_qty: round(o),
      received_qty: round(r),
      outstanding_qty: round(Math.max(0, o - r)),
      item_count: items.length,
      items,
    };
  }

  const rows = pos.map((p) => ({
    name: p.name,
    supplier: p.supplier,
    supplier_name: p.supplier_name || p.supplier,
    transaction_date: p.transaction_date,
    schedule_date: p.schedule_date,
    grand_total: round(num(p.grand_total)),
    currency: p.currency || settings.currency || 'MYR',
    status: p.status,
    docstatus: p.docstatus,
    per_received: round(num(p.per_received)),
    per_billed: round(num(p.per_billed)),
    ...(byName[p.name] || {
      ordered_qty: 0,
      received_qty: 0,
      outstanding_qty: 0,
      item_count: 0,
      items: [],
    }),
  }));

  const counts = {
    total: rows.length,
    draft: rows.filter((r) => r.docstatus === 0).length,
    open: rows.filter((r) => r.docstatus === 1 && !['Closed', 'Completed', 'Cancelled'].includes(r.status)).length,
  };

  return { generated_at: new Date().toISOString(), company, counts, rows };
}

async function buildStockLedger(query) {
  const item = query.item_code;
  if (!item) throw new ErpError('item_code is required.', 400);
  const rows = await getList('Stock Ledger Entry', {
    fields: ['posting_date', 'posting_time', 'voucher_type', 'voucher_no', 'actual_qty', 'qty_after_transaction', 'warehouse'],
    filters: [['item_code', '=', item]],
    limit: 100,
    orderBy: 'posting_date desc, posting_time desc, creation desc',
  });
  return { generated_at: new Date().toISOString(), item_code: item, rows };
}

function buildPoDoc({ company, supplier, lines, settings }) {
  const schedule = shiftDate(settings.lead_time_days || 0);
  return {
    doctype: 'Purchase Order',
    company,
    supplier,
    transaction_date: isoToday(),
    schedule_date: schedule,
    currency: settings.currency || 'MYR',
    conversion_rate: 1,
    buying_price_list: settings.buying_price_list || 'Standard Buying',
    items: lines.map((line) => ({
      item_code: line.item_code,
      qty: line.qty,
      rate: num(line.rate),
      warehouse: line.warehouse || settings.default_warehouse || undefined,
      schedule_date: schedule,
    })),
  };
}

async function createPurchaseOrders(body) {
  const settings = getSettings();
  const company = body.company || settings.company;
  const groups = Array.isArray(body.groups) ? body.groups : [];
  const actor = body.actor || 'unknown';
  const role = body.role || '';
  if (!roleAllowed(role, WRITE_ROLES)) {
    audit({ actor, role, action: 'create_purchase_order', result: 'denied', message: 'Role not allowed to create purchase orders.' });
    throw new ErpError('Your role is not allowed to create purchase orders.', 403);
  }
  if (groups.length === 0) throw new ErpError('No supplier groups were selected.', 400);
  const created = [];
  for (const group of groups) {
    const lines = (group.lines || [])
      .map((l) => ({ ...l, qty: num(l.qty ?? l.suggested_qty) }))
      .filter((l) => l.qty > 0);
    if (lines.length === 0) continue;
    if (!group.supplier || group.supplier === 'No default supplier') {
      created.push({
        supplier: group.supplier,
        ok: false,
        error: 'No default supplier for these items. Add an Item Supplier row in ERPNext first.',
      });
      continue;
    }
    const correlation = randomUUID();
    const doc = buildPoDoc({ company, supplier: group.supplier, lines, settings });
    try {
      const res = await erp('/api/method/frappe.client.insert', { method: 'POST', body: { doc } });
      const name = res.message?.name;
      const total = num(res.message?.grand_total);
      created.push({ supplier: group.supplier, ok: true, name, total, items: lines.length, correlation, url: docUrl('Purchase Order', name) });
      audit({
        actor,
        role,
        action: 'create_purchase_order',
        doctype: 'Purchase Order',
        docname: name,
        detail: { supplier: group.supplier, lines, total },
        result: 'ok',
        message: `Draft PO created for ${group.supplier}`,
        correlationId: correlation,
      });
    } catch (error) {
      const msg = error.message || 'ERPNext rejected the Purchase Order.';
      created.push({ supplier: group.supplier, ok: false, error: msg, correlation });
      audit({
        actor,
        role,
        action: 'create_purchase_order',
        doctype: 'Purchase Order',
        docname: null,
        detail: { supplier: group.supplier, lines, doc },
        result: 'failed',
        message: msg,
        correlationId: correlation,
      });
    }
  }
  return { company, created };
}

async function submitDocument(body) {
  const { doctype, name, actor, role } = body;
  if (!doctype || !name) throw new ErpError('doctype and name are required.', 400);
  requireRole(body, 'submit_document');
  const correlation = randomUUID();
  try {
    const got = await erp('/api/method/frappe.client.get', { params: { doctype, name } });
    const doc = got.message;
    if (!doc) throw new ErpError(`Document ${name} was not returned by ERPNext.`, 404);
    if (doc.docstatus !== 0) throw new ErpError(`${name} is not a draft (docstatus ${doc.docstatus}).`, 409);
    const res = await erp('/api/method/frappe.client.submit', { method: 'POST', body: { doc } });
    const submitted = res.message?.name || name;
    audit({
      actor,
      role,
      action: 'submit_document',
      doctype,
      docname: submitted,
      detail: { previous_docstatus: 0 },
      result: 'ok',
      message: `${doctype} ${submitted} submitted`,
      correlationId: correlation,
    });
    return { ok: true, name: submitted, correlation };
  } catch (error) {
    audit({
      actor,
      role,
      action: 'submit_document',
      doctype,
      docname: name,
      detail: null,
      result: 'failed',
      message: error.message,
      correlationId: correlation,
    });
    throw error;
  }
}

async function cancelDocument(body) {
  const { doctype, name, actor, role } = body;
  if (!doctype || !name) throw new ErpError('doctype and name are required.', 400);
  requireRole(body, 'cancel_document', ['administrator']);
  const correlation = randomUUID();
  try {
    await erp('/api/method/frappe.client.cancel', { method: 'POST', body: { doctype, name } });
    audit({
      actor,
      role,
      action: 'cancel_document',
      doctype,
      docname: name,
      detail: null,
      result: 'ok',
      message: `${doctype} ${name} cancelled`,
      correlationId: correlation,
    });
    return { ok: true, name, correlation };
  } catch (error) {
    audit({
      actor,
      role,
      action: 'cancel_document',
      doctype,
      docname: name,
      detail: null,
      result: 'failed',
      message: error.message,
      correlationId: correlation,
    });
    throw error;
  }
}

async function addComment(body) {
  const { doctype, name, text, actor, role } = body;
  if (!doctype || !name || !text) throw new ErpError('doctype, name and text are required.', 400);
  if (String(text).length > 2000) throw new ErpError('Comment is too long (max 2000 characters).', 400);
  requireRole(body, 'add_comment');
  const correlation = randomUUID();
  const prefix = actor && actor !== 'unknown' ? `[Copilot - ${actor}] ` : '[Copilot] ';
  const doc = {
    doctype: 'Comment',
    comment_type: 'Comment',
    reference_doctype: doctype,
    reference_name: name,
    content: prefix + String(text).trim(),
  };
  try {
    const res = await erp('/api/method/frappe.client.insert', { method: 'POST', body: { doc } });
    audit({
      actor,
      role,
      action: 'add_comment',
      doctype,
      docname: name,
      detail: { comment: doc.content, comment_name: res.message?.name },
      result: 'ok',
      message: 'Reminder note added to the document',
      correlationId: correlation,
    });
    return { ok: true, comment: res.message?.name, correlation };
  } catch (error) {
    audit({
      actor,
      role,
      action: 'add_comment',
      doctype,
      docname: name,
      detail: { comment: doc.content },
      result: 'failed',
      message: error.message,
      correlationId: correlation,
    });
    throw error;
  }
}

const FLOOR_ROLES = [
  { role: 'stores', key: 'floor_stores', prefix: 'Stores', label: 'Stores' },
  { role: 'wip', key: 'floor_wip', prefix: 'Work In Progress', label: 'Work In Progress' },
  { role: 'fg', key: 'floor_fg', prefix: 'Finished Goods', label: 'Finished Goods' },
];

function floorList(value) {
  if (!value) return [];
  return (Array.isArray(value) ? value : String(value).split(','))
    .map((v) => String(v).trim())
    .filter(Boolean);
}

function floorMs(row) {
  const t = String(row.posting_time || '00:00:00').split('.')[0].split(':').concat(['0', '0', '0']).slice(0, 3).map((p) => p.padStart(2, '0')).join(':');
  const ms = Date.parse(`${row.posting_date}T${t}`);
  return Number.isFinite(ms) ? ms : 0;
}

async function floorWarehouses(settings) {
  const company = settings.floor_company || settings.company || null;
  const all = await getList('Warehouse', { fields: ['name', 'is_group', 'disabled', 'company'], limit: 0 });
  const byName = new Map(all.map((w) => [w.name, w]));
  const found = {};
  const problems = [];
  const owner = {};
  for (const { role, key, prefix, label } of FLOOR_ROLES) {
    let names = floorList(settings[key]);
    if (!names.length) {
      const guess = all.find(
        (w) => !num(w.is_group) && !num(w.disabled) && w.name.startsWith(prefix) && (!company || w.company === company)
      );
      if (guess) names = [guess.name];
    }
    const good = [];
    for (const w of [...new Set(names)]) {
      const info = byName.get(w);
      if (!info) problems.push(`${label}: warehouse '${w}' does not exist.`);
      else if (num(info.is_group)) problems.push(`${label}: '${w}' is a group warehouse. Choose the warehouses that hold the stock.`);
      else if (num(info.disabled)) problems.push(`${label}: warehouse '${w}' is disabled.`);
      else if (company && info.company !== company) problems.push(`${label}: '${w}' belongs to ${info.company}, not ${company}.`);
      else if (owner[w]) problems.push(`'${w}' is listed under both ${owner[w]} and ${label}.`);
      else {
        owner[w] = label;
        good.push(w);
      }
    }
    found[role] = good;
    if (!good.length && role === 'stores') problems.push('No Stores warehouse found. Set one in Copilot Settings.');
  }
  return { found, problems, company };
}

async function floorCurrency(company, settings) {
  try {
    if (company) {
      const rows = await getList('Company', { fields: ['default_currency'], filters: [['name', '=', company]], limit: 1 });
      if (rows[0]?.default_currency) return rows[0].default_currency;
    }
  } catch {}
  return settings.currency || null;
}

async function buildFloorSnapshot() {
  const hit = cacheGet('floor_snapshot', 10000);
  if (hit) return hit;
  const settings = getSettings();
  const { found, problems, company } = await floorWarehouses(settings);
  const { stores, wip, fg } = found;
  const wipSet = new Set(wip);
  const fgSet = new Set(fg);
  const storesSet = new Set(stores);
  const whs = [...stores, ...wip, ...fg];
  const maxItems = Math.max(1, Math.trunc(num(settings.floor_max_items) || 10));
  const maxWs = Math.max(1, Math.trunc(num(settings.floor_max_workstations) || 6));
  const defaultCap = Math.max(num(settings.floor_default_capacity) || 1000, 1);

  const byItem = {};
  const bins = whs.length
    ? await getList('Bin', {
        fields: ['item_code', 'warehouse', 'actual_qty', 'valuation_rate'],
        filters: [['warehouse', 'in', whs]],
        limit: 0,
      })
    : [];
  for (const b of bins) {
    const d = (byItem[b.item_code] ||= { stores: 0, wip: 0, fg: 0, rate: 0, raw: false });
    const qty = num(b.actual_qty);
    if (fgSet.has(b.warehouse)) d.fg += qty;
    else if (wipSet.has(b.warehouse)) {
      d.wip += qty;
      d.raw = true;
    } else if (storesSet.has(b.warehouse)) {
      d.stores += qty;
      d.raw = true;
    }
    d.rate = d.rate || num(b.valuation_rate);
  }
  const value = (c) => (byItem[c].stores + byItem[c].wip) * byItem[c].rate;
  const raw = Object.keys(byItem)
    .filter((c) => byItem[c].raw)
    .sort((a, b) => value(b) - value(a))
    .slice(0, maxItems);
  const fgc = Object.keys(byItem)
    .filter((c) => byItem[c].fg > 0)
    .sort((a, b) => byItem[b].fg - byItem[a].fg)
    .slice(0, 6);
  const codes = [...new Set([...raw, ...fgc])];

  const [itemRows, rules, sle, stations, cards, doneCards, routings] = await Promise.all([
    codes.length
      ? getList('Item', { fields: ['name', 'item_name', 'stock_uom'], filters: [['name', 'in', codes]], limit: 0 })
      : [],
    codes.length && whs.length
      ? getList('Putaway Rule', {
          fields: ['item_code', 'warehouse', 'capacity'],
          filters: [['item_code', 'in', codes], ['warehouse', 'in', whs]],
          limit: 0,
        }).catch(() => [])
      : [],
    codes.length
      ? getList('Stock Ledger Entry', {
          fields: ['item_code', 'warehouse', 'actual_qty', 'voucher_type', 'posting_date', 'posting_time'],
          filters: [['item_code', 'in', codes], ['warehouse', 'in', whs], ['is_cancelled', '=', 0]],
          orderBy: 'posting_date desc, posting_time desc, creation desc',
          limit: Math.max(60, codes.length * 8),
        })
      : [],
    getList('Workstation', { fields: ['name', 'production_capacity', 'status'], limit: 0 }).catch(() =>
      getList('Workstation', { fields: ['name', 'production_capacity'], limit: 0 })
    ),
    getList('Job Card', {
      fields: ['name', 'workstation', 'status', 'for_quantity', 'total_completed_qty', 'work_order', 'operation'],
      filters: [['status', 'in', ['Open', 'Work In Progress', 'Material Transferred']], ['docstatus', '<', 2]],
      orderBy: 'creation asc',
      limit: 0,
    }),
    getList('Job Card', {
      fields: ['workstation', 'total_completed_qty'],
      filters: [['status', '=', 'Completed'], ['modified', '>=', isoToday()]],
      limit: 0,
    }),
    getList('Routing', { fields: ['name'], orderBy: 'modified desc', limit: 1 }).catch(() => []),
  ]);

  const [receipts, openPos, deliveries, openSos] = await Promise.all([
    getList('Purchase Receipt', {
      fields: ['name', 'supplier', 'supplier_name', 'posting_date', 'posting_time', 'total_qty', 'set_warehouse', 'status'],
      filters: [['docstatus', '=', 1], ...(company ? [['company', '=', company]] : [])],
      orderBy: 'posting_date desc, posting_time desc, creation desc',
      limit: 8,
    }).catch(() => []),
    getList('Purchase Order', {
      fields: ['name', 'supplier', 'supplier_name', 'schedule_date', 'total_qty', 'per_received', 'status'],
      filters: [['docstatus', '=', 1], ['status', 'in', ['To Receive and Bill', 'To Receive']], ...(company ? [['company', '=', company]] : [])],
      orderBy: 'schedule_date asc, creation asc',
      limit: 8,
    }).catch(() => []),
    getList('Delivery Note', {
      fields: ['name', 'customer', 'customer_name', 'posting_date', 'posting_time', 'total_qty', 'status'],
      filters: [['docstatus', '=', 1], ['is_return', '=', 0], ...(company ? [['company', '=', company]] : [])],
      orderBy: 'posting_date desc, posting_time desc, creation desc',
      limit: 8,
    }).catch(() => []),
    getList('Sales Order', {
      fields: ['name', 'customer', 'customer_name', 'delivery_date', 'total_qty', 'per_delivered', 'status'],
      filters: [['docstatus', '=', 1], ['status', 'in', ['To Deliver and Bill', 'To Deliver']], ...(company ? [['company', '=', company]] : [])],
      orderBy: 'delivery_date asc, creation asc',
      limit: 8,
    }).catch(() => []),
  ]);
  const dayMs = (d) => {
    const ms = Date.parse(`${d}T00:00:00`);
    return Number.isFinite(ms) ? ms : 0;
  };
  const inbound = {
    done: receipts.map((r) => ({ doc: r.name, dt: 'Purchase Receipt', party: r.supplier_name || r.supplier, qty: num(r.total_qty), at: floorMs(r) || dayMs(r.posting_date), status: r.status })),
    open: openPos.map((r) => ({
      doc: r.name,
      dt: 'Purchase Order',
      party: r.supplier_name || r.supplier,
      qty: round(num(r.total_qty) * (1 - num(r.per_received) / 100), 2),
      at: dayMs(r.schedule_date),
      status: r.status,
    })),
  };
  const outbound = {
    done: deliveries.map((r) => ({ doc: r.name, dt: 'Delivery Note', party: r.customer_name || r.customer, qty: num(r.total_qty), at: floorMs(r) || dayMs(r.posting_date), status: r.status })),
    open: openSos.map((r) => ({
      doc: r.name,
      dt: 'Sales Order',
      party: r.customer_name || r.customer,
      qty: round(num(r.total_qty) * (1 - num(r.per_delivered) / 100), 2),
      at: dayMs(r.delivery_date),
      status: r.status,
    })),
  };

  const meta = new Map(itemRows.map((i) => [i.name, i]));
  const caps = {};
  const fgCaps = {};
  for (const r of rules) {
    const target = fgSet.has(r.warehouse) ? fgCaps : caps;
    target[r.item_code] = (target[r.item_code] || 0) + num(r.capacity);
  }
  const row = (c) => {
    const m = meta.get(c);
    return { code: c, name: m?.item_name || c, uom: m?.stock_uom || 'pcs', rate: round(byItem[c].rate, 2) };
  };
  const items = raw.map((c) => ({
    ...row(c),
    stores: byItem[c].stores,
    wip: byItem[c].wip,
    cap: Math.max(caps[c] || defaultCap, 1),
  }));
  const fgLines = fgc.map((c) => ({ ...row(c), qty: byItem[c].fg, ...(fgCaps[c] ? { cap: fgCaps[c] } : {}) }));

  const log = {};
  const fgLog = [];
  for (const e of sle) {
    if (fgSet.has(e.warehouse)) {
      if (fgLog.length < 8) fgLog.push({ t: e.voucher_type, d: num(e.actual_qty), at: floorMs(e), item: e.item_code });
    } else {
      const list = (log[e.item_code] ||= []);
      if (list.length < 6) {
        list.push({ t: e.voucher_type + (wipSet.has(e.warehouse) ? ' (WIP)' : ''), d: num(e.actual_qty), at: floorMs(e) });
      }
    }
  }

  const done = {};
  for (const c of doneCards) done[c.workstation] = (done[c.workstation] || 0) + num(c.total_completed_qty);
  const jobs = {};
  for (const c of cards) {
    (jobs[c.workstation] ||= []).push({
      jc: c.name,
      wo: c.work_order,
      op: c.operation,
      qty: num(c.for_quantity),
      done: num(c.total_completed_qty),
      state: c.status === 'Work In Progress' ? 'run' : 'open',
    });
  }
  stations.sort((a, b) => Number(!jobs[a.name]) - Number(!jobs[b.name]) || String(a.name).localeCompare(String(b.name)));
  const downStates = floorList(settings.floor_down_statuses || 'Problem,Maintenance');
  const ws = stations.slice(0, maxWs).map((s) => ({
    name: s.name,
    cap: Math.max(Math.trunc(num(s.production_capacity)), 1),
    op: (jobs[s.name] || [{ op: 'Workstation' }])[0].op,
    doneToday: done[s.name] || 0,
    down: downStates.includes(s.status),
    jobs: jobs[s.name] || [],
    log: [],
  }));

  const index = new Map(ws.map((w, i) => [w.name, i]));
  let routes = [];
  if (routings[0]) {
    const doc = await erp('/api/method/frappe.client.get', { params: { doctype: 'Routing', name: routings[0].name } })
      .then((r) => r.message)
      .catch(() => null);
    const steps = (doc?.operations || [])
      .slice()
      .sort((a, b) => num(a.sequence_id) - num(b.sequence_id) || num(a.idx) - num(b.idx))
      .map((s) => ({ ws: index.has(s.workstation) ? index.get(s.workstation) : -1, op: s.operation }));
    if (steps.length) routes.push({ name: routings[0].name, label: routings[0].name, steps });
  }
  if (!routes.length) {
    routes = [{ name: 'Workstations', label: 'Workstation order', steps: ws.map((w, i) => ({ ws: i, op: w.op })) }];
  }

  return cacheSet('floor_snapshot', {
    message: {
      items,
      currency: await floorCurrency(company, settings),
      setup: { ok: !problems.length, problems, settings_url: `${APP_URL}/settings` },
      warehouses: found,
      fg: {
        name: fg.length === 1 ? fg[0] : 'Finished Goods',
        cap: num(settings.floor_fg_capacity) || 5000,
        lines: fgLines,
        log: fgLog,
      },
      ws,
      routes,
      log,
      inbound,
      outbound,
      debug: { stores, wip, fg, bin_rows: Object.keys(byItem).length, items_found: items.length },
    },
  });
}

const FLOOR_HTML = readFileSync(join(SERVER_DIR, 'vendor', 'warehouse-floor.html'), 'utf8')
  .replace('https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js', '/floor/three.min.js')
  .replace(
    '<script>\n(function () {',
    `<script>document.documentElement.dataset.theme = 'dark'; window.WF_CONFIG = { snapshotUrl: '/floor/snapshot', refreshMs: 30000 };</script>\n<script>\n(function () {`
  );
const THREE_JS = readFileSync(join(SERVER_DIR, 'vendor', 'three.min.js'), 'utf8');

function csvEscape(value) {
  const s = value === null || value === undefined ? '' : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

async function health() {
  const out = {
    ok: false,
    service: 'ERPNext Copilot API',
    erp_url: ERP_URL,
    app_url: APP_URL,
    scanner_url: `${API_BASE}/scanner`,
    now: new Date().toISOString(),
    erpnext: { url: ERP_URL },
    database: {},
  };
  try {
    const versions = await erp('/api/method/frappe.utils.change_log.get_versions', { timeout: 8000 });
    out.erpnext.reachable = true;
    out.erpnext.erpnext_version = versions.message?.erpnext?.version || null;
    out.erpnext.frappe_version = versions.message?.frappe?.version || null;
    out.ok = true;
  } catch (error) {
    out.erpnext.reachable = false;
    out.erpnext.error = error.message;
  }
  try {
    out.database.ok = true;
    out.database.audit_entries = db.prepare('SELECT COUNT(*) AS n FROM audit_log').get()?.n ?? 0;
    out.database.exceptions = db.prepare('SELECT COUNT(*) AS n FROM exceptions').get()?.n ?? 0;
  } catch (error) {
    out.database.ok = false;
    out.database.error = error.message;
  }
  out.settings = getSettings();
  return out;
}

function readAudit(query) {
  const limit = Math.min(Number(query.limit || 200), 1000);
  const filters = [];
  const params = [];
  if (query.action) {
    filters.push('action = ?');
    params.push(query.action);
  }
  if (query.result) {
    filters.push('result = ?');
    params.push(query.result);
  }
  const where = filters.length ? `WHERE ${filters.join(' AND ')}` : '';
  const rows = db.prepare(`SELECT * FROM audit_log ${where} ORDER BY id DESC LIMIT ${limit}`).all(...params);
  const totals = db
    .prepare("SELECT COUNT(*) AS total, SUM(CASE WHEN result = 'failed' THEN 1 ELSE 0 END) AS failed, SUM(CASE WHEN result = 'denied' THEN 1 ELSE 0 END) AS denied FROM audit_log")
    .get();
  return { rows, totals: { total: totals?.total || 0, failed: totals?.failed || 0, denied: totals?.denied || 0 } };
}

function send(res, status, payload, contentType = 'application/json') {
  const body = contentType === 'application/json' ? JSON.stringify(payload) : String(payload);
  res.writeHead(status, {
    'Content-Type': contentType,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  res.end(body);
}

async function readBody(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 1_000_000) throw new ErpError('Request body too large.', 413);
    chunks.push(chunk);
  }
  if (chunks.length === 0) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw new ErpError('Body must be valid JSON.', 400);
  }
}

const ALLOWED_HOSTS = new Set([`127.0.0.1:${PORT}`, `localhost:${PORT}`, `[::1]:${PORT}`]);

function keyMatches(given) {
  if (!API_KEY || typeof given !== 'string') return false;
  const a = Buffer.from(given);
  const b = Buffer.from(API_KEY);
  return a.length === b.length && timingSafeEqual(a, b);
}

function guardRequest(req) {
  if (!ALLOWED_HOSTS.has(String(req.headers.host || '').toLowerCase())) throw new ErpError('Host not allowed.', 421);
  if (req.method === 'GET' || req.method === 'HEAD') return;
  if (req.headers.origin) throw new ErpError('Cross-origin writes are not allowed.', 403);
  const hasBody = Number(req.headers['content-length'] || 0) > 0 || Boolean(req.headers['transfer-encoding']);
  if (hasBody && !String(req.headers['content-type'] || '').toLowerCase().startsWith('application/json')) {
    throw new ErpError('Write requests must be application/json.', 415);
  }
  if (!keyMatches(req.headers['x-copilot-key'])) throw new ErpError('Missing or invalid API key.', 401);
}

function queryObject(url) {
  const out = {};
  for (const [k, v] of url.searchParams.entries()) out[k] = v;
  return out;
}

const JSQR = readFileSync(join(SERVER_DIR, 'vendor', 'jsQR.js'), 'utf8');
const API_BASE = (env.COPILOT_API_URL || `http://127.0.0.1:${PORT}`).replace(/\/$/, '');

const SCANNER_HTML = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Camera scanner - ERPNext Copilot</title>
  <style>
    :root { color-scheme: dark; }
    body { margin: 0; background: #0e1116; color: #f9fafb; font-family: Inter, system-ui, sans-serif; display: flex; flex-direction: column; align-items: center; gap: 14px; padding: 20px; }
    h1 { font-size: 18px; margin: 0; text-align: center; }
    p { color: #9ca3af; font-size: 13px; margin: 0; text-align: center; max-width: 560px; line-height: 1.5; }
    .shell { position: relative; width: 100%; max-width: 560px; }
    video { width: 100%; max-width: 560px; border-radius: 12px; background: #000; display: block; min-height: 180px; }
    .frame { position: absolute; inset: 12% 18%; border: 2px solid rgba(82,120,245,0.9); border-radius: 12px; pointer-events: none; }
    .box { border: 1px solid #2a3140; border-radius: 12px; padding: 14px; max-width: 560px; width: 100%; box-sizing: border-box; display: flex; flex-direction: column; gap: 8px; }
    input, select { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #2a3140; background: #161a22; color: #fff; font-size: 14px; box-sizing: border-box; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; }
    button { padding: 10px 14px; border-radius: 8px; border: 0; background: #4c7dff; color: #fff; font-size: 14px; cursor: pointer; flex: 1 1 140px; }
    button.secondary { background: #232936; border: 1px solid #2a3140; }
    #status { font-size: 13px; color: #9ca3af; min-height: 18px; }
    .tag { font-size: 12px; color: #60a5fa; }
  </style>
</head>
<body>
  <h1>Scan a QR code, barcode or type a code</h1>
  <p>Point the camera at a unit QR label or a barcode. Codes are resolved against ERPNext in the Copilot app.</p>
  <div class="shell">
    <video id="cam" autoplay muted playsinline></video>
    <div class="frame" id="frame" style="display:none"></div>
  </div>
  <div class="box">
    <div id="status">Camera is idle.</div>
    <div class="row">
      <button id="start">Start camera</button>
      <button id="stop" class="secondary">Stop</button>
    </div>
    <select id="device" style="display:none"></select>
    <input id="manual" placeholder="or type a serial / item code" autocomplete="off" />
    <button id="go" class="secondary">Look up manually</button>
    <p class="tag">Works in Chrome, Edge, Firefox and Safari. The camera needs a secure origin (localhost or https).</p>
  </div>
  <script src="/scanner/jsqr.js"></script>
  <script>
    (function () {
      var configuredApp = ${JSON.stringify(APP_URL)};
      var params = new URLSearchParams(window.location.search);
      var appOverride = params.get('app');
      var referrer = document.referrer || '';
      var referrerOrigin = configuredApp;
      if (referrer) {
        try { referrerOrigin = new URL(referrer).origin; } catch (e) { referrerOrigin = configuredApp; }
      }
      var appUrl = String(appOverride || referrerOrigin || configuredApp).replace(/\\/+$/, '');
      var statusEl = document.getElementById('status');
      var video = document.getElementById('cam');
      var frame = document.getElementById('frame');
      var deviceSel = document.getElementById('device');
      var stream = null;
      var detector = null;
      var scanning = false;
      var canvas = document.createElement('canvas');
      var ctx = canvas.getContext('2d', { willReadFrequently: true });
      var hasNative = 'BarcodeDetector' in window;

      function setStatus(text, tone) {
        statusEl.textContent = text;
        statusEl.style.color = tone === 'error' ? '#f87171' : tone === 'ok' ? '#34d399' : '#9ca3af';
      }

      function extractCode(raw) {
        if (!raw) return '';
        var value = String(raw).trim();
        try {
          var url = new URL(value);
          var fromQuery = url.searchParams.get('code');
          if (fromQuery) return fromQuery.trim();
          var segments = url.pathname.split('/').filter(Boolean);
          if (segments.length) return decodeURIComponent(segments[segments.length - 1]).trim();
        } catch (e) {}
        var match = value.match(/[?&]code=([^&]+)/);
        if (match) return decodeURIComponent(match[1]).trim();
        return value;
      }

      function navigate(raw) {
        var code = extractCode(raw);
        if (!code) return;
        scanning = false;
        setStatus('Found ' + code + ' - opening the Copilot scan page...', 'ok');
        stopCamera();
        window.location.href = appUrl + '/scan?code=' + encodeURIComponent(code);
      }

      function stopCamera() {
        scanning = false;
        if (stream) {
          stream.getTracks().forEach(function (track) { track.stop(); });
          stream = null;
        }
        video.srcObject = null;
        frame.style.display = 'none';
      }

      function detect(paint) {
        if (detector) {
          return detector.detect(video).then(function (codes) {
            if (codes && codes.length) return codes[0].rawValue;
            return null;
          }).catch(function () { return null; });
        }
        if (typeof jsQR !== 'function') return Promise.resolve(null);
        if (!video.videoWidth || !video.videoHeight) return Promise.resolve(null);
        var width = Math.min(video.videoWidth, 720);
        var height = Math.round((video.videoHeight / video.videoWidth) * width);
        canvas.width = width;
        canvas.height = height;
        ctx.drawImage(video, 0, 0, width, height);
        var image = ctx.getImageData(0, 0, width, height);
        if (paint) paint(image);
        var result = jsQR(image.data, image.width, image.height, { inversionAttempts: 'dontInvert' });
        return Promise.resolve(result && result.data ? result.data : null);
      }

      function loop() {
        if (!scanning) return;
        detect(null).then(function (code) {
          if (!scanning) return;
          if (code) return navigate(code);
          if (video.readyState >= 2) requestAnimationFrame(loop);
          else setTimeout(loop, 250);
        });
      }

      async function listCameras() {
        try {
          var devices = await navigator.mediaDevices.enumerateDevices();
          var cams = devices.filter(function (d) { return d.kind === 'videoinput'; });
          if (cams.length > 1) {
            deviceSel.innerHTML = '';
            cams.forEach(function (cam, index) {
              var option = document.createElement('option');
              option.value = cam.deviceId;
              option.textContent = cam.label || 'Camera ' + (index + 1);
              deviceSel.appendChild(option);
            });
            deviceSel.style.display = 'block';
          }
        } catch (e) {}
      }

      async function startCamera() {
        stopCamera();
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          setStatus('This browser cannot open a camera. Type the code below instead.', 'error');
          return;
        }
        try {
          setStatus('Requesting camera permission...');
          var deviceId = deviceSel.value || undefined;
          stream = await navigator.mediaDevices.getUserMedia({
            video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: 'environment' } },
            audio: false
          });
          video.srcObject = stream;
          await video.play().catch(function () {});
          frame.style.display = 'block';
          if (hasNative) {
            try {
              detector = new BarcodeDetector({ formats: ['qr_code', 'code_128', 'code_39', 'ean_13', 'ean_8', 'upc_a', 'upc_e'] });
            } catch (e) {
              detector = new BarcodeDetector();
            }
            setStatus('Scanning with the built-in BarcodeDetector...');
          } else {
            setStatus('Scanning with the bundled jsQR decoder...');
          }
          scanning = true;
          listCameras();
          loop();
        } catch (error) {
          stopCamera();
          var name = error && error.name;
          if (name === 'NotAllowedError') setStatus('Camera permission was denied. Allow the camera for this page, or type the code below.', 'error');
          else if (name === 'NotFoundError') setStatus('No camera was found on this device. Type the code below.', 'error');
          else setStatus('Camera unavailable: ' + (error && error.message ? error.message : 'unknown error'), 'error');
        }
      }

      document.getElementById('start').addEventListener('click', startCamera);
      document.getElementById('stop').addEventListener('click', function () {
        stopCamera();
        setStatus('Camera stopped.');
      });
      deviceSel.addEventListener('change', startCamera);

      function go() {
        var value = document.getElementById('manual').value.trim();
        if (!value) {
          setStatus('Type a serial number or item code first.', 'error');
          return;
        }
        navigate(value);
      }
      document.getElementById('go').addEventListener('click', go);
      document.getElementById('manual').addEventListener('keydown', function (event) {
        if (event.key === 'Enter') go();
      });

      if (!window.isSecureContext) {
        setStatus('Camera needs a secure origin (http://localhost or https://). Type the code below.', 'error');
      }
    })();
  </script>
</body>
</html>`;

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const path = url.pathname.replace(/\/$/, '') || '/';
  try {
    guardRequest(req);
    if (req.method === 'GET' && path === '/health') return send(res, 200, await health());
    if (req.method === 'GET' && path === '/scanner') return send(res, 200, SCANNER_HTML, 'text/html; charset=utf-8');
    if (req.method === 'GET' && path === '/scanner/jsqr.js') return send(res, 200, JSQR, 'application/javascript; charset=utf-8');
    if (req.method === 'GET' && path === '/floor') return send(res, 200, FLOOR_HTML, 'text/html; charset=utf-8');
    if (req.method === 'GET' && path === '/floor/three.min.js') return send(res, 200, THREE_JS, 'application/javascript; charset=utf-8');
    if (req.method === 'GET' && path === '/floor/snapshot') return send(res, 200, await buildFloorSnapshot());
    if (req.method === 'GET' && path === '/companies') {
      const companies = await loadCompanies();
      return send(res, 200, {
        rows: companies,
        options: companies.map((c) => ({ label: c.name, value: c.name })),
      });
    }
    if (req.method === 'GET' && path === '/overview') return send(res, 200, await buildOverview());
    if (req.method === 'GET' && path === '/inventory') {
      const q = queryObject(url);
      const [rows, wh, groups] = await Promise.all([buildInventory(), loadWarehouses(), loadItemGroups()]);
      let filtered = rows;
      if (q.search) {
        const s = q.search.toLowerCase();
        filtered = filtered.filter((r) => r.code.toLowerCase().includes(s) || String(r.name).toLowerCase().includes(s));
      }
      if (q.warehouse) filtered = filtered.filter((r) => r.warehouse === q.warehouse);
      if (q.group) filtered = filtered.filter((r) => r.group === q.group);
      if (q.status) filtered = filtered.filter((r) => r.status === q.status);
      return send(res, 200, {
        rows: filtered,
        count: filtered.length,
        total: rows.length,
        warehouses: wh.map((w) => w.name),
        groups: groups.map((g) => g.name),
        warehouse_options: [{ label: 'All warehouses', value: '' }, ...wh.map((w) => ({ label: w.name, value: w.name }))],
        group_options: [{ label: 'All item groups', value: '' }, ...groups.map((g) => ({ label: g.name, value: g.name }))],
        status_options: [
          { label: 'All statuses', value: '' },
          { label: 'Normal', value: 'normal' },
          { label: 'Low stock', value: 'low' },
          { label: 'Out of stock', value: 'out' },
          { label: 'Inactive', value: 'inactive' },
          { label: 'Non-stock', value: 'service' },
        ],
        generated_at: new Date().toISOString(),
      });
    }
    if (req.method === 'GET' && path === '/item-options') {
      const items = await loadItems();
      const rows = items
        .filter((i) => num(i.is_stock_item) === 1 && num(i.disabled) !== 1)
        .map((i) => ({
          value: i.name,
          label: `${i.item_name} (${i.name})`,
          name: i.item_name,
          uom: i.stock_uom,
          has_serial: num(i.has_serial_no) === 1,
          has_batch: num(i.has_batch_no) === 1,
        }));
      return send(res, 200, { rows, options: rows.map((r) => ({ label: r.label, value: r.value })) });
    }
    if (req.method === 'GET' && path === '/item') return send(res, 200, await getItemDetail(queryObject(url).code));
    if (req.method === 'GET' && path === '/lookup') {
      const q = queryObject(url);
      let code = String(q.code || '').trim();
      if (!code) return send(res, 200, { found: false, type: 'none', reason: 'No code supplied.' });
      const urlMatch = code.match(/[?&]code=([^&]+)/);
      if (urlMatch) code = decodeURIComponent(urlMatch[1]);
      const serial = await getSerialDetail(code);
      if (serial.found) return send(res, 200, { ...serial, query: code });
      const item = await getItemDetail(code);
      if (item.found) return send(res, 200, { ...item, type: 'item', query: code });
      const items = await loadItems();
      const needle = code.toLowerCase();
      const suggestions = items
        .filter((i) => String(i.name).toLowerCase().includes(needle) || String(i.item_name).toLowerCase().includes(needle))
        .slice(0, 10)
        .map((i) => ({ code: i.name, name: i.item_name, group: i.item_group }));
      return send(res, 200, {
        found: false,
        type: 'none',
        query: code,
        reason: `No Serial No or Item matches "${code}".`,
        suggestions,
      });
    }
    if (req.method === 'GET' && path === '/serial') return send(res, 200, await getSerialDetail(queryObject(url).code));
    if (req.method === 'GET' && path === '/serial-options') {
      const q = queryObject(url);
      return send(res, 200, { rows: await listSerialOptions(q.item_code, q.warehouse) });
    }
    if (req.method === 'GET' && path === '/movements') {
      const q = queryObject(url);
      const rows = await buildMovements({ limit: 300, search: q.search, warehouse: q.warehouse, docstatus: q.docstatus });
      const wh = await loadWarehouses();
      return send(res, 200, {
        rows,
        count: rows.length,
        warehouses: wh.map((w) => w.name),
        warehouse_options: [{ label: 'All warehouses', value: '' }, ...wh.map((w) => ({ label: w.name, value: w.name }))],
        status_options: [
          { label: 'All statuses', value: '' },
          { label: 'Draft', value: '0' },
          { label: 'Submitted', value: '1' },
          { label: 'Cancelled', value: '2' },
        ],
      });
    }
    if (req.method === 'GET' && path === '/warehouses') {
      const wh = await loadWarehouses();
      return send(res, 200, { rows: wh.map((w) => ({ value: w.name, label: w.name })) });
    }
    if (req.method === 'GET' && path === '/options') {
      const [wh, groups] = await Promise.all([loadWarehouses(), loadItemGroups()]);
      return send(res, 200, {
        warehouses: wh.map((w) => ({ label: w.name, value: w.name })),
        groups: groups.map((g) => ({ label: g.name, value: g.name })),
      });
    }
    if (req.method === 'POST' && path === '/transfer') return send(res, 200, await createTransfer(await readBody(req)));
    if (req.method === 'GET' && path === '/exceptions') return send(res, 200, listExceptions(queryObject(url)));
    if (req.method === 'POST' && path === '/exceptions/scan') return send(res, 200, await detectExceptions());
    if (req.method === 'GET' && path === '/exception') return send(res, 200, getException(queryObject(url).id));
    if (req.method === 'POST' && path === '/exceptions/action') return send(res, 200, exceptionAction(await readBody(req)));
    if (req.method === 'GET' && path === '/reports') return send(res, 200, await buildReports(queryObject(url)));
    if (req.method === 'GET' && path === '/settings') return send(res, 200, getSettings());
    if (req.method === 'PUT' && path === '/settings') {
      const body = await readBody(req);
      const role = String(body.role || '').toLowerCase();
      const actor = body.actor || 'unknown';
      if (role !== 'administrator') {
        audit({ actor, role, action: 'settings_update', result: 'denied', message: 'Only administrators can change settings.' });
        throw new ErpError('Only administrators can change application settings.', 403);
      }
      const patch = sanitizeSettings(body);
      const next = saveSettings(patch);
      audit({ actor, role, action: 'settings_update', detail: patch, result: 'ok' });
      return send(res, 200, next);
    }
    if (req.method === 'GET' && path === '/audit') return send(res, 200, readAudit(queryObject(url)));
    if (req.method === 'GET' && path === '/purchasing') return send(res, 200, await buildPurchasing(queryObject(url)));
    if (req.method === 'GET' && path === '/purchase-orders') return send(res, 200, await buildPurchaseOrders(queryObject(url)));
    if (req.method === 'POST' && path === '/purchase-orders') return send(res, 200, await createPurchaseOrders(await readBody(req)));
    if (req.method === 'GET' && path === '/suppliers') return send(res, 200, await buildSuppliers(queryObject(url)));
    if (req.method === 'GET' && path === '/stock-ledger') return send(res, 200, await buildStockLedger(queryObject(url)));
    if (req.method === 'POST' && path === '/submit-document') return send(res, 200, await submitDocument(await readBody(req)));
    if (req.method === 'POST' && path === '/cancel-document') return send(res, 200, await cancelDocument(await readBody(req)));
    if (req.method === 'POST' && path === '/comment') return send(res, 200, await addComment(await readBody(req)));
    if (req.method === 'GET' && path === '/export/purchasing.csv') {
      const data = await buildPurchasing(queryObject(url));
      const header = [
        'supplier','item_code','item_name','uom','urgency','stock','available','incoming','sold_qty',
        'avg_daily','days_left','safety','reorder_point','suggested_qty','lead_time_days','cover_days','window_days',
      ];
      const rows = data.groups.flatMap((g) => g.lines.map((l) => [g.supplier, l]));
      const csv = [header.join(',')]
        .concat(rows.map(([supplier, l]) => [supplier, ...header.slice(1).map((k) => l[k])].map(csvEscape).join(',')))
        .join('\n');
      res.writeHead(200, {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': `attachment; filename="copilot-purchasing-${isoToday()}.csv"`,
      });
      return res.end(csv);
    }
    if (path === '/') {
      return send(res, 200, {
        ok: true,
        service: 'ERPNext Copilot API',
        endpoints: [
          '/health', '/companies', '/overview', '/inventory', '/item', '/serial', '/lookup', '/movements', '/transfer',
          '/exceptions', '/exceptions/scan', '/exceptions/action', '/reports', '/settings', '/audit',
          '/purchasing', '/purchase-orders', '/suppliers', '/stock-ledger', '/submit-document', '/cancel-document',
          '/comment', '/export/purchasing.csv', '/scanner', '/floor', '/floor/snapshot'
        ],
      });
    }
    return send(res, 404, { error: 'Not found' });
  } catch (error) {
    const status = error instanceof ErpError ? error.status : 500;
    if (!(error instanceof ErpError)) console.error(error);
    return send(res, status, { error: error.message, detail: error.detail || null });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`ERPNext Copilot API listening on http://127.0.0.1:${PORT}`);
  console.log(`ERPNext: ${ERP_URL}`);
  console.log(`Scanner: ${API_BASE}/scanner (returns to ${APP_URL})`);
});
