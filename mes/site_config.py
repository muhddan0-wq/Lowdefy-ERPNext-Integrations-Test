"""Per-site MES configuration. One YAML file in mes/sites/ describes the ERPNext site the MES connects to.

Consumers: setup/install_server_scripts.py (renders the server-script prelude), setup/install-mes.ps1 and the
bench-side setup scripts (check_site, create_sector_roles, create_api_user, install_shopfloor), appsmith/build_app.py,
appsmith/deploy_appsmith.py, appsmith/dev_harness.py and appsmith/update_report_appendix.py.
The file is plain YAML and needs PyYAML, which ERPNext already bundles and the host has via requirements.
"""
import os
import pathlib

import yaml

HERE = pathlib.Path(__file__).resolve().parent
SITES = HERE / "sites"
DEFAULT_SITE = "p1-shah-alam"
PRELUDE_MARKER = "@@SITE@@"
REQUIRED = ["code", "company", "plant_floor", "site_prefix", "warehouses", "erp", "appsmith"]
WAREHOUSE_KEYS = ["stores", "wip", "fg"]
DEFAULT_CONTAINER = "comp_demo-bench-1"
DEFAULT_API_ROLES = ["Manufacturing User", "Manufacturing Manager", "Stock User", "MES Batch Reader"]


def path_for(name=None):
    name = name or os.environ.get("MES_SITE") or DEFAULT_SITE
    p = pathlib.Path(name)
    if p.suffix in (".yaml", ".yml") or p.exists():
        return p
    return SITES / f"{name}.yaml"


def load(path=None):
    p = pathlib.Path(path) if path else path_for()
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        raise SystemExit(f"{p}: missing keys {', '.join(missing)}")
    missing_wh = [k for k in WAREHOUSE_KEYS if k not in cfg["warehouses"]]
    if missing_wh:
        raise SystemExit(f"{p}: warehouses missing {', '.join(missing_wh)}")
    cfg["horizon_days"] = int(cfg.get("horizon_days", 60))
    cfg["erp"].setdefault("container", DEFAULT_CONTAINER)
    cfg.setdefault("sector_roles", {})
    api = cfg.setdefault("api_user", {})
    api.setdefault("email", f"appsmith-mes@{cfg.get('test_account_domain', 'local.test')}")
    api.setdefault("roles", list(DEFAULT_API_ROLES))
    cfg.setdefault("test_users", [])
    cfg.setdefault("test_account_domain", "local.test")
    cfg["source"] = str(p)
    return cfg


def server_values(cfg):
    wh = cfg["warehouses"]
    return [
        ("COMPANY", cfg["company"]["name"]),
        ("PLANT_FLOOR", cfg["plant_floor"]),
        ("SITE_PREFIX", cfg["site_prefix"]),
        ("WH", {k: wh[k] for k in WAREHOUSE_KEYS}),
        ("HORIZON_DAYS", cfg["horizon_days"]),
    ]


def render_prelude(prelude, cfg):
    if PRELUDE_MARKER not in prelude:
        raise SystemExit(f"_prelude.py has no {PRELUDE_MARKER} marker")
    lines = []
    for key, value in server_values(cfg):
        lines.append(f'    "{key}": {value!r},')
    return prelude.replace(f"    {PRELUDE_MARKER}", "\n".join(lines))


def lookup(cfg, dotted):
    v = cfg
    for part in dotted.split("."):
        v = v[part]
    return v


def from_bench():
    """Inside the bench: the site YAML the install scripts copied next to themselves (MES_SITE_CONFIG overrides)."""
    return load(os.environ.get("MES_SITE_CONFIG") or HERE / "site.yaml")


if __name__ == "__main__":
    import sys
    print(lookup(load(sys.argv[1]), sys.argv[2]))
