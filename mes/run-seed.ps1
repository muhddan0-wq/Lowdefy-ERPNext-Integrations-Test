param(
    [string]$Site = "p1-shah-alam",
    [string]$Container = "comp_demo-bench-1",
    [string]$FrappeSite = "frontend",
    [switch]$NoPlan,
    [switch]$ResetPlan
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$siteFile = Join-Path $here "sites\$Site.yaml"
if (-not (Test-Path $siteFile)) { throw "Site file not found: $siteFile" }
$dest = "/home/frappe/frappe-bench/sites/mes_seed"
docker exec $Container mkdir -p $dest | Out-Null
docker cp (Join-Path $here "seed_mes.py") "${Container}:$dest/seed_mes.py"
docker cp (Join-Path $here "products.yaml") "${Container}:$dest/products.yaml"
docker cp $siteFile "${Container}:$dest/site.yaml"
$extra = @()
if ($NoPlan) { $extra += "--no-plan" }
if ($ResetPlan) { $extra += "--reset-plan" }
docker exec -e FRAPPE_SITE=$FrappeSite -w /home/frappe/frappe-bench/sites $Container ../env/bin/python -W ignore "mes_seed/seed_mes.py" "mes_seed/products.yaml" "mes_seed/site.yaml" @extra
if ($LASTEXITCODE -ne 0) { throw "Seed failed (exit $LASTEXITCODE)" }
