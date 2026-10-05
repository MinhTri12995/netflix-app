import unittest
from unittest.mock import patch, MagicMock
import checker

class TestChecker(unittest.TestCase):
    def test_http_500_returns_unknown_not_live(self):
        """F09 Invariant: HTTP 500 error on /YourAccount must return UNKNOWN, not LIVE."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.ok = False
        mock_resp.url = "https://www.netflix.com/YourAccount"
        mock_resp.text = "Internal Server Error"

        with patch("requests.get", return_value=mock_resp):
            status, plan = checker.check_account_live("nid123", "snid123", check_payment=True)

        self.assertEqual(status, "UNKNOWN")
        self.assertIsNone(plan)

    def test_http_403_or_429_returns_unknown(self):
        """HTTP 403 and 429 rate limit or IP block must return UNKNOWN, not DIE or LIVE."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.ok = False
        mock_resp.url = "https://www.netflix.com/YourAccount"
        mock_resp.text = "Access Denied"

        with patch("requests.get", return_value=mock_resp):
            status, plan = checker.check_account_live("nid123", "snid123", check_payment=True)

        self.assertEqual(status, "UNKNOWN")
        self.assertIsNone(plan)

    def test_empty_or_alien_page_returns_unknown(self):
        """Captive portal or ISP intercept page must return UNKNOWN, not LIVE."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.url = "http://wifi-login.local"
        mock_resp.text = "<html><body>Please log in to hotel Wi-Fi</body></html>"

        with patch("requests.get", return_value=mock_resp):
            status, plan = checker.check_account_live("nid123", "snid123", check_payment=True)

        self.assertEqual(status, "UNKNOWN")
        self.assertIsNone(plan)

    def test_missing_token_in_ambiguous_response_returns_unknown(self):
        """If Token API returns 200 but token is missing and response has no DIE indicators -> UNKNOWN."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.url = checker.NETFLIX_API_URL
        mock_resp.json.return_value = {"value": {"account": {}}}

        with patch("requests.get", return_value=mock_resp):
            status, plan = checker.check_account_live("nid123", "snid123", check_payment=False)

        self.assertEqual(status, "UNKNOWN")
        self.assertIsNone(plan)

    def test_live_account_does_not_default_to_premium(self):
        """If plan cannot be identified from HTML, plan must be None, NOT defaulted to Premium."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.url = "https://www.netflix.com/YourAccount"
        # Netflix page with account markers, but no plan name
        mock_resp.text = '<html>netflix YourAccount nextBillingDate: {"fieldType":"String","value":"2099-12-31"}</html>'

        # Force API to simulate web-only check
        with patch("checker._get_token_and_plan_api", return_value="API_DEAD"), \
             patch("requests.get", return_value=mock_resp):
            status, plan = checker.check_account_live("nid123", "snid123", check_payment=True)

        self.assertEqual(status, "LIVE")
        self.assertIsNone(plan)

    def test_live_account_identifies_standard_and_premium(self):
        """Explicit plan text maps correctly to standard or premium."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.url = "https://www.netflix.com/YourAccount"
        mock_resp.text = '<html>netflix YourAccount plan: standard nextBillingDate: {"fieldType":"String","value":"2099-12-31"}</html>'

        with patch("checker._get_token_and_plan_api", return_value="API_DEAD"), \
             patch("requests.get", return_value=mock_resp):
            status, plan = checker.check_account_live("nid123", "snid123", check_payment=True)

        self.assertEqual(status, "LIVE")
        self.assertEqual(plan, "Standard")

    def test_definite_die_returns_die(self):
        """Redirect to login or payment hold keyword definitely returns DIE."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.url = "https://www.netflix.com/YourAccount"
        mock_resp.text = "<html>netflix YourAccount membership is on hold</html>"

        with patch("checker._get_token_and_plan_api", return_value="API_DEAD"), \
             patch("requests.get", return_value=mock_resp):
            status, plan = checker.check_account_live("nid123", "snid123", check_payment=True)

        self.assertEqual(status, "DIE")
        self.assertIsNone(plan)

if __name__ == "__main__":
    unittest.main()
