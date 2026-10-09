import unittest
from unittest.mock import patch, MagicMock
import database
from app.services.token_service import CookieError
from tests.conftest import create_isolated_test_app

class TestActivationAutoRecovery(unittest.TestCase):
    def setUp(self):
        self.app, self.db_path, self.orig_conn = create_isolated_test_app()
        self.client = self.app.test_client()

        # Clean tables
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("DELETE FROM netflix_accounts")
        c.execute("DELETE FROM access_keys")
        c.execute("DELETE FROM requests")
        c.execute("DELETE FROM operations")
        conn.commit()
        conn.close()

    def tearDown(self):
        database.get_sqlite_conn = self.orig_conn
        import os
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_activation_recovers_from_dead_account_safely(self):
        """
        When buyer activates a code assigned to a dead account:
        1. Token generator raises CookieError.
        2. System automatically rotates to a live account.
        3. Old dead account is marked needs_review and NOT deleted.
        4. Response succeeds with genuine nftoken and launch links.
        """
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        # Insert dead account and live account
        c.execute("INSERT INTO netflix_accounts (email, netflix_id, secure_netflix_id, plan, status) VALUES ('dead_cookie@nf.com', 'dead_nid', 'dead_snid', 'Premium', 'usable')")
        c.execute("INSERT INTO netflix_accounts (email, netflix_id, secure_netflix_id, plan, status) VALUES ('live_cookie@nf.com', 'live_nid', 'live_snid', 'Premium', 'usable')")
        code = "ANHTJ7VN29MCVZ6L"
        c.execute("INSERT INTO access_keys (code, assigned_email, plan, expire_at) VALUES (?, 'dead_cookie@nf.com', 'Premium', '2099-12-31')", (code,))
        conn.commit()
        conn.close()

        def mock_fetch_token(nid, snid=""):
            if nid == "dead_nid":
                raise CookieError("Dead cookie detected")
            return "GENUINE_NFTOKEN_FOR_TEST_XYZ"

        with patch("app.blueprints.portal.routes.fetch_netflix_nftoken_api", side_effect=mock_fetch_token), \
             patch("app.blueprints.portal.routes.fetch_realtime_account_info", return_value=("Premium", "2099-12-31")):
            res = self.client.post("/api/generate_nftoken", json={"cookie": code})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("nftoken=GENUINE_NFTOKEN_FOR_TEST_XYZ", data.get("pc_link"))
        self.assertIn("nftoken=GENUINE_NFTOKEN_FOR_TEST_XYZ", data.get("mobile_link"))
        self.assertIn("nftoken=GENUINE_NFTOKEN_FOR_TEST_XYZ", data.get("tv_link"))
        self.assertIn("nftoken=GENUINE_NFTOKEN_FOR_TEST_XYZ", data.get("general_link"))
        self.assertTrue(data.get("cookie_json"))

        # Verify key was reassigned to live account
        key = database.get_access_key(code)
        self.assertEqual(key[1], "live_cookie@nf.com")

        # Verify dead account still exists in database and is marked needs_review
        dead_acc = database.get_account_by_email("dead_cookie@nf.com")
        self.assertIsNotNone(dead_acc, "Dead account must NOT be deleted!")
        self.assertEqual(dead_acc[6], "needs_review", "Dead account must be marked needs_review")

    def test_activation_skips_unusable_statuses(self):
        """
        Candidate selection must exclude accounts with status needs_review, dead, expired, etc.
        """
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("INSERT INTO netflix_accounts (email, netflix_id, plan, status) VALUES ('acc_review@nf.com', 'nid1', 'Premium', 'needs_review')")
        c.execute("INSERT INTO netflix_accounts (email, netflix_id, plan, status) VALUES ('acc_dead@nf.com', 'nid2', 'Premium', 'dead')")
        c.execute("INSERT INTO netflix_accounts (email, netflix_id, plan, status) VALUES ('acc_expired@nf.com', 'nid3', 'Premium', 'expired')")
        c.execute("INSERT INTO netflix_accounts (email, netflix_id, plan, status) VALUES ('acc_good@nf.com', 'nid4', 'Premium', 'usable')")
        code = "CODE_SKIP_REVIEW"
        c.execute("INSERT INTO access_keys (code, assigned_email, plan, expire_at) VALUES (?, 'acc_dead@nf.com', 'Premium', '2099-12-31')", (code,))
        conn.commit()
        conn.close()

        with patch("app.blueprints.portal.routes.fetch_netflix_nftoken_api", return_value="TOKEN_OK"), \
             patch("app.blueprints.portal.routes.fetch_realtime_account_info", return_value=("Premium", "2099-12-31")):
            res = self.client.post("/api/generate_nftoken", json={"cookie": code})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))

        # Must have picked acc_good@nf.com, completely bypassing acc_review and acc_dead
        key = database.get_access_key(code)
        self.assertEqual(key[1], "acc_good@nf.com")

if __name__ == "__main__":
    unittest.main()
