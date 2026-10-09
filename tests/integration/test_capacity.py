import os
import sys
import threading
import unittest
import tempfile
import sqlite3

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import database as db
from app.services.allocation_service import allocate

class TestCapacityIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "accounts.db")
        self.orig_conn = db.get_sqlite_conn
        db.get_sqlite_conn = lambda p="accounts.db": sqlite3.connect(self.db_path)
        db.SUPABASE_KEY = ""

        conn = db.get_sqlite_conn()
        conn.execute("""CREATE TABLE IF NOT EXISTS netflix_accounts (
            email TEXT PRIMARY KEY,
            expire_date TEXT,
            netflix_id TEXT,
            secure_netflix_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan TEXT,
            status TEXT DEFAULT 'usable'
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS access_keys (
            code TEXT PRIMARY KEY,
            assigned_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expire_at TEXT,
            plan TEXT
        )""")
        conn.commit()
        conn.close()

    def tearDown(self):
        db.get_sqlite_conn = self.orig_conn
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            os.rmdir(self.tmp_dir)
        except Exception:
            pass

    def test_twenty_concurrent_requests_solo_mode_only_one_succeeds(self):
        """20 yêu cầu tranh một chỗ (Solo Mode, sức chứa 1): duy nhất 1 thành công, 19 báo out_of_stock."""
        db.set_config("SHARE_MODE_ENABLED", False)
        db.save_account("solo_race@nf.com", "2099-12-31", "nid_solo", plan="Premium")

        results = []
        barrier = threading.Barrier(20)

        def worker(idx):
            code = f"SOLO_RACE_{idx:04d}_KEY"
            barrier.wait()
            res = allocate(code, "Premium")
            results.append(res)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        success_count = sum(1 for r in results if r.status == "success")
        oos_count = sum(1 for r in results if r.status == "out_of_stock")

        self.assertEqual(success_count, 1, f"Expected exactly 1 success for solo mode, got {success_count}")
        self.assertEqual(oos_count, 19, f"Expected exactly 19 out_of_stock, got {oos_count}")

        conn = db.get_sqlite_conn()
        key_count = conn.execute("SELECT COUNT(*) FROM access_keys WHERE assigned_email = 'solo_race@nf.com'").fetchone()[0]
        conn.close()
        self.assertEqual(key_count, 1)

    def test_twenty_concurrent_requests_shared_premium_two_succeed(self):
        """20 requests for one Premium account admit exactly two codes."""
        db.set_config("SHARE_MODE_ENABLED", True)
        db.save_account("prem_race@nf.com", "2099-12-31", "nid_prem", plan="Premium")

        results = []
        barrier = threading.Barrier(20)

        def worker(idx):
            code = f"PREM_RACE_{idx:04d}_KEY"
            barrier.wait()
            res = allocate(code, "Premium")
            results.append(res)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        success_count = sum(1 for r in results if r.status == "success")
        oos_count = sum(1 for r in results if r.status == "out_of_stock")

        self.assertEqual(success_count, 2, f"Expected exactly 2 successes for Premium shared mode, got {success_count}")
        self.assertEqual(oos_count, 18, f"Expected exactly 18 out_of_stock, got {oos_count}")

        conn = db.get_sqlite_conn()
        key_count = conn.execute("SELECT COUNT(*) FROM access_keys WHERE assigned_email = 'prem_race@nf.com'").fetchone()[0]
        conn.close()
        self.assertEqual(key_count, 2)

    def test_twenty_concurrent_requests_shared_standard_two_succeed(self):
        """20 yêu cầu tranh tài khoản Standard (Shared Mode, sức chứa 2): đúng 2 thành công, 18 báo out_of_stock."""
        db.set_config("SHARE_MODE_ENABLED", True)
        db.save_account("std_race@nf.com", "2099-12-31", "nid_std", plan="Standard")

        results = []
        barrier = threading.Barrier(20)

        def worker(idx):
            code = f"STD_RACE_{idx:04d}_KEY"
            barrier.wait()
            res = allocate(code, "Standard")
            results.append(res)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        success_count = sum(1 for r in results if r.status == "success")
        oos_count = sum(1 for r in results if r.status == "out_of_stock")

        self.assertEqual(success_count, 2, f"Expected exactly 2 successes for Standard shared mode, got {success_count}")
        self.assertEqual(oos_count, 18, f"Expected exactly 18 out_of_stock, got {oos_count}")

        conn = db.get_sqlite_conn()
        key_count = conn.execute("SELECT COUNT(*) FROM access_keys WHERE assigned_email = 'std_race@nf.com'").fetchone()[0]
        conn.close()
        self.assertEqual(key_count, 2)

if __name__ == "__main__":
    unittest.main()
