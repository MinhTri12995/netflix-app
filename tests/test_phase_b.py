"""
Regression test suite for Phase B fixes:
- F04: Supabase / SQLite State Sync & Anti-Resurrection
- F05: Checker JSON Spacing & 3-State Classification (LIVE, DIE, UNKNOWN)
- F08: Admin Accept Idempotency & Safe Rotation (F13 fix: proper admin auth & CSRF)
- F09: Account Capacity Bounds & Allocation Safeguards
- F11: DB Write Failure Handling
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import sqlite3

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database
import checker
from app import create_app

class TestPhaseB(unittest.TestCase):
    def setUp(self):
        # Create temp sqlite db for test isolation
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "accounts.db")
        self.orig_get_sqlite_conn = database.get_sqlite_conn
        database.get_sqlite_conn = lambda p="accounts.db": sqlite3.connect(self.db_path)

        # Initialize schema
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS netflix_accounts (
            email TEXT PRIMARY KEY,
            expire_date TEXT,
            netflix_id TEXT,
            secure_netflix_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS access_keys (
            code TEXT PRIMARY KEY,
            assigned_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expire_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            u7buy_order_id TEXT,
            image_url TEXT,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()
        conn.close()

    def tearDown(self):
        database.get_sqlite_conn = self.orig_get_sqlite_conn
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            os.rmdir(self.tmp_dir)
        except Exception:
            pass

    # --- F04: Supabase / SQLite State Sync ---
    def test_f04_cloud_empty_result_is_authoritative(self):
        """When Supabase returns empty data, SQLite must NOT resurrect deleted accounts."""
        mock_supabase = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []  # Empty in cloud
        mock_supabase.table().select().range().execute.return_value = mock_response

        # Insert phantom account in local SQLite
        conn = database.get_sqlite_conn()
        conn.execute("INSERT INTO netflix_accounts (email, netflix_id) VALUES ('phantom@test.com', 'nid_phantom')")
        conn.commit()
        conn.close()

        with patch("database.SUPABASE_KEY", "dummy_key"), \
             patch("database.get_supabase", return_value=mock_supabase):
            rows = database.fetch_all_rows("netflix_accounts")
            self.assertEqual(len(rows), 0, "Empty cloud data must be authoritative, no local resurrection!")

    def test_f04_sqlite_only_fallback_when_supabase_unreachable(self):
        """SQLite should only be queried when Supabase API throws exception or is unconfigured."""
        # Insert local account
        conn = database.get_sqlite_conn()
        conn.execute("INSERT INTO netflix_accounts (email, netflix_id) VALUES ('local@test.com', 'nid_local')")
        conn.commit()
        conn.close()

        # Unconfigured Supabase -> returns local
        with patch("database.SUPABASE_KEY", ""):
            rows = database.fetch_all_rows("netflix_accounts")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["email"], "local@test.com")

        # Configured Supabase with API error -> returns local fallback
        mock_supabase = MagicMock()
        mock_supabase.table().select().range().execute.side_effect = Exception("Network down")
        with patch("database.SUPABASE_KEY", "dummy_key"), \
             patch("database.get_supabase", return_value=mock_supabase):
            rows = database.fetch_all_rows("netflix_accounts")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["email"], "local@test.com")

    # --- F05: Checker 3-State Classification & Payment Dead Detection ---
    def test_f05_checker_detects_payment_failure_without_space_breakage(self):
        """Checker must correctly detect payment failures and dead statuses regardless of whitespace."""
        dead_data_unhold = {
            "value": {
                "account": {
                    "token": None,
                    "isPaymentFailure": False,
                    "membershipStatus": "never_member"
                }
            }
        }
        self.assertTrue(checker._is_dict_dead(dead_data_unhold), "never_member must be flagged dead")

        dead_data_pay = {
            "value": {
                "account": {
                    "isPaymentFailure": True
                }
            }
        }
        self.assertTrue(checker._is_dict_dead(dead_data_pay), "isPaymentFailure=True must be flagged dead")

        live_data = {
            "value": {
                "account": {
                    "token": {"default": {"token": "valid_token"}},
                    "isPaymentFailure": False,
                    "membershipStatus": "current_member"
                }
            }
        }
        self.assertFalse(checker._is_dict_dead(live_data), "Healthy account dict must not be flagged dead")

    def test_f05_checker_network_errors_return_unknown_never_live(self):
        """When both API and Web fail due to network/5xx, checker MUST return UNKNOWN, never LIVE."""
        with patch("checker._get_token_and_plan_api", return_value="ERROR"), \
             patch("checker.check_web_account_status_and_plan", return_value=("ERROR", None)):
            status, plan = checker.check_account_live("nid_dummy", "snid_dummy", check_payment=True)
            self.assertEqual(status, "UNKNOWN", "Network error must return UNKNOWN, never LIVE!")
            self.assertIsNone(plan)

    # --- F08: Admin Accept Idempotency & Safe Rotation (F13 fix applied) ---
    def test_f08_admin_accept_idempotent_no_duplicate_rotation(self):
        """Accepting an already-accepted request must NOT rotate again or delete accounts."""
        app = create_app()
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test_secret"

        # Insert request with status 'accepted'
        conn = database.get_sqlite_conn()
        conn.execute("INSERT INTO requests (id, code, u7buy_order_id, status) VALUES (101, 'CODE101', 'ORD101', 'accepted')")
        conn.commit()
        conn.close()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["logged_in"] = True
                sess["_csrf_token"] = "valid-csrf-token"

            with patch("database.rotate_access_key") as mock_rotate, \
                 patch("database.delete_account") as mock_delete:
                res = client.post("/admin/request/101/accept", data={"csrf_token": "valid-csrf-token"}, follow_redirects=True)
                mock_rotate.assert_not_called()
                mock_delete.assert_not_called()

    def test_f08_admin_accept_fails_safe_when_vault_empty(self):
        """When vault is empty, admin accept must NOT delete the old account, and keep status pending_out_of_stock."""
        app = create_app()
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test_secret"

        # Insert request and access key
        conn = database.get_sqlite_conn()
        conn.execute("INSERT INTO requests (id, code, u7buy_order_id, status) VALUES (102, 'CODE102', 'ORD102', 'pending')")
        conn.execute("INSERT INTO access_keys (code, assigned_email) VALUES ('CODE102', 'curr@test.com')")
        conn.commit()
        conn.close()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["logged_in"] = True
                sess["_csrf_token"] = "valid-csrf-token"

            # Mock rotate failing because vault is empty
            with patch("database.rotate_access_key", return_value=False), \
                 patch("database.delete_account") as mock_delete:
                res = client.post("/admin/request/102/accept", data={"csrf_token": "valid-csrf-token"}, follow_redirects=True)
                mock_delete.assert_not_called()

                # Status must remain in pending family (e.g. pending_out_of_stock)
                req = database.get_request_by_id(102)
                self.assertTrue(req["status"].startswith("pending"), "Failed rotation must leave request pending")

    # --- F09: Capacity Limits & Allocation Safeguards ---
    def test_f09_capacity_bounds_solo_mode(self):
        """In solo mode (SHARE_MODE_ENABLED=False), each account holds at most 1 code. When full, returns None."""
        with patch("database.SUPABASE_KEY", ""):
            database.set_config("SHARE_MODE_ENABLED", False)

            # Insert 1 Premium account in SQLite
            database.save_account("acc1@test.com", "2099-01-01", "nid1", "snid1", "Premium")

            # First assignment: succeeds
            success, _ = database.create_access_key("ABCDEFGHIJKLM15") # 15 chars = Premium
            self.assertTrue(success)

            # Second assignment: must fail because acc1@test.com reached max_capacity = 1
            success2, msg2 = database.create_access_key("ZYXWVUTSRQPON15")
            self.assertFalse(success2, "Solo mode must NOT allow more than 1 code per account!")
            self.assertIn("No available", msg2)

    def test_f09_rotation_avoids_same_account(self):
        """rotate_access_key must pass exclude_email so it does not assign the same broken account."""
        with patch("database.SUPABASE_KEY", ""):
            database.set_config("SHARE_MODE_ENABLED", True)

            # Insert 2 Premium accounts
            database.save_account("broken@test.com", "2099-01-01", "nid_b", "snid_b", "Premium")
            database.save_account("backup@test.com", "2099-01-01", "nid_ok", "snid_ok", "Premium")

            code = "123456789012345"
            database.create_access_key(code)

            # Force key to be on broken@test.com
            conn = database.get_sqlite_conn()
            conn.execute("UPDATE access_keys SET assigned_email = 'broken@test.com' WHERE code = ?", (code,))
            conn.commit()
            conn.close()

            rotated = database.rotate_access_key(code)
            self.assertTrue(rotated)

            new_key = database.get_access_key(code)
            self.assertEqual(new_key[1], "backup@test.com", "Rotation must assign the backup, NOT re-assign the broken email!")

    # --- F11: DB Write Failure Handling ---
    def test_f11_save_request_returns_boolean_status(self):
        """save_request must return True on successful write and False on complete failure."""
        with patch("database.SUPABASE_KEY", ""):
            success = database.save_request("CODE_T", "ORD_T", "http://img.com", "reason", "pending")
            self.assertTrue(success, "Valid SQLite write must return True")

            # Simulate failure by pointing to non-writable db
            with patch("database.get_sqlite_conn", side_effect=sqlite3.OperationalError("disk error")):
                fail_status = database.save_request("CODE_T", "ORD_T", "http://img.com", "reason", "pending")
                self.assertFalse(fail_status, "Write failure must return False")

if __name__ == "__main__":
    unittest.main()
