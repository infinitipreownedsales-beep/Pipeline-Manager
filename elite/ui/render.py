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
:root{--fg:#1a1d21;--muted:#5a6470;--line:#d5dbe2;--bg:#f6f8fa;--card:#fff;--accent:#0b5cad}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--fg);background:var(--bg)}
a{color:var(--accent)}header.shell{display:flex;align-items:center;gap:16px;padding:10px 18px;background:var(--card);border-bottom:2px solid var(--line);flex-wrap:wrap}
header.shell .brand{font-weight:700}header.shell .ctx{color:var(--muted);font-size:13px}
header.shell .spacer{flex:1}.attention{font-weight:700}
nav.primary{display:flex;flex-wrap:wrap;gap:4px;padding:8px 16px;background:var(--card);border-bottom:1px solid var(--line);align-items:center}
nav.primary a{padding:8px 14px;border-radius:8px;text-decoration:none;color:var(--fg);font-weight:600;letter-spacing:.01em}
nav.primary a:hover{background:var(--bg)}
nav.primary a[aria-current=page]{background:var(--accent);color:#fff}
nav.primary .navspacer{flex:1}
nav.primary a.admin{font-weight:500;color:var(--muted);font-size:13px}
.trust{display:flex;flex-wrap:wrap;gap:14px;align-items:center;padding:6px 16px;background:var(--card);border-bottom:1px solid var(--line);font-size:13px;color:var(--muted)}
.trust .date{font-weight:600;color:var(--fg)}
.trust .src{display:inline-flex;align-items:center;gap:5px}
.trust .dot{width:9px;height:9px;border-radius:50%;display:inline-block;border:1px solid rgba(0,0,0,.15)}
.dot.green{background:#1f9d4d}.dot.yellow{background:#e0a400}.dot.red{background:#c0392b}.dot.gray{background:#b8c0c8}
.trust .upd{margin-left:auto}
main{max-width:1180px;margin:0 auto;padding:22px}
h1{font-size:22px;margin:6px 0 12px}h2{font-size:17px;margin:20px 0 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600}
.badge{display:inline-block;padding:1px 8px;border:1px solid var(--line);border-radius:20px;font-size:12px;white-space:nowrap}
.scenario{border-style:dashed}.stale{background:#fff6e6}.muted{color:var(--muted)}
.callout{border-left:4px solid var(--accent);padding:8px 12px;background:#eef4fb}
form.mut{display:inline}button,input,select,textarea{font:inherit}
button{padding:7px 12px;border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:7px;cursor:pointer}
button.secondary{background:#fff;color:var(--accent)}
label{display:block;font-size:13px;color:var(--muted);margin:8px 0 2px}
input,select,textarea{width:100%;max-width:520px;padding:7px;border:1px solid var(--line);border-radius:7px}
:focus{outline:3px solid #7db3f0;outline-offset:1px}
.err{border-left:4px solid #b00020;background:#fdecef;padding:10px 12px;border-radius:6px}
.empty{color:var(--muted);padding:24px;text-align:center;border:1px dashed var(--line);border-radius:10px}
.kv{display:grid;grid-template-columns:200px 1fr;gap:2px 12px}.kv dt{color:var(--muted)}.kv dd{margin:0}
.bars{display:grid;gap:7px;margin:8px 0}
.bars .brow{display:grid;grid-template-columns:150px 1fr auto;gap:10px;align-items:center;font-size:13px}
.bars .blabel{color:var(--fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bars .track{background:var(--bg);border:1px solid var(--line);border-radius:6px;height:16px;position:relative;overflow:hidden}
.bars .fill{position:absolute;left:0;top:0;height:100%;background:var(--accent);opacity:.85}
.bars .bval{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.dist .track{background:var(--bg);border:1px solid var(--line);border-radius:6px;height:18px;position:relative;overflow:hidden}
.dist .iqr{position:absolute;top:0;height:100%;background:var(--accent);opacity:.35}
.dist .med{position:absolute;top:0;width:2px;height:100%;background:var(--accent)}
.dist .cap{position:absolute;top:50%;width:1px;height:10px;transform:translateY(-50%);background:var(--muted)}
/* --- workflow cockpit components --- */
main.wide{max-width:1320px}
.wshead{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin:2px 0 6px}
.wshead h1{margin:0}
.mnav{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap}
.mnav a,.mnav span.cur{padding:6px 12px;border:1px solid var(--line);border-radius:8px;text-decoration:none;color:var(--fg);font-size:14px;background:var(--card)}
.mnav a:hover{background:var(--bg)}
.mnav .cur{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:700}
.mnav form.mut{display:inline-flex;gap:6px;align-items:center;margin-left:4px}
.mnav select{max-width:180px;padding:6px}
.stat{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0}
.metric{border:1px solid var(--line);border-radius:9px;padding:8px 12px;min-width:96px;background:var(--card)}
.metric .v{font-size:20px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums}
.metric .l{font-size:12px;color:var(--muted);margin-top:2px}
.metric.attn .v{color:var(--accent)}
.progress{height:10px;border-radius:6px;background:var(--bg);border:1px solid var(--line);overflow:hidden;margin:8px 0 4px;max-width:360px}
.progress .p{height:100%;background:#1f9d4d}
.chip{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:20px;font-size:12px;border:1px solid var(--line);white-space:nowrap}
.chip.need{background:#eef4fb;border-color:#bcd6f2;color:var(--accent);font-weight:600}
.chip.done{background:#e9f6ee;border-color:#bfe4cc;color:#1f7a44}
.chip.skip{background:#f3f4f6;color:var(--muted)}
.chip.bench{background:#fff6e6;border-color:#e7cf98;color:#8a6d1f}
.queue{display:grid;gap:10px;margin:10px 0}
.rec{border:1px solid var(--line);border-radius:11px;padding:12px 14px;background:var(--card);display:grid;grid-template-columns:auto 1fr auto;gap:6px 16px;align-items:start}
.rec.resolved{opacity:.62;background:var(--bg)}
.rec .rank{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums;padding-top:4px}
.rec .body{min-width:0}
.rec .ident{font-weight:600;font-size:15px}
.rec .call{font-size:22px;font-weight:800;letter-spacing:.01em;margin:2px 0 4px}
.rec .pos{color:var(--muted);font-size:13px}
.rec .side{text-align:right;display:flex;flex-direction:column;gap:6px;align-items:flex-end}
.rec details{margin-top:6px}
.rec details>summary{cursor:pointer;color:var(--accent);font-size:13px}
.rec .why{margin-top:6px;font-size:13px}
.actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.actions form.mut{display:inline}
.actions button{padding:6px 12px;font-size:13px}
.restraint{border-left:4px solid #1f9d4d;background:#eef8f1;padding:10px 14px;border-radius:8px;margin:10px 0}
.restraint strong{color:#1f7a44}
@media(max-width:720px){.rec{grid-template-columns:1fr}.rec .side{text-align:left;align-items:flex-start}.actions{justify-content:flex-start}}
ol.timeline{list-style:none;padding-left:0}ol.timeline li{padding:6px 0 6px 16px;border-left:2px solid var(--line);margin-left:6px}
@media(max-width:640px){.kv{grid-template-columns:1fr}main{padding:10px}}
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
    return (f'<div class="trust" role="contentinfo">'
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
    nav += '<span class="navspacer"></span>'
    nav += "".join(
        f'<a href="{esc(p)}"{" aria-current=page" if p == active_path else ""}>{esc(label)}</a>'
        for p, label in NAV_END)
    nav += '<a class="admin" href="/admin">Admin</a>'
    header = (
        '<header class="shell" role="banner">'
        f'<span class="brand">Elite Pipeline</span>'
        f'<span class="ctx">{esc(ctx.get("principal_name", "—"))}</span>'
        f'<span class="ctx">Store: <strong>{esc(ctx.get("scope", "—"))}</strong></span>'
        '<span class="spacer"></span>'
        f'<span class="badge">env: {esc(ctx.get("environment", "?"))}</span>'
        '<a class="ctx" href="/help">Help</a>'
        '<a class="ctx" href="/logout">Sign out</a>'
        '</header>')
    flash_html = f'<div class="callout" role="status">{esc(flash)}</div>' if flash else ""
    title_html = "" if hide_title else f'<h1>{esc(title)}</h1>'
    main_cls = "wide" if wide else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(title)} — Elite Pipeline</title><style>{_CSS}</style></head>'
            f'<body>{header}{_trust_strip(ctx)}'
            f'<nav class="primary" role="navigation" aria-label="Primary">{nav}</nav>'
            f'<main role="main" class="{main_cls}">{title_html}{flash_html}{body}</main></body></html>')


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
