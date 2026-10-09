"""
Regression test suite for Phase C fixes:
- F14: CSRF Protection & Secret Key Persistence
- F12: Rate Limiting (Sliding Window) & CSPRNG Entropy
- F13: Parser Hardening, Multi-Account Flush & File Parsing
- F15: Background Scan Concurrency Guard & System Health Check
- F16: Dependency Pinning
"""
import os
import sys
import unittest
import tempfile
import sqlite3
import io
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import parser
import database
from app import create_app
from app.config import Config
from app.services.rate_limiter import check_rate_limit, reset_rate_limit, _ip_buckets
import app.blueprints.admin.routes as admin_routes

class TestPhaseC(unittest.TestCase):
    def setUp(self):
        # Create temp sqlite db for isolation
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
        c.execute("""CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        conn.commit()
        conn.close()

        # Reset rate limiter storage between tests
        _ip_buckets.clear()

        # Create test app client
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

    def tearDown(self):
        database.get_sqlite_conn = self.orig_get_sqlite_conn
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    # ----------------------------------------------------
    # 1. CSRF Protection (F14)
    # ----------------------------------------------------
    def test_csrf_protection_rejects_missing_token(self):
        """Logged-in admin POST without CSRF token must be rejected with HTTP 403."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True

        res = self.client.post("/admin/generate_key", data={"plan_type": "basic", "duration": "1"})
        self.assertEqual(res.status_code, 403)
        self.assertIn(b"CSRF token missing or invalid", res.data)

    def test_csrf_protection_rejects_invalid_token(self):
        """Logged-in admin POST with invalid CSRF token must be rejected with HTTP 403."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["csrf_token"] = "valid_secret_csrf_token_12345678"

        res = self.client.post(
            "/admin/generate_key",
            data={"plan_type": "basic", "duration": "1", "csrf_token": "wrong_token_attempt"}
        )
        self.assertEqual(res.status_code, 403)

    def test_csrf_protection_allows_valid_token_in_form(self):
        """Logged-in admin POST with matching session CSRF token passes."""
        token = "test_valid_csrf_token_abcdef123456"
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["csrf_token"] = token

        res = self.client.post(
            "/admin/generate_key",
            data={"plan_type": "basic", "duration": "1", "csrf_token": token}
        )
        # Should succeed and redirect to admin.dashboard (302)
        self.assertEqual(res.status_code, 302)

    def test_csrf_protection_allows_valid_token_in_header(self):
        """Logged-in admin POST with matching X-CSRF-Token header passes."""
        token = "test_valid_csrf_token_header_123456"
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["csrf_token"] = token

        res = self.client.post(
            "/admin/generate_key",
            headers={"X-CSRF-Token": token},
            data={"plan_type": "basic", "duration": "1"}
        )
        self.assertEqual(res.status_code, 302)

    def test_csrf_does_not_block_portal_when_admin_logged_in(self):
        """Public portal endpoints (/api/generate_nftoken) must not be blocked by CSRF even when logged into admin."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True

        # Call public portal endpoint without CSRF token
        res = self.client.post("/api/generate_nftoken", json={"cookie": "TEST_CODE"})
        # Should not be 403 Forbidden!
        self.assertNotEqual(res.status_code, 403)

    # ----------------------------------------------------
    # 2. Rate Limiting & Entropy (F12)
    # ----------------------------------------------------
    def test_rate_limiter_blocks_abuse(self):
        """Sliding window rate limiter triggers 429 when requests exceed threshold."""
        ip = "192.168.1.100"
        endpoint = "test_endpoint"
        limit = 5
        window = 60

        for _ in range(limit):
            allowed, _ = check_rate_limit(f"{ip}:{endpoint}", limit, window)
            self.assertTrue(allowed)

        # 6th request must be blocked
        allowed, retry_after = check_rate_limit(f"{ip}:{endpoint}", limit, window)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)

    def test_portal_api_rate_limiter_http(self):
        """API endpoints return HTTP 429 on excessive requests."""
        ip_header = {"X-Forwarded-For": "203.0.113.10"}
        for i in range(30):
            res = self.client.post("/api/generate_nftoken", headers=ip_header, json={})
            self.assertNotEqual(res.status_code, 429)

        # 31st request triggers 429
        res = self.client.post("/api/generate_nftoken", headers=ip_header, json={})
        self.assertEqual(res.status_code, 429)
        self.assertIn("Too many requests", res.get_json().get("error", ""))

    # ----------------------------------------------------
    # 3. Parser Multi-line & Raw Cookie Hardening (F13)
    # ----------------------------------------------------
    def test_parser_multiple_raw_cookie_lines_no_data_loss(self):
        """Sequential raw cookie lines without email headers must all be preserved."""
        raw_lines = [
            "NetflixId=cookie_val_1; SecureNetflixId=secure_val_1",
            "NetflixId=cookie_val_2; SecureNetflixId=secure_val_2",
            "NetflixId=cookie_val_3; SecureNetflixId=secure_val_3"
        ]
        accounts = parser.parse_lines(raw_lines)
        self.assertEqual(len(accounts), 3)
        self.assertEqual(accounts[0]['netflix_id'], "cookie_val_1")
        self.assertEqual(accounts[1]['netflix_id'], "cookie_val_2")
        self.assertEqual(accounts[2]['netflix_id'], "cookie_val_3")

    def test_parser_multiline_without_email_preserved(self):
        """Multi-line accounts without Email lines must not be dropped."""
        text = """
NetflixId: nid_account_1
SecureNetflixId: snid_account_1
Plan: Premium
# ===
NetflixId: nid_account_2
SecureNetflixId: snid_account_2
Plan: Standard
"""
        accounts = parser.parse_lines(text.splitlines())
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[0]['netflix_id'], "nid_account_1")
        self.assertEqual(accounts[0]['plan'], "Premium")
        self.assertEqual(accounts[1]['netflix_id'], "nid_account_2")
        self.assertEqual(accounts[1]['plan'], "Standard")

    def test_parse_netflix_file(self):
        """parse_netflix_file reads file and returns accounts properly."""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
            tf.write("NetflixId=file_nid_1; SecureNetflixId=file_snid_1\n")
            tf.write("NetflixId=file_nid_2; SecureNetflixId=file_snid_2\n")
            filepath = tf.name

        try:
            accs = parser.parse_netflix_file(filepath)
            self.assertEqual(len(accs), 2)
            self.assertEqual(accs[0]['netflix_id'], "file_nid_1")
            self.assertEqual(accs[1]['netflix_id'], "file_nid_2")
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

    # ----------------------------------------------------
    # 4. Scan Concurrency & Health Check (F15)
    # ----------------------------------------------------
    def test_scan_concurrency_lock(self):
        """Background scan routes block concurrent executions when _is_scanning is active."""
        token = "test_csrf_token_scan"
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["_csrf_token"] = token
            sess["csrf_token"] = token

        from app.services.inventory_jobs import enqueue, progress
        conn = database.get_sqlite_conn()
        conn.execute("INSERT INTO netflix_accounts(email,netflix_id) VALUES('scan@test.invalid','fake')")
        conn.commit(); conn.close()
        existing = enqueue('full_scan')
        with patch('app.services.inventory_jobs.start_worker'):
            res = self.client.post("/admin/check_all", data={"csrf_token": token}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Đang có tác vụ chạy".encode("utf-8"), res.data)
        self.assertEqual(progress()['run']['id'], existing['id'])

    def test_api_health_endpoint(self):
        """api_health returns 200 with inventory and database status."""
        database.save_account("health_test@nf.com", "2099-01-01", "nid_h1")
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO access_keys (code, assigned_email, expire_at) VALUES ('HEALTHKEY1', 'health_test@nf.com', '2099-01-01')")
        conn.commit()
        conn.close()

        with self.client.session_transaction() as sess:
            sess["logged_in"] = True

        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["sqlite"], "OK")
        self.assertGreaterEqual(data["inventory"]["accounts"], 1)
        self.assertGreaterEqual(data["inventory"]["access_keys"], 1)

    # ----------------------------------------------------
    # 5. Submit Request Auto-Approval (TOO_MANY_PEOPLE & PAYMENT_ERROR)
    # ----------------------------------------------------
    def test_submit_request_too_many_people_auto_rotate(self):
        """TOO_MANY_PEOPLE screenshot triggers auto-rotation and deletes faulty account."""
        database.save_account("faulty_screen@nf.com", "2099-01-01", "nid_faulty1", plan="Premium")
        database.save_account("spare_screen@nf.com", "2099-01-01", "nid_spare1", plan="Premium")
        
        code = "SCRN12345678901"
        conn = database.get_sqlite_conn()
        conn.execute("INSERT OR REPLACE INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code, "faulty_screen@nf.com", "2099-01-01"))
        conn.commit()
        conn.close()

        from app.services.order_service import create_or_update_order
        create_or_update_order("U7_SCREEN_101", code, "verified")

        mock_ai_resp = MagicMock()
        mock_ai_resp.status_code = 200
        mock_ai_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"error_type": "TOO_MANY_PEOPLE", "is_netflix": true, "visible_email": "faulty_screen@nf.com", "error_description": "Too many people watching on your account"}'
                }
            }]
        }

        from tests.conftest import create_valid_png_bytes
        png_bytes = create_valid_png_bytes()
        data = {
            "u7buy_order_id": "U7_SCREEN_101",
            "code": code,
            "reason_category": "TOO_MANY_PEOPLE",
            "reason": "Screen limit on TV",
            "image": (io.BytesIO(png_bytes), "screenshot.png")
        }

        with patch("requests.post", return_value=mock_ai_resp), patch("app.blueprints.portal.routes.send_telegram_alert"), patch.object(Config, "AUTO_APPROVAL_ENABLED", True), patch.object(Config, "MISTRAL_API_KEY", "test-only-key"):
            res = self.client.post("/api/submit_request", data=data, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        self.assertTrue(res_json.get("success"))
        self.assertTrue(res_json.get("auto_rotated"))

        self.assertIsNone(database.get_account_by_email("faulty_screen@nf.com"))
        key_row = database.get_access_key(code)
        self.assertEqual(key_row[1], "spare_screen@nf.com")

    def test_submit_request_payment_error_auto_rotate(self):
        """In Task 1, PAYMENT_ERROR screenshot routes to manual Admin review (pending), not auto-rotate."""
        database.save_account("faulty_pay@nf.com", "2099-01-01", "nid_faulty_pay", plan="Premium")
        database.save_account("spare_pay@nf.com", "2099-01-01", "nid_spare_pay", plan="Premium")

        code = "PAY123456789012"
        conn = database.get_sqlite_conn()
        conn.execute("INSERT OR REPLACE INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code, "faulty_pay@nf.com", "2099-01-01"))
        conn.commit()
        conn.close()

        mock_ai_resp = MagicMock()
        mock_ai_resp.status_code = 200
        mock_ai_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"error_type": "PAYMENT_ERROR", "is_netflix": true, "card_last4": null, "visible_email": null, "error_description": "Membership on hold: Please update payment"}'
                }
            }]
        }

        from tests.conftest import create_valid_png_bytes
        png_bytes = create_valid_png_bytes()
        data = {
            "u7buy_order_id": "U7_PAY_202",
            "code": code,
            "reason_category": "PAYMENT_ERROR",
            "reason": "Membership on hold",
            "image": (io.BytesIO(png_bytes), "screenshot.png")
        }

        with patch("requests.post", return_value=mock_ai_resp), patch("app.blueprints.portal.routes.send_telegram_alert"), patch.object(Config, "AUTO_APPROVAL_ENABLED", True):
            res = self.client.post("/api/submit_request", data=data, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        self.assertTrue(res_json.get("success"))
        # In Task 1 / Phase 0, payment errors must route to Admin review (auto_rotated: False)
        self.assertFalse(res_json.get("auto_rotated", False))

        key_row = database.get_access_key(code)
        self.assertEqual(key_row[1], "faulty_pay@nf.com")

    # ----------------------------------------------------
    # 6. Dependency Lock (F16)
    # ----------------------------------------------------
    def test_requirements_txt_is_pinned(self):
        """requirements.txt must have exact pinned dependencies with =="""
        req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
        with open(req_path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

        self.assertGreater(len(lines), 0)
        for line in lines:
            self.assertIn("==", line, f"Requirement line '{line}' is not pinned with ==")

if __name__ == "__main__":
    unittest.main()
