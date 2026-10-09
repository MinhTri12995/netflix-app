import pytest


def test_health_header_identifies_running_render_commit(client, monkeypatch):
    revision = 'a' * 40
    monkeypatch.setenv('RENDER_GIT_COMMIT', revision)
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.headers['X-App-Revision'] == revision
    assert response.json == {'status': 'healthy'}


@pytest.mark.parametrize('revision', ['', 'not-a-commit', 'a' * 40 + '\nprivate'])
def test_revision_header_ignores_invalid_configuration(client, monkeypatch, revision):
    monkeypatch.setenv('RENDER_GIT_COMMIT', revision)
    response = client.get('/api/health')
    assert 'X-App-Revision' not in response.headers
