"""The operator application — a stdlib WSGI app over the Phase 1-9 services.

Session context is server-side (an opaque cookie token maps to a Principal + scope + CSRF token held on
the server) so NO authoritative state lives in the browser. State-changing requests must carry a valid
CSRF token. A safe error boundary renders governed-action failures without leaking stack traces or
secrets. Below-UI authorization + scope are enforced by the Phase 1-9 services the handlers call, not by
hiding navigation.
"""
from __future__ import annotations

import secrets
import urllib.parse

from ..errors import AuthorizationError, ConcurrencyError, EliteError, PersistenceError, ValidationError
from ..ids import new_id
from .http import Request, Response, Router
from .prefs import PrefsService
from .render import error_page, esc, page

PUBLIC = {"/login", "/logout", "/healthz"}


class Session:
    def __init__(self, token, principal_id, principal_name, scope):
        self.token = token
        self.principal_id = principal_id
        self.principal_name = principal_name
        self.scope = scope
        self.csrf_token = secrets.token_urlsafe(16)
        self.flash = None


class App:
    def __init__(self, p9, *, environment="test"):
        self.p9 = p9
        self.stack = p9.stack
        self.store = p9.store            # GovernStore
        self.environment = environment
        self.prefs = PrefsService(self.stack.db.conn, self.stack.clock)
        self.router = Router()
        self.sessions = {}               # token -> Session
        from . import views              # noqa: register all routes
        views.register(self)

    # ---- routing decorators ------------------------------------------------
    def get(self, pattern):
        return self.router.route("GET", pattern)

    def post(self, pattern):
        return self.router.route("POST", pattern)

    # ---- sessions ----------------------------------------------------------
    def login(self, principal_id, secret, scope):
        self.stack.authn.authenticate(principal_id, secret)          # raises on bad credentials
        p = self.stack.principals.get(principal_id)
        token = secrets.token_urlsafe(24)
        self.sessions[token] = Session(token, principal_id, p.display_name if p else principal_id, scope)
        return token

    def logout(self, token):
        self.sessions.pop(token, None)

    def require(self, session, capability):
        """Below-UI authorization for navigation/read screens — enforced by the Phase 1 authorizer, not
        by hiding links. Raises AuthorizationError (rendered as a safe 403) when the operator lacks it."""
        self.stack.authz.require(session.principal_id, capability, session.scope)

    def switch_scope(self, session, scope):
        """A scope change must not expose unauthorized data: require the operator to hold ANY grant at
        the requested scope."""
        holds = any(g.effective() and (g.scope == "*" or g.scope == scope)
                    for g in self.stack.grants.list_for(session.principal_id))
        if not holds:
            raise AuthorizationError(message="You do not have access to that store.",
                                     technical_detail=f"no grant at scope {scope}")
        session.scope = scope

    # ---- shell context -----------------------------------------------------
    def ctx(self, session):
        from .views.inbox import attention_count
        return {"environment": self.environment,
                "principal_name": session.principal_name if session else "—",
                "scope": session.scope if session else "—",
                "attention": attention_count(self, session) if session else 0,
                "freshness": _now_label(self.stack.clock),
                "data_quality": _data_quality(self, session) if session else "—",
                "revision": self.stack.db.version()}

    # ---- dispatch ----------------------------------------------------------
    def handle(self, method, path, *, query=None, form=None, session_token=None, correlation_id=None):
        session = self.sessions.get(session_token)
        correlation_id = correlation_id or new_id("corr")
        req = Request(method, path, query=query, form=form, session=session, correlation_id=correlation_id)
        public = path in PUBLIC
        handler, params = self.router.match(method, path)
        if handler is None:
            if params == "METHOD":
                return Response("Method not allowed", status=405)
            return self._safe_page(session, "Not found", "That screen does not exist.", 404)
        req.params = params or {}
        if not public and session is None:
            return Response.redirect("/login")
        if not public and method == "POST":
            if (form or {}).get("_csrf") != session.csrf_token:
                return self._safe_page(session, "Security check failed",
                                       "This action could not be verified. Please try again.", 403)
        try:
            return handler(self, req)
        except AuthorizationError as e:
            return self._safe_page(session, "Not permitted",
                                   "You do not have permission to do that in this store.", 403)
        except (ValidationError, ConcurrencyError) as e:
            return self._safe_page(session, "Action not completed", e.message or "That action was not allowed.", 409)
        except PersistenceError:
            return self._safe_page(session, "Action not completed safely",
                                   "The action could not be completed and was not applied. Nothing was changed.", 409)
        except EliteError as e:
            return self._safe_page(session, "Action not completed", e.message or "Something went wrong.", 400)
        except Exception:
            # never leak a stack trace or secret to an operator
            return self._safe_page(session, "Something went wrong",
                                   "An unexpected problem occurred. No changes were made.", 500)

    def _safe_page(self, session, title, message, status):
        return Response(error_page(title, message, ctx=self.ctx(session) if session else {}), status=status)

    # ---- WSGI --------------------------------------------------------------
    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/") or "/"
        query = _parse_qs(environ.get("QUERY_STRING", ""))
        form = {}
        if method == "POST":
            try:
                length = int(environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                length = 0
            body = environ["wsgi.input"].read(length).decode("utf-8") if length else ""
            form = _parse_qs(body)
        cookies = _parse_cookies(environ.get("HTTP_COOKIE", ""))
        resp = self.handle(method, path, query=query, form=form, session_token=cookies.get("elite_session"))
        start_response(resp.status_line, resp.wsgi_headers())
        return [resp.body.encode("utf-8")]


def _parse_qs(s):
    return {k: v[-1] for k, v in urllib.parse.parse_qs(s, keep_blank_values=True).items()}


def _parse_cookies(header):
    out = {}
    for part in header.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out[k] = v
    return out


def _now_label(clock):
    from ..clock import to_utc_iso
    return to_utc_iso(clock.now())[:16].replace("T", " ") + " UTC"


def _data_quality(app, session):
    n = len(app.store.op_exceptions())
    return "ok" if n == 0 else f"{n} open exception(s)"


def make_server(app, host="127.0.0.1", port=8010):
    """Run the operator app with the stdlib WSGI reference server (local operator use)."""
    from wsgiref.simple_server import make_server as _mk
    return _mk(host, port, app)
