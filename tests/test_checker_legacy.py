"""Behavior requested when restoring the b98aa31 account checker."""
from unittest.mock import Mock, patch
import checker


def test_legacy_plan_keywords_and_html_fallback():
    assert checker.normalize_plan_name('Ultra HD') == 'Premium'
    assert checker.normalize_plan_name('', 'plan: standard') == 'Standard'


def test_legacy_web_plan_without_json_assignment():
    response = Mock(status_code=200, ok=True,
                    url='https://www.netflix.com/YourAccount',
                    text='<p>Netflix membership: Premium plan</p>')
    with patch('checker.requests.get', return_value=response):
        assert checker.check_web_account_status_and_plan({}, None) == ('LIVE', 'Premium')


def test_legacy_expired_billing_date():
    response = Mock(status_code=200, ok=True,
                    url='https://www.netflix.com/YourAccount',
                    text='Netflix nextBillingDate" : {"fieldType":"String","value":"2000-01-01"}')
    with patch('checker.requests.get', return_value=response):
        assert checker.check_web_account_status_and_plan({}, None) == ('DIE', None)


def test_legacy_token_plan_falls_back_to_response_keywords():
    response = Mock(status_code=200, ok=True)
    response.json.return_value = {
        'value': {'account': {'token': {'default': {'token': 'synthetic-token'}}}},
        'planName': 'Basic', 'offers': ['Premium'],
    }
    with patch('checker.requests.get', return_value=response):
        # Deliberately preserves b98aa31's keyword precedence.
        assert checker._get_token_and_plan_api('synthetic-cookie') == 'Premium'
