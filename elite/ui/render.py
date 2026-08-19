"""Safe HTML rendering helpers for the operator app.

Every dynamic value is escaped (`html.escape`). Status is conveyed by TEXT (a label + a shape glyph),
never by color alone. The shell exposes application/environment, the authenticated Principal, the current
scope, navigation, an attention count, a freshness + data-quality indicator, the current revision, help,
and safe unauthorized/error states. No external assets — all CSS is inline and self-hosted.
"""
from __future__ import annotations

from html import escape as _e

# Text glyphs so status never depends on color alone.
STATUS_GLYPH = {
    "ok": "●", "healthy": "●", "attention": "▲", "blocked": "■", "stale": "◷", "expired": "◌",
    "failed": "✕", "unresolved": "?", "scenario": "◇", "completed": "✓", "pending": "…",
}

# Daily OPERATOR navigation — the dealership-facing product. Governance / engineering surfaces are NOT
# here; they live behind the secondary Admin index so normal operation never hits a permission wall.
NAV = [
    ("/", "Pipeline"), ("/ordering", "Ordering"), ("/dealer-trade", "Dealer Trade"),
    ("/wholesale", "Wholesale"), ("/service-loaner", "Service Loaners"), ("/demos", "Demos"),
    ("/ctp", "CTP"),
]
NAV_END = [("/data", "Data")]

# Internal governance / engineering screens — reachable only from the Admin index (/admin), never primary.
ADMIN_NAV = [
    ("/inbox", "Decision Inbox"), ("/new-inventory", "New Inventory (engine board)"),
    ("/production", "Production & Supply"), ("/executive-demo", "Executive Demo (backend)"),
    ("/scenarios", "Scenarios"), ("/calibration", "Learning & Calibration"),
    ("/approvals", "Approvals"), ("/execution", "Execution"), ("/exceptions", "Exceptions"),
    ("/audit", "Audit"), ("/authority", "Authority"), ("/readiness", "Readiness"),
]

