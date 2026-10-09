import unittest
from tests.conftest import create_isolated_test_app, setup_admin_session, TEST_CSRF_TOKEN
import database

class TestAdminRequestChange(unittest.TestCase):
    def setUp(self):
        self.app, self.db_path, self.orig_conn = create_isolated_test_app()
        self.client = self.app.test_client()
        self.admin_client = setup_admin_session(self.app.test_client())

        # Seed sample accounts and key
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("DELETE FROM netflix_accounts")
        c.execute("DELETE FROM access_keys")
        c.execute("DELETE FROM requests")
        c.execute("DELETE FROM rotation_events")

        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('old_acc@nf.com', 'Premium', 'usable')")
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('new_acc@nf.com', 'Premium', 'usable')")
        c.execute("INSERT INTO access_keys (code, assigned_email, plan, expire_at) VALUES ('TEST_KEY_ADMIN_1', 'old_acc@nf.com', 'Premium', '2099-12-31')")
        conn.commit()
        conn.close()

    def tearDown(self):
        database.get_sqlite_conn = self.orig_conn
        import os
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_unauthorized_access_blocked(self):
        """Anonymous requests must be redirected to login or forbidden."""
        res = self.client.get("/admin/api/key_info/TEST_KEY_ADMIN_1")
        self.assertIn(res.status_code, [302, 401, 403])

        res_post = self.client.post("/admin/request_change", data={"code": "TEST_KEY_ADMIN_1"})
        self.assertIn(res_post.status_code, [302, 401, 403])

    def test_api_key_info_found(self):
        """GET /admin/api/key_info/<code> returns JSON with code details."""
        res = self.admin_client.get("/admin/api/key_info/TEST_KEY_ADMIN_1")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        key_info = data.get("key")
        self.assertEqual(key_info["code"], "TEST_KEY_ADMIN_1")
        self.assertEqual(key_info["assigned_email"], "old_acc@nf.com")
        self.assertEqual(key_info["plan"], "Premium")
        self.assertFalse(key_info["is_expired"])

    def test_api_key_info_not_found(self):
        """GET /admin/api/key_info/NONEXISTENT returns 404 JSON."""
        res = self.admin_client.get("/admin/api/key_info/NONEXISTENT")
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertFalse(data.get("success"))

    def test_admin_request_change_mode_keep(self):
        """Mode 1: mode='keep' rotates account to new_acc, keeps old_acc in vault."""
        res = self.admin_client.post(
            "/admin/request_change",
            data={
                "csrf_token": TEST_CSRF_TOKEN,
                "code": "TEST_KEY_ADMIN_1",
                "mode": "keep",
                "reason_category": "TOO_MANY_PEOPLE",
                "note": "Screen limit on customer TV"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("assigned_email"), "new_acc@nf.com")
        self.assertFalse(data.get("deleted_old"))

        # Check access key was updated
        k = database.get_access_key("TEST_KEY_ADMIN_1")
        self.assertEqual(k[1], "new_acc@nf.com")

        # Check old account still exists in vault
        old = database.get_account_by_email("old_acc@nf.com")
        self.assertIsNotNone(old, "Old account MUST be kept in netflix_accounts for Mode 1")

    def test_admin_request_change_mode_delete(self):
        """Mode 2: mode='delete' rotates account to new_acc, permanently deletes old_acc from vault."""
        res = self.admin_client.post(
            "/admin/request_change",
            data={
                "csrf_token": TEST_CSRF_TOKEN,
                "code": "TEST_KEY_ADMIN_1",
                "mode": "delete",
                "reason_category": "PAYMENT_ERROR",
                "note": "Payment hold error"
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("assigned_email"), "new_acc@nf.com")
        self.assertTrue(data.get("deleted_old"))

        # Check access key was updated
        k = database.get_access_key("TEST_KEY_ADMIN_1")
        self.assertEqual(k[1], "new_acc@nf.com")

        # Check old account is DELETED from vault
        old = database.get_account_by_email("old_acc@nf.com")
        self.assertIsNone(old, "Old account MUST be permanently deleted for Mode 2")

    def test_rotate_key_table_route_with_delete_mode(self):
        """POST /admin/rotate_key/<code> with mode=delete deletes old account."""
        res = self.admin_client.post(
            "/admin/rotate_key/TEST_KEY_ADMIN_1",
            data={
                "csrf_token": TEST_CSRF_TOKEN,
                "mode": "delete"
            },
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)

        # Check key updated and old account deleted
        k = database.get_access_key("TEST_KEY_ADMIN_1")
        self.assertEqual(k[1], "new_acc@nf.com")
        old = database.get_account_by_email("old_acc@nf.com")
        self.assertIsNone(old, "Old account should be deleted when mode=delete")

    def test_rotate_key_table_route_with_keep_mode(self):
        """POST /admin/rotate_key/<code> with mode=keep preserves old account."""
        res = self.admin_client.post(
            "/admin/rotate_key/TEST_KEY_ADMIN_1",
            data={
                "csrf_token": TEST_CSRF_TOKEN,
                "mode": "keep"
            },
            follow_redirects=True
        )
        self.assertEqual(res.status_code, 200)

        k = database.get_access_key("TEST_KEY_ADMIN_1")
        self.assertEqual(k[1], "new_acc@nf.com")
        old = database.get_account_by_email("old_acc@nf.com")
        self.assertIsNotNone(old, "Old account should be preserved when mode=keep")

if __name__ == "__main__":
    unittest.main()
