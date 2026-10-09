"""Activation regressions: exercise handlers and stores with fake upstream services."""
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
import database
from app.services import token_service
from app.services.allocation_service import replace


def token_response(token):
    return {"value": {"account": {"token": {"default": {"token": token}}}}}


def upstream(data=None, status=200, json_error=None):
    response = requests.Response()
    response.status_code = status
    if json_error:
        response.json = lambda: (_ for _ in ()).throw(json_error)
    else:
        response.json = lambda: data
    return response


@pytest.fixture
def assigned_client(client):
    with database.get_sqlite_conn() as conn:
        conn.execute("INSERT INTO netflix_accounts (email, netflix_id, plan, status) "
                     "VALUES ('first@example.test', 'private-cookie', 'Premium', 'usable')")
        conn.execute("INSERT INTO netflix_accounts (email, netflix_id, plan, status) "
                     "VALUES ('spare@example.test', 'spare-cookie', 'Premium', 'live')")
        conn.execute("INSERT INTO access_keys (code, assigned_email, plan, expire_at) "
                     "VALUES ('LOCALACTIVATION01', 'first@example.test', 'Premium', '2099-12-31')")
    return client


@pytest.mark.parametrize("data", [
    {}, {"value": None}, [], token_response(None), token_response(""),
    token_response("   "), token_response(123), token_response({}),
    token_response("https://www.netflix.com"), token_response("FALLBACK:[]"),
])
def test_unverified_response_preserves_assignment_and_status(assigned_client, data):
    # Removing response validation or classifying missing tokens as CookieError breaks this.
    with patch.object(token_service.proxies_list, 'get_random_proxy', return_value=None), \
            patch.object(token_service.requests, 'get', return_value=upstream(data)):
        response = assigned_client.post('/api/generate_nftoken', json={'cookie': 'LOCALACTIVATION01'})
    assert response.status_code == 503
    assert response.json['success'] is False
    assert response.json['error_code'] == 'TOKEN_RESPONSE_UNVERIFIED'
    assert response.json['retryable'] is True
    assert 'pc_link' not in response.json
    with database.get_sqlite_conn() as conn:
        assert conn.execute("SELECT assigned_email FROM access_keys").fetchone()[0] == 'first@example.test'
        assert dict(conn.execute("SELECT email, status FROM netflix_accounts")) == {
            'first@example.test': 'usable', 'spare@example.test': 'live'}
        assert conn.execute("SELECT COUNT(*) FROM rotation_events").fetchone()[0] == 0


def test_non_json_response_is_unknown_not_dead(assigned_client, capsys):
    with patch.object(token_service.proxies_list, 'get_random_proxy', return_value=None), \
            patch.object(token_service.requests, 'get', return_value=upstream(json_error=ValueError('private-cookie'))):
        response = assigned_client.post('/api/generate_nftoken', json={'cookie': 'LOCALACTIVATION01'})
    assert response.status_code == 503
    assert response.json['error_code'] == 'TOKEN_RESPONSE_UNVERIFIED'
    assert database.get_access_key('LOCALACTIVATION01')[1] == 'first@example.test'
    assert 'private-cookie' not in capsys.readouterr().out


def test_raw_cookie_uses_same_unverified_response_result(assigned_client):
    with patch.object(token_service.proxies_list, 'get_random_proxy', return_value=None), \
            patch.object(token_service.requests, 'get', return_value=upstream({})):
        response = assigned_client.post('/api/generate_nftoken', json={'cookie': 'NetflixId=private-cookie'})
    assert response.status_code == 503
    assert response.json['error_code'] == 'TOKEN_RESPONSE_UNVERIFIED'


