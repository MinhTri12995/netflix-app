import unittest
import time
from app.services.job_service import create_job, claim_job, complete_job, retry_or_fail_job, init_job_tables
import database

class TestJobsLimits(unittest.TestCase):
    def setUp(self):
        database.init_db()
        init_job_tables()
        conn = database.get_sqlite_conn()
        conn.execute("DELETE FROM background_jobs")
        conn.commit()
        conn.close()

    def test_single_job_claimed_by_only_one_worker(self):
        """When two workers compete for a job, only one gets it."""
        job_id = create_job("outbox_dispatch", {"batch_size": 5})

        job_worker_1 = claim_job("worker_A", lease_seconds=60)
        job_worker_2 = claim_job("worker_B", lease_seconds=60)

        self.assertIsNotNone(job_worker_1)
        self.assertEqual(job_worker_1.id, job_id)
        self.assertEqual(job_worker_1.worker_id, "worker_A")
        # Second worker finds nothing pending
        self.assertIsNone(job_worker_2)

    def test_stale_worker_rejected_after_lease_expiry(self):
        """Worker A's lease expires; Worker B re-claims; Worker A tries to complete -> REJECTED."""
        job_id = create_job("inventory_check", {"email": "acc@nf.com"})

        # Worker A claims with 0-second lease (immediately expires)
        job_a = claim_job("worker_A", lease_seconds=0)
        self.assertIsNotNone(job_a)

        time.sleep(1.1)

        # Worker B re-claims the expired job
        job_b = claim_job("worker_B", lease_seconds=60)
        self.assertIsNotNone(job_b)
        self.assertEqual(job_b.id, job_id)
        self.assertEqual(job_b.worker_id, "worker_B")

        # Worker A tries to complete with stale lease token -> MUST BE REJECTED
        ok_a = complete_job(job_id, job_a.lease_token, {"status": "stale"})
        self.assertFalse(ok_a)

        # Worker B completes with active lease token -> SUCCESS
        ok_b = complete_job(job_id, job_b.lease_token, {"status": "fresh"})
        self.assertTrue(ok_b)

    def test_retry_count_and_failure_transition(self):
        """Job retries up to max_retries then transitions to failed."""
        job_id = create_job("test_retry_job", {"attempt": 1}, max_retries=2)

        # Attempt 1
        job = claim_job("worker_1", lease_seconds=60)
        is_retried, status = retry_or_fail_job(job.id, job.lease_token, "Error 1")
        self.assertTrue(is_retried)
        self.assertEqual(status, "pending")

        # Attempt 2 (reaches max_retries=2)
        job_2 = claim_job("worker_2", lease_seconds=60)
        is_retried_2, status_2 = retry_or_fail_job(job_2.id, job_2.lease_token, "Error 2")
        self.assertFalse(is_retried_2)
        self.assertEqual(status_2, "failed")

if __name__ == "__main__":
    unittest.main()
