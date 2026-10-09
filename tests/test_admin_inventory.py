from unittest.mock import patch
import database
from tests.conftest import setup_admin_session, TEST_CSRF_TOKEN


def populate():
    conn = database.get_sqlite_conn()
    conn.execute('DELETE FROM access_keys')
    conn.execute('DELETE FROM netflix_accounts')
    for index in range(61):
        conn.execute("INSERT INTO netflix_accounts(email,netflix_id,plan,status) VALUES(?,?,?,?)", (f'item{index:03}@test.invalid','secret-cookie','Premium','needs_review' if index == 60 else 'live'))
    conn.execute("INSERT INTO access_keys(code,assigned_email,plan,expire_at) VALUES('ADMINTESTKEY12345','item060@test.invalid','Standard','2099-12-31')")
    conn.commit()
    conn.close()


def test_dashboard_uses_database_paging_and_status_filter(test_app):
    populate()
    client = setup_admin_session(test_app.test_client())
    with patch('database.get_all_accounts', side_effect=AssertionError('Full inventory read forbidden')), patch('database.get_all_access_keys', side_effect=AssertionError('Full codes read forbidden')):
        response = client.get('/admin/dashboard?account_status=needs_review')
    assert response.status_code == 200
    assert b'item060@test.invalid' in response.data
    assert b'item001@test.invalid' not in response.data


def test_account_detail_shows_affected_codes_without_credentials(test_app):
    populate()
    client = setup_admin_session(test_app.test_client())
    response = client.get('/admin/accounts/item060@test.invalid/details')
    assert response.status_code == 200
    assert 'ADMINTESTKEY12345' in response.json['codes']
    assert 'secret-cookie' not in response.get_data(as_text=True)


def test_single_check_unknown_keeps_previous_status(test_app):
    populate()
    client = setup_admin_session(test_app.test_client())
    with patch('checker.check_account_live', return_value=('UNKNOWN',None)):
        response = client.post('/admin/accounts/item060@test.invalid/check', data={'csrf_token':TEST_CSRF_TOKEN})
    assert response.status_code == 302
    assert database.get_account_by_email('item060@test.invalid')[6] == 'needs_review'


def test_pages_clamp_and_summary_uses_requested_legacy_counter(test_app):
    populate()
    from app.services.admin_inventory_service import inventory_page, inventory_summary
    page = inventory_page('accounts', page=-1, per_page=10)
    assert len(page['rows']) == 10
    assert page['page'] == 1
    assert page['total'] == 61
    stats = inventory_summary()
    assert stats['codes']['Standard'] == 0
    assert stats['codes']['Premium'] == 1
    assert stats['health']['needs_review'] == 1


def test_legacy_counter_groups_unrecognized_account_names_as_premium(test_app):
    populate()
    conn = database.get_sqlite_conn()
    conn.execute("UPDATE netflix_accounts SET plan='Standard with Ads' WHERE email='item060@test.invalid'")
    conn.execute("UPDATE netflix_accounts SET plan=' Basic ' WHERE email='item059@test.invalid'")
    conn.commit(); conn.close()
    from app.services.admin_inventory_service import inventory_summary
    stats = inventory_summary()
    assert stats['accounts']['Premium'] == 60
    assert stats['accounts']['Basic'] == 1
    assert stats['accounts']['Standard_Ads'] == 0
    assert sum(stats['accounts'][p] for p in ('Premium','Standard','Standard_Ads','Basic')) == 61


def test_admin_cloud_failure_shows_unavailable_instead_of_local_data(test_app):
    client = setup_admin_session(test_app.test_client())
    with patch('database.SUPABASE_KEY','test-key'), patch('database.get_supabase',side_effect=RuntimeError('offline')):
        response = client.get('/admin/dashboard')
    assert response.status_code == 503
    assert 'Chưa thể tải' in response.get_data(as_text=True)


def test_admin_cannot_delete_account_with_customer_codes(test_app):
    populate()
    client = setup_admin_session(test_app.test_client())
    response = client.post('/admin/accounts/item060@test.invalid/delete',data={'csrf_token':TEST_CSRF_TOKEN})
    assert response.status_code == 302
    assert database.get_account_by_email('item060@test.invalid') is not None


def test_single_check_does_not_reopen_blocked_account(test_app):
    populate()
    conn=database.get_sqlite_conn()
    conn.execute("UPDATE netflix_accounts SET status='blocked_for_new_assignments' WHERE email='item060@test.invalid'")
    conn.commit();conn.close()
    client=setup_admin_session(test_app.test_client())
    with patch('checker.check_account_live',return_value=('LIVE','Premium')):
        response=client.post('/admin/accounts/item060@test.invalid/check',data={'csrf_token':TEST_CSRF_TOKEN})
    assert response.status_code == 302
    assert database.get_account_by_email('item060@test.invalid')[6] == 'blocked_for_new_assignments'
