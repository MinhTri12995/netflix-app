"""
Comprehensive regression safety suite for architectural invariants:
- Auth & CSRF Boundaries on Admin Handlers
- Positive Regression: Portal access with Admin session
- Safe behavior assertions matching the 15 audit findings
"""
import io
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import sqlite3

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database as db
import checker
from app import create_app
from app.config import Config
from tests.conftest import TEST_CSRF_TOKEN

class TestRegressionSafety(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "accounts.db")
        self.orig_get_sqlite_conn = db.get_sqlite_conn
        db.get_sqlite_conn = lambda p="accounts.db": sqlite3.connect(self.db_path)
        db.SUPABASE_KEY = ""

        conn = db.get_sqlite_conn()
        conn.execute("""CREATE TABLE IF NOT EXISTS netflix_accounts (
            email TEXT PRIMARY KEY,
            expire_date TEXT,
            netflix_id TEXT,
            secure_netflix_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS access_keys (
            code TEXT PRIMARY KEY,
            assigned_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expire_at TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS requests (
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

        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="safety-suite-secret-key-32-chars",
            WTF_CSRF_ENABLED=False
        )
        self.client = self.app.test_client()

    def tearDown(self):
        db.get_sqlite_conn = self.orig_get_sqlite_conn
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            os.rmdir(self.tmp_dir)
        except Exception:
            pass

    def _sample_png(self):
        from tests.conftest import create_valid_png_bytes
        return create_valid_png_bytes()

    # -------------------------------------------------------------------------
    # 1. Auth & CSRF Boundaries on Admin Endpoints
    # -------------------------------------------------------------------------
    def test_accept_handler_called_with_proper_auth_and_csrf(self):
        """Admin with valid logged_in session and CSRF token successfully calls accept handler."""
        db.save_account("acc_old@nf.com", "2099-12-31", "nid_old", plan="Premium")
        db.save_account("acc_spare@nf.com", "2099-12-31", "nid_spare", plan="Premium")
        code = "ACCEPTSAFE12345"
        conn = db.get_sqlite_conn()
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code, "acc_old@nf.com", "2099-12-31"))
        conn.execute("INSERT INTO requests (id, code, u7buy_order_id, status) VALUES (501, ?, 'U7_501', 'pending')",
                     (code,))
        conn.commit()
        conn.close()

        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["_csrf_token"] = TEST_CSRF_TOKEN

        with patch("app.blueprints.admin.routes.send_telegram_alert"):
            res = self.client.post("/admin/request/501/accept", data={"csrf_token": TEST_CSRF_TOKEN}, follow_redirects=False)

        # Handler should execute and redirect to admin.dashboard
        self.assertEqual(res.status_code, 302)
        # Verify request status transitioned to accepted
        req = db.get_request_by_id(501)
        self.assertEqual(req["status"], "accepted")
        # Verify key was rotated to spare
        key = db.get_access_key(code)
        self.assertEqual(key[1], "acc_spare@nf.com")

    def test_accept_handler_blocked_without_auth(self):
        """Unauthenticated POST to admin handler must be blocked (403 or redirect), never executed."""
        with patch("database.rotate_access_key") as mock_rotate:
            res = self.client.post("/admin/request/501/accept", data={"csrf_token": "any"}, follow_redirects=False)
            self.assertIn(res.status_code, [302, 401, 403])
            mock_rotate.assert_not_called()

    def test_accept_handler_blocked_without_csrf(self):
        """Authenticated admin POST missing valid CSRF token must be rejected with HTTP 403."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["_csrf_token"] = TEST_CSRF_TOKEN

        with patch("database.rotate_access_key") as mock_rotate:
            res = self.client.post("/admin/request/501/accept", data={"csrf_token": "wrong_csrf"}, follow_redirects=False)
            self.assertEqual(res.status_code, 403)
            mock_rotate.assert_not_called()

    # -------------------------------------------------------------------------
    # 2. Positive Regression: Portal API with Admin Session
    # -------------------------------------------------------------------------
    def test_portal_api_accessible_with_admin_session(self):
        """Portal API (/api/generate_nftoken) must reach business logic even if browser has an admin session."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True

        res = self.client.post("/api/generate_nftoken", json={"cookie": "NONEXISTENT15CH"})
        # Must reach business validation (400 Invalid Access Code), NOT 403 CSRF forbidden
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json().get("success"))

    # -------------------------------------------------------------------------
    # 3. Safe Invariants: Shared Account Protection
    # -------------------------------------------------------------------------
    def test_safe_shared_account_delete_prevention(self):
        """Rotating code A does not delete shared account if code B still references it."""
        db.save_account("shared_vault@nf.com", "2099-12-31", "nid_s", plan="Premium")
        db.save_account("spare_vault@nf.com", "2099-12-31", "nid_sp", plan="Premium")
        code_a = "KEY_USER_ALPHA1"
        code_b = "KEY_USER_BETA02"
        conn = db.get_sqlite_conn()
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code_a, "shared_vault@nf.com", "2099-12-31"))
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code_b, "shared_vault@nf.com", "2099-12-31"))
        conn.commit()
        conn.close()

        # Admin accepts replacement for Code A
        conn = db.get_sqlite_conn()
        conn.execute("INSERT INTO requests (id, code, u7buy_order_id, status) VALUES (601, ?, 'U7_601', 'pending')",
                     (code_a,))
        conn.commit()
        conn.close()

        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["_csrf_token"] = TEST_CSRF_TOKEN

        with patch("app.blueprints.admin.routes.send_telegram_alert"):
            self.client.post("/admin/request/601/accept", data={"csrf_token": TEST_CSRF_TOKEN})

        # Key A now points to spare
        self.assertEqual(db.get_access_key(code_a)[1], "spare_vault@nf.com")
        # Shared account must still exist for Key B
        self.assertIsNotNone(db.get_account_by_email("shared_vault@nf.com"))
        self.assertEqual(db.get_access_key(code_b)[1], "shared_vault@nf.com")

    # -------------------------------------------------------------------------
    # 4. Safe Invariants: Out of Stock Requests Visible & Acceptable
    # -------------------------------------------------------------------------
    def test_safe_out_of_stock_pending_visibility(self):
        """Requests with pending_out_of_stock are included in pending list and can be accepted by admin."""
        code = "KEY_OOS_1234567"
        conn = db.get_sqlite_conn()
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, 'acc@nf.com', '2099-12-31')", (code,))
        conn.execute("INSERT INTO requests (id, code, u7buy_order_id, status) VALUES (701, ?, 'U7_701', 'pending_out_of_stock')", (code,))
        conn.commit()
        conn.close()

        pending_reqs = db.get_pending_requests()
        req_ids = [r["id"] for r in pending_reqs]
        self.assertIn(701, req_ids, "pending_out_of_stock must be listed in pending requests")

        # Restock account
        db.save_account("restocked@nf.com", "2099-12-31", "nid_re", plan="Premium")

        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["_csrf_token"] = TEST_CSRF_TOKEN

        with patch("app.blueprints.admin.routes.send_telegram_alert"):
            res = self.client.post("/admin/request/701/accept", data={"csrf_token": TEST_CSRF_TOKEN}, follow_redirects=False)

        self.assertEqual(res.status_code, 302)
        req = db.get_request_by_id(701)
        self.assertEqual(req["status"], "accepted")

    # -------------------------------------------------------------------------
    # 5. Safe Invariants: AI Vision & Fraud Guards
    # -------------------------------------------------------------------------
    def test_safe_ai_other_does_not_auto_rotate(self):
        """When AI returns OTHER, client selection must NOT override classification."""
        db.save_account("primary@nf.com", "2099-12-31", "nid_p", plan="Premium")
        db.save_account("spare@nf.com", "2099-12-31", "nid_sp", plan="Premium")
        code = "KEY_NO_BYPASS12"
        conn = db.get_sqlite_conn()
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, 'primary@nf.com', '2099-12-31')", (code,))
        conn.commit()
        conn.close()

        ai_mock = MagicMock()
        ai_mock.status_code = 200
        ai_mock.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"error_type": "OTHER", "is_netflix": True})}}]
        }

        data = {
            "code": code,
            "u7buy_order_id": "U7_BP",
            "reason_category": "TOO_MANY_PEOPLE",
            "image": (io.BytesIO(self._sample_png()), "proof.png")
        }

        with patch("requests.post", return_value=ai_mock), patch("app.blueprints.portal.routes.send_telegram_alert"):
            res = self.client.post("/api/submit_request", data=data, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json().get("auto_rotated", False))
        # Key must not have been rotated
        self.assertEqual(db.get_access_key(code)[1], "primary@nf.com")

    # -------------------------------------------------------------------------
    # 6. Portal Access Code Normalization & Cookie JSON Export
    # -------------------------------------------------------------------------
    def test_generate_nftoken_case_insensitive_and_cookie_json(self):
        """Portal generation must support lowercase/spaced code and always return valid cookie_json."""
        db.save_account("user_export@nf.com", "2099-12-31", "test_nid_val", secure_netflix_id="test_snid_val", plan="Premium")
        code = "CASE123TEST456"
        conn = db.get_sqlite_conn()
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, 'user_export@nf.com', '2099-12-31')", (code,))
        conn.commit()
        conn.close()

        with patch("app.blueprints.portal.routes.fetch_netflix_nftoken_api", return_value="mock_live_token_123"), \
             patch("app.blueprints.portal.routes.fetch_realtime_account_info", return_value=("Premium", "2099-12-31")):
            res = self.client.post("/api/generate_nftoken", json={"cookie": "  case123test456  "})

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("mock_live_token_123", data.get("pc_link"))
        # cookie_json must be populated and parseable
        cookie_json_str = data.get("cookie_json")
        self.assertTrue(bool(cookie_json_str))
        cookie_parsed = json.loads(cookie_json_str)
        self.assertIsInstance(cookie_parsed, list)
        names = [c.get("name") for c in cookie_parsed]
        self.assertIn("NetflixId", names)
        self.assertIn("SecureNetflixId", names)

    def test_check_live_code_case_insensitive(self):
        """Portal check_live_code must support lowercase code."""
        db.save_account("live_chk@nf.com", "2099-12-31", "test_nid_chk", plan="Premium")
        code = "LIVECHKCODE12"
        conn = db.get_sqlite_conn()
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, 'live_chk@nf.com', '2099-12-31')", (code,))
        conn.commit()
        conn.close()

        with patch("checker.check_account_live", return_value=("LIVE", "Premium")):
            res = self.client.post("/api/check_live_code", json={"cookie": "livechkcode12"})

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get("success"))

if __name__ == "__main__":
    unittest.main()
