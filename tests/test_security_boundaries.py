import unittest
from unittest.mock import patch
from app import create_app
from app.config import Config
from app.services.rate_limiter import get_client_ip
from tests.conftest import setup_admin_session, TEST_CSRF_TOKEN
import database

class TestSecurityBoundaries(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="security-boundary-key-32-chars")
        self.client = self.app.test_client()

    def test_f11_admin_session_with_arbitrary_api_key_still_requires_csrf(self):
        """F11 Guard: Admin session CANNOT bypass CSRF simply by sending an arbitrary X-API-Key."""
        client = setup_admin_session(self.app.test_client())
        # Clear CSRF token to test CSRF enforcement
        with client.session_transaction() as sess:
            sess.pop("_csrf_token", None)

        res = client.post(
            "/api/check_and_import",
            json={"netflix_id": "nid_test"},
            headers={"X-API-Key": "any_random_forged_key"}
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("CSRF", res.get_data(as_text=True))

    def test_f11_anonymous_call_without_valid_api_key_returns_401(self):
        """Anonymous caller without valid ADMIN_API_KEY is rejected with 401."""
        with patch.object(Config, "ADMIN_API_KEY", "real-secret-admin-key-123"):
            res = self.client.post(
                "/api/check_and_import",
                json={"netflix_id": "nid_test"},
                headers={"X-API-Key": "wrong-key"}
            )
            self.assertEqual(res.status_code, 401)

    def test_f11_anonymous_call_with_valid_api_key_accepted(self):
        """Server-to-server call with valid ADMIN_API_KEY is authorized."""
        with patch.object(Config, "ADMIN_API_KEY", "real-secret-admin-key-123"), \
             patch("checker.check_account_live", return_value=("LIVE", "Standard")):
            res = self.client.post(
                "/api/check_and_import",
                json={"email": "s2s@nf.com", "netflix_id": "nid_s2s"},
                headers={"X-API-Key": "real-secret-admin-key-123"}
            )
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.get_json()["success"])

    def test_f12_untrusted_peer_cannot_spoof_ip(self):
        """F12 Guard: Client cannot bypass rate limiter by forging CF-Connecting-IP from untrusted peer."""
        class DummyRequest:
            remote_addr = "203.0.113.50"  # Untrusted client
            headers = {
                "CF-Connecting-IP": "198.51.100.99",
                "X-Forwarded-For": "198.51.100.99, 10.0.0.1"
            }

        with patch.object(Config, "TRUSTED_PROXIES", ["127.0.0.1", "10.0.0.1"]):
            ip = get_client_ip(DummyRequest())
            # Must strictly use remote_addr, ignoring forged headers!
            self.assertEqual(ip, "203.0.113.50")

    def test_f12_trusted_proxy_peer_trusts_forwarded_ip(self):
        """When peer is a verified trusted proxy, proxy headers are respected."""
        class DummyRequest:
            remote_addr = "10.0.0.1"  # Trusted reverse proxy
            headers = {
                "CF-Connecting-IP": "203.0.113.77"
            }

        with patch.object(Config, "TRUSTED_PROXIES", ["10.0.0.1"]):
            ip = get_client_ip(DummyRequest())
            self.assertEqual(ip, "203.0.113.77")

    def test_public_health_check_leaks_no_inventory(self):
        """Public /api/health returns minimal status without inventory counts or version."""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("status", data)
        self.assertNotIn("inventory", data)
        self.assertNotIn("version", data)
        self.assertNotIn("sqlite", data)

    def test_admin_health_check_returns_full_diagnostics(self):
        """Authenticated admin session receives detailed health telemetry."""
        admin_client = setup_admin_session(self.app.test_client())
        res = admin_client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("status", data)
        self.assertIn("inventory", data)
        self.assertIn("version", data)
        self.assertIn("sqlite", data)

if __name__ == "__main__":
    unittest.main()
