param([string]$Container, [string]$FrappeSite, [switch]$TestUsers, [switch]$SkipBackup,
      [string]$SiteConfig = (Join-Path (Split-Path -Parent $PSScriptRoot) "sites\p1-shah-alam.yaml"))
# Creates/updates the shopfloor DocTypes, then installs every MES server script. -TestUsers adds the site YAML test_users (no passwords).
$ErrorActionPreference = "Stop"
$common = @{ SiteConfig = $SiteConfig }
if ($Container) { $common.Container = $Container }
if ($FrappeSite) { $common.FrappeSite = $FrappeSite }
& (Join-Path $PSScriptRoot "install-mes.ps1") @common -Only doctypes -TestUsers:$TestUsers -SkipBackup:$SkipBackup
& (Join-Path $PSScriptRoot "install-mes.ps1") @common -Only scripts -SkipBackup
