import unittest
import threading
import database
from app.services.allocation_service import replace

class TestReplacementIntegration(unittest.TestCase):
    def setUp(self):
        database.init_db()

    def test_20_concurrent_accept_calls_exact_one_rotation(self):
        """
        Acceptance Gate 2:
        20 concurrent accept calls on the same request ID result in:
        - Exactly 1 rotation event
        - Exactly 1 outbox entry
        - Exactly 1 'success' result
        - 19 'already_processed' results with matching assigned_email
        """
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("DELETE FROM netflix_accounts")
        c.execute("DELETE FROM access_keys")
        c.execute("DELETE FROM requests")
        c.execute("DELETE FROM rotation_events")
        c.execute("DELETE FROM events_outbox")
        c.execute("DELETE FROM operations")

        # Setup 1 active account and 1 spare account
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('active_user@nf.com', 'Premium', 'usable')")
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('spare_pool@nf.com', 'Premium', 'usable')")

        # Setup access key
        test_code = "CONCURRENT_REQ_01"
        c.execute("INSERT INTO access_keys (code, assigned_email, plan, assignment_version) VALUES (?, 'active_user@nf.com', 'Premium', 1)", (test_code,))

        # Setup pending request
        c.execute("INSERT INTO requests (code, u7buy_order_id, image_url, reason, status) VALUES (?, 'U7_CONCURRENT', 'http://img.png', 'Screen limit', 'pending')", (test_code,))
        req_id = c.lastrowid
        conn.commit()
        conn.close()

        results = []
        barrier = threading.Barrier(20)

        def worker(thread_idx):
            barrier.wait()
            op_id = f"worker_accept_{thread_idx}_{req_id}"
            res = replace(request_id=req_id, actor=f"admin_{thread_idx}", operation_id=op_id)
            results.append(res)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 20)

        successes = [r for r in results if r.status == "success"]
        already_processed = [r for r in results if r.status == "already_processed"]

        self.assertEqual(len(successes), 1, f"Expected exactly 1 success, got {len(successes)}")
        self.assertEqual(len(already_processed), 19, f"Expected 19 already_processed, got {len(already_processed)}")

        # Verify all return the exact same assigned email
        for r in results:
            self.assertEqual(r.assigned_email, "spare_pool@nf.com")

        # Verify database state
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM rotation_events WHERE request_id = ?", (str(req_id),))
        event_count = c.fetchone()[0]
        self.assertEqual(event_count, 1, f"Expected exactly 1 rotation_event row, got {event_count}")

        c.execute("SELECT COUNT(*) FROM events_outbox")
        outbox_count = c.fetchone()[0]
        self.assertEqual(outbox_count, 1, f"Expected exactly 1 events_outbox row, got {outbox_count}")

        c.execute("SELECT status FROM requests WHERE id = ?", (req_id,))
        req_status = c.fetchone()[0]
        self.assertEqual(req_status, "accepted")

        c.execute("SELECT assigned_email FROM access_keys WHERE code = ?", (test_code,))
        final_assigned = c.fetchone()[0]
        self.assertEqual(final_assigned, "spare_pool@nf.com")
        conn.close()

    def test_out_of_stock_preserves_old_link_and_marks_pending_out_of_stock(self):
        """
        When replacement candidate is unavailable:
        - Status returns 'out_of_stock'
        - Request status becomes 'pending_out_of_stock'
        - Old access key link is NOT destroyed
        - Account is NOT deleted
        """
        conn = database.get_sqlite_conn()
        c = conn.cursor()
        c.execute("DELETE FROM netflix_accounts")
        c.execute("DELETE FROM access_keys")
        c.execute("DELETE FROM requests")

        # Only 1 account in vault, which is already used by this code -> 0 candidates!
        c.execute("INSERT INTO netflix_accounts (email, plan, status) VALUES ('solitary@nf.com', 'Premium', 'usable')")
        test_code = "OOS_KEY_12345678"
        c.execute("INSERT INTO access_keys (code, assigned_email, plan) VALUES (?, 'solitary@nf.com', 'Premium')", (test_code,))
        c.execute("INSERT INTO requests (code, u7buy_order_id, image_url, reason, status) VALUES (?, 'U7_OOS', 'http://img.png', 'Hold', 'pending')", (test_code,))
        req_id = c.lastrowid
        conn.commit()
        conn.close()

        res = replace(request_id=req_id, actor="admin")
        self.assertEqual(res.status, "out_of_stock")

        # Verify old link is preserved
        key_row = database.get_access_key(test_code)
        self.assertEqual(key_row[1], "solitary@nf.com")

        # Verify request status
        req = database.get_request_by_id(req_id)
        self.assertEqual(req["status"], "pending_out_of_stock")

        # Verify account still exists
        acc = database.get_account_by_email("solitary@nf.com")
        self.assertIsNotNone(acc)

if __name__ == "__main__":
    unittest.main()
