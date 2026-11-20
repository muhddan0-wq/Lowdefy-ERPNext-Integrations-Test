import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

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
const dbPath = env.COPILOT_DB_PATH;
if (!dbPath) throw new Error('COPILOT_DB_PATH missing from .env');

mkdirSync(dirname(dbPath), { recursive: true });
const db = new DatabaseSync(dbPath);
db.exec('PRAGMA journal_mode = WAL;');
db.exec(`
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
  CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts DESC);
  CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT
  );
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
`);

const defaults = {
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
};
const excColumns = db.prepare('PRAGMA table_info(exceptions)').all().map((c) => c.name);
const excWanted = {
  source: "TEXT NOT NULL DEFAULT 'inventory'",
  subtitle: "TEXT DEFAULT ''",
  amount: 'REAL',
  currency: 'TEXT',
  action: 'TEXT',
  action_label: 'TEXT',
};
for (const [name, type] of Object.entries(excWanted)) {
  if (!excColumns.includes(name)) db.exec(`ALTER TABLE exceptions ADD COLUMN ${name} ${type}`);
}
const auditColumns = db.prepare('PRAGMA table_info(audit_log)').all().map((c) => c.name);
if (!auditColumns.includes('role')) db.exec('ALTER TABLE audit_log ADD COLUMN role TEXT');
if (!auditColumns.includes('correlation_id')) db.exec('ALTER TABLE audit_log ADD COLUMN correlation_id TEXT');

const row = db.prepare('SELECT key FROM settings WHERE key = ?').get('app');
if (!row) {
  db.prepare('INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)').run(
    'app',
    JSON.stringify(defaults),
    new Date().toISOString()
  );
  console.log('Seeded default settings row.');
}
console.log(`Database ready at ${dbPath}`);
db.close();