_CSS = """
/* ============================================================================================
   ELITE PIPELINE — DESIGN TOKEN SYSTEM  (Slice 1: global system + shell + login)
   One coherent visual language for every operator screen. Status is conveyed by TEXT + shape,
   never by color alone; semantic color (ready / timing / danger) is separate from the command
   accent. Fonts are LOCAL-SAFE stacks (no runtime/CDN dependency): the intended faces are named
   first and picked up automatically if the Windows deployment installs them, otherwise the app
   falls back to Segoe UI / Consolas which carry the same hierarchy fully offline.
   ============================================================================================ */
:root{
  /* type — intended character first, local-safe Windows fallback second (offline-proof) */
  --font-display:"Archivo","Segoe UI Variable Display","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
  --font-body:"IBM Plex Sans","Segoe UI","Segoe UI Variable Text",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
  --font-mono:"IBM Plex Mono",ui-monospace,"Cascadia Mono","Cascadia Code",Consolas,"SF Mono",Menlo,"Liberation Mono",monospace;
  /* reading surfaces (cool-biased neutrals — chosen, not default grey) */
  --fg:#171b22;--muted:#4c5663;--faint:#6b7684;
  --line:#dbe1e9;--line-2:#eceff4;--bg:#f3f6f9;--card:#ffffff;--raise:#fbfcfe;
  /* command surface (graphite) — where the operator acts (top command bar) */
  --cmd:#10151d;--cmd-2:#19212c;--cmd-line:#2b3542;--cmd-fg:#eef2f7;--cmd-muted:#94a2b4;
  /* semantic palette (independent of the command accent) */
  --accent:#2f6fed;--accent-fg:#ffffff;--accent-weak:#eaf1fe;--accent-line:#c3d8fb;
  --ready:#17936a;--ready-weak:#e6f4ee;--ready-line:#bfe3d3;
  --timing:#c07d18;--timing-weak:#fbf1dd;--timing-line:#ecd3a0;
  --danger:#c8443c;--danger-weak:#fbeceb;--danger-line:#eec4c1;
  --slate:#5d6775;
  --focus:#7db3f0;
  --r-sm:6px;--r:9px;--r-lg:12px;
  --shadow:0 1px 2px rgba(16,21,29,.05),0 2px 8px rgba(16,21,29,.04);
}
@media (prefers-color-scheme: dark){
  /* restrained dark — legible on a dark OS, NOT a fashion statement. Command bar stays graphite;
     only reading surfaces flip. */
  :root:not([data-theme="light"]){
    --fg:#e6eaf1;--muted:#a5b0be;--faint:#8390a0;
    --line:#2a333f;--line-2:#222a34;--bg:#0d1117;--card:#161c25;--raise:#1c232d;
    --accent:#5b8cf5;--accent-weak:#182335;--accent-line:#294067;
    --ready:#3bb488;--ready-weak:#12241d;--ready-line:#254a3b;
    --timing:#dc9a3a;--timing-weak:#2a2213;--timing-line:#4d3c1c;
    --danger:#e06a62;--danger-weak:#2a1716;--danger-line:#4d2622;
    --shadow:0 1px 2px rgba(0,0,0,.4);
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;font:15px/1.55 var(--font-body);color:var(--fg);background:var(--bg);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:var(--accent)}
h1,h2,h3{font-family:var(--font-display);letter-spacing:-.01em;text-wrap:balance}
h1{font-size:23px;font-weight:700;margin:6px 0 12px}
h2{font-size:17px;font-weight:600;margin:20px 0 8px}
.skip{position:absolute;left:-9999px;top:0;z-index:50;background:var(--accent);color:#fff;
  padding:8px 14px;border-radius:0 0 var(--r) 0;font-weight:600}
.skip:focus{left:0}
/* ---- command bar (top navigation — chosen over a left rail to preserve work-surface width) ---- */
header.shell{background:var(--cmd);color:var(--cmd-fg);border-bottom:1px solid #05080c}
.shell-in{display:flex;align-items:center;gap:18px;padding:9px 20px;flex-wrap:wrap;
  max-width:1600px;margin:0 auto}
.shell .brand{display:inline-flex;align-items:center;gap:9px;font-family:var(--font-display);
  font-weight:700;letter-spacing:-.01em;color:var(--cmd-fg);font-size:15.5px;white-space:nowrap}
.shell .mark{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:7px;
  background:linear-gradient(160deg,var(--accent),#1d4fbf);color:#fff;font-size:12px;font-weight:800;letter-spacing:.02em}
.shell .ctx{color:var(--cmd-muted);font-size:12.5px;white-space:nowrap}
.shell .ctx b,.shell .ctx strong{color:var(--cmd-fg);font-weight:600}
.shell .spacer{flex:1}
.shell .shell-ctx{display:inline-flex;align-items:center;gap:14px;flex-wrap:wrap}
.shell .shell-ctx a{color:var(--cmd-muted);text-decoration:none;font-size:12.5px}
.shell .shell-ctx a:hover{color:var(--cmd-fg)}
.shell .env{border:1px solid var(--cmd-line);border-radius:20px;padding:1px 9px;font-size:11.5px;
  color:var(--cmd-muted);text-transform:lowercase}
/* primary nav lives inside the command bar (compact, horizontal) */
nav.primary{display:flex;flex-wrap:wrap;gap:2px;align-items:center}
nav.primary a{padding:6px 12px;border-radius:7px;text-decoration:none;color:#cfd7e2;
  font-weight:600;font-size:13.5px;letter-spacing:.005em;white-space:nowrap}
nav.primary a:hover{background:rgba(255,255,255,.08);color:#fff}
nav.primary a[aria-current=page]{background:var(--accent);color:#fff}
nav.primary .navspacer{width:1px;align-self:stretch;background:var(--cmd-line);margin:3px 7px}
nav.primary a.admin{font-weight:500;color:var(--cmd-muted);font-size:12.5px}
nav.primary a.admin:hover{color:var(--cmd-fg)}
/* ---- trust strip (honest source-health ribbon) ---- */
.trust{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding:7px 20px;
  background:var(--card);border-bottom:1px solid var(--line);font-size:12.5px;color:var(--muted)}
.trust .date{font-weight:600;color:var(--fg);font-variant-numeric:tabular-nums}
.trust .src{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.trust .dot{width:8px;height:8px;border-radius:50%;display:inline-block;box-shadow:0 0 0 1px rgba(0,0,0,.08) inset}
.dot.green{background:var(--ready)}.dot.yellow{background:var(--timing)}.dot.red{background:var(--danger)}.dot.gray{background:#aab4c0}
.trust .upd{margin-left:auto;font-weight:600;text-decoration:none;white-space:nowrap}
.trust .upd:hover{text-decoration:underline}
/* ---- work area ---- */
main{max-width:1180px;margin:0 auto;padding:24px 22px 48px}
main.wide{max-width:1360px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r-lg);padding:15px;margin:12px 0;box-shadow:var(--shadow)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:12.5px;letter-spacing:.02em}
td{font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:1px 9px;border:1px solid var(--line);border-radius:20px;font-size:12px;white-space:nowrap;color:var(--muted)}
.scenario{border-style:dashed}.stale{background:var(--timing-weak)}.muted{color:var(--muted)}
.callout{border-left:3px solid var(--accent);padding:9px 13px;background:var(--accent-weak);border-radius:0 var(--r) var(--r) 0}
form.mut{display:inline}button,input,select,textarea{font:inherit}
button{padding:7px 13px;border:1px solid var(--accent);background:var(--accent);color:var(--accent-fg);border-radius:var(--r-sm);cursor:pointer;font-weight:600}
button:hover{filter:brightness(1.05)}
button.secondary{background:var(--card);color:var(--accent)}
label{display:block;font-size:12.5px;color:var(--muted);margin:9px 0 3px;font-weight:500}
input,select,textarea{width:100%;max-width:520px;padding:8px 9px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--card);color:var(--fg)}
:focus-visible{outline:3px solid var(--focus);outline-offset:1px}
:focus{outline:3px solid var(--focus);outline-offset:1px}
.err{border-left:3px solid var(--danger);background:var(--danger-weak);padding:11px 13px;border-radius:0 var(--r) var(--r) 0}
.empty{color:var(--muted);padding:26px;text-align:center;border:1px dashed var(--line);border-radius:var(--r-lg)}
.kv{display:grid;grid-template-columns:200px 1fr;gap:3px 14px}.kv dt{color:var(--muted)}.kv dd{margin:0}
.bars{display:grid;gap:7px;margin:8px 0}
.bars .brow{display:grid;grid-template-columns:150px 1fr auto;gap:10px;align-items:center;font-size:13px}
.bars .blabel{color:var(--fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bars .track{background:var(--bg);border:1px solid var(--line);border-radius:var(--r-sm);height:16px;position:relative;overflow:hidden}
.bars .fill{position:absolute;left:0;top:0;height:100%;background:var(--accent);opacity:.85}
.bars .bval{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.dist .track{background:var(--bg);border:1px solid var(--line);border-radius:var(--r-sm);height:18px;position:relative;overflow:hidden}
.dist .iqr{position:absolute;top:0;height:100%;background:var(--accent);opacity:.32}
.dist .med{position:absolute;top:0;width:2px;height:100%;background:var(--accent)}
.dist .cap{position:absolute;top:50%;width:1px;height:10px;transform:translateY(-50%);background:var(--muted)}
/* --- workflow cockpit components (structure unchanged this slice; retuned to the token palette) --- */
.wshead{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin:2px 0 6px}
.wshead h1{margin:0}
.mnav{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap}
.mnav a,.mnav span.cur{padding:6px 12px;border:1px solid var(--line);border-radius:var(--r-sm);text-decoration:none;color:var(--fg);font-size:14px;background:var(--card)}
.mnav a:hover{background:var(--bg)}
.mnav .cur{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:700}
.mnav form.mut{display:inline-flex;gap:6px;align-items:center;margin-left:4px}
.mnav select{max-width:180px;padding:6px}
.stat{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0}
.metric{border:1px solid var(--line);border-radius:var(--r);padding:9px 13px;min-width:96px;background:var(--card)}
.metric .v{font-family:var(--font-display);font-size:21px;font-weight:700;line-height:1.05;font-variant-numeric:tabular-nums}
.metric .l{font-size:12px;color:var(--muted);margin-top:2px}
.metric.attn .v{color:var(--accent)}
.progress{height:10px;border-radius:var(--r-sm);background:var(--bg);border:1px solid var(--line);overflow:hidden;margin:8px 0 4px;max-width:360px}
.progress .p{height:100%;background:var(--ready)}
.chip{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:20px;font-size:12px;border:1px solid var(--line);white-space:nowrap}
.chip.need{background:var(--accent-weak);border-color:var(--accent-line);color:var(--accent);font-weight:600}
.chip.done{background:var(--ready-weak);border-color:var(--ready-line);color:var(--ready)}
.chip.skip{background:var(--line-2);color:var(--muted)}
.chip.bench{background:var(--timing-weak);border-color:var(--timing-line);color:var(--timing)}
.queue{display:grid;gap:10px;margin:10px 0}
.rec{border:1px solid var(--line);border-radius:var(--r-lg);padding:13px 15px;background:var(--card);display:grid;grid-template-columns:auto 1fr auto;gap:6px 16px;align-items:start;box-shadow:var(--shadow)}
.rec.resolved{opacity:.62;background:var(--bg);box-shadow:none}
.rec .rank{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;padding-top:4px}
.rec .body{min-width:0}
.rec .ident{font-weight:600;font-size:15px}
.rec .call{font-family:var(--font-display);font-size:22px;font-weight:800;letter-spacing:-.01em;margin:2px 0 4px}
.rec .pos{color:var(--muted);font-size:13px}
.rec .side{text-align:right;display:flex;flex-direction:column;gap:6px;align-items:flex-end}
.rec details{margin-top:6px}
.rec details>summary{cursor:pointer;color:var(--accent);font-size:13px}
.rec .why{margin-top:6px;font-size:13px}
.actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.actions form.mut{display:inline}
.actions button{padding:6px 12px;font-size:13px}
.restraint{border-left:3px solid var(--ready);background:var(--ready-weak);padding:11px 14px;border-radius:0 var(--r) var(--r) 0;margin:10px 0}
.restraint strong{color:var(--ready)}
/* compact recommendation row (ranks 4..N) — one-line-scannable sibling of the rich card */
.recrow{display:flex;align-items:center;gap:6px 14px;flex-wrap:wrap;padding:8px 13px;border:1px solid var(--line);border-radius:var(--r);background:var(--card)}
.recrow.resolved{opacity:.6;background:var(--bg)}
.recrow .rrank{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums;min-width:1.6em;text-align:right}
.recrow .rcall{font-family:var(--font-display);font-weight:800;font-size:15px;letter-spacing:-.01em;white-space:nowrap;min-width:74px}
.recrow .rmain{flex:1;min-width:170px;display:flex;gap:2px 10px;flex-wrap:wrap;align-items:baseline}
.recrow .rident{font-weight:600;font-size:14px}
.recrow .rident a{color:var(--accent);text-decoration:none}.recrow .rident a:hover{text-decoration:underline}
.recrow .rpos{color:var(--muted);font-size:12.5px;font-variant-numeric:tabular-nums}
.recrow .rside{display:flex;align-items:center;gap:8px;margin-left:auto;flex-wrap:wrap;justify-content:flex-end}
.recrow .rside .actions{gap:5px}.recrow .rside .actions button{padding:4px 9px;font-size:12.5px}
.recrow .rwhy{flex-basis:100%;margin-top:1px}
.recrow .rwhy>details>summary{cursor:pointer;color:var(--accent);font-size:12.5px}
.recrow .rwhy .why{margin-top:6px;font-size:13px}
/* collapsed, receded group for handled/worked items */
.workgroup{margin:10px 0}
.workgroup>summary{cursor:pointer;color:var(--muted);font-size:13px;font-weight:600;padding:6px 2px}
.workgroup>summary:hover{color:var(--fg)}
.worklist{display:grid;gap:6px;margin-top:6px}
ol.timeline{list-style:none;padding-left:0}ol.timeline li{padding:6px 0 6px 16px;border-left:2px solid var(--line);margin-left:6px}
/* ---- login / auth experience (chrome-free; no operator nav) ---- */
body.auth{background:linear-gradient(180deg,var(--cmd) 0,var(--cmd) 210px,var(--bg) 210px,var(--bg) 100%);min-height:100vh}
.authwrap{max-width:420px;margin:0 auto;padding:56px 20px 40px}
.authbrand{display:inline-flex;align-items:center;gap:10px;color:var(--cmd-fg);font-family:var(--font-display);
  font-weight:700;font-size:19px;letter-spacing:-.01em;margin-bottom:4px}
.authbrand .mark{width:30px;height:30px;font-size:13px}
.authsub{color:var(--cmd-muted);font-size:13px;margin:0 0 26px}
.authcard{background:var(--card);border:1px solid var(--line);border-radius:var(--r-lg);padding:22px;box-shadow:0 8px 30px rgba(16,21,29,.12)}
.authcard h1{font-size:18px;margin:0 0 4px}
.authcard .lede{color:var(--muted);font-size:13px;margin:0 0 12px}
.authcard input{max-width:none}
.authcard button{width:100%;padding:10px;font-size:15px;margin-top:14px}
.authfoot{color:var(--muted);font-size:12px;text-align:center;margin-top:18px}
/* ---- responsive shell ---- */
@media(max-width:900px){
  .shell-in{gap:10px 14px}
  .shell .shell-ctx{gap:10px}
  nav.primary{order:3;width:100%}
}
@media(max-width:720px){.rec{grid-template-columns:1fr}.rec .side{text-align:left;align-items:flex-start}.actions{justify-content:flex-start}}
@media(max-width:640px){.kv{grid-template-columns:1fr}main{padding:14px 12px 32px}.shell .spacer{display:none}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""


def esc(v):
    return _e("" if v is None else str(v))


def esc_text(v):
    """Escape for element TEXT content (leaves quotes/apostrophes literal — still XSS-safe because
    `<`, `>`, and `&` are escaped). Use for human-readable prose shown verbatim, never in attributes."""
    return _e("" if v is None else str(v), quote=False)


def badge(kind, text=None):
    g = STATUS_GLYPH.get((kind or "").lower(), "•")
    label = text if text is not None else (kind or "")
    cls = "badge scenario" if kind == "scenario" else ("badge stale" if kind == "stale" else "badge")
    return f'<span class="{cls}"><span aria-hidden="true">{g}</span> {esc(label)}</span>'


def _trust_strip(ctx):
    """Permanent top trust strip: today's date + four source-health indicators. Freshness is honest —
    a source with no known successful load shows NOT LOADED (gray), never a fabricated 'fresh'."""
    date = esc(ctx.get("today", "—"))
    srcs = ctx.get("sources") or []
    chips = ""
    for label, word, tone in srcs:
        chips += (f'<span class="src" title="{esc(label)}: {esc(word)}">'
                  f'<span class="dot {esc(tone)}" aria-hidden="true"></span>{esc(label)}: {esc(word)}</span>')
    return (f'<div class="trust" role="contentinfo" aria-label="Source data health">'
            f'<span class="date">{date}</span>{chips}'
            f'<a class="upd" href="/data">Update Data →</a></div>')


def page(title, body, *, ctx=None, active_path="/", flash=None, wide=False, hide_title=False):
    """Render the full operator shell around `body` (already-safe HTML). `wide` widens the work area for
    desktop cockpit screens; `hide_title` omits the default <h1> when `body` provides its own workspace
    header (title + context navigator)."""
    ctx = ctx or {}
    nav = "".join(
        f'<a href="{esc(p)}"{" aria-current=page" if p == active_path else ""}>{esc(label)}</a>'
        for p, label in NAV)
    nav += '<span class="navspacer" aria-hidden="true"></span>'
    nav += "".join(
        f'<a href="{esc(p)}"{" aria-current=page" if p == active_path else ""}>{esc(label)}</a>'
        for p, label in NAV_END)
    nav += '<a class="admin" href="/admin">Admin</a>'
    # Compact top command bar (graphite): brand + inline primary nav + operator context on one line.
    # Chosen over a left rail so wide work surfaces (Pipeline / CPO / Dealer Trade) keep full width.
    header = (
        '<header class="shell" role="banner"><div class="shell-in">'
        '<span class="brand"><span class="mark" aria-hidden="true">EP</span>Elite Pipeline</span>'
        f'<nav class="primary" role="navigation" aria-label="Primary">{nav}</nav>'
        '<span class="spacer"></span>'
        '<span class="shell-ctx">'
        f'<span class="ctx">{esc(ctx.get("principal_name", "—"))}</span>'
        f'<span class="ctx">Store <b>{esc(ctx.get("scope", "—"))}</b></span>'
        f'<span class="badge env">{esc(ctx.get("environment", "?"))}</span>'
        '<a href="/help">Help</a>'
        '<a href="/logout">Sign out</a>'
        '</span></div></header>')
    flash_html = f'<div class="callout" role="status">{esc(flash)}</div>' if flash else ""
    title_html = "" if hide_title else f'<h1>{esc(title)}</h1>'
    main_cls = "wide" if wide else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(title)} — Elite Pipeline</title><style>{_CSS}</style></head>'
            f'<body><a class="skip" href="#work">Skip to work area</a>{header}{_trust_strip(ctx)}'
            f'<main id="work" role="main" class="{main_cls}">{title_html}{flash_html}{body}</main></body></html>')


def auth_page(title, body, *, ctx=None, subtitle="Dealership inventory operating system"):
    """The sign-in experience — deliberately chrome-free: no operator navigation, no trust strip, no
    store/principal context (there is no authenticated operator yet). A graphite brand band tops a single
    focused card. `body` is already-safe HTML (the form or an error)."""
    ctx = ctx or {}
    env = esc(ctx.get("environment", "?"))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(title)} — Elite Pipeline</title><style>{_CSS}</style></head>'
            f'<body class="auth"><main id="work" role="main"><div class="authwrap">'
            f'<div class="authbrand"><span class="mark" aria-hidden="true">EP</span>Elite Pipeline</div>'
            f'<p class="authsub">{esc(subtitle)} · <span style="opacity:.8">{env}</span></p>'
            f'<div class="authcard">{body}</div>'
            f'<p class="authfoot">Runs locally · your session never leaves this store</p>'
            f'</div></main></body></html>')


def empty(msg):
    return f'<p class="empty">{esc(msg)}</p>'


def table(headers, rows):
    if not rows:
        return empty("Nothing here right now.")
    head = "".join(f"<th scope=col>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="card" style="overflow-x:auto"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def kv(pairs):
    items = "".join(f"<dt>{esc(k)}</dt><dd>{v if _is_html(v) else esc(v)}</dd>" for k, v in pairs)
    return f'<dl class="kv">{items}</dl>'


def bars(rows, *, max_value=None, unit="", caption=None):
    """A labeled horizontal-bar chart. `rows` = list of (label, value[, value_text]). The numeric value is
    always shown as text (never color-alone). Answers 'how big is each category relative to the largest'."""
    vals = [(r[2] if len(r) > 2 else None, float(r[1] or 0)) for r in rows]
    mx = max_value if max_value is not None else max([v for _t, v in vals] + [0]) or 1
    out = ['<div class="bars" role="img"' + (f' aria-label="{esc(caption)}"' if caption else "") + ">"]
    for (label, value, *rest) in rows:
        vt = rest[0] if rest else (f"{value:g}{unit}")
        pct = max(0.0, min(100.0, (float(value or 0) / mx) * 100.0))
        out.append(f'<div class="brow"><span class="blabel" title="{esc(label)}">{esc(label)}</span>'
                   f'<span class="track"><span class="fill" style="width:{pct:.1f}%"></span></span>'
                   f'<span class="bval">{esc(vt)}</span></div>')
    out.append("</div>")
    return "".join(out)


def dist_row(label, dist, *, scale_max, unit=" days"):
    """One historical-distribution row: a light IQR box (p25–p75) with a median marker + min/max whiskers,
    all values labeled in text. `dist` is a mapping/obj with minimum/p25/median/p75/maximum/count."""
    def g(k):
        v = getattr(dist, k, None) if not isinstance(dist, dict) else dist.get(k)
        return None if v is None else float(v)
    lo, q1, med, q3, hi, n = g("minimum"), g("p25"), g("median"), g("p75"), g("maximum"), (
        getattr(dist, "count", None) if not isinstance(dist, dict) else dist.get("count"))
    sm = float(scale_max) or 1.0
    def pct(v):
        return max(0.0, min(100.0, (v / sm) * 100.0)) if v is not None else 0.0
    track = ""
    if med is not None:
        left, right = pct(q1 if q1 is not None else med), pct(q3 if q3 is not None else med)
        track = (f'<span class="cap" style="left:{pct(lo):.1f}%"></span>'
                 f'<span class="iqr" style="left:{left:.1f}%;width:{max(0.6, right-left):.1f}%"></span>'
                 f'<span class="med" style="left:{pct(med):.1f}%"></span>'
                 f'<span class="cap" style="left:{pct(hi):.1f}%"></span>')
    txt = (f"med {med:g}{unit} · IQR {q1:g}–{q3:g} · n={n}" if med is not None else "no usable sample")
    return ('<div class="dist" style="margin:6px 0">'
            f'<div style="font-size:13px;margin-bottom:3px">{esc(label)} — <span class="muted">{esc(txt)}</span></div>'
            f'<div class="track">{track}</div></div>')


def _is_html(v):
    return isinstance(v, _Html)


class _Html(str):
    """Marks an already-safe HTML fragment so kv() won't re-escape it."""


