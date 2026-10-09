from unittest.mock import patch, Mock
import pytest
import database
from app.services.token_service import CookieError, ProxyError
from app.services.account_service import fetch_realtime_account_info


def seed():
    conn = database.get_sqlite_conn()
    conn.execute("DELETE FROM access_keys")
    conn.execute("DELETE FROM netflix_accounts")
    for email, nid, plan in [('old@test.invalid', 'old', 'Premium'), ('new@test.invalid', 'new', 'Premium')]:
        conn.execute("INSERT INTO netflix_accounts(email,netflix_id,plan,status) VALUES(?,?,?,'usable')", (email,nid,plan))
    conn.execute("INSERT INTO access_keys(code,assigned_email,plan,expire_at) VALUES('PAYMENTTESTCODE16','old@test.invalid','Premium','2099-12-31')")
    conn.commit()
    conn.close()


def test_payment_with_valid_token_does_not_return_old_link(test_app):
    seed()
    def metadata(nid, snid):
        if nid == 'old':
            raise CookieError('Confirmed payment hold')
        return 'Premium', '2099-12-31'
    with patch('app.blueprints.portal.routes.fetch_netflix_nftoken_api', side_effect=lambda nid, snid: 'TOKEN_'+nid), patch('app.blueprints.portal.routes.fetch_realtime_account_info', side_effect=metadata):
        response = test_app.test_client().post('/api/generate_nftoken', json={'cookie':'PAYMENTTESTCODE16'})
    assert response.status_code == 200
    assert 'TOKEN_new' in response.json['pc_link']
    assert database.get_access_key('PAYMENTTESTCODE16')[1] == 'new@test.invalid'


def test_unverified_payment_keeps_assignment_and_does_not_mark_live(test_app):
    seed()
    with patch('app.blueprints.portal.routes.fetch_netflix_nftoken_api', return_value='TOKEN'), patch('app.blueprints.portal.routes.fetch_realtime_account_info', side_effect=ProxyError('Timeout')):
        response = test_app.test_client().post('/api/generate_nftoken', json={'cookie':'PAYMENTTESTCODE16'})
    assert response.status_code == 503
    assert not response.json['success']
    assert database.get_access_key('PAYMENTTESTCODE16')[1] == 'old@test.invalid'
    assert database.get_account_by_email('old@test.invalid')[6] == 'usable'


def test_all_replacements_payment_preserves_original_assignment(test_app):
    seed()
    with patch('app.blueprints.portal.routes.fetch_netflix_nftoken_api', return_value='TOKEN'), patch('app.blueprints.portal.routes.fetch_realtime_account_info', side_effect=CookieError('Payment hold')):
        response = test_app.test_client().post('/api/generate_nftoken', json={'cookie':'PAYMENTTESTCODE16'})
    assert not response.json['success']
    assert database.get_access_key('PAYMENTTESTCODE16')[1] == 'old@test.invalid'


def test_premium_never_recovers_into_standard(test_app):
    seed()
    conn = database.get_sqlite_conn()
    conn.execute("UPDATE netflix_accounts SET plan='Standard' WHERE email='new@test.invalid'")
    conn.commit()
    conn.close()
    with patch('app.blueprints.portal.routes.fetch_netflix_nftoken_api', side_effect=lambda nid, snid: (_ for _ in ()).throw(CookieError('Expired')) if nid == 'old' else 'TOKEN'), patch('app.blueprints.portal.routes.fetch_realtime_account_info', return_value=('Standard','2099-12-31')):
        response = test_app.test_client().post('/api/generate_nftoken', json={'cookie':'PAYMENTTESTCODE16'})
    assert not response.json['success']
    assert database.get_access_key('PAYMENTTESTCODE16')[1] == 'old@test.invalid'


@pytest.mark.parametrize('status,body,url', [
    (403,'account is on hold','https://www.netflix.com/YourAccount'),
    (429,'payment was declined','https://www.netflix.com/YourAccount'),
    (500,'Netflix','https://www.netflix.com/YourAccount'),
    (200,'','https://www.netflix.com/YourAccount'),
    (200,'<html>maintenance</html>','https://www.netflix.com/YourAccount'),
    (200,'Netflix membership is on hold','https://netflix.com.attacker.invalid/YourAccount')])
def test_metadata_unknown_never_marks_dead_or_defaults_plan(status, body, url):
    response = Mock(status_code=status, text=body, url=url, ok=status < 400)
    with patch('app.services.account_service.requests.get', return_value=response), patch('proxies_list.get_random_proxy',return_value=None):
        with pytest.raises(ProxyError):
            fetch_realtime_account_info('nid','snid')


def test_payment_flags_reject_even_when_token_exists():
    response = Mock(status_code=200, ok=True, url='https://www.netflix.com/YourAccount', text='{"membershipStatus":"CURRENT_MEMBER","isPaymentFailure":true}')
    with patch('app.services.account_service.requests.get', return_value=response), patch('proxies_list.get_random_proxy',return_value=None):
        with pytest.raises(CookieError):
            fetch_realtime_account_info('nid','snid')


