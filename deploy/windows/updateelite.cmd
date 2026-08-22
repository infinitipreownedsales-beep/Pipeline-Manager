@echo off
REM ==========================================================================================
REM  updateelite  —  safe pull of the current repair branch, then relaunch via startelite
REM ==========================================================================================
REM  NON-DESTRUCTIVE: no reset --hard, no clean, no DB touch. Refuses to pull over uncommitted
REM  local work. The permanent DB lives OUTSIDE the repo (C:\ElitePipeline\data) so a pull can
REM  never affect it.
REM ==========================================================================================
setlocal EnableExtensions
set "ELITE_REPO=C:\Code\Pipeline-Manager"
set "ELITE_BRANCH=elite-pipeline-repair-2026-08-15"

if not exist "%ELITE_REPO%\.git" (
  echo [updateelite] No git repo at "%ELITE_REPO%".
  endlocal & exit /b 2
)
pushd "%ELITE_REPO%"

echo [updateelite] current version:
git rev-parse --short HEAD

REM refuse to pull over uncommitted changes (never discard local work)
set "DIRTY="
for /f "delims=" %%s in ('git status --porcelain') do set "DIRTY=1"
if defined DIRTY (
  echo(
  echo [updateelite] Uncommitted local changes are present — NOT pulling ^(your work is safe^).
  git status --short
  echo   Commit or stash them first, then run updateelite again.
  popd & endlocal & exit /b 3
)

echo [updateelite] fetching + fast-forwarding %ELITE_BRANCH% ...
git fetch origin %ELITE_BRANCH% || (echo [updateelite] fetch failed & popd & endlocal & exit /b 4)
git checkout %ELITE_BRANCH% 1>nul 2>nul
git merge --ff-only origin/%ELITE_BRANCH%
if errorlevel 1 (
  echo [updateelite] Could not fast-forward ^(history diverged^). No changes made. Resolve manually.
  popd & endlocal & exit /b 5
)

echo [updateelite] updated version:
git rev-parse --short HEAD
echo [updateelite] permanent DB at C:\ElitePipeline\data\elite.db is untouched.
popd

echo [updateelite] restarting Elite ...
call startelite
endlocal & exit /b %ERRORLEVEL%
