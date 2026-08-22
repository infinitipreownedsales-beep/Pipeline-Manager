# Elite Pipeline — Windows launcher

Safe, permanent way to run the Elite pilot from any new PowerShell window:

- `startelite`  — launch the app (serves http://127.0.0.1:8010/login)
- `updateelite` — pull the latest app, then relaunch

These scripts contain **no secret** and never touch the database.

## Layout

| Path | What it is |
|------|-----------|
| `C:\Code\Pipeline-Manager` | the git checkout (this repo) |
| `C:\ElitePipeline\data\elite.db` | the **permanent** database (outside the repo — a pull can never affect it) |
| `C:\ElitePipeline\config\elite.env` | **local, untracked** file holding `ELITE_AUTH_SECRET` (never committed) |
| `C:\ElitePipeline\bin` | where `startelite.cmd` / `updateelite.cmd` are installed (added to the USER PATH) |

## One-time install

From any PowerShell window:

```
powershell -ExecutionPolicy Bypass -File C:\Code\Pipeline-Manager\deploy\windows\install-elite-launcher.ps1
```

It creates the local dirs, copies the two `.cmd` launchers into `C:\ElitePipeline\bin`,
prompts (hidden input) for the auth secret and stores it in `C:\ElitePipeline\config\elite.env`,
and adds the bin dir to the USER PATH (idempotent — no duplicate entries).

> Enter the **same** auth secret you launched Elite with before. The pepper is global:
> the same secret verifies existing logins; a different one will not. The vehicle / loaner /
> program data itself is pepper-independent and is unaffected either way.

## Daily use

Open a **new** PowerShell window (so the updated PATH is loaded), then:

```
updateelite
startelite
```

Open http://127.0.0.1:8010/login.

## Runtime contract

`startelite` sets the required runtime identity and launches the canonical entry point
`python -m elite.ops.cli serve`:

| Var | Value | Notes |
|-----|-------|-------|
| `ELITE_ENV` | `pilot` | |
| `ELITE_PILOT_SCOPE` | `store:HG_INFINITI_JACKSON` | |
| `ELITE_AUTH_SECRET` | *(from local `elite.env`)* | credential pepper — never printed, never committed |
| `ELITE_DB_PATH` | `C:\ElitePipeline\data\elite.db` | permanent DB; never created/replaced by the launcher |
| `ELITE_SINGLE_OPERATOR_PILOT` | `1` | sole-operator self-approval |
| `ELITE_UI_PORT` | `8010` | |

`startelite` fails with a clear message (and does **not** launch) if the config file is
missing, the secret is unset, the DB is absent, or the repo is not found.

## Safety notes

- `updateelite` is **non-destructive**: it refuses to pull over uncommitted local changes and
  only ever does a fast-forward merge. There is no `reset --hard`, no `clean`, no DB replacement,
  and no schema recreation anywhere in these scripts.
- If the auth secret is ever truly lost, it cannot be recovered from the DB (it is a pepper, not
  stored). Existing logins only verify under the original secret. Re-enter the original secret to
  restore access; the database is preserved regardless.
