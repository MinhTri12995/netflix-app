import json
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import database
from app.services import inventory_jobs as jobs
from tests.conftest import setup_admin_session, TEST_CSRF_TOKEN


def seed():
    conn = database.get_sqlite_conn()
    conn.executemany("INSERT INTO netflix_accounts(email,netflix_id,secure_netflix_id,plan,status) VALUES(?,?,?,?,?)",
                     [('a@example.test','fake-a','','Basic','usable'),
                      ('b@example.test','fake-b','','Premium','blocked_for_new_assignments'),
                      ('c@example.test','fake-c','','Premium','live')])
    conn.execute("INSERT INTO access_keys(code,assigned_email) VALUES('SAFE','c@example.test')")
    conn.commit(); conn.close()


def test_two_workers_claim_distinct_items_and_restart_keeps_progress(test_app):
    seed(); run = jobs.enqueue('full_scan')
    assert jobs.enqueue('payment_scan') == {'id':run['id'], 'existing':True}
    with ThreadPoolExecutor(2) as pool:
        items = list(pool.map(lambda _:jobs.claim(), range(2)))
    assert len({x['id'] for x in items}) == 2
    assert jobs.finish(items[0],'LIVE','Basic')
    assert jobs.finish(items[1],'LIVE',None)
    # A freshly opened connection sees committed progress and can resume remaining work.
    assert jobs.progress(run['id'])['processed'] == 2
    third = jobs.claim(); assert third
    conn=database.get_sqlite_conn();conn.execute('UPDATE inventory_items SET attempts=3 WHERE id=?',(third['id'],));conn.commit();conn.close()
    assert jobs.finish(third,'UNKNOWN')
    assert jobs.progress(run['id'])['run']['status'] == 'completed'
    conn = database.get_sqlite_conn()
    assert conn.execute("SELECT status FROM netflix_accounts WHERE email='b@example.test'").fetchone()[0] == 'blocked_for_new_assignments'
    assert conn.execute("SELECT assigned_email FROM access_keys WHERE code='SAFE'").fetchone()[0] == 'c@example.test'
    conn.close()


def test_expired_worker_cannot_write_or_complete_reclaimed_item(test_app):
    seed(); jobs.enqueue('full_scan'); old = jobs.claim()
    conn = database.get_sqlite_conn()
    conn.execute('UPDATE inventory_items SET lease_until=? WHERE id=?',(time.time()-1,old['id'])); conn.commit(); conn.close()
    assert not jobs.finish(old,'DIE')
    new = jobs.claim(); assert new['id'] == old['id']
    assert not jobs.finish(old,'LIVE','Premium')
    assert jobs.finish(new,'LIVE','Basic')


def test_unknown_preserves_plan_dead_keeps_link_changed_cookie_fenced(test_app):
    seed(); jobs.enqueue('full_scan'); a=jobs.claim()
    conn=database.get_sqlite_conn();conn.execute('UPDATE inventory_items SET attempts=3 WHERE id=?',(a['id'],));conn.commit();conn.close()
    assert jobs.finish(a,'UNKNOWN')
    b=jobs.claim()
    conn=database.get_sqlite_conn(); conn.execute("UPDATE netflix_accounts SET netflix_id='replacement' WHERE email=?",(b['email'],)); conn.commit(); conn.close()
    assert jobs.finish(b,'DIE')
    c=jobs.claim(); assert jobs.finish(c,'DIE')
    conn=database.get_sqlite_conn()
    assert conn.execute("SELECT plan FROM netflix_accounts WHERE email='a@example.test'").fetchone()[0]=='Basic'
    assert conn.execute("SELECT status FROM netflix_accounts WHERE email='c@example.test'").fetchone()[0]=='needs_review'
    assert conn.execute("SELECT assigned_email FROM access_keys WHERE code='SAFE'").fetchone()[0]=='c@example.test'
    conn.close()
    assert jobs.progress()['counts']['CHANGED']==1


def test_worker_checks_payment_and_progress_never_exposes_cookie(test_app):
    seed(); jobs.enqueue('full_scan')
    with patch('checker.check_account_live', return_value=('LIVE','Basic')) as check:
        assert jobs.work_once()
        assert check.call_args.kwargs['check_payment'] is True
    safe=json.dumps(jobs.progress())
    assert 'fake-a' not in safe and 'lease_token' not in safe and 'fingerprint' not in safe


def test_progress_auth_csrf_and_dashboard_restore(test_app):
    seed(); client=test_app.test_client()
    assert client.get('/admin/jobs/progress').status_code==302
    setup_admin_session(client)
    assert client.post('/admin/force_check_all').status_code==403
    with patch('app.services.inventory_jobs.start_worker'):
        assert client.post('/admin/force_check_all',data={'csrf_token':TEST_CSRF_TOKEN}).status_code==302
    progress=client.get('/admin/jobs/progress')
    assert progress.status_code==200 and progress.json['run']['total']==3
    assert progress.headers['Cache-Control']=='no-store'
    assert b'inventory-jobs.js' in client.get('/admin/').data


