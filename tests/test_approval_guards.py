import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import database as db
from app import create_app
from app.config import Config
from app.services import token_service as token
from app.services import rate_limiter as limiter

class TestApprovalGuards(unittest.TestCase):
    def setUp(self):
        # Configure test app with isolated in-memory or test SQLite database
        self.test_db = "test_guards.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

        # Patch database path
        self.db_patch = patch.object(db, "SUPABASE_KEY", "")
        self.db_patch.start()
        
        # Point sqlite connection to test_db
        self.orig_get_sqlite_conn = db.get_sqlite_conn
        db.get_sqlite_conn = lambda db_path=self.test_db: self.orig_get_sqlite_conn(self.test_db)

        db.init_db()
        conn = db.get_sqlite_conn(self.test_db)
        for t in ["access_keys", "requests", "netflix_accounts"]:
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
        conn.close()

        token._code_last_request_time.clear()
        token._code_attempts_history.clear()
        token._code_last_live_check.clear()
        limiter._ip_buckets.clear()

        self.app = create_app()
        self.app.config.update(TESTING=True, SECRET_KEY="guard-test-secret")
        self.client = self.app.test_client()

    def tearDown(self):
        self.db_patch.stop()
        db.get_sqlite_conn = self.orig_get_sqlite_conn
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    def _create_sample_png(self):
        from tests.conftest import create_valid_png_file
        return create_valid_png_file()

    def test_ai_other_client_too_many_people_does_not_rotate(self):
        """F05 Guard: User selects TOO_MANY_PEOPLE, but AI returns OTHER with unrelated email.
        Must NOT auto-rotate! Key stays with original account, request queued as pending."""
        db.save_account("original@netflix.com", "2099-12-31", "nid_orig", plan="Premium")
        db.save_account("spare@netflix.com", "2099-12-31", "nid_spare", plan="Premium")
        
        code = "TESTKEY12345678"
        conn = db.get_sqlite_conn(self.test_db)
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code, "original@netflix.com", "2099-12-31"))
        conn.commit()
        conn.close()

        # Mock AI returning OTHER
        ai_resp = MagicMock()
        ai_resp.status_code = 200
        ai_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "error_type": "OTHER",
                        "is_netflix": True,
                        "visible_email": "unrelated@gmail.com",
                        "error_description": "Unknown screen error"
                    })
                }
            }]
        }

        data = {
            "code": code,
            "u7buy_order_id": "U7_TEST_01",
            "reason_category": "TOO_MANY_PEOPLE",
            "reason": "Screen limit selected by client",
            "image": (self._create_sample_png(), "test.png")
        }

        with patch("requests.post", return_value=ai_resp), patch("app.blueprints.portal.routes.send_telegram_alert"):
            res = self.client.post("/api/submit_request", data=data, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        res_data = res.get_json()
        self.assertFalse(res_data.get("auto_rotated", False), "Client selection must NOT override AI OTHER!")
        
        # Verify key was NOT rotated
        key_row = db.get_access_key(code)
        self.assertEqual(key_row[1], "original@netflix.com")
        self.assertIsNotNone(db.get_account_by_email("original@netflix.com"))

    def test_payment_error_routes_to_manual_admin_queue(self):
        """F06 Guard: PAYMENT_ERROR must route to manual Admin queue in Task 1, not auto-rotate."""
        db.save_account("pay_orig@netflix.com", "2099-12-31", "nid_orig", plan="Premium")
        db.save_account("pay_spare@netflix.com", "2099-12-31", "nid_spare", plan="Premium")

        code = "TESTPAYKEY12345"
        conn = db.get_sqlite_conn(self.test_db)
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code, "pay_orig@netflix.com", "2099-12-31"))
        conn.commit()
        conn.close()

        ai_resp = MagicMock()
        ai_resp.status_code = 200
        ai_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "error_type": "PAYMENT_ERROR",
                        "is_netflix": True,
                        "card_last4": None,
                        "visible_email": None,
                        "error_description": "Membership on hold"
                    })
                }
            }]
        }

        data = {
            "code": code,
            "u7buy_order_id": "U7_PAY_01",
            "reason_category": "PAYMENT_ERROR",
            "reason": "Payment error",
            "image": (self._create_sample_png(), "pay.png")
        }

        with patch("requests.post", return_value=ai_resp), patch("app.blueprints.portal.routes.send_telegram_alert"):
            res = self.client.post("/api/submit_request", data=data, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        res_data = res.get_json()
        self.assertFalse(res_data.get("auto_rotated", False), "Payment errors must route to Admin review, not auto-rotate!")

        # Key must not be rotated
        key_row = db.get_access_key(code)
        self.assertEqual(key_row[1], "pay_orig@netflix.com")

    def test_pending_out_of_stock_and_mismatch_visible_and_acceptable_by_admin(self):
        """F08 Guard: Requests saved with pending_out_of_stock or pending_card_mismatch
        must be returned in get_pending_requests() and admin must be able to accept them."""
        db.save_account("cust_acc@netflix.com", "2099-12-31", "nid_cust", plan="Premium")
        code = "CODEOUTSTOCK123"
        conn = db.get_sqlite_conn(self.test_db)
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code, "cust_acc@netflix.com", "2099-12-31"))
        conn.commit()
        conn.close()

        # Save requests with out_of_stock and card_mismatch statuses
        db.save_request(code, "U7_OOS", "img_oos", "Out of stock when rotated", "pending_out_of_stock")
        db.save_request(code, "U7_MISMATCH", "img_mis", "Card mismatch review", "pending_card_mismatch")

        pending_list = db.get_pending_requests()
        statuses = [r["status"] for r in pending_list]
        self.assertIn("pending_out_of_stock", statuses, "pending_out_of_stock must be visible in admin pending requests!")
        self.assertIn("pending_card_mismatch", statuses, "pending_card_mismatch must be visible in admin pending requests!")

        # Add spare account to vault so admin can accept
        db.save_account("new_spare@netflix.com", "2099-12-31", "nid_new_spare", plan="Premium")

        # Find request ID for pending_out_of_stock
        oos_req = next(r for r in pending_list if r["status"] == "pending_out_of_stock")
        req_id = oos_req["id"]

        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["_csrf_token"] = "test-csrf"

        with patch("app.blueprints.admin.routes.send_telegram_alert"):
            resp = self.client.post(f"/admin/request/{req_id}/accept", data={"csrf_token": "test-csrf"}, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        # Check that request status is now accepted
        req_after = db.get_request_by_id(req_id)
        self.assertEqual(req_after["status"], "accepted", "Admin must be able to accept pending_out_of_stock requests!")

    def test_failed_db_save_does_not_return_success(self):
        """F07 Guard: If database.save_request returns False, the endpoint must return 500 error."""
        db.save_account("acc1@netflix.com", "2099-12-31", "nid1", plan="Premium")
        code = "TESTKEYFAIL1234"
        conn = db.get_sqlite_conn(self.test_db)
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code, "acc1@netflix.com", "2099-12-31"))
        conn.commit()
        conn.close()

        data = {
            "code": code,
            "u7buy_order_id": "U7_SAVE_FAIL",
            "reason_category": "OTHER",
            "reason": "Test save failure",
            "image": (self._create_sample_png(), "test.png")
        }

        with patch.object(db, "save_request", return_value=False), patch("app.blueprints.portal.routes.send_telegram_alert"):
            res = self.client.post("/api/submit_request", data=data, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 500)
        res_data = res.get_json()
        self.assertFalse(res_data.get("success"), "Must NOT return success=True when DB save fails!")

    def test_shared_account_not_deleted_when_other_customer_shares_it(self):
        """F03 Guard: When Code A rotates, if Code B still shares the old account,
        the old account must NOT be deleted from netflix_accounts."""
        db.save_account("shared@netflix.com", "2099-12-31", "nid_shared", plan="Premium")
        db.save_account("spare_for_a@netflix.com", "2099-12-31", "nid_spare", plan="Premium")

        code_a = "KEY_CUSTOMER_A1"
        code_b = "KEY_CUSTOMER_B2"
        conn = db.get_sqlite_conn(self.test_db)
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code_a, "shared@netflix.com", "2099-12-31"))
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code_b, "shared@netflix.com", "2099-12-31"))
        conn.commit()
        conn.close()

        # Admin accepts replacement for Code A
        db.save_request(code_a, "ORDER_A", "img_a", "Request from customer A", "pending")
        req_id = db.get_pending_requests()[0]["id"]

        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["_csrf_token"] = "test-csrf"

        with patch("app.blueprints.admin.routes.send_telegram_alert"):
            self.client.post(f"/admin/request/{req_id}/accept", data={"csrf_token": "test-csrf"})

        # Code A should now have spare_for_a
        key_a = db.get_access_key(code_a)
        self.assertEqual(key_a[1], "spare_for_a@netflix.com")

        # Code B still points to shared@netflix.com, and shared@netflix.com MUST STILL EXIST!
        key_b = db.get_access_key(code_b)
        self.assertEqual(key_b[1], "shared@netflix.com")
        self.assertIsNotNone(db.get_account_by_email("shared@netflix.com"),
                             "Account shared by Customer B must NOT be deleted when Customer A rotates!")

    def test_activation_cookie_error_does_not_delete_account_when_vault_is_empty(self):
        """F14 Guard: If activation encounters CookieError and vault has no spare accounts,
        the account must NOT be deleted beforehand, leaving key orphaned."""
        db.save_account("only_acc@netflix.com", "2099-12-31", "nid_only", plan="Premium")
        code = "KEY_SOLO_123456"
        conn = db.get_sqlite_conn(self.test_db)
        conn.execute("INSERT INTO access_keys (code, assigned_email, expire_at) VALUES (?, ?, ?)",
                     (code, "only_acc@netflix.com", "2099-12-31"))
        conn.commit()
        conn.close()

        # Simulate generate token with CookieError
        from app.services.token_service import CookieError
        with patch("app.blueprints.portal.routes.fetch_netflix_nftoken_api", side_effect=CookieError("Session invalid")):
            res = self.client.post("/api/generate_nftoken", json={"cookie": code})

        self.assertEqual(res.status_code, 500)
        # Verify account was NOT deleted because rotation failed (no spare)
        self.assertIsNotNone(db.get_account_by_email("only_acc@netflix.com"),
                             "Account must NOT be deleted if vault is out of stock!")
        key_row = db.get_access_key(code)
        self.assertEqual(key_row[1], "only_acc@netflix.com", "Access key must retain link to account!")

if __name__ == "__main__":
    unittest.main()