def safe(s):
    return _Html(s)


# --- canonical workflow-cockpit components (reusable across domains) -------------------------------------
def workspace_header(title, right_html=""):
    """Page title paired with a strong context control (e.g. a month navigator) on the right."""
    return (f'<div class="wshead"><h1>{esc(title)}</h1>'
            f'<div class="mnav">{right_html if _is_html(right_html) else esc(right_html)}</div></div>')


def month_nav(base_path, prev, cur, nxt, *, jump_html=""):
    """Deterministic server-backed month navigator. `prev`/`cur`/`nxt` are (ym, label); prev/nxt may be
    None to disable an edge. Current month is a plain highlighted label; neighbours are GET links carrying
    ?month=… (no JS, cannot regress a submit-dependent selector). `jump_html` is the secondary jump control."""
    out = []
    if prev:
        out.append(f'<a href="{esc(base_path)}?month={esc(prev[0])}" rel="prev" title="{esc(prev[1])}">‹ {esc(prev[1])}</a>')
    out.append(f'<span class="cur">{esc(cur[1])}</span>')
    if nxt:
        out.append(f'<a href="{esc(base_path)}?month={esc(nxt[0])}" rel="next" title="{esc(nxt[1])}">{esc(nxt[1])} ›</a>')
    if jump_html:
        out.append(jump_html if _is_html(jump_html) else esc(jump_html))
    return safe("".join(out))