@pytest.mark.parametrize('wrapped', [True, False])
def test_valid_token_links_preserve_token_query_value(assigned_client, wrapped):
    token = 'verified+/token=&suffix'
    data = token_response(token)
    if not wrapped:
        data['value']['account']['token']['default'] = token
    with patch.object(token_service.proxies_list, 'get_random_proxy', return_value=None), \
            patch.object(token_service.requests, 'get', return_value=upstream(data)), \
            patch('app.blueprints.portal.routes.fetch_realtime_account_info', return_value=('Premium', None)):
        response = assigned_client.post('/api/generate_nftoken', json={'cookie': 'LOCALACTIVATION01'})
    assert response.status_code == 200
    assert response.json['success'] is True
    for field in ('pc_link', 'mobile_link', 'tv_link', 'general_link'):
        assert parse_qs(urlsplit(response.json[field]).query) == {'nftoken': [token]}
    assert response.json['cookie_json']
    assert database.get_account_by_email('first@example.test')[6] == 'live'


def test_http_401_still_signals_invalid_cookie():
    with patch.object(token_service.proxies_list, 'get_random_proxy', return_value=None), \
            patch.object(token_service.requests, 'get', return_value=upstream(status=401)):
        with pytest.raises(token_service.CookieError):
            token_service.fetch_netflix_nftoken_api('private-cookie')


def test_transport_error_diagnostics_do_not_expose_secrets(capsys):
    with patch.object(token_service.proxies_list, 'get_random_proxy', return_value=None), \
            patch.object(token_service.requests, 'get', side_effect=requests.ConnectionError('private-cookie proxy-password')):
        with pytest.raises(token_service.ProxyError) as exc:
            token_service.fetch_netflix_nftoken_api('private-cookie')
    diagnostic = str(exc.value) + capsys.readouterr().out
    assert 'private-cookie' not in diagnostic
    assert 'proxy-password' not in diagnostic


class FakeCloud:
    """Stateful PostgREST boundary with optional old-schema failures."""
    def __init__(self, missing_status=False):
        self.missing_status = missing_status
        self.rows = {
            'netflix_accounts': [
                {'email': 'first@example.test', 'netflix_id': 'cookie-A', 'plan': 'Premium', 'status': 'usable'},
                {'email': 'spare@example.test', 'netflix_id': 'cookie-B', 'plan': 'Premium', 'status': 'usable'}],
            'access_keys': [{'code': 'LOCALACTIVATION01', 'assigned_email': 'first@example.test',
                             'plan': 'Premium', 'expire_at': '2099-12-31', 'assignment_version': 1}],
            'requests': [], 'events_outbox': [], 'system_config': []}
        for row in self.rows['netflix_accounts']:
            row.update(expire_date='2099-12-31', secure_netflix_id='', created_at='2026-10-09')

    def table(self, name):
        return CloudQuery(self, name)


class CloudQuery:
    def __init__(self, cloud, name):
        self.cloud, self.name = cloud, name
        self.columns, self.payload, self.action = '*', None, 'select'
        self.filters = []

    def select(self, columns):
        self.columns = columns
        return self

    def update(self, payload):
        self.action, self.payload = 'update', payload
        return self

    def insert(self, payload):
        self.action, self.payload = 'insert', payload
        return self

    def eq(self, column, value):
        self.filters.append(lambda row: row.get(column) == value)
        return self

    def neq(self, column, value):
        self.filters.append(lambda row: row.get(column) != value)
        return self

    def in_(self, column, values):
        self.filters.append(lambda row: row.get(column) in values)
        return self

    def gt(self, column, value):
        self.filters.append(lambda row: str(row.get(column, '')) > value)
        return self

    def limit(self, count):
        return self

    def execute(self):
        if self.name == 'netflix_accounts' and self.cloud.missing_status:
            if 'status' in self.columns or (self.payload and 'status' in self.payload):
                raise RuntimeError("PGRST204: Could not find the 'status' column")
        if self.name == 'events_outbox':
            raise RuntimeError('PGRST205: events_outbox absent from schema cache')
        rows = [r for r in self.cloud.rows[self.name] if all(f(r) for f in self.filters)]
        if self.action == 'update':
            for row in rows:
                row.update(self.payload)
        if self.columns == '*':
            data = [dict(row) for row in rows]
            if self.name == 'netflix_accounts' and self.cloud.missing_status:
                for row in data:
                    row.pop('status', None)
        else:
            data = [{col.strip(): row.get(col.strip()) for col in self.columns.split(',')} for row in rows]
        return SimpleNamespace(data=data)


