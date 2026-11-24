#!/usr/bin/env bash
# REST checks for the MES API, run with the dedicated appsmith-mes key (never Administrator).
# Usage: bash mes/setup/verify_api.sh [m0|m1|m2|all]
cd "$(dirname "$0")/../.." || exit 1
set -a; . mes/.secrets/appsmith-mes.env; set +a
H="Authorization: token $ERP_API_KEY:$ERP_API_SECRET"
B=http://localhost:8000
get() { curl -s -H "$H" "$B$1"; }
what=${1:-all}

if [[ $what == m0 || $what == all ]]; then
  echo "== M0"
  get "/api/resource/Workstation?filters=%5B%5B%22plant_floor%22%2C%22%3D%22%2C%22P1%20Shah%20Alam%20Plant%22%5D%5D&limit_page_length=100" \
    | python -c "import json,sys;d=json.load(sys.stdin)['data'];print('P1 workstations:',len(d))"
  echo -n "SHRDC company doc HTTP: "; curl -s -o /dev/null -w '%{http_code}\n' -H "$H" "$B/api/resource/Company/SHRDC"
  get "/api/resource/Work%20Order?filters=%5B%5B%22company%22%2C%22%3D%22%2C%22SHRDC%22%5D%5D" | python -c "import json,sys;print('SHRDC work orders visible:',len(json.load(sys.stdin)['data']))"
  get "/api/resource/Company" | python -c "import json,sys;print('companies visible:',[c['name'] for c in json.load(sys.stdin)['data']])"
fi
if [[ $what == m1 || $what == all ]]; then
  echo "== M1"
  get "/api/method/mes_work_orders?plan=MFG-PP-2026-00001" | python -c "
import json,sys;m=json.load(sys.stdin)['message'];print('forward WOs:',len(m['rows']),'kpi:',m['kpi'])
import collections;print('status:',dict(collections.Counter(r['status'] for r in m['rows'])))"
  get "/api/method/mes_work_order_detail?work_order=MFG-WO-2026-00036" | python -c "
import json,sys;m=json.load(sys.stdin)['message'];h=m['header'];print('detail',h['name'],h['status'],'ops',[(o['operation'],o['workstation'],o['job_card'],o['job_card_status']) for o in m['operations']]);print('materials',[(x['item_code'],x['required_qty'],x['transferred_qty'],x['in_stock'],x['short']) for x in m['materials']])"
fi
if [[ $what == m2 || $what == all ]]; then
  echo "== M2"
  get "/api/method/mes_schedule_board?from_date=2026-11-20&to_date=2027-01-31" | python -c "
import json,sys;m=json.load(sys.stdin)['message'];print('groups',len(m['groups']),'blocks',len(m['items']),'job cards',m['job_card_count'],'conflicts',m['conflicts']['count'])"
  get "/api/method/mes_schedule_conflicts" | python -c "import json,sys;m=json.load(sys.stdin)['message'];print('mes_schedule_conflicts:',m['count'])"
  get "/api/method/mes_workstation_load?from_date=2026-11-25&to_date=2026-12-04" | python -c "
import json,sys;m=json.load(sys.stdin)['message'];print('load rows',len(m['rows']),'days',len(m['days']),'max %',max((c['load_pct'] or 0) for r in m['rows'] for c in r['cells']))"
fi
