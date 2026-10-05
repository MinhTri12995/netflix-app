import os
import sys
import io
import uuid
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
import database
from app.services.token_service import fetch_netflix_nftoken_api, ProxyError, CookieError

class TestPhaseA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config.update(TESTING=True, SECRET_KEY="phase-a-test-secret")
        database.init_db()
        database.save_account("seed_phase_a@nf.com", "2099-12-31", "nid_a", plan="Premium")

    @classmethod
    def tearDownClass(cls):
        database.delete_account("seed_phase_a@nf.com", force=True)

    def setUp(self):
        self.client = self.app.test_client()

    def test_f02_force_rotate_code_removed(self):
        """F02: /api/force_rotate_code must be completely removed (return 404)."""
        res = self.client.post("/api/force_rotate_code", json={"cookie": "ANY_CODE"})
        self.assertEqual(res.status_code, 404)

    def test_f07_image_upload_rejects_non_image(self):
        """F07: Reject uploads without genuine image header bytes with HTTP 400."""
        test_code = "P" + uuid.uuid4().hex[:14].upper()
        database.create_access_key(test_code, "2027-12-31")

        fake_data = b"This is just plain text, not a real image header!"
        form_fake = {
            "u7buy_order_id": "TEST_ORDER_001",
            "code": test_code,
            "reason": "Test non-image",
            "image": (io.BytesIO(fake_data), "fake.png", "image/png")
        }
        res_fake = self.client.post("/api/submit_request", data=form_fake, content_type="multipart/form-data")
        self.assertEqual(res_fake.status_code, 400)
        self.assertIn("Unsupported image format", res_fake.get_json()["error"])

        database.delete_access_key(test_code)

    def test_f07_image_upload_accepts_png(self):
        """F07: Accept genuine PNG images with HTTP 200."""
        test_code = "P" + uuid.uuid4().hex[:14].upper()
        database.create_access_key(test_code, "2027-12-31")

        from tests.conftest import create_valid_png_bytes
        valid_png_bytes = create_valid_png_bytes()
        form_valid = {
            "u7buy_order_id": "TEST_ORDER_002",
            "code": test_code,
            "reason": "Test real image",
            "image": (io.BytesIO(valid_png_bytes), "screenshot.png", "image/png")
        }
        res_valid = self.client.post("/api/submit_request", data=form_valid, content_type="multipart/form-data")
        self.assertEqual(res_valid.status_code, 200)
        self.assertTrue(res_valid.get_json()["success"])

        database.delete_access_key(test_code)

    def test_f07_rotation_count_counts_auto_accepted(self):
        """F07: 24h Quota counts 'auto_accepted' as well as accepted."""
        auto_code = "Q" + uuid.uuid4().hex[:14].upper()
        database.create_access_key(auto_code, "2027-12-31")
        database.save_request(auto_code, "ORDER_AUTO", "http://example.com/img.png", "Screen full", "auto_accepted")

        count = database.get_today_rotation_count(auto_code)
        self.assertEqual(count, 1)

        database.delete_access_key(auto_code)

    def test_f06_token_endpoint_404_raises_proxy_error_never_cookie_error(self):
        """F06: HTTP 404 from upstream token API must raise ProxyError, NEVER CookieError."""
        mock_resp_404 = MagicMock()
        mock_resp_404.status_code = 404
        mock_resp_404.ok = False

        with patch("requests.get", return_value=mock_resp_404):
            with self.assertRaises(ProxyError) as ctx:
                fetch_netflix_nftoken_api("dummy_netflix_id")
            self.assertIn("404", str(ctx.exception))

    def test_f10_admin_dashboard_form_actions_have_admin_prefix(self):
        """F10: Admin dashboard form action URLs must all be prefixed with /admin/."""
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["admin_email"] = "admin@example.com"

        res_admin = self.client.get("/admin/dashboard")
        self.assertEqual(res_admin.status_code, 200)
        html = res_admin.get_data(as_text=True)
        self.assertIn('action="/admin/upload"', html)
        self.assertIn('action="/admin/filter_duplicates"', html)
        self.assertIn('action="/admin/check_payment"', html)
        self.assertIn('action="/admin/force_check_all"', html)
        self.assertIn('action="/admin/check_all"', html)
        self.assertIn('action="/admin/delete/', html)
        self.assertNotIn('action="/upload"', html)
        self.assertNotIn('action="/filter_duplicates"', html)

if __name__ == "__main__":
    unittest.main()