def test_past_billing_date_does_not_prove_inactive_membership():
    response = Mock(status_code=200, ok=True, url='https://www.netflix.com/YourAccount', text='{"membershipStatus":"CURRENT_MEMBER","nextBillingDate":{"fieldType":"String","value":"2020-01-01"}}')
    with patch('app.services.account_service.requests.get', return_value=response), patch('proxies_list.get_random_proxy',return_value=None):
        plan, _ = fetch_realtime_account_info('nid','snid')
    assert plan is None


def test_twenty_concurrent_recovery_commits_one_event(test_app):
    seed()
    from concurrent.futures import ThreadPoolExecutor
    from app.services.activation_recovery_service import commit_verified
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: commit_verified('PAYMENTTESTCODE16','old@test.invalid','new@test.invalid','Premium'),range(20)))
    assert sum(r.is_success for r in results) == 1
    conn = database.get_sqlite_conn()
    assert conn.execute("SELECT COUNT(*) FROM rotation_events WHERE code='PAYMENTTESTCODE16'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM events_outbox WHERE event_type='account_replaced'").fetchone()[0] == 1
    conn.close()


def test_cloud_reads_never_use_local_account_on_failure(test_app):
    seed()
    with patch('database.SUPABASE_KEY','test-only'),patch('database.get_supabase',side_effect=RuntimeError('offline')):
        with pytest.raises(RuntimeError):
            database.get_account_by_email('old@test.invalid')
        with pytest.raises(RuntimeError):
            database.get_access_key('PAYMENTTESTCODE16')
        assert database.update_account_status('old@test.invalid','live') is False


def test_blocked_for_new_assignments_keeps_existing_customer(test_app):
    seed()
    conn = database.get_sqlite_conn()
    conn.execute("UPDATE netflix_accounts SET status='blocked_for_new_assignments' WHERE email='old@test.invalid'")
    conn.commit(); conn.close()
    with patch('app.blueprints.portal.routes.fetch_netflix_nftoken_api',return_value='TOKEN'),patch('app.blueprints.portal.routes.fetch_realtime_account_info',return_value=('Premium',None)):
        response = test_app.test_client().post('/api/generate_nftoken',json={'cookie':'PAYMENTTESTCODE16'})
    assert response.json['success']
    assert database.get_access_key('PAYMENTTESTCODE16')[1] == 'old@test.invalid'
    assert database.get_account_by_email('old@test.invalid')[6] == 'blocked_for_new_assignments'


def test_payment_strings_inside_translation_script_do_not_reject_active_account():
    response = Mock(status_code=200,ok=True,url='https://www.netflix.com/YourAccount',text='<script>const translations={"hold":"your account is on hold"};</script><script>{"membershipStatus":"CURRENT_MEMBER"}</script><main>Account settings</main>')
    with patch('app.services.account_service.requests.get',return_value=response),patch('proxies_list.get_random_proxy',return_value=None):
        plan,_ = fetch_realtime_account_info('nid','snid')
    assert plan is None


def test_payment_rejection_does_not_require_successful_token_request(test_app):
    seed()
    with patch('app.blueprints.portal.routes.fetch_netflix_nftoken_api',side_effect=ProxyError('upstream')) as fetch,patch('app.blueprints.portal.routes.fetch_realtime_account_info',side_effect=CookieError('Payment hold')):
        response = test_app.test_client().post('/api/generate_nftoken',json={'cookie':'PAYMENTTESTCODE16'})
    assert not response.json['success']
    assert database.get_account_by_email('old@test.invalid')[6] == 'needs_review'
    fetch.assert_not_called()


@pytest.mark.parametrize('plan',['Standard','Standard_Ads','Basic'])
def test_generated_sixteen_character_code_keeps_requested_plan(test_app,plan):
    conn=database.get_sqlite_conn()
    conn.execute('DELETE FROM access_keys'); conn.execute('DELETE FROM netflix_accounts')
    conn.execute("INSERT INTO netflix_accounts(email,netflix_id,plan,status) VALUES('generated@test.invalid','generated',?,'live')",(plan,))
    conn.commit();conn.close()
    from app.services.allocation_service import allocate,generate_secure_code
    code=generate_secure_code(plan)
    assert allocate(code,plan=plan,expire_at='2099-12-31').is_success
    assert database.get_access_key(code)[3] == plan
    with patch('app.blueprints.portal.routes.fetch_realtime_account_info',return_value=(plan,None)),patch('app.blueprints.portal.routes.fetch_netflix_nftoken_api',return_value='TOKEN'):
        response=test_app.test_client().post('/api/generate_nftoken',json={'cookie':code})
    assert response.json['success']
    assert response.json['plan'] == plan


def test_plan_offer_translation_cannot_override_explicit_flat_account_plan():
    response=Mock(status_code=200,ok=True,url='https://www.netflix.com/YourAccount',text='<script>translations={"offer":"Standard with Ads"}; account={"membershipStatus":"CURRENT_MEMBER","planName":"Premium"};</script>')
    with patch('app.services.account_service.requests.get',return_value=response),patch('proxies_list.get_random_proxy',return_value=None):
        plan,_=fetch_realtime_account_info('nid','snid')
    assert plan == 'Premium'
