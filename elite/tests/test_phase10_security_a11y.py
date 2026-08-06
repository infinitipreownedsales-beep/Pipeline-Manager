"""Phase 10 acceptance — security (91-95) + accessibility/usability (96-100)."""
import os
import tempfile
import unittest

from elite.ui.fixtures import Phase10
from elite.workflow.fixtures import SCOPE


class TestPhase10SecurityA11y(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = Phase10(os.path.join(self.tmp, "elite.db"))
        self.full = self.p.login(self.p.op_full)

    def tearDown(self):
        self.p.close()

    # ---- security (91-95) -------------------------------------------------
    def test_91_no_authoritative_state_in_localstorage(self):
        import elite.ui.render as render
        import elite.ui.views.inbox as inbox
        for mod in (render, inbox):
            self.assertNotIn("localStorage", open(mod.__file__).read())
        # the session cookie is an opaque server-side token (HttpOnly) — no business state in the browser
        r = self.p.app.handle("POST", "/login", form={"principal_id": self.p.op_full, "secret": "pw",
                                                       "scope": SCOPE})
        self.assertIn("HttpOnly", "".join(v for _, v in r.wsgi_headers() if _ == "Set-Cookie"))

    def test_92_pref_deletion_no_business_change(self):
        d = self.p.decided_item["decision_ref"]
        before = self.p.p9.store.get_decision(d)["disposition"] if d else None
        self.p.app.prefs.set_pref(self.p.op_full, "sort", {"by": "age"})
        self.p.app.prefs.delete_pref(self.p.op_full, "sort")
        self.assertEqual(self.p.p9.store.get_decision(d)["disposition"] if d else None, before)
        self.assertEqual(self.full.get("/").status, 200)   # app still works

    def test_93_csrf_required(self):
        d = self.p.decided_item["decision_ref"]
        r = self.p.app.handle("POST", "/ack/" + d, form={}, session_token=self.full.token)   # no CSRF
        self.assertEqual(r.status, 403)

    def test_94_double_submission_no_duplicate(self):
        decider = self.p.login(self.p.op_decider)
        form = {"disposition": "ACCEPT", "selected_action": "x", "_idem": "idem-dbl"}
        decider.post("/item/" + self.p.fresh_item["id"] + "/decide", dict(form))
        decider.post("/item/" + self.p.fresh_item["id"] + "/decide", dict(form))
        self.assertEqual(len(self.p.p9.store.decisions_for_item(self.p.fresh_item["id"])), 1)

    def test_95_errors_hide_traces_and_secrets(self):
        orig = self.p.stack.audit.append
        self.p.stack.audit.append = lambda conn, e: (_ for _ in ()).throw(RuntimeError("SECRET_boom_token"))
        decider = self.p.login(self.p.op_decider)
        try:
            r = decider.post("/item/" + self.p.fresh_item["id"] + "/decide",
                             {"disposition": "ACCEPT", "selected_action": "x"})
        finally:
            self.p.stack.audit.append = orig
        self.assertNotIn("Traceback", r.body)
        self.assertNotIn("SECRET_boom_token", r.body)      # no secret / internal detail leaked

    # ---- accessibility / usability (96-100) -------------------------------
    def test_96_keyboard_accessible_primary_actions(self):
        # primary actions are real <button> elements (keyboard-focusable) with a visible focus style
        r = self.full.get("/item/" + self.p.fresh_item["id"] + "/decide")
        self.assertIn("<button", r.body)
        import elite.ui.render as render
        self.assertIn(":focus", open(render.__file__).read())         # visible focus outline
        self.assertNotIn("</a></button>", r.body)                      # no non-focusable action hacks

    def test_97_status_not_color_only(self):
        body = self.full.get("/").body
        self.assertIn('aria-hidden="true"', body)          # status badges carry a text glyph + label
        # every status badge shows a text label, not just a color
        self.assertIn("badge", body)
        self.assertRegex(body, r'badge[^>]*>.*?</span>')

    def test_98_forms_have_labels(self):
        r = self.full.get("/item/" + self.p.fresh_item["id"] + "/decide")
        self.assertIn("<label", r.body)
        self.assertIn('for=disp', r.body)                  # label associated to the disposition control

    def test_99_empty_states_usable(self):
        self.full.post("/scope", {"scope": "store:EMPTY"})
        r = self.full.get("/")
        self.assertIn("Nothing here", r.body)              # a usable empty state, not a blank page

    def test_100_failure_states_usable(self):
        r = self.full.get("/item/does-not-exist")
        self.assertEqual(r.status, 404)
        self.assertIn("Return to the Decision Inbox", r.body)   # a usable failure state with a way back


if __name__ == "__main__":
    unittest.main()
