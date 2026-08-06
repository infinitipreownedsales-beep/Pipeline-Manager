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

NAV = [
    ("/", "Today / Decision Inbox"), ("/new-inventory", "New Inventory"),
    ("/production", "Production & Supply"), ("/service-loaner", "Service Loaners"),
    ("/executive-demo", "Executive Demos"), ("/scenarios", "Scenarios"),
    ("/calibration", "Learning & Calibration"), ("/approvals", "Approvals"),
    ("/execution", "Execution"), ("/exceptions", "Exceptions"), ("/audit", "Audit"),
    ("/authority", "Authority"), ("/readiness", "Readiness"),
]

_CSS = """
:root{--fg:#1a1d21;--muted:#5a6470;--line:#d5dbe2;--bg:#f6f8fa;--card:#fff;--accent:#0b5cad}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--fg);background:var(--bg)}
a{color:var(--accent)}header.shell{display:flex;align-items:center;gap:16px;padding:10px 18px;background:var(--card);border-bottom:2px solid var(--line);flex-wrap:wrap}
header.shell .brand{font-weight:700}header.shell .ctx{color:var(--muted);font-size:13px}
header.shell .spacer{flex:1}.attention{font-weight:700}
nav.primary{display:flex;flex-wrap:wrap;gap:2px;padding:6px 12px;background:var(--card);border-bottom:1px solid var(--line)}
nav.primary a{padding:6px 10px;border-radius:6px;text-decoration:none;color:var(--fg)}
nav.primary a[aria-current=page]{background:var(--accent);color:#fff}
main{max-width:1100px;margin:0 auto;padding:18px}
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


def page(title, body, *, ctx=None, active_path="/", flash=None):
    """Render the full operator shell around `body` (already-safe HTML)."""
    ctx = ctx or {}
    nav = "".join(
        f'<a href="{esc(p)}"{" aria-current=page" if p == active_path else ""}>{esc(label)}</a>'
        for p, label in NAV)
    attention = ctx.get("attention", 0)
    header = (
        '<header class="shell" role="banner">'
        f'<span class="brand">Elite Pipeline</span>'
        f'<span class="badge">env: {esc(ctx.get("environment", "?"))}</span>'
        f'<span class="ctx">Operator: <strong>{esc(ctx.get("principal_name", "—"))}</strong></span>'
        f'<span class="ctx">Store: <strong>{esc(ctx.get("scope", "—"))}</strong></span>'
        '<span class="spacer"></span>'
        f'<span class="ctx" title="items needing attention">{badge("attention", f"{attention} need attention")}</span>'
        f'<span class="ctx" title="data freshness">Fresh as of {esc(ctx.get("freshness", "—"))}</span>'
        f'<span class="ctx" title="data quality">Data: {esc(ctx.get("data_quality", "ok"))}</span>'
        f'<span class="ctx">rev {esc(ctx.get("revision", "—"))}</span>'
        '<a class="ctx" href="/help">Help</a>'
        '<a class="ctx" href="/logout">Sign out</a>'
        '</header>')
    flash_html = f'<div class="callout" role="status">{esc(flash)}</div>' if flash else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{esc(title)} — Elite Pipeline</title><style>{_CSS}</style></head>'
            f'<body>{header}<nav class="primary" role="navigation" aria-label="Primary">{nav}</nav>'
            f'<main role="main"><h1>{esc(title)}</h1>{flash_html}{body}</main></body></html>')


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


def _is_html(v):
    return isinstance(v, _Html)


class _Html(str):
    """Marks an already-safe HTML fragment so kv() won't re-escape it."""


def safe(s):
    return _Html(s)


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
