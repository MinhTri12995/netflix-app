"""Check actual account evidence instead of legacy broad keywords."""
from unittest.mock import Mock, patch
import checker


def account(html):
    return Mock(status_code=200, ok=True, url='https://www.netflix.com/YourAccount', text=html)


def test_basic_hd_is_not_standard_and_ads_are_not_a_current_plan():
    assert checker.normalize_plan_name('Basic HD') == 'Basic'
    assert checker.normalize_plan_name('', 'Premium plan') is None


def test_expired_billing_date_alone_is_not_proof_of_dead_membership():
    with patch('checker.requests.get', return_value=account('Netflix nextBillingDate" : {"fieldType":"String","value":"2000-01-01"}')):
        assert checker.check_web_account_status_and_plan({}, None) == ('LIVE', None)


def test_token_uses_current_basic_not_premium_offer():
    response = Mock(status_code=200, ok=True)
    response.json.return_value = {'value': {'account': {'token': {'default': {'token': 'synthetic-token'}}}}, 'planName': 'Basic', 'offers': ['Premium']}
    with patch('checker.requests.get', return_value=response):
        assert checker._get_token_and_plan_api('synthetic-cookie') == 'Basic'


def test_payment_translation_and_offer_flags_do_not_kill_account():
    html = '<script>account={"membershipStatus":"CURRENT_MEMBER","planName":"Basic","offers":[{"isMembershipActive":false}]}; translations={"error":"membership is on hold"};</script>'
    with patch('checker.requests.get', return_value=account(html)):
        assert checker.check_web_account_status_and_plan({}, None) == ('LIVE', 'Basic')


def test_current_account_payment_flag_is_dead():
    with patch('checker.requests.get', return_value=account('<script>account={"isPaymentFailure":true};</script>')):
        assert checker.check_web_account_status_and_plan({}, None) == ('DIE', None)


def test_offer_assignment_comments_and_strings_do_not_supply_account_flags():
    false_assignments = (
        'offer_account={"isPaymentFailure":true};',
        '/* account={"isPaymentFailure":true}; */',
        '// account={"isPaymentFailure":true};\n',
        "const text='account={\"isPaymentFailure\":true};';",
    )
    for fake in false_assignments:
        html = '<script>'+fake+' account={"membershipStatus":"CURRENT_MEMBER","planName":"Basic"};</script>'
        with patch('checker.requests.get', return_value=account(html)):
            assert checker.check_web_account_status_and_plan({}, None) == ('LIVE', 'Basic')


def test_web_live_without_verified_token_is_unknown():
    for api in ('API_DEAD', 'ERROR'):
        with patch('checker._get_token_and_plan_api', return_value=api), patch('checker.check_web_account_status_and_plan', return_value=('LIVE', 'Premium')):
            assert checker.check_account_live('synthetic-cookie') == ('UNKNOWN', None)


def test_rate_limit_does_not_immediately_retry_another_connection():
    with patch('checker.requests.get', return_value=Mock(status_code=429, ok=False)) as get:
        assert checker.check_account_live('synthetic-cookie') == ('UNKNOWN', None)
        assert get.call_count == 1


def test_invalid_token_cannot_be_live():
    response = Mock(status_code=200, ok=True)
    response.json.return_value = {'value': {'account': {'token': {'default': {'token': 'netflix.com'}}}}}
    with patch('checker.requests.get', return_value=response):
        assert checker._get_token_and_plan_api('synthetic-cookie') == 'ERROR'


def test_conflicting_verified_plans_do_not_overwrite_stored_plan():
    with patch('checker._get_token_and_plan_api', return_value='Basic'), patch('checker.check_web_account_status_and_plan', return_value=('LIVE', 'Premium')):
        assert checker.check_account_live('synthetic-cookie') == ('LIVE', None)


def test_conflict_in_either_source_is_not_masked_by_other_source():
    for api, web in ((checker.PLAN_CONFLICT, 'Premium'), ('Basic', checker.PLAN_CONFLICT), (checker.PLAN_CONFLICT, None), ('VALID', checker.PLAN_CONFLICT)):
        with patch('checker._get_token_and_plan_api', return_value=api), patch('checker.check_web_account_status_and_plan', return_value=('LIVE', web)):
            assert checker.check_account_live('synthetic-cookie') == ('LIVE', None)


def test_unverified_token_with_conflicting_web_plan_is_not_live():
    with patch('checker._get_token_and_plan_api', return_value='ERROR'), patch('checker.check_web_account_status_and_plan', return_value=('LIVE', checker.PLAN_CONFLICT)):
        assert checker.check_account_live('synthetic-cookie') == ('UNKNOWN', None)


def test_conflicting_token_metadata_retains_conflict_signal():
    response = Mock(status_code=200, ok=True)
    response.json.return_value = {'value': {'account': {'token': {'default': {'token': 'synthetic-token'}}, 'planName': 'Basic'}}, 'planName': 'Premium'}
    with patch('checker.requests.get', return_value=response):
        assert checker._get_token_and_plan_api('synthetic-cookie') == checker.PLAN_CONFLICT


def test_conflicting_web_metadata_retains_conflict_signal():
    with patch('checker.requests.get', return_value=account('<script>account={"planName":"Basic"}; userInfo={"planName":"Premium"};</script>')):
        assert checker.check_web_account_status_and_plan({}, None) == ('LIVE', checker.PLAN_CONFLICT)