def test_old_schema_never_rotates_back_to_attempted_account(assigned_client):
    cloud = FakeCloud(missing_status=True)
    attempted = []

    def unauthorized(nid, snid=''):
        attempted.append(nid)
        raise token_service.CookieError('HTTP 401')

    with patch.object(database, 'SUPABASE_KEY', 'test-only'), \
            patch.object(database, 'get_supabase', return_value=cloud), \
            patch('app.blueprints.portal.routes.fetch_netflix_nftoken_api', side_effect=unauthorized):
        response = assigned_client.post('/api/generate_nftoken', json={'cookie': 'LOCALACTIVATION01'})
    assert response.json['success'] is False
    assert attempted == ['cookie-A', 'cookie-B']
    assert cloud.rows['access_keys'][0]['assigned_email'] == 'spare@example.test'
    assert cloud.rows['access_keys'][0]['assignment_version'] == 2


def test_attempt_budget_does_not_rotate_to_untested_fifth_account(assigned_client):
    with database.get_sqlite_conn() as conn:
        for i in range(3):
            conn.execute("INSERT INTO netflix_accounts (email,netflix_id,plan,status) VALUES (?,?,'Premium','usable')",
                         (f'extra{i}@example.test', f'cookie-extra{i}'))
    attempted = []

    def unauthorized(nid, snid=''):
        attempted.append(nid)
        raise token_service.CookieError('HTTP 401')

    with patch('app.blueprints.portal.routes.fetch_netflix_nftoken_api', side_effect=unauthorized):
        response = assigned_client.post('/api/generate_nftoken', json={'cookie': 'LOCALACTIVATION01'})
    assert response.status_code == 503
    assert len(attempted) == len(set(attempted)) == 4
    with database.get_sqlite_conn() as conn:
        assert conn.execute('SELECT COUNT(*) FROM rotation_events').fetchone()[0] == 3
        assigned_cookie = conn.execute('SELECT netflix_id FROM netflix_accounts '
                                      'WHERE email = (SELECT assigned_email FROM access_keys)').fetchone()[0]
        assert assigned_cookie == attempted[-1]


@pytest.mark.parametrize('store', ['sqlite', 'cloud'])
@pytest.mark.parametrize('candidate_plan', ['Premium', 'Standard'])
def test_excluded_account_not_selected_even_by_plan_fallback(assigned_client, store, candidate_plan):
    # An excluded account remains usable here; exclusion must apply independently of status persistence.
    if store == 'sqlite':
        with database.get_sqlite_conn() as conn:
            conn.execute("UPDATE netflix_accounts SET plan = ? WHERE email = 'spare@example.test'", (candidate_plan,))
        result = replace(code='LOCALACTIVATION01', ignore_quota=True, delete_old_account=False,
                         exclude_emails={'SPARE@example.test'})
        assigned = database.get_access_key('LOCALACTIVATION01')[1]
    else:
        cloud = FakeCloud()
        cloud.rows['netflix_accounts'][1]['plan'] = candidate_plan
        with patch.object(database, 'SUPABASE_KEY', 'test-only'), \
                patch.object(database, 'get_supabase', return_value=cloud):
            result = replace(code='LOCALACTIVATION01', ignore_quota=True, delete_old_account=False,
                             exclude_emails={'SPARE@example.test'})
        assigned = cloud.rows['access_keys'][0]['assigned_email']
    assert result.status == 'out_of_stock'
    assert assigned == 'first@example.test'


def test_initialization_preserves_previously_reviewed_seed_account(assigned_client):
    cloud = FakeCloud()
    reviewed = {'email': 'sandy.glenn68@icloud.com', 'plan': 'Premium', 'status': 'needs_review'}
    cloud.rows['netflix_accounts'].append(reviewed)
    with patch.object(database, 'SUPABASE_KEY', 'test-only'), \
            patch.object(database, 'get_supabase', return_value=cloud):
        database.init_db()
        database.init_db()
    assert reviewed['status'] == 'needs_review'
