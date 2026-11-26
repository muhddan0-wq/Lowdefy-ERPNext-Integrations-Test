param(
    [string]$SiteConfig = (Join-Path (Split-Path -Parent $PSScriptRoot) "sites\p1-shah-alam.yaml"),
    [string]$Container,
    [string]$FrappeSite,
    [ValidateSet("all", "check", "doctypes", "scripts", "roles", "apiuser", "barcodes")][string]$Only = "all",
    [string]$AdminUser,
    [switch]$ResetPassword,
    [switch]$TestUsers,
    [switch]$NewKeys,
    [switch]$Strict,
    [switch]$SkipBackup
)
# Generic MES install against the ERPNext site described by -SiteConfig: precondition check, shopfloor DocTypes,
# server scripts, sector roles and the Appsmith API user. Loads no demo data (that is run-seed.ps1).
$ErrorActionPreference = "Stop"
$mes = Split-Path -Parent $PSScriptRoot
$SiteConfig = (Resolve-Path $SiteConfig).Path
function Get-SiteValue([string]$Key) {
    $v = & python (Join-Path $mes "site_config.py") $SiteConfig $Key
    if ($LASTEXITCODE -ne 0) { throw "Cannot read $Key from $SiteConfig" }
    return "$v".Trim()
}
if (-not $Container) { $Container = Get-SiteValue "erp.container" }
if (-not $FrappeSite) { $FrappeSite = Get-SiteValue "erp.site" }
Write-Host "MES install: $SiteConfig -> container $Container, site $FrappeSite, step $Only"

$bench = "/home/frappe/frappe-bench/sites"
$dest = "mes_install"
function Invoke-Bench([string]$Script, [string[]]$ScriptArgs = @(), [string[]]$EnvVars = @()) {
    $envArgs = @("-e", "FRAPPE_SITE=$FrappeSite")
    foreach ($e in $EnvVars) { $envArgs += @("-e", $e) }
    docker exec @envArgs -w $bench $Container ../env/bin/python -W ignore "$dest/$Script" @ScriptArgs
    if ($LASTEXITCODE -ne 0) { throw "$Script failed (exit $LASTEXITCODE)" }
}

docker exec -u root $Container rm -rf "$bench/$dest" | Out-Null
docker exec $Container mkdir -p "$bench/$dest/src" | Out-Null
foreach ($f in @("check_site.py", "install_shopfloor.py", "install_server_scripts.py", "create_sector_roles.py", "create_api_user.py", "unit_barcodes.py")) {
    docker cp (Join-Path $PSScriptRoot $f) "${Container}:$bench/$dest/$f" | Out-Null
}
Get-ChildItem (Join-Path $mes "server_scripts") -Filter *.py | ForEach-Object {
    docker cp $_.FullName "${Container}:$bench/$dest/src/$($_.Name)" | Out-Null
}
docker cp (Join-Path $mes "site_config.py") "${Container}:$bench/$dest/site_config.py" | Out-Null
docker cp $SiteConfig "${Container}:$bench/$dest/site.yaml" | Out-Null
docker exec -u root $Container chown -R frappe:frappe "$bench/$dest" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Copy into $Container failed" }

try {
    $checkArgs = @()
    if ($Strict) { $checkArgs += "--strict" }
    Invoke-Bench "check_site.py" $checkArgs
    if ($Only -eq "check") { return }

    if (-not $SkipBackup) {
        docker exec -w /home/frappe/frappe-bench $Container bench --site $FrappeSite backup
        if ($LASTEXITCODE -ne 0) { throw "Backup failed" }
    }
    if ($Only -in @("all", "doctypes")) {
        $a = @()
        if ($TestUsers) { $a += "--test-users" }
        Invoke-Bench "install_shopfloor.py" $a
    }
    if ($Only -in @("all", "scripts")) {
        Invoke-Bench "install_server_scripts.py" @("$dest/src", "$dest/site.yaml")
    }
    if ($Only -in @("all", "barcodes")) {
        Invoke-Bench "unit_barcodes.py"
    }
    if ($Only -in @("all", "roles")) {
        $a = @(); $e = @()
        if ($AdminUser) { $e += "NEW_USER=$AdminUser" }
        if ($ResetPassword) { $a += "--reset-password" }
        Invoke-Bench "create_sector_roles.py" $a $e
    }
    if ($Only -in @("all", "apiuser")) {
        $keyFile = "$dest/appsmith-mes.env"
        $a = @()
        if ($NewKeys) { $a += "--new-keys" }
        $out = Invoke-Bench "create_api_user.py" $a @("KEY_FILE=$keyFile")
        $out | ForEach-Object { Write-Host $_ }
        if ($out -match "^KEYS_WRITTEN=") {
            $secrets = Join-Path $mes ".secrets"
            New-Item -ItemType Directory -Force $secrets | Out-Null
            docker cp "${Container}:$bench/$keyFile" (Join-Path $secrets "appsmith-mes.env") | Out-Null
            Write-Host "API keys saved to $(Join-Path $secrets 'appsmith-mes.env'); update the Appsmith datasource with them"
        }
    }
} finally {
    docker exec -u root $Container rm -rf "$bench/$dest" | Out-Null
}
Write-Host "MES install finished ($Only)"
