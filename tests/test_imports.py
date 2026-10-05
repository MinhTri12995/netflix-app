import unittest
from unittest.mock import patch, MagicMock
import os
import tempfile
import database
from app.services.import_service import import_accounts, process_import_file, ImportResult
from app import create_app

class TestImports(unittest.TestCase):
    def setUp(self):
        database.init_db()
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("DELETE FROM netflix_accounts")
        conn.commit()
        conn.close()

    def test_import_accounts_verifies_save_success(self):
        """F10 Invariant: If save_account fails, count as retryable_failure and not complete success."""
        accounts = [
            {"email": "acc1@nf.com", "expire": "2099-12-31", "netflix_id": "nid_1", "plan": "Premium"},
            {"email": "acc2@nf.com", "expire": "2099-12-31", "netflix_id": "nid_2", "plan": "Premium"}
        ]

        # Simulate database error where save_account returns False for all
        with patch("database.save_account", return_value=False):
            res = import_accounts(accounts)

        self.assertEqual(res.saved_count, 0)
        self.assertEqual(res.failure_count, 2)
        self.assertFalse(res.is_complete_success)

    def test_import_accounts_missing_netflix_id_marked_invalid(self):
        """Rows without netflix_id are counted as invalid."""
        accounts = [
            {"email": "bad@nf.com", "expire": "2099-12-31", "netflix_id": "", "plan": "Premium"}
        ]
        res = import_accounts(accounts)
        self.assertEqual(res.invalid_count, 1)
        self.assertEqual(res.saved_count, 0)

    def test_partial_save_retry(self):
        """If row 1 succeeds and row 2 fails, retry processes row 2."""
        acc1 = {"email": "acc1@nf.com", "expire": "2099-12-31", "netflix_id": "nid_1", "plan": "Premium"}
        acc2 = {"email": "acc2@nf.com", "expire": "2099-12-31", "netflix_id": "nid_2", "plan": "Premium"}

        # First run: acc1 succeeds, acc2 fails
        def side_effect_save(email, *args, **kwargs):
            return email == "acc1@nf.com"

        with patch("database.save_account", side_effect=side_effect_save):
            res1 = import_accounts([acc1, acc2])

        self.assertEqual(res1.saved_count, 1)
        self.assertEqual(res1.failure_count, 1)
        self.assertFalse(res1.is_complete_success)

        # Retry with fixed database
        res2 = import_accounts([acc2])
        self.assertEqual(res2.saved_count, 1)
        self.assertEqual(res2.failure_count, 0)
        self.assertTrue(res2.is_complete_success)

    def test_check_and_import_returns_unknown_not_die(self):
        """API check-and-import must preserve UNKNOWN and not convert it to DIE."""
        from tests.conftest import setup_admin_session, TEST_CSRF_TOKEN
        app = create_app()
        app.config["TESTING"] = True
        client = setup_admin_session(app.test_client())

        # Mock checker returning UNKNOWN
        with patch("checker.check_account_live", return_value=("UNKNOWN", None)):
            res = client.post(
                "/api/check_and_import",
                json={"netflix_id": "nid_unknown_test"},
                headers={"X-CSRF-Token": TEST_CSRF_TOKEN}
            )

        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        self.assertFalse(res_json.get("success"))
        self.assertEqual(res_json.get("status"), "UNKNOWN")

    def test_check_and_import_saves_and_returns_live(self):
        """API check-and-import imports live account successfully."""
        from tests.conftest import setup_admin_session, TEST_CSRF_TOKEN
        app = create_app()
        app.config["TESTING"] = True
        client = setup_admin_session(app.test_client())

        with patch("checker.check_account_live", return_value=("LIVE", "Standard")):
            res = client.post(
                "/api/check_and_import",
                json={
                    "email": "live_user@nf.com",
                    "netflix_id": "nid_live_test"
                },
                headers={"X-CSRF-Token": TEST_CSRF_TOKEN}
            )

        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        self.assertTrue(res_json.get("success"))
        self.assertEqual(res_json.get("status"), "LIVE")
        self.assertEqual(res_json.get("plan"), "Standard")

        # Verify saved in database
        acc = database.get_account_by_netflix_id("nid_live_test")
        self.assertIsNotNone(acc)
        self.assertEqual(acc[5], "Standard")

    def test_process_import_file_routing(self):
        """Files with failures go to Errors directory; full successes go to Processed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            watch_dir = tmp_dir
            test_file = os.path.join(watch_dir, "test_batch.txt")

            with open(test_file, "w", encoding="utf-8") as f:
                f.write("user@nf.com:pass | Cookie = NetflixId=nid_route_test\n")

            # Process with successful save
            res = process_import_file(test_file, watch_dir=watch_dir)
            self.assertTrue(res.is_complete_success)

            # Original file should be gone from watch root
            self.assertFalse(os.path.exists(test_file))

            # Should exist in Processed folder
            processed_dir = os.path.join(watch_dir, "Processed")
            self.assertTrue(os.path.exists(processed_dir))
            self.assertEqual(len(os.listdir(processed_dir)), 1)

if __name__ == "__main__":
    unittest.main()