def metric(value, label, *, attn=False):
    return f'<div class="metric{" attn" if attn else ""}"><div class="v">{esc(value)}</div><div class="l">{esc(label)}</div></div>'


def stat_row(metrics):
    return f'<div class="stat">{"".join(metrics)}</div>'


def progress(done, total):
    total = max(0, int(total or 0))
    done = max(0, min(int(done or 0), total))
    pct = (done / total * 100.0) if total else 0.0
    return (f'<div class="progress" role="progressbar" aria-valuenow="{done}" aria-valuemin="0" '
            f'aria-valuemax="{total}"><span class="p" style="width:{pct:.0f}%"></span></div>'
            f'<div class="muted" style="font-size:12px">{done} of {total} reviewed</div>')


def chip(kind, text):
    k = {"need": "need", "done": "done", "skip": "skip", "bench": "bench"}.get(kind, "")
    return f'<span class="chip {k}">{esc(text)}</span>'


def disclosure(summary, body_html):
    return f'<details><summary>{esc(summary)}</summary><div class="why">{body_html}</div></details>'


def action_group(buttons_html):
    return f'<div class="actions">{buttons_html}</div>'


def rec_card(rank, ident_html, call, pos_html, why_html, actions_html, *, resolved=False, chip_html=""):
    """A recommendation as an actionable unit: dominant call, secondary position, a Why disclosure, and an
    action group. Resolved (confirmed / not-ordering / benched) cards visibly recede."""
    return (f'<div class="rec{" resolved" if resolved else ""}">'
            f'<div class="rank">{esc(rank)}</div>'
            f'<div class="body"><div class="ident">{ident_html if _is_html(ident_html) else esc(ident_html)}</div>'
            f'<div class="call">{esc(call)}</div>'
            f'<div class="pos">{pos_html if _is_html(pos_html) else esc(pos_html)}</div>'
            f'{why_html}</div>'
            f'<div class="side">{chip_html}{actions_html}</div></div>')


