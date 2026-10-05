"""
Background Worker Entrypoint.
Runs background tasks using job_service with lease isolation.
"""

import os
import sys
import time
import signal
import uuid
from typing import Dict, Any

from app.services.job_service import claim_job, complete_job, retry_or_fail_job
from app.services.outbox_service import dispatch_outbox_events

RUNNING = True

def handle_sigterm(signum, frame):
    global RUNNING
    print("Worker received termination signal. Shutting down gracefully...")
    RUNNING = False

signal.signal(signal.SIGINT, handle_sigterm)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, handle_sigterm)

def process_single_job(job) -> Dict[str, Any]:
    """Routes job based on job_type."""
    if job.job_type == "outbox_dispatch":
        dispatched = dispatch_outbox_events(limit=job.payload.get("batch_size", 10))
        return {"dispatched_count": dispatched}
    elif job.job_type == "inventory_check":
        # Checkpoint single account live status
        import checker
        import database
        email = job.payload.get("email")
        cookie = job.payload.get("netflix_id")
        status, plan = checker.check_account_live(cookie, fallback_email=email)
        database.update_account_plan_and_status(email, plan=plan, status=status)
        return {"email": email, "status": status, "plan": plan}
    else:
        return {"status": "noop"}

def run_worker_loop(worker_id: str = None, single_run: bool = False, poll_interval: float = 2.0):
    """Main worker loop."""
    if not worker_id:
        worker_id = f"worker_{uuid.uuid4().hex[:8]}"

    print(f"[*] Starting background worker [{worker_id}]...")
    processed_count = 0

    while RUNNING:
        try:
            job = claim_job(worker_id=worker_id, lease_seconds=60)
            if job:
                print(f"[{worker_id}] Claimed job {job.id} (type: {job.job_type})")
                try:
                    result = process_single_job(job)
                    ok = complete_job(job.id, job.lease_token, result=result)
                    if ok:
                        print(f"[{worker_id}] Completed job {job.id}")
                        processed_count += 1
                    else:
                        print(f"[{worker_id}] Completion rejected for {job.id} (lease expired/transferred)")
                except Exception as proc_err:
                    print(f"[{worker_id}] Error executing job {job.id}: {proc_err}")
                    retry_or_fail_job(job.id, job.lease_token, error_msg=str(proc_err))
            else:
                if single_run:
                    break
                time.sleep(poll_interval)
        except Exception as e:
            print(f"[{worker_id}] Worker loop error: {e}")
            if single_run:
                break
            time.sleep(poll_interval)

    print(f"[*] Worker [{worker_id}] finished. Total jobs processed: {processed_count}")
    return processed_count

if __name__ == "__main__":
    single_pass = "--once" in sys.argv
    run_worker_loop(single_run=single_pass)
