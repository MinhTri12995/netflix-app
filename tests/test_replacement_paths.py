import unittest
from unittest.mock import patch
import database
from app.services.allocation_service import replace
from app.services.outbox_service import record_outbox_event, deliver_event, process_outbox

class TestReplacementPaths(unittest.TestCase):
    def setUp(self):
        database.init_db()
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("DELETE FROM netflix_accounts")
        c.execute("DELETE FROM access_keys")
        c.execute("DELETE FROM requests")
        c.execute("DELETE FROM rotation_events")
        c.execute("DELETE FROM events_outbox")
        c.execute("DELETE FROM operations")
        conn.commit()
        conn.close()

    def test_shared_account_protection_on_rotation(self):
        """
        F03 Invariant:
        Code A and Code B share the same account 'shared@nf.com'.
        When Code A is rotated to 'spare@nf.com':
        - Code A points to 'spare@nf.com'
        - Code B STILL points to 'shared@nf.com'
        - 'shared@nf.com' is NOT deleted from netflix_accounts
        """
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('shared@nf.com', 'Premium', 'usable')")
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('spare@nf.com', 'Premium', 'usable')")

        code_a = "KEY_SHARED_USER_A"
        code_b = "KEY_SHARED_USER_B"

        c.execute("INSERT INTO access_keys (code, assigned_email, plan) VALUES (?, 'shared@nf.com', 'Premium')", (code_a,))
        c.execute("INSERT INTO access_keys (code, assigned_email, plan) VALUES (?, 'shared@nf.com', 'Premium')", (code_b,))
        conn.commit()
        conn.close()

        # Rotate Code A
        res = replace(code=code_a, actor="admin", reason="Code A screen limit")
        self.assertTrue(res.is_success)
        self.assertEqual(res.assigned_email, "spare@nf.com")

        # Verify Code A has new account
        key_a = database.get_access_key(code_a)
        self.assertEqual(key_a[1], "spare@nf.com")

        # Verify Code B is UNTOUCHED
        key_b = database.get_access_key(code_b)
        self.assertEqual(key_b[1], "shared@nf.com")

        # Verify shared account still exists in netflix_accounts
        acc = database.get_account_by_email("shared@nf.com")
        self.assertIsNotNone(acc, "Shared account must NOT be deleted!")

    def test_24h_quota_limit_exceeded(self):
        """Codes reaching 5 rotations in 24 hours must be rejected with limit_exceeded."""
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('quota_acc@nf.com', 'Premium', 'usable')")
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('spare_acc@nf.com', 'Premium', 'usable')")
        code = "QUOTA_TEST_KEY_1"
        c.execute("INSERT INTO access_keys (code, assigned_email, plan) VALUES (?, 'quota_acc@nf.com', 'Premium')", (code,))

        # Insert 5 accepted requests in last 2 hours
        for i in range(5):
            c.execute("INSERT INTO requests (code, u7buy_order_id, image_url, reason, status, created_at) VALUES (?, 'U7_Q', 'img', 'err', 'accepted', datetime('now', '-1 hour'))", (code,))
        conn.commit()
        conn.close()

        res = replace(code=code, actor="system", reason="Attempting 6th rotation")
        self.assertEqual(res.status, "limit_exceeded")
        self.assertEqual(res.detail_code, "QUOTA_EXCEEDED")

    def test_assignment_version_optimistic_concurrency(self):
        """When expected_assignment_version does not match current version, return already_processed."""
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('ver_acc1@nf.com', 'Premium', 'usable')")
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('ver_acc2@nf.com', 'Premium', 'usable')")
        code = "VERSION_TEST_KEY"
        # Current version is 2
        c.execute("INSERT INTO access_keys (code, assigned_email, plan, assignment_version) VALUES (?, 'ver_acc1@nf.com', 'Premium', 2)", (code,))
        conn.commit()
        conn.close()

        # Caller expects version 1 (outdated evidence/token)
        res = replace(code=code, actor="ai", expected_assignment_version=1)
        self.assertEqual(res.status, "already_processed")
        self.assertEqual(res.detail_code, "VERSION_MISMATCH")

    def test_outbox_notification_failure_resilience(self):
        """Telegram alert failure does NOT rollback rotation transaction; outbox records pending for retry."""
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('fail_notif@nf.com', 'Premium', 'usable')")
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('spare_notif@nf.com', 'Premium', 'usable')")
        code = "NOTIF_FAIL_TEST"
        c.execute("INSERT INTO access_keys (code, assigned_email, plan) VALUES (?, 'fail_notif@nf.com', 'Premium')", (code,))
        conn.commit()
        conn.close()

        # Mock send_telegram_alert to fail/return False
        with patch("app.services.outbox_service.send_telegram_alert", return_value=False):
            res = replace(code=code, actor="admin", reason="Test outbox resilience")

        # Main transaction must still SUCCEED!
        self.assertTrue(res.is_success)
        self.assertEqual(res.assigned_email, "spare_notif@nf.com")

        # Verify outbox row exists and recorded retry attempt
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("SELECT status, retry_count FROM events_outbox WHERE event_type = 'telegram_alert'")
        row = c.fetchone()
        self.assertIsNotNone(row)
        self.assertIn(row[0], ["pending", "delivered"])
        conn.close()

    def test_direct_replacement_without_request_id(self):
        """Activation CookieError and Live-check DIE invoke replace directly without request_id."""
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('cookie_err@nf.com', 'Premium', 'usable')")
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('spare_cookie@nf.com', 'Premium', 'usable')")
        code = "DIRECT_REPLACE_1"
        c.execute("INSERT INTO access_keys (code, assigned_email, plan) VALUES (?, 'cookie_err@nf.com', 'Premium')", (code,))
        conn.commit()
        conn.close()

        res = replace(code=code, actor="system:activation", reason="CookieError: token invalid")
        self.assertTrue(res.is_success)
        self.assertEqual(res.assigned_email, "spare_cookie@nf.com")

        # Rotation event was recorded
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("SELECT old_email, new_email, actor FROM rotation_events WHERE code = ?", (code,))
        evt = c.fetchone()
        self.assertIsNotNone(evt)
        self.assertEqual(evt[0], "cookie_err@nf.com")
        self.assertEqual(evt[1], "spare_cookie@nf.com")
        self.assertEqual(evt[2], "system:activation")
        conn.close()

if __name__ == "__main__":
    unittest.main()
