from unittest.mock import Mock, patch
import checker


def token_response(plan=None):
    data={'value':{'account':{'token':{'default':{'token':'synthetic-token'}}}},'offers':['Premium']}
    if plan is not None:
        data['planName']=plan
    return Mock(status_code=200,ok=True,json=lambda:data)


def test_token_api_uses_current_basic_not_premium_offer():
    with patch('checker.requests.get',return_value=token_response('Basic')):
        assert checker._get_token_and_plan_api('synthetic-cookie') == 'Basic'


def test_token_without_plan_does_not_guess_from_offers():
    with patch('checker.requests.get',return_value=token_response()):
        assert checker._get_token_and_plan_api('synthetic-cookie') == 'VALID'


def test_unicode_plan_is_not_corrupted_or_guessed_from_hd():
    assert checker.normalize_plan_name('พรีเมียม') == 'Premium'
    assert checker.normalize_plan_name('Basic HD') == 'Basic'
    assert checker.normalize_plan_name('Not a Premium plan') is None


def test_formatted_account_metadata_preserves_basic():
    html='<script>account = {"membershipStatus":"CURRENT_MEMBER", "planName": {"fieldType": "String", "value": "Basic"}, "offers":["Premium"]};</script><p>Upgrade to Premium plan</p>'
    response=Mock(status_code=200,ok=True,url='https://www.netflix.com/YourAccount',text=html)
    with patch('checker.requests.get',return_value=response):
        assert checker.check_web_account_status_and_plan({},None) == ('LIVE','Basic')


def test_web_upgrade_without_current_plan_keeps_plan_unknown():
    html='<script>account={"membershipStatus":"CURRENT_MEMBER","offers":[{"planName":"Premium"}]};</script><p>Upgrade to Premium plan</p>'
    response=Mock(status_code=200,ok=True,url='https://www.netflix.com/YourAccount',text=html)
    with patch('checker.requests.get',return_value=response):
        assert checker.check_web_account_status_and_plan({},None) == ('LIVE',None)


def test_visible_upgrade_labels_never_supply_current_plan():
    from app.services.plan_parser import html_plan
    for advert in ('Upgrade your plan: Premium','Recommended plan: Premium','plan: Premium'):
        assert html_plan('<script>account={"membershipStatus":"CURRENT_MEMBER"};</script><p>'+advert+'</p>') is None
