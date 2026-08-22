@echo off
REM ==========================================================================================
REM  startelite  —  safe permanent launcher for the Elite Pipeline pilot (Windows)
REM ==========================================================================================
REM  This script contains NO secret. It loads ELITE_AUTH_SECRET from a LOCAL, untracked file
REM  (%ELITE_HOME%\config\elite.env) so the credential pepper is never committed to git and the
REM  existing login credentials keep working. It never touches the permanent database.
REM
REM  Runtime contract (verified against elite.ops.cli serve / elite.ui.serve.build_app):
REM    ELITE_ENV=pilot   ELITE_PILOT_SCOPE=<store>   ELITE_AUTH_SECRET=<pepper>   ELITE_DB_PATH=<db>
REM  Serves http://127.0.0.1:8010/login
REM ==========================================================================================
setlocal EnableExtensions

REM --- fixed deployment locations (edit here only if the machine layout changes) ---
set "ELITE_REPO=C:\Code\Pipeline-Manager"
set "ELITE_HOME=C:\ElitePipeline"
set "ELITE_DB_PATH=%ELITE_HOME%\data\elite.db"
set "ELITE_CONFIG=%ELITE_HOME%\config\elite.env"

REM --- required runtime identity (NOT secret) ---
set "ELITE_ENV=pilot"
set "ELITE_PILOT_SCOPE=store:HG_INFINITI_JACKSON"
set "ELITE_SINGLE_OPERATOR_PILOT=1"
set "ELITE_UI_PORT=8010"

REM --- load the local secret + any local overrides from the untracked config file ---
if not exist "%ELITE_CONFIG%" (
  echo(
  echo [startelite] CONFIG MISSING: "%ELITE_CONFIG%"
  echo   The credential secret is not configured on this machine.
  echo   Run the one-time installer, or create the file with a single line:
  echo       ELITE_AUTH_SECRET=your-existing-secret
  echo   Use the SAME secret you launched with before, or existing logins will not verify.
  echo(
  endlocal & exit /b 2
)
REM read KEY=VALUE lines (ignore blanks and lines beginning with #)
for /f "usebackq eol=# tokens=1,* delims==" %%K in ("%ELITE_CONFIG%") do (
  if not "%%~K"=="" set "%%~K=%%~L"
)

if not defined ELITE_AUTH_SECRET (
  echo [startelite] ELITE_AUTH_SECRET is not set in "%ELITE_CONFIG%". Add: ELITE_AUTH_SECRET=your-existing-secret
  endlocal & exit /b 2
)
if not exist "%ELITE_DB_PATH%" (
  echo [startelite] Permanent DB not found at "%ELITE_DB_PATH%". Not creating one. Check the path.
  endlocal & exit /b 2
)
if not exist "%ELITE_REPO%\elite\ops\cli.py" (
  echo [startelite] Repo not found at "%ELITE_REPO%". Check the checkout location.
  endlocal & exit /b 2
)

REM --- launch the canonical entry point from the repo (absolute cd; not dependent on CWD) ---
pushd "%ELITE_REPO%"
echo [startelite] env=%ELITE_ENV% scope=%ELITE_PILOT_SCOPE% db=%ELITE_DB_PATH% (secret loaded, not shown)
echo [startelite] open http://127.0.0.1:%ELITE_UI_PORT%/login
python -m elite.ops.cli serve
set "RC=%ERRORLEVEL%"
popd
endlocal & exit /b %RC%
