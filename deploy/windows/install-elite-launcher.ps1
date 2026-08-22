<#
  install-elite-launcher.ps1  —  ONE-TIME setup so `startelite` / `updateelite` work from any
  new PowerShell window. Safe and idempotent: creates local dirs, copies the launcher scripts
  from the repo, stores the auth secret in a LOCAL untracked file (never git, never chat), and
  adds the launcher dir to the USER PATH without duplicating it. It never touches the database.

  Usage (run once, from any PowerShell window):
      powershell -ExecutionPolicy Bypass -File C:\Code\Pipeline-Manager\deploy\windows\install-elite-launcher.ps1

  It will PROMPT (hidden input) for the auth secret if one is not already stored. Enter the SAME
  secret you launched Elite with before — a different secret will not verify existing logins
  (the vehicle/loaner/program data is unaffected either way).
#>
[CmdletBinding()]
param(
  [string]$Repo   = "C:\Code\Pipeline-Manager",
  [string]$Home_  = "C:\ElitePipeline",
  [string]$AuthSecret = ""          # optional; if omitted you are prompted with hidden input
)
$ErrorActionPreference = "Stop"

$binDir    = Join-Path $Home_ "bin"
$cfgDir    = Join-Path $Home_ "config"
$cfgFile   = Join-Path $cfgDir "elite.env"
$srcDir    = Join-Path $Repo  "deploy\windows"

Write-Host "[install] repo=$Repo  home=$Home_"

# 1) local dirs (config + bin live OUTSIDE the git repo)
New-Item -ItemType Directory -Force -Path $binDir, $cfgDir | Out-Null

# 2) copy the launcher scripts from the repo into the local bin dir
foreach ($f in @("startelite.cmd","updateelite.cmd")) {
  $src = Join-Path $srcDir $f
  if (-not (Test-Path $src)) { throw "missing launcher template: $src (is the repo checked out?)" }
  Copy-Item $src (Join-Path $binDir $f) -Force
  Write-Host "[install] installed $f -> $binDir"
}

# 3) auth secret -> local untracked config file (only if not already present)
$hasSecret = (Test-Path $cfgFile) -and ((Get-Content $cfgFile -Raw) -match "(?m)^\s*ELITE_AUTH_SECRET\s*=\s*\S")
if ($hasSecret -and -not $AuthSecret) {
  Write-Host "[install] existing ELITE_AUTH_SECRET kept in $cfgFile (not changed)."
} else {
  if (-not $AuthSecret) {
    $sec = Read-Host -AsSecureString "Enter the Elite auth secret (hidden; use the SAME one as before)"
    $AuthSecret = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR(
                    [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
  }
  if (-not $AuthSecret) { throw "no secret entered; nothing written" }
  # write the env file (single authoritative secret line; UTF-8 no BOM so the .cmd parser reads it cleanly)
  $line = "ELITE_AUTH_SECRET=$AuthSecret"
  [System.IO.File]::WriteAllText($cfgFile, "$line`r`n", (New-Object System.Text.UTF8Encoding($false)))
  # lock the file down to the current user only (best-effort)
  try {
    icacls $cfgFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
  } catch { Write-Host "[install] (note) could not tighten ACL on $cfgFile" }
  Write-Host "[install] auth secret stored in $cfgFile (hidden; not echoed)."
}

# 4) add bin to USER PATH idempotently (no duplicates, no setx 1024-char truncation)
$userPath = [Environment]::GetEnvironmentVariable("Path","User")
if (-not $userPath) { $userPath = "" }
$parts = $userPath.Split(';') | Where-Object { $_ -ne "" }
if ($parts -notcontains $binDir) {
  $newPath = (($parts + $binDir) -join ';')
  [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
  Write-Host "[install] added $binDir to USER PATH."
} else {
  Write-Host "[install] $binDir already on USER PATH."
}

Write-Host ""
Write-Host "[install] DONE. Open a NEW PowerShell window, then:"
Write-Host "    updateelite     # pull the latest app"
Write-Host "    startelite      # launch, then open http://127.0.0.1:8010/login"
Write-Host "[install] permanent DB at $($Home_)\data\elite.db is preserved and untouched."