def rec_row(rank, ident_html, call, pos_html, why_html, actions_html, *, resolved=False, chip_html=""):
    """A COMPACT actionable recommendation — the lower-priority sibling of rec_card. Same information and the
    same actions (Confirm / Not ordering / Bench / Undo, Why on request), rendered on essentially one line so
    ranks 4..N of a model stay scannable. Resolved rows recede. The call uses `.rcall` (NOT `.call`) so it is
    never confused with a rich card by callers that key on the hero call."""
    return (f'<div class="recrow{" resolved" if resolved else ""}">'
            f'<span class="rrank">{esc(rank)}</span>'
            f'<span class="rcall">{esc(call)}</span>'
            f'<span class="rmain"><span class="rident">{ident_html if _is_html(ident_html) else esc(ident_html)}</span>'
            f'<span class="rpos">{pos_html if _is_html(pos_html) else esc(pos_html)}</span></span>'
            f'<span class="rside">{chip_html}{actions_html}</span>'
            f'<div class="rwhy">{why_html}</div></div>')


def work_group(summary, rows_html):
    """A collapsed, visibly-receded group for handled/worked items — keeps them one click away (and undoable)
    without letting completed work consume the model's vertical space."""
    return (f'<details class="workgroup"><summary>{esc(summary)}</summary>'
            f'<div class="worklist">{rows_html if _is_html(rows_html) else esc(rows_html)}</div></details>')


