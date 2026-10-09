from unittest.mock import patch
import database
from app.services import inventory_jobs as jobs


def seed():
    conn=database.get_sqlite_conn()
    conn.executemany("INSERT INTO netflix_accounts(email,netflix_id,plan,status) VALUES(?,?,?,?)",[
        ('bad@example.test','synthetic-a','Premium','needs_review'),
        ('linked@example.test','synthetic-b','Premium','needs_review'),
        ('live@example.test','synthetic-c','Premium','live')])
    conn.execute("INSERT INTO access_keys(code,assigned_email,plan) VALUES('LIVEKEY','linked@example.test','Premium')")
    conn.commit();conn.close()


def test_cleanup_verifies_twice_before_delete_and_keeps_codes(test_app):
    seed();jobs.enqueue('cleanup')
    assert jobs.progress()['run']['total']==2
    with patch('checker.check_account_live',return_value=('DIE',None)) as check,patch('app.services.inventory_jobs.time.sleep'):
        while jobs.work_once():pass
    assert check.call_count==4
    assert jobs.progress()['counts']=={'DELETED':1,'PROTECTED':1}
    conn=database.get_sqlite_conn()
    assert not conn.execute("SELECT 1 FROM netflix_accounts WHERE email='bad@example.test'").fetchone()
    assert conn.execute("SELECT assigned_email FROM access_keys WHERE code='LIVEKEY'").fetchone()[0]=='linked@example.test'
    assert conn.execute("SELECT status FROM netflix_accounts WHERE email='linked@example.test'").fetchone()[0]=='needs_review'
    conn.close()


def test_cleanup_recovery_and_ambiguous_confirmation_keep_accounts(test_app):
    seed();jobs.enqueue('cleanup')
    with patch('checker.check_account_live',side_effect=[('DIE',None),('LIVE','Standard')]),patch('app.services.inventory_jobs.time.sleep'):
        jobs.work_once()
    conn=database.get_sqlite_conn()
    assert conn.execute("SELECT status,plan FROM netflix_accounts WHERE email='bad@example.test'").fetchone()==('live','Premium')
    conn.close()
    with patch('checker.check_account_live',side_effect=[('DIE',None),('UNKNOWN',None)]),patch('app.services.inventory_jobs.time.sleep'):
        jobs.work_once()
    assert jobs.progress()['processed']==1
    conn=database.get_sqlite_conn()
    assert conn.execute("SELECT 1 FROM netflix_accounts WHERE email='linked@example.test'").fetchone()
    conn.close()


def test_cleanup_same_cookie_but_admin_restored_account_is_protected(test_app):
    seed();jobs.enqueue('cleanup');item=jobs.claim()
    conn=database.get_sqlite_conn();conn.execute("UPDATE netflix_accounts SET status='live' WHERE email=?",(item['email'],));conn.commit();conn.close()
    assert jobs.finish(item,'DIE_CONFIRMED')
    assert jobs.progress()['counts']['CHANGED']==1
