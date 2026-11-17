"""Unit tests for FEAT-005 service helpers.

Plain ``unittest.TestCase`` classes so they run under both ``pytest tests/``
and ``python -m unittest discover -s tests``. The ICS and CSV helpers are pure
and need no DB; the notify/cyhire tests use an isolated temp SQLite database.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from app.services import export as export_service
from app.services import ics as ics_service


class IcsTest(unittest.TestCase):
    def test_build_ics_structure_and_crlf(self):
        data = ics_service.build_ics([
            {"uid": "a@spark",
             "start": datetime(2025, 5, 1, 17, 0, tzinfo=timezone.utc),
             "summary": "Profile deadline"},
        ])
        self.assertIsInstance(data, bytes)
        text = data.decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn("END:VCALENDAR", text)
        self.assertIn("BEGIN:VEVENT", text)
        self.assertIn("UID:a@spark", text)
        self.assertIn("DTSTART:20250501T170000Z", text)
        self.assertIn("SUMMARY:Profile deadline", text)
        # Every line separator must be CRLF and the file ends with CRLF.
        self.assertTrue(text.endswith("\r\n"))
        for line in text.split("\r\n"):
            self.assertNotIn("\n", line)

    def test_text_escaping(self):
        text = ics_service.build_ics([
            {"uid": "x", "start": datetime(2025, 1, 1, tzinfo=timezone.utc),
             "summary": "A, b; c\\d"},
        ]).decode()
        self.assertIn("SUMMARY:A\\, b\\; c\\\\d", text)

    def test_naive_datetime_treated_as_utc(self):
        text = ics_service.build_ics([
            {"uid": "x", "start": datetime(2025, 1, 2, 3, 4, 5), "summary": "s"},
        ]).decode()
        self.assertIn("DTSTART:20250102T030405Z", text)


class CsvTest(unittest.TestCase):
    def test_csv_quotes_special_chars(self):
        out = export_service.csv([
            ["Section", "Item", "Value"],
            ["a", "has, comma", 'has "quote"'],
            ["b", "line\nbreak", 3],
        ]).decode("utf-8")
        self.assertTrue(out.startswith("Section,Item,Value\r\n"))
        self.assertIn('"has, comma"', out)
        self.assertIn('"has ""quote"""', out)
        self.assertIn('"line\nbreak"', out)

    def test_none_renders_empty(self):
        out = export_service.csv([["x", None]]).decode("utf-8")
        self.assertEqual(out, "x,\r\n")


class _DictRow(dict):
    """Minimal row supporting ['col'] and .keys() like sqlite3.Row."""


class ProjectHtmlTest(unittest.TestCase):
    def _project(self):
        return _DictRow(
            id=1, title="CRISPR <b>study</b>", description="<p>desc</p>",
            background="bg", responsibilities="resp", positions=2,
            comp_type="credit", credit_option="1-3", hourly_rate=None,
            primary_department_id=None, noncitizen_eligible=1, session_id=7,
            capacity=2, status="published",
        )

    def test_project_html_escapes_title_keeps_sanitized_body(self):
        html = export_service.project_html(self._project(), mentors=[], department="Biology")
        self.assertIn("CRISPR &lt;b&gt;study&lt;/b&gt;", html)   # title escaped
        self.assertIn("<p>desc</p>", html)                       # body already sanitized
        self.assertIn("Biology", html)

    def test_project_pdf_has_print_hook(self):
        html = export_service.project_pdf(self._project(), mentors=[], department=None)
        self.assertIn("window.print", html)
        self.assertIn("@media print", html)


class _ServiceDBTest(unittest.TestCase):
    def setUp(self):
        self._fd, self._path = tempfile.mkstemp(suffix=".db")
        os.close(self._fd)
        os.environ["SPARK_DB"] = self._path
        # Import after setting SPARK_DB so db.DB_PATH picks it up via connect(path).
        from app import db
        self.db = db
        db.reset_db(self._path)
        self.conn = db.connect(self._path)

    def tearDown(self):
        self.conn.close()
        os.environ.pop("SPARK_DB", None)
        if os.path.exists(self._path):
            os.remove(self._path)

    def _user(self, email, role="faculty"):
        return self.db.insert(
            self.conn, "users", email=email, display_name=email.split("@")[0],
            given_name="G", family_name="F", role=role, password_hash="x",
            password_salt="y", password_iter=1, is_blocked=0, updated_at=self.db.utcnow())


