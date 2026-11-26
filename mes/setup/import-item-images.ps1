param([string]$Container = "comp_demo-bench-1", [string]$FrappeSite = "frontend", [switch]$DryRun, [switch]$SkipBackup)
# Imports mes/appsmith/ITEMIMAGEs into ERPNext Item.image. Report lands in mes/state/item-image-import.md.
$ErrorActionPreference = "Stop"
$mes = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $DryRun -and -not $SkipBackup) {
    docker exec -w /home/frappe/frappe-bench $Container bench --site $FrappeSite backup
    if ($LASTEXITCODE -ne 0) { throw "Backup failed" }
}
$dest = "/home/frappe/frappe-bench/sites/mes_images"
docker exec -u root $Container rm -rf $dest | Out-Null
docker exec $Container mkdir -p "$dest/report" | Out-Null
docker cp (Join-Path $mes "appsmith\ITEMIMAGEs") "${Container}:$dest/images"
docker cp (Join-Path $mes "setup\item_images.yaml") "${Container}:$dest/item_images.yaml"
docker cp (Join-Path $mes "setup\import_item_images.py") "${Container}:$dest/import_item_images.py"
docker exec -u root $Container chown -R frappe:frappe $dest | Out-Null
$extra = @()
if ($DryRun) { $extra += "--dry-run" }
docker exec -e FRAPPE_SITE=$FrappeSite -w /home/frappe/frappe-bench/sites $Container ../env/bin/python -W ignore "mes_images/import_item_images.py" "mes_images/images" "mes_images/item_images.yaml" "mes_images/report" @extra
$code = $LASTEXITCODE
docker cp "${Container}:$dest/report/item-image-import.md" (Join-Path $mes "state\item-image-import.md") | Out-Null
docker cp "${Container}:$dest/report/item-image-import.json" (Join-Path $mes "state\item-image-import.json") | Out-Null
if ($code -ne 0) { throw "Image import finished with failures (exit $code); see mes/state/item-image-import.md" }
