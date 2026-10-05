import unittest
from app.services.evidence_service import (
    parse_and_validate_ai_response,
    evaluate_evidence_for_auto_approval
)

class TestEvidenceService(unittest.TestCase):
    def test_string_boolean_is_netflix_is_rejected(self):
        """String boolean ('true' or 'false') must fail strict schema validation."""
        raw = {
            "is_netflix": "true",
            "error_type": "TOO_MANY_PEOPLE",
            "visible_email": "user@nf.com"
        }
        ok, data, msg = parse_and_validate_ai_response(raw)
        self.assertFalse(ok)
        self.assertIn("must be a strict boolean", msg)

    def test_malformed_json_returns_error(self):
        """Malformed JSON string returns error."""
        raw_str = "```json {is_netflix: true, error_type: TOO_MANY_PEOPLE} ```" # invalid json (unquoted keys)
        ok, data, msg = parse_and_validate_ai_response(raw_str)
        self.assertFalse(ok)
        self.assertIn("JSON_DECODE_ERROR", msg)

    def test_non_netflix_screenshot_rejected(self):
        """is_netflix: False must be rejected."""
        raw = {
            "is_netflix": False,
            "error_type": "OTHER",
            "visible_email": None
        }
        ok, data, msg = parse_and_validate_ai_response(raw)
        self.assertFalse(ok)
        self.assertIn("does not show Netflix", msg)

    def test_unknown_error_type_defaults_to_other(self):
        """Unrecognized error_type defaults to OTHER."""
        raw = {
            "is_netflix": True,
            "error_type": "SOME_RANDOM_ERROR",
            "visible_email": "user@nf.com"
        }
        ok, data, msg = parse_and_validate_ai_response(raw)
        self.assertTrue(ok)
        self.assertEqual(data["error_type"], "OTHER")

    def test_screen_limit_without_email_accepted_for_auto_approval(self):
        """Netflix screen limit overlay does not display user email; valid screen limit is accepted for auto-approval."""
        evidence = {
            "is_netflix": True,
            "error_type": "TOO_MANY_PEOPLE",
            "visible_email": None
        }
        ok, reason = evaluate_evidence_for_auto_approval(evidence, "assigned@nf.com")
        self.assertTrue(ok)
        self.assertEqual(reason, "ELIGIBLE_FOR_AUTO_APPROVAL")

    def test_email_mismatch_rejected_for_auto_approval(self):
        """Visible email must match assigned email; mismatch routes to admin."""
        evidence = {
            "is_netflix": True,
            "error_type": "TOO_MANY_PEOPLE",
            "visible_email": "hacker@gmail.com"
        }
        ok, reason = evaluate_evidence_for_auto_approval(evidence, "assigned@nf.com")
        self.assertFalse(ok)
        self.assertIn("EMAIL_MISMATCH", reason)

    def test_payment_error_rejected_for_auto_approval(self):
        """Payment errors must never be auto-approved; must route to admin."""
        evidence = {
            "is_netflix": True,
            "error_type": "PAYMENT_ERROR",
            "visible_email": "assigned@nf.com"
        }
        ok, reason = evaluate_evidence_for_auto_approval(evidence, "assigned@nf.com")
        self.assertFalse(ok)
        self.assertIn("ERROR_TYPE_NOT_SCREEN_LIMIT", reason)

    def test_valid_screen_limit_with_matching_email_eligible(self):
        """Proper screen limit error with verified matching email passes auto-approval evaluation."""
        evidence = {
            "is_netflix": True,
            "error_type": "TOO_MANY_PEOPLE",
            "visible_email": "Assigned@NF.com"
        }
        ok, reason = evaluate_evidence_for_auto_approval(evidence, "assigned@nf.com")
        self.assertTrue(ok)
        self.assertEqual(reason, "ELIGIBLE_FOR_AUTO_APPROVAL")

if __name__ == "__main__":
    unittest.main()
