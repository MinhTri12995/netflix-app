"""
Distributed Job Queue Service with Atomic Lease Locking.
Prevents duplicate processing across multiple worker processes.
Supports job claiming, lease heartbeat, stale-worker rejection, and retry limits.
"""

import os
import time
import uuid
import json
import sqlite3
import datetime
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
import database

@dataclass
class Job:
    id: str
    job_type: str
    payload: Dict[str, Any]
    worker_id: Optional[str] = None
    lease_token: Optional[str] = None
    retry_count: int = 0
    status: str = "pending"

def init_job_tables():
    """Ensure job queue tables exist in SQLite."""
    conn = database.get_sqlite_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS background_jobs (
        id TEXT PRIMARY KEY,
        job_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        worker_id TEXT,
        lease_token TEXT,
        lease_expires_at TIMESTAMP,
        retry_count INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        error TEXT,
        result TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_lease ON background_jobs (status, lease_expires_at)")
    conn.commit()
    conn.close()

def create_job(job_type: str, payload: Dict[str, Any], max_retries: int = 3) -> str:
    """Enqueues a new background job."""
    init_job_tables()
    job_id = f"job_{uuid.uuid4().hex}"
    payload_json = json.dumps(payload)
    
    conn = database.get_sqlite_conn()
    c = conn.cursor()
    c.execute("""INSERT INTO background_jobs 
        (id, job_type, payload, status, max_retries, retry_count) 
        VALUES (?, ?, ?, 'pending', ?, 0)""",
        (job_id, job_type, payload_json, max_retries))
    conn.commit()
    conn.close()
    return job_id

def claim_job(worker_id: str, lease_seconds: int = 60) -> Optional[Job]:
    """
    Atomically claims a pending or expired job.
    Generates a unique lease_token that must be presented upon completion.
    """
    init_job_tables()
    conn = database.get_sqlite_conn()
    conn.isolation_level = "EXCLUSIVE"
    c = conn.cursor()

    try:
        now_ts = datetime.datetime.now(datetime.timezone.utc)
        # Find next available job: status is 'pending' OR (status is 'processing' and lease expired)
        c.execute("""SELECT id, job_type, payload, retry_count, lease_expires_at 
            FROM background_jobs 
            WHERE status = 'pending' 
               OR (status = 'processing' AND lease_expires_at < CURRENT_TIMESTAMP)
            ORDER BY created_at ASC 
            LIMIT 1""")
        row = c.fetchone()
        if not row:
            conn.commit()
            conn.close()
            return None

        job_id, job_type, payload_str, retry_count, _ = row
        lease_token = uuid.uuid4().hex
        lease_expires = (now_ts + datetime.timedelta(seconds=lease_seconds)).strftime("%Y-%m-%d %H:%M:%S")

        c.execute("""UPDATE background_jobs 
            SET status = 'processing',
                worker_id = ?,
                lease_token = ?,
                lease_expires_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?""",
            (worker_id, lease_token, lease_expires, job_id))
        conn.commit()
        conn.close()

        payload = json.loads(payload_str) if payload_str else {}
        return Job(
            id=job_id,
            job_type=job_type,
            payload=payload,
            worker_id=worker_id,
            lease_token=lease_token,
            retry_count=retry_count,
            status="processing"
        )
    except Exception as e:
        conn.rollback()
        conn.close()
        return None

def complete_job(job_id: str, lease_token: str, result: Optional[Dict[str, Any]] = None) -> bool:
    """
    Marks a job completed.
    Fails if lease_token does not match or lease has already expired and been re-claimed.
    """
    conn = database.get_sqlite_conn()
    conn.isolation_level = "EXCLUSIVE"
    c = conn.cursor()

    try:
        c.execute("""SELECT lease_token, lease_expires_at, status 
            FROM background_jobs WHERE id = ?""", (job_id,))
        row = c.fetchone()
        if not row:
            conn.rollback()
            conn.close()
            return False

        current_token, lease_expires_str, status = row
        if status != "processing" or current_token != lease_token:
            # Stale worker attempted completion after lease was transferred!
            conn.rollback()
            conn.close()
            return False

        res_json = json.dumps(result or {})
        c.execute("""UPDATE background_jobs 
            SET status = 'completed',
                result = ?,
                updated_at = CURRENT_TIMESTAMP 
            WHERE id = ? AND lease_token = ?""",
            (res_json, job_id, lease_token))
        success = (c.rowcount > 0)
        conn.commit()
        conn.close()
        return success
    except Exception:
        conn.rollback()
        conn.close()
        return False

def retry_or_fail_job(job_id: str, lease_token: str, error_msg: str) -> Tuple[bool, str]:
    """
    Retries or marks failed if retries exceeded.
    Returns (is_retried, new_status).
    """
    conn = database.get_sqlite_conn()
    conn.isolation_level = "EXCLUSIVE"
    c = conn.cursor()

    try:
        c.execute("SELECT retry_count, max_retries, lease_token FROM background_jobs WHERE id = ?", (job_id,))
        row = c.fetchone()
        if not row or row[2] != lease_token:
            conn.rollback()
            conn.close()
            return False, "invalid_lease"

        retries, max_retries, _ = row
        new_retries = retries + 1

        if new_retries < max_retries:
            c.execute("""UPDATE background_jobs 
                SET status = 'pending',
                    retry_count = ?,
                    error = ?,
                    worker_id = NULL,
                    lease_token = NULL,
                    updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?""", (new_retries, error_msg, job_id))
            conn.commit()
            conn.close()
            return True, "pending"
        else:
            c.execute("""UPDATE background_jobs 
                SET status = 'failed',
                    retry_count = ?,
                    error = ?,
                    updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?""", (new_retries, error_msg, job_id))
            conn.commit()
            conn.close()
            return False, "failed"
    except Exception:
        conn.rollback()
        conn.close()
        return False, "error"
