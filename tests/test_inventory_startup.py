from unittest.mock import Mock, patch
from app.services import inventory_jobs as jobs


def test_cloud_sdk_initializes_before_worker_threads_start(monkeypatch):
    monkeypatch.setenv('DISABLE_ADMIN_WORKER','0')
    events=[]
    worker=Mock();worker.is_alive.return_value=False
    worker.start.side_effect=lambda:events.append('worker')
    with patch.object(jobs,'_workers',[]),patch.object(jobs.database,'SUPABASE_KEY','synthetic'),patch.object(jobs.database,'get_supabase',side_effect=lambda:events.append('sdk')),patch.object(jobs.threading,'Thread',return_value=worker):
        jobs.start_worker(Mock(testing=False))
    assert events==['sdk','worker','worker','worker']
