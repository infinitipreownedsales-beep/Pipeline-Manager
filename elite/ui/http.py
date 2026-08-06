"""Minimal stdlib HTTP plumbing for the operator app — Request, Response, Router.

No third-party web framework. A Router maps (method, path-pattern) to a handler(request) -> Response.
Patterns support `{name}` path segments. Requests carry the resolved operator session (principal +
scope + CSRF token); mutations are validated for CSRF before dispatch. Nothing here is authoritative —
it only shuttles HTTP to the Phase 1-9 services.
"""
from __future__ import annotations

import re


class Request:
    def __init__(self, method, path, *, query=None, form=None, cookies=None, params=None,
                 session=None, correlation_id=None):
        self.method = method.upper()
        self.path = path
        self.query = query or {}
        self.form = form or {}
        self.cookies = cookies or {}
        self.params = params or {}
        self.session = session          # Session or None
        self.correlation_id = correlation_id

    @property
    def principal(self):
        return self.session.principal_id if self.session else None

    @property
    def scope(self):
        return self.session.scope if self.session else None

    def q(self, key, default=None):
        return self.query.get(key, default)

    def f(self, key, default=None):
        return self.form.get(key, default)


class Response:
    def __init__(self, body="", *, status=200, content_type="text/html; charset=utf-8", headers=None,
                 cookies=None):
        self.body = body if isinstance(body, str) else str(body)
        self.status = status
        self.content_type = content_type
        self.headers = list(headers or [])
        self.cookies = cookies or {}      # name -> value

    @classmethod
    def redirect(cls, location, *, status=303, cookies=None):
        return cls("", status=status, headers=[("Location", location)], cookies=cookies)

    @property
    def status_line(self):
        return {200: "200 OK", 303: "303 See Other", 400: "400 Bad Request", 403: "403 Forbidden",
                404: "404 Not Found", 405: "405 Method Not Allowed", 409: "409 Conflict",
                500: "500 Internal Server Error"}.get(self.status, f"{self.status} Status")

    def wsgi_headers(self):
        hdrs = [("Content-Type", self.content_type),
                # conservative, safe defaults — no external assets, no framing
                ("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline' 'self'"),
                ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"),
                ("Referrer-Policy", "same-origin")]
        hdrs += self.headers
        for name, value in self.cookies.items():
            hdrs.append(("Set-Cookie", f"{name}={value}; Path=/; HttpOnly; SameSite=Strict"))
        return hdrs


_PARAM = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _compile(pattern):
    regex = "^" + _PARAM.sub(lambda m: f"(?P<{m.group(1)}>[^/]+)", pattern) + "$"
    return re.compile(regex)


class Router:
    def __init__(self):
        self.routes = []    # (method, compiled, handler, raw)

    def add(self, method, pattern, handler):
        self.routes.append((method.upper(), _compile(pattern), handler, pattern))

    def route(self, method, pattern):
        def deco(fn):
            self.add(method, pattern, fn)
            return fn
        return deco

    def match(self, method, path):
        """Return (handler, params) or (None, None). 405 is signaled by (None, 'METHOD')."""
        path_matched = False
        for m, rx, handler, _raw in self.routes:
            mt = rx.match(path)
            if mt:
                path_matched = True
                if m == method.upper():
                    return handler, mt.groupdict()
        if path_matched:
            return None, "METHOD"
        return None, None
