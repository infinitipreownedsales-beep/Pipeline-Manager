"""Presentation-state persistence — NON-authoritative operator preferences only.

Saved filters, preferred store view, column visibility, sort preference, dismissed hints, and last
selected domain. These records hold no business state: deleting any of them changes no Decision,
approval, execution, policy, identity, supply, Demand, Need, Economic Call, or governance state. They
persist server-side (migration v10), never in browser localStorage.
"""
from __future__ import annotations

import json

from ..clock import to_utc_iso
from ..ids import new_id


class PrefsService:
    def __init__(self, conn, clock):
        self.conn, self.clock = conn, clock

    def _now(self):
        return to_utc_iso(self.clock.now())

    # ---- key/value preferences --------------------------------------------
    def set_pref(self, principal, key, value):
        with self.conn:
            self.conn.execute("INSERT INTO operator_view_preference(id,principal_id,pref_key,pref_value,updated_at) "
                              "VALUES(?,?,?,?,?) ON CONFLICT(principal_id,pref_key) DO UPDATE SET pref_value=excluded."
                              "pref_value,updated_at=excluded.updated_at",
                              (new_id("ovp"), principal, key, json.dumps(value), self._now()))

    def get_pref(self, principal, key, default=None):
        r = self.conn.execute("SELECT pref_value FROM operator_view_preference WHERE principal_id=? AND pref_key=?",
                              (principal, key)).fetchone()
        return json.loads(r["pref_value"]) if r and r["pref_value"] is not None else default

    def all_prefs(self, principal):
        rows = self.conn.execute("SELECT pref_key,pref_value FROM operator_view_preference WHERE principal_id=?",
                                 (principal,)).fetchall()
        return {r["pref_key"]: json.loads(r["pref_value"]) for r in rows}

    def delete_pref(self, principal, key):
        """Deleting a presentation preference changes NO business state (proven by acceptance item 92)."""
        with self.conn:
            self.conn.execute("DELETE FROM operator_view_preference WHERE principal_id=? AND pref_key=?",
                              (principal, key))

    # ---- saved filters -----------------------------------------------------
    def save_filter(self, principal, name, screen, filt):
        fid = new_id("sf")
        with self.conn:
            self.conn.execute("INSERT INTO saved_filter(id,principal_id,name,screen,filter_json,created_at) "
                              "VALUES(?,?,?,?,?,?)", (fid, principal, name, screen, json.dumps(filt), self._now()))
        return fid

    def filters(self, principal, screen):
        rows = self.conn.execute("SELECT * FROM saved_filter WHERE principal_id=? AND screen=? ORDER BY created_at",
                                 (principal, screen)).fetchall()
        return [{"id": r["id"], "name": r["name"], "filter": json.loads(r["filter_json"] or "{}")} for r in rows]

    # ---- instructional hints ----------------------------------------------
    def dismiss_hint(self, principal, hint_key):
        with self.conn:
            self.conn.execute("INSERT INTO instructional_hint_state(id,principal_id,hint_key,dismissed,updated_at) "
                              "VALUES(?,?,?,1,?) ON CONFLICT(principal_id,hint_key) DO UPDATE SET dismissed=1,"
                              "updated_at=excluded.updated_at", (new_id("ihs"), principal, hint_key, self._now()))

    def hint_dismissed(self, principal, hint_key):
        r = self.conn.execute("SELECT dismissed FROM instructional_hint_state WHERE principal_id=? AND hint_key=?",
                              (principal, hint_key)).fetchone()
        return bool(r and r["dismissed"])

    # ---- recent operator context ------------------------------------------
    def set_context(self, principal, *, last_domain=None, last_scope=None):
        with self.conn:
            self.conn.execute("INSERT INTO recent_operator_context(id,principal_id,last_domain,last_scope,updated_at) "
                              "VALUES(?,?,?,?,?) ON CONFLICT(principal_id) DO UPDATE SET last_domain=excluded."
                              "last_domain,last_scope=excluded.last_scope,updated_at=excluded.updated_at",
                              (new_id("roc"), principal, last_domain, last_scope, self._now()))

    def get_context(self, principal):
        r = self.conn.execute("SELECT last_domain,last_scope FROM recent_operator_context WHERE principal_id=?",
                              (principal,)).fetchone()
        return {"last_domain": r["last_domain"], "last_scope": r["last_scope"]} if r else {}
