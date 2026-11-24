param(
    [ValidateSet("execution", "analytics", "modules", "verify")]
    [Parameter(Mandatory = $true)][string]$Step,
    [string]$Site = "p1-shah-alam",
    [string]$Container = "comp_demo-bench-1",
    [string]$FrappeSite = "frontend",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$siteFile = Join-Path $here "sites\$Site.yaml"
if (-not (Test-Path $siteFile)) { throw "Site file not found: $siteFile" }
$dest = "/home/frappe/frappe-bench/sites/mes_seed"
docker exec $Container mkdir -p "$dest/state" | Out-Null
foreach ($f in @("seed_mes.py", "mes_common.py", "mes_execution.py", "mes_analytics.py", "mes_modules.py", "mes_verify.py", "products.yaml")) {
    $src = Join-Path $here $f
    if (Test-Path $src) { docker cp $src "${Container}:$dest/$f" | Out-Null }
}
docker cp $siteFile "${Container}:$dest/site.yaml" | Out-Null
docker cp (Join-Path $here "state\shrdc-baseline.json") "${Container}:$dest/state/shrdc-baseline.json" | Out-Null
$dry = if ($DryRun) { "1" } else { "0" }
docker exec -e FRAPPE_SITE=$FrappeSite -e MES_DRY_RUN=$dry -e PYTHONUNBUFFERED=1 -w /home/frappe/frappe-bench/sites $Container ../env/bin/python -W ignore "mes_seed/mes_$Step.py"
if ($LASTEXITCODE -ne 0) { throw "MES step '$Step' failed (exit $LASTEXITCODE)" }
if ($Step -eq "verify") {
    docker cp "${Container}:$dest/state/." (Join-Path $here "state") | Out-Null
}
