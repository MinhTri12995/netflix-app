import unittest
import database
from app.services.order_service import (
    create_or_update_order,
    get_order,
    verify_order_for_request,
    import_orders_csv,
    init_orders_schema
)

class TestOrderService(unittest.TestCase):
    def setUp(self):
        database.init_db()
        init_orders_schema()
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("DELETE FROM orders")
        c.execute("DELETE FROM order_audit_log")
        c.execute("DELETE FROM access_keys")
        c.execute("DELETE FROM netflix_accounts")
        # Setup test accounts & keys
        c.execute("INSERT INTO netflix_accounts (email, plan) VALUES ('test_order@nf.com', 'Premium')")
        c.execute("INSERT INTO access_keys (code, assigned_email, plan) VALUES ('VALID_CODE_01', 'test_order@nf.com', 'Premium')")
        c.execute("INSERT INTO access_keys (code, assigned_email, plan) VALUES ('VALID_CODE_02', 'test_order@nf.com', 'Premium')")
        conn.commit()
        conn.close()

    def test_create_order_for_nonexistent_code_fails(self):
        """Binding order to non-existent access key must fail."""
        ok, msg = create_or_update_order("ORD_999", "NON_EXISTENT_CODE", "verified")
        self.assertFalse(ok)
        self.assertIn("CODE_NOT_FOUND", msg)

    def test_create_and_verify_valid_order(self):
        """Binding order to existing code succeeds and passes verification."""
        ok, msg = create_or_update_order("U7_1001", "VALID_CODE_01", "verified")
        self.assertTrue(ok)

        # Verification succeeds
        verified, reason = verify_order_for_request("VALID_CODE_01", "U7_1001")
        self.assertTrue(verified)
        self.assertEqual(reason, "VERIFIED")

    def test_one_code_cannot_have_two_orders(self):
        """A code already bound to Order 1 cannot be bound to Order 2."""
        ok1, _ = create_or_update_order("U7_FIRST", "VALID_CODE_01", "verified")
        self.assertTrue(ok1)

        ok2, msg2 = create_or_update_order("U7_SECOND", "VALID_CODE_01", "verified")
        self.assertFalse(ok2)
        self.assertIn("CODE_ALREADY_LINKED", msg2)

    def test_order_mismatch_or_cancelled_fails_verification(self):
        """Wrong code or cancelled order fails verification."""
        create_or_update_order("U7_CANCELLED", "VALID_CODE_01", "cancelled")
        verified, reason = verify_order_for_request("VALID_CODE_01", "U7_CANCELLED")
        self.assertFalse(verified)
        self.assertIn("cancelled", reason)

        # Wrong code
        create_or_update_order("U7_OTHER", "VALID_CODE_02", "verified")
        verified_wrong, reason_wrong = verify_order_for_request("VALID_CODE_01", "U7_OTHER")
        self.assertFalse(verified_wrong)
        self.assertIn("MISMATCH", reason_wrong)

    def test_import_orders_csv_line_by_line(self):
        """CSV import processes valid rows and returns line-by-line errors."""
        csv_data = """order_id,code,status
U7_CSV_1,VALID_CODE_01,verified
U7_CSV_BAD,INVALID_CODE,verified
U7_CSV_2,VALID_CODE_02,verified
"""
        result = import_orders_csv(csv_data, actor="admin_csv")
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["order_id"], "U7_CSV_BAD")
        self.assertIn("CODE_NOT_FOUND", result["errors"][0]["error"])

        # Verify audit log recorded changes
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM order_audit_log WHERE actor = 'admin_csv'")
        audit_count = c.fetchone()[0]
        self.assertEqual(audit_count, 2)
        conn.close()

    def test_unverified_order_routes_to_admin_pending_queue(self):
        """When an order is unverified or missing, warranty request routes to admin review (pending)."""
        import io
        from unittest.mock import patch, MagicMock
        from app import create_app
        from app.config import Config

        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        # Do NOT create order for VALID_CODE_01 (it's unverified)
        from tests.conftest import create_valid_png_bytes
        png_bytes = create_valid_png_bytes()
        mock_ai_resp = MagicMock()
        mock_ai_resp.status_code = 200
        mock_ai_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"error_type": "TOO_MANY_PEOPLE", "is_netflix": true, "visible_email": "test_order@nf.com", "error_description": "Screen limit"}'
                }
            }]
        }
        data = {
            "u7buy_order_id": "U7_UNVERIFIED_ORDER",
            "code": "VALID_CODE_01",
            "reason_category": "TOO_MANY_PEOPLE",
            "reason": "Screen limit",
            "image": (io.BytesIO(png_bytes), "screenshot.png")
        }

        with patch("requests.post", return_value=mock_ai_resp), patch("app.blueprints.portal.routes.send_telegram_alert"), patch.object(Config, "AUTO_APPROVAL_ENABLED", True):
            res = client.post("/api/submit_request", data=data, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        self.assertTrue(res_json.get("success"))
        # Must NOT auto-rotate because order is unverified!
        self.assertFalse(res_json.get("auto_rotated"))

        # Verify request saved as pending in database
        reqs = database.get_pending_requests()
        found = [r for r in reqs if r.get("code") == "VALID_CODE_01"]
        self.assertTrue(len(found) > 0)
        self.assertEqual(found[0]["status"], "pending")

if __name__ == "__main__":
    unittest.main()

