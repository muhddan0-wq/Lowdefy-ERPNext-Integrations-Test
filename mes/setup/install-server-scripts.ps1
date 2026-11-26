param([string]$Container, [string]$FrappeSite, [switch]$SkipBackup,
      [string]$SiteConfig = (Join-Path (Split-Path -Parent $PSScriptRoot) "sites\p1-shah-alam.yaml"))
# Installs/updates every mes/server_scripts/mes_*.py as an API Server Script on the site.
$ErrorActionPreference = "Stop"
$common = @{ SiteConfig = $SiteConfig }
if ($Container) { $common.Container = $Container }
if ($FrappeSite) { $common.FrappeSite = $FrappeSite }
& (Join-Path $PSScriptRoot "install-mes.ps1") @common -Only scripts -SkipBackup:$SkipBackup