def test_duplicates_protect_all_assigned_accounts(test_app):
    seed(); conn=database.get_sqlite_conn()
    conn.execute("UPDATE netflix_accounts SET netflix_id='same' WHERE email IN ('b@example.test','c@example.test')")
    conn.execute("INSERT INTO netflix_accounts(email,netflix_id,plan) VALUES('d@example.test','same','Premium')")
    conn.commit(); conn.close()
    jobs.enqueue('duplicates')
    while jobs.work_once(): pass
    conn=database.get_sqlite_conn()
    assert conn.execute("SELECT 1 FROM netflix_accounts WHERE email='c@example.test'").fetchone()
    assert not conn.execute("SELECT 1 FROM netflix_accounts WHERE email='d@example.test'").fetchone()
    conn.close()
    assert jobs.progress()['counts']['DELETED']==2


def test_import_is_durable_verified_and_private(test_app):
    seed()
    job=jobs.enqueue('import',[{'email':'new@example.test','netflix_id':'synthetic-new'}])
    assert 'synthetic-new' not in json.dumps(jobs.progress(job['id']))
    with patch('checker.check_account_live',return_value=('LIVE','Basic')):
        assert jobs.work_once()
    conn=database.get_sqlite_conn()
    assert conn.execute("SELECT plan FROM netflix_accounts WHERE email='new@example.test'").fetchone()[0]=='Basic'
    assert conn.execute('SELECT payload FROM inventory_items WHERE run_id=?',(job['id'],)).fetchone()[0] is None
    conn.close()
    assert jobs.progress(job['id'])['counts']['LIVE']==1


def test_import_unknown_and_duplicate_do_not_guess_or_overwrite(test_app):
    seed()
    jobs.enqueue('import',[{'email':'a@example.test','netflix_id':'fake-a'}])
    conn=database.get_sqlite_conn();conn.execute('UPDATE inventory_items SET attempts=2');conn.commit();conn.close()
    with patch('checker.check_account_live',return_value=('LIVE',None)):
        jobs.work_once()
    assert jobs.progress()['counts']['UNKNOWN']==1
    jobs.enqueue('import',[{'email':'other@example.test','netflix_id':'fake-a'}])
    with patch('checker.check_account_live',return_value=('LIVE','Premium')):
        jobs.work_once()
    assert jobs.progress()['counts']['KEPT']==1
    conn=database.get_sqlite_conn()
    assert conn.execute("SELECT plan FROM netflix_accounts WHERE email='a@example.test'").fetchone()[0]=='Basic'
    assert not conn.execute("SELECT 1 FROM netflix_accounts WHERE email='other@example.test'").fetchone()
    conn.close()


def test_retry_ceiling_completes_with_error(test_app):
    conn=database.get_sqlite_conn()
    conn.execute("INSERT INTO netflix_accounts(email,netflix_id) VALUES('retry@example.test','synthetic')")
    conn.commit();conn.close()
    jobs.enqueue('full_scan')
    for _ in range(3):
        item=jobs.claim();assert item
        conn=database.get_sqlite_conn()
        conn.execute('UPDATE inventory_items SET lease_until=0 WHERE id=?',(item['id'],));conn.commit();conn.close()
    assert jobs.claim() is None
    assert jobs.progress()['counts']['ERROR']==1
    assert jobs.progress()['run']['status']=='completed'


def test_network_error_retries_then_finishes_unknown(test_app):
    conn=database.get_sqlite_conn()
    conn.execute("INSERT INTO netflix_accounts(email,netflix_id,plan) VALUES('retry@example.test','synthetic','Basic')")
    conn.commit();conn.close()
    jobs.enqueue('full_scan')
    with patch('checker.check_account_live',return_value=('UNKNOWN',None)) as check:
        for attempt in range(3):
            assert jobs.work_once()
            assert jobs.progress()['processed']==(1 if attempt==2 else 0)
            conn=database.get_sqlite_conn();conn.execute('UPDATE inventory_items SET lease_until=0 WHERE status=\'pending\'');conn.commit();conn.close()
        assert check.call_count==3
    assert jobs.progress()['counts']['UNKNOWN']==1


def test_legacy_comma_references_are_protected(test_app):
    seed();conn=database.get_sqlite_conn()
    conn.execute("UPDATE netflix_accounts SET netflix_id='same'")
    conn.execute("UPDATE access_keys SET assigned_email='a@example.test, b@example.test, c@example.test'")
    conn.commit();conn.close()
    jobs.enqueue('duplicates')
    while jobs.work_once(): pass
    assert jobs.progress()['counts'].get('DELETED',0)==0