def restraint_note(html):
    """Intentionally-open capacity presented as a positive Elite judgment (restraint), not leftover work."""
    return f'<div class="restraint">{html if _is_html(html) else esc(html)}</div>'


def form(action, fields_html, *, csrf, idem=None, submit="Submit", method="post", confirm=None,
         extra_buttons=""):
    """A state-changing form. Carries the CSRF token and a per-render idempotency nonce so a double
    submit replays idempotently rather than duplicating the governed action."""
    hidden = f'<input type="hidden" name="_csrf" value="{esc(csrf)}">'
    if idem is not None:
        hidden += f'<input type="hidden" name="_idem" value="{esc(idem)}">'
    onclick = f' onclick="return confirm({_js(confirm)})"' if confirm else ""
    return (f'<form class="mut" method="{esc(method)}" action="{esc(action)}">{hidden}{fields_html}'
            f'<div style="margin-top:10px"><button type="submit"{onclick}>{esc(submit)}</button>{extra_buttons}</div></form>')


def _js(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def error_page(title, message, *, ctx=None):
    body = f'<div class="err" role="alert"><strong>{esc(title)}</strong><p>{esc(message)}</p>' \
           '<p><a href="/">Return to the Decision Inbox</a></p></div>'
    return page(title, body, ctx=ctx or {})
