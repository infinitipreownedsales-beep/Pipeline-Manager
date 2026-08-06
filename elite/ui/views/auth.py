"""Login / logout / help / health — the authenticated operator context."""
from __future__ import annotations

from ..render import esc, page
from ..http import Response


def register(app):
    @app.get("/login")
    def login_form(app, req):
        body = ('<div class="card"><form method="post" action="/login">'
                '<label for="pid">Operator ID</label><input id="pid" name="principal_id" required>'
                '<label for="sec">Password</label><input id="sec" name="secret" type="password" required>'
                '<label for="scope">Store / scope</label><input id="scope" name="scope" value="store:HG" required>'
                '<div style="margin-top:10px"><button type="submit">Sign in</button></div></form></div>')
        return Response(page("Sign in", body, ctx={"environment": app.environment}))

    @app.post("/login")
    def do_login(app, req):
        try:
            token = app.login(req.f("principal_id", ""), req.f("secret", ""), req.f("scope", "store:HG"))
        except Exception:
            return Response(page("Sign in", '<div class="err" role="alert">Sign-in failed. Check your '
                                 'operator ID and password.</div>', ctx={"environment": app.environment}),
                            status=403)
        return Response.redirect("/", cookies={"elite_session": token})

    @app.get("/logout")
    def logout(app, req):
        cookie = req.cookies.get("elite_session")
        # session token is resolved via the app; clear whatever is presented
        for tok, sess in list(app.sessions.items()):
            if req.session and sess is req.session:
                app.logout(tok)
        return Response.redirect("/login", cookies={"elite_session": ""})

    @app.get("/healthz")
    def healthz(app, req):
        return Response("ok", content_type="text/plain; charset=utf-8")

    @app.get("/help")
    def help_page(app, req):
        body = ('<div class="card"><h2>How this works</h2>'
                '<p>Every recommendation shows the <strong>Call</strong> (what to do), '
                '<strong>Why</strong> (the reasoning), <strong>Proof</strong> (the accepted facts and '
                'calculations behind it), and <strong>Raw History</strong> (the full evidence trail). '
                'Recommendation, approval, execution, and completion are separate steps. Scenarios are '
                'hypothetical and never change official state.</p></div>')
        return Response(page("Help", body, ctx=app.ctx(req.session), active_path="/help"))

    @app.post("/scope")
    def set_scope(app, req):
        app.switch_scope(req.session, req.f("scope", req.session.scope))
        return Response.redirect("/")