class NotifyTest(_ServiceDBTest):
    def test_send_persists_row_and_returns_true(self):
        from app.services import notify
        uid = self._user("f@spark")
        ok = notify.send(self.conn, uid, channel="email", subject="Hi", body="Body",
                         kind="match_published")
        self.conn.commit()
        self.assertTrue(ok)
        notes = self.db.list_notifications(self.conn, uid)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["channel"], "email")
        self.assertEqual(notes[0]["kind"], "match_published")

    def test_unknown_channel_rejected(self):
        from app.services import notify
        uid = self._user("f2@spark")
        with self.assertRaises(ValueError):
            notify.send(self.conn, uid, channel="carrier-pigeon")

    def test_pluggable_provider(self):
        from app.services import notify
        calls = []

        class Rec(notify.Provider):
            def deliver(self, conn, user_id, subject, body, meta=None):
                calls.append((user_id, subject))
                return True

        notify.register_provider("sms", Rec())
        try:
            uid = self._user("f3@spark")
            notify.send(self.conn, uid, channel="sms", subject="S", body="B")
            self.assertEqual(len(calls), 1)
        finally:
            notify.register_provider("sms", notify.InAppProvider())

    def test_mark_read(self):
        from app.services import notify
        uid = self._user("f4@spark")
        notify.send(self.conn, uid, channel="inapp", subject="s")
        self.conn.commit()
        nid = self.db.list_notifications(self.conn, uid)[0]["id"]
        self.assertEqual(self.db.unread_notification_count(self.conn, uid), 1)
        self.db.mark_notification_read(self.conn, nid, uid)
        self.conn.commit()
        self.assertEqual(self.db.unread_notification_count(self.conn, uid), 0)


class RatingTest(_ServiceDBTest):
    def test_rating_summary_counts_distinct_raters(self):
        subject = self._user("prof@spark")
        sid = self.db.insert(
            self.conn, "match_sessions", name="S", mode="mutual", status="open",
            matching_method="mutual", weighting="equal", timezone="UTC",
            updated_at=self.db.utcnow())
        for i in range(5):
            rater = self._user("s%d@spark" % i, role="student")
            self.db.add_rating(self.conn, sid, rater, subject, stars=4)
        self.conn.commit()
        avg, raters = self.db.rating_summary_for_subject(self.conn, subject)
        self.assertEqual(raters, 5)
        self.assertAlmostEqual(avg, 4.0)


class CyhireTest(_ServiceDBTest):
    def test_forward_builds_12twenty_payload_and_records(self):
        from app.services import cyhire
        pi = self._user("pi@spark")
        sid = self.db.insert(
            self.conn, "match_sessions", name="S", mode="mutual", status="closed",
            matching_method="mutual", weighting="equal", timezone="UTC",
            updated_at=self.db.utcnow())
        pid = self.db.insert(
            self.conn, "projects", session_id=sid, title="P", description="<p>d</p>",
            positions=3, capacity=3, comp_type="pay", hourly_rate=15.0,
            noncitizen_eligible=1, status="published", updated_at=self.db.utcnow())
        self.db.insert(self.conn, "project_mentors", project_id=pid, user_id=pi,
                       role="faculty", is_pi=1, permission="editor")
        project = self.db.get_project(self.conn, pid)
        event_id, payload = cyhire.forward(self.conn, project, openings=3)
        self.conn.commit()
        self.assertIn("jobPosting", payload)
        jp = payload["jobPosting"]
        self.assertEqual(jp["externalId"], "spark-project-%d" % pid)
        self.assertEqual(jp["positionsAvailable"], 3)
        self.assertEqual(jp["compensation"]["type"], "hourly")
        events = self.db.list_integration_events(self.conn, target="cyhire")
        self.assertEqual(len(events), 1)
        self.assertEqual(json.loads(events[0]["payload_json"])["jobPosting"]["title"], "P")


if __name__ == "__main__":
    unittest.main()
