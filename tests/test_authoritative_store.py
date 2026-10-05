import os
import sys
import threading
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import sqlite3

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database as db
from app.services.business_result import OperationResult
from app.services.allocation_service import (
    allocate,
    lookup_operation,
    generate_secure_code,
    get_plan_for_code
)

class TestAuthoritativeStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "accounts.db")
        self.orig_conn = db.get_sqlite_conn
        db.get_sqlite_conn = lambda p="accounts.db": sqlite3.connect(self.db_path)
        db.SUPABASE_KEY = ""

        # Initialize schema
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
        conn.execute("""CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            u7buy_order_id TEXT,
            image_url TEXT,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS operations (
            operation_id TEXT PRIMARY KEY,
            status TEXT,
            assigned_email TEXT,
            detail_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    def test_csp_rng_code_generation(self):
        """Mã mới CSPRNG ít nhất 16 ký tự, ngẫu nhiên bảo mật."""
        codes = [generate_secure_code("Premium") for _ in range(50)]
        for c in codes:
            self.assertGreaterEqual(len(c), 16)
        # All codes must be unique
        self.assertEqual(len(set(codes)), 50)

    def test_legacy_code_length_mapping(self):
        """Hỗ trợ tương thích mã legacy theo độ dài."""
        self.assertEqual(get_plan_for_code("A" * 15), "Premium")
        self.assertEqual(get_plan_for_code("A" * 10), "Standard")
        self.assertEqual(get_plan_for_code("A" * 8), "Standard_Ads")
        self.assertEqual(get_plan_for_code("A" * 5), "Basic")
        # 16-char code defaults to Premium if not specified
        self.assertEqual(get_plan_for_code("A" * 16), "Premium")

    def test_cloud_write_failure_does_not_silently_write_to_sqlite(self):
        """F04: Cloud write failure must return temporarily_unavailable, NOT silently write to SQLite and report success."""
        cloud_mock = MagicMock()
        cloud_mock.table().select().eq().execute.side_effect = RuntimeError("Supabase connection timeout")
        cloud_mock.table().insert().execute.side_effect = RuntimeError("Supabase connection timeout")

        with patch("database.SUPABASE_KEY", "dummy-key"), \
             patch("database.get_supabase", return_value=cloud_mock):
            res = allocate("TESTCODE16CHARS1", "Premium", operation_id="op_cloud_fail")

        self.assertEqual(res.status, "temporarily_unavailable")
        self.assertTrue(res.retryable)

        # Verify nothing was written to local SQLite
        conn = db.get_sqlite_conn()
        row = conn.execute("SELECT * FROM access_keys WHERE code = 'TESTCODE16CHARS1'").fetchone()
        conn.close()
        self.assertIsNone(row, "Cloud failure must NOT resurrect or store phantom data in SQLite!")

    def test_atomic_allocation_prevents_capacity_race(self):
        """F01: Concurrent allocation in solo mode must never exceed capacity (1 account = 1 key)."""
        db.set_config("SHARE_MODE_ENABLED", False)
        # Seed exactly 1 account
        db.save_account("single_acc@nf.com", "2099-12-31", "nid_s", plan="Premium")

        results = []
        threads = []

        def worker(code_str, op_id):
            res = allocate(code_str, "Premium", operation_id=op_id)
            results.append(res)

        t1 = threading.Thread(target=worker, args=("CODE_THREAD_0001", "op_t1"))
        t2 = threading.Thread(target=worker, args=("CODE_THREAD_0002", "op_t2"))

        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        statuses = [r.status for r in results]
        # Exactly one must succeed and one must be out_of_stock
        self.assertEqual(statuses.count("success"), 1, f"Expected exactly 1 success, got: {statuses}")
        self.assertEqual(statuses.count("out_of_stock"), 1, f"Expected exactly 1 out_of_stock, got: {statuses}")

        # Check DB has only 1 key assigned to single_acc
        conn = db.get_sqlite_conn()
        keys = conn.execute("SELECT code, assigned_email FROM access_keys").fetchall()
        conn.close()
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0][1], "single_acc@nf.com")

    def test_idempotent_operation_lookup(self):
        """Re-submitting with the same operation_id returns the saved result without double-allocating."""
        db.set_config("SHARE_MODE_ENABLED", False)
        db.save_account("idemp_acc@nf.com", "2099-12-31", "nid_i", plan="Premium")

        op_id = "op_unique_12345"
        res1 = allocate("IDEMP_CODE_00001", "Premium", operation_id=op_id)
        self.assertEqual(res1.status, "success")
        self.assertEqual(res1.assigned_email, "idemp_acc@nf.com")

        # Second call with same operation_id
        res2 = allocate("IDEMP_CODE_00001", "Premium", operation_id=op_id)
        self.assertEqual(res2.status, "success")
        self.assertEqual(res2.assigned_email, "idemp_acc@nf.com")
        self.assertEqual(res2.operation_id, op_id)

        # Check only 1 key exists in DB
        conn = db.get_sqlite_conn()
        keys = conn.execute("SELECT COUNT(*) FROM access_keys").fetchone()[0]
        conn.close()
        self.assertEqual(keys, 1)

if __name__ == "__main__":
    unittest.main()
