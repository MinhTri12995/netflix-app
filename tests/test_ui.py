import unittest
from app import create_app
from tests.conftest import setup_admin_session
import database

class TestUIAccessibility(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="ui-test-key-32-chars")
        self.client = self.app.test_client()

    def test_portal_page_has_csrf_meta_and_portal_js(self):
        """Portal index includes CSRF meta tag, language options, and portal.js script."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('<meta name="csrf-token"', html)
        self.assertIn('<script src="/static/js/portal.js"></script>', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-modal="true"', html)
        self.assertIn('aria-label="Close warranty modal"', html)
        self.assertIn('id="languageSelect"', html)
        # Check that non-functional languages are excluded
        self.assertNotIn('<option value="es">', html)
        self.assertNotIn('<option value="tr">', html)

    def test_login_page_has_accessible_labels_and_autocomplete(self):
        """Admin login form includes labels and standard autocomplete attributes."""
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('<label for="admin-email"', html)
        self.assertIn('<label for="admin-password"', html)
        self.assertIn('autocomplete="username"', html)
        self.assertIn('autocomplete="current-password"', html)

    def test_admin_dashboard_has_responsive_meta_and_masked_cookie(self):
        """Admin dashboard has status filters and masked cookie elements."""
        admin_client = setup_admin_session(self.app.test_client())
        database.save_account("ui_test@nf.com", "2099-12-31", "test_cookie_123456", plan="Premium")

        res = admin_client.get("/admin", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('filterRequests', html)
        self.assertIn('toggleMask', html)
        self.assertIn('masked-cookie', html)
        self.assertIn('•••••••••••••••• (click to reveal)', html)
        # Raw cookie must not be exposed in visible table text
        self.assertNotIn('>test_cookie_123456<', html)

        database.delete_account("ui_test@nf.com", force=True)

if __name__ == "__main__":
    unittest.main()
