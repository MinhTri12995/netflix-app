from unittest.mock import patch, Mock
import database
from app.services.allocation_service import allocate, replace, load_assignment_accounts, load_assignment_usage, match_plan
from app.services.activation_recovery_service import candidate, commit_verified
from tests.conftest import setup_admin_session, TEST_CSRF_TOKEN

CODE='PREMIUMKEY00001'  # 15 characters


def seed(mix=True, premium=False):
    assert len(CODE)==15
    database.set_config('MIX_PREMIUM_STANDARD',mix)
    database.set_config('SHARE_MODE_ENABLED',True)
    conn=database.get_sqlite_conn()
    for email,plan in [('standard@test.invalid','Standard'),('ads@test.invalid','Standard_Ads'),('basic@test.invalid','Basic')]:
        conn.execute("INSERT INTO netflix_accounts(email,netflix_id,plan,status) VALUES(?,?,?,'live')",(email,'synthetic',plan))
    if premium:
        conn.execute("INSERT INTO netflix_accounts(email,netflix_id,plan,status) VALUES('premium@test.invalid','synthetic','Premium','usable')")
    conn.commit();conn.close()


def test_legacy_premium_uses_standard_when_enabled(test_app):
    seed()
    result=allocate(CODE,plan='Premium',expire_at='2099-12-31')
    assert result.is_success and result.assigned_email=='standard@test.invalid'
    assert database.get_access_key(CODE)[3]=='Premium'


def test_premium_priority_and_capacity_then_standard(test_app):
    seed(premium=True)
    assert allocate(CODE,plan='Premium').assigned_email=='premium@test.invalid'
    assert allocate('PREMIUMKEY00002',plan='Premium').assigned_email=='premium@test.invalid'
    assert allocate('PREMIUMKEY00003',plan='Premium').assigned_email=='standard@test.invalid'


def test_disabled_and_nonlegacy_codes_never_use_standard(test_app):
    seed(mix=False)
    assert allocate(CODE,plan='Premium').status=='out_of_stock'
    database.set_config('MIX_PREMIUM_STANDARD',True)
    assert allocate(CODE+'X',plan='Premium').status=='out_of_stock'
    conn=database.get_sqlite_conn();conn.execute("DELETE FROM netflix_accounts WHERE plan='Standard'");conn.commit();conn.close()
    assert allocate(CODE,plan='Premium').status=='out_of_stock'


def test_replace_and_recovery_apply_same_switch(test_app):
    seed()
    conn=database.get_sqlite_conn()
    conn.execute("INSERT INTO netflix_accounts(email,netflix_id,plan,status) VALUES('old@test.invalid','synthetic','Premium','needs_review')")
    conn.execute("INSERT INTO access_keys(code,assigned_email,plan,expire_at) VALUES(?,'old@test.invalid','Premium','2099-12-31')",(CODE,))
    conn.commit();conn.close()
    account=candidate('Premium',{'old@test.invalid'},code=CODE)
    assert account[0]=='standard@test.invalid'
    assert commit_verified(CODE,'old@test.invalid',account[0],'Premium').is_success


def test_disabled_replace_rejects_basic_and_ads(test_app):
    seed(mix=False)
    conn=database.get_sqlite_conn()
    conn.execute("INSERT INTO netflix_accounts(email,netflix_id,plan,status) VALUES('old@test.invalid','synthetic','Premium','needs_review')")
    conn.execute("INSERT INTO access_keys(code,assigned_email,plan,expire_at) VALUES(?,'old@test.invalid','Premium','2099-12-31')",(CODE,))
    conn.commit();conn.close()
    assert replace(code=CODE,actor='admin',ignore_quota=True).status=='out_of_stock'
    assert database.get_access_key(CODE)[1]=='old@test.invalid'


def test_existing_standard_link_works_after_switch_off(test_app):
    seed(mix=False)
    conn=database.get_sqlite_conn()
    conn.execute("INSERT INTO access_keys(code,assigned_email,plan,expire_at) VALUES(?,'standard@test.invalid','Premium','2099-12-31')",(CODE,))
    conn.commit();conn.close()
    with patch('app.blueprints.portal.routes.fetch_realtime_account_info',return_value=('Standard',None)),patch('app.blueprints.portal.routes.fetch_netflix_nftoken_api',return_value='SYNTHETIC'):
        response=test_app.test_client().post('/api/generate_nftoken',json={'cookie':CODE})
    assert response.json['success'] and response.json['plan']=='Standard'
    assert database.get_access_key(CODE)[1]=='standard@test.invalid'


def test_toggle_requires_auth_csrf_and_confirmed_write(test_app):
    client=setup_admin_session(test_app.test_client())
    assert b'/admin/toggle_mix_plan' in client.get('/admin/').data
    assert client.post('/admin/toggle_mix_plan',data={'enabled':'true'}).status_code==403
    with patch('database.set_config',return_value=False):
        response=client.post('/admin/toggle_mix_plan',data={'enabled':'true','csrf_token':TEST_CSRF_TOKEN},follow_redirects=True)
    assert 'Không thể lưu'.encode() in response.data


def test_cloud_config_failure_never_writes_local_or_reports_success(test_app,tmp_path):
    with patch.object(database,'SUPABASE_KEY','synthetic'),patch('database.get_supabase',side_effect=RuntimeError('unavailable')),patch.object(database,'CONFIG_FILE',str(tmp_path/'config.json')):
        assert database.set_config('MIX_PREMIUM_STANDARD',True) is False
        assert not (tmp_path/'config.json').exists()


def test_cloud_mixed_pool_includes_legacy_premium_after_response_limit(test_app):
    from types import SimpleNamespace
    rows=[{'email':f'a{i:04d}', 'plan':'Standard', 'status':'live'} for i in range(500)]
    rows.append({'email':'z-premium', 'plan':'premium', 'status':'live'})
    class Query:
        def select(self,*args):return self
        def neq(self,*args):return self
        def order(self,*args):return self
        def range(self,start,end):self.bounds=(start,end);return self
        def execute(self):return SimpleNamespace(data=rows[self.bounds[0]:self.bounds[1]+1])
    cloud=Mock();cloud.table.side_effect=lambda *args:Query()
    with patch('database.get_supabase',return_value=cloud):
        loaded=load_assignment_accounts(['Premium','Standard']).data
    assert len(loaded)==501
    assert min(loaded,key=lambda r:0 if match_plan(r['plan'],'Premium') else 1)['email']=='z-premium'


def test_cloud_mixed_usage_batches_and_pages_all_references(test_app):
    from types import SimpleNamespace
    emails=[f'premium{i:04d}' for i in range(600)]
    rows=[{'assigned_email':email} for email in emails for _ in range(2)]
    # A legacy over-capacity account exercises multiple response pages per batch.
    rows += [{'assigned_email':emails[0]} for _ in range(600)]
    class Query:
        def select(self,*args):return self
        def in_(self,column,values):assert len(values)<=100;self.emails=values;return self
        def order(self,*args):return self
        def range(self,start,end):self.bounds=(start,end);return self
        def execute(self):
            subset=[row for row in rows if row['assigned_email'] in self.emails]
            return SimpleNamespace(data=subset[self.bounds[0]:self.bounds[1]+1])
    cloud=Mock();cloud.table.side_effect=lambda *args:Query()
    with patch('database.get_supabase',return_value=cloud):
        loaded=load_assignment_usage(emails+['standard'],mixed=True).data
    assert len(loaded)==1800
    from collections import Counter
    counts=Counter(row['assigned_email'] for row in loaded)
    assert all(counts[email]>=2 for email in emails)
    assert counts['standard']==0
