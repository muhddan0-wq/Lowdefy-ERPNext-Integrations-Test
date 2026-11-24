param([string]$Container = "comp_demo-bench-1", [string]$FrappeSite = "frontend", [switch]$SkipBackup)
# Installs/updates every mes/server_scripts/mes_*.py as an API Server Script on the site.
$ErrorActionPreference = "Stop"
$mes = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $SkipBackup) {
    docker exec -w /home/frappe/frappe-bench $Container bench --site $FrappeSite backup
    if ($LASTEXITCODE -ne 0) { throw "Backup failed" }
}
$dest = "/home/frappe/frappe-bench/sites/mes_scripts"
docker exec $Container rm -rf $dest | Out-Null
docker exec $Container mkdir -p "$dest/src" | Out-Null
Get-ChildItem (Join-Path $mes "server_scripts") -Filter *.py | ForEach-Object {
    docker cp $_.FullName "${Container}:$dest/src/$($_.Name)"
}
docker cp (Join-Path $mes "setup\install_server_scripts.py") "${Container}:$dest/install_server_scripts.py"
docker exec -e FRAPPE_SITE=$FrappeSite -w /home/frappe/frappe-bench/sites $Container ../env/bin/python -W ignore "mes_scripts/install_server_scripts.py" "mes_scripts/src"
if ($LASTEXITCODE -ne 0) { throw "Install failed (exit $LASTEXITCODE)" }
