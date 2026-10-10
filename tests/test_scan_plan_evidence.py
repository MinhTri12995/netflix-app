"""Strict extraction still used by activation and counters, separate from legacy checking."""
from unittest.mock import Mock
from app.services.plan_parser import current_plan, normalize_plan, html_plan


def token_response(plan=None):
    data={'value':{'account':{'token':{'default':{'token':'synthetic-token'}}}},'offers':['Premium']}
    if plan is not None:
        data['planName']=plan
    return Mock(status_code=200,ok=True,json=lambda:data)


def test_token_api_uses_current_basic_not_premium_offer():
    assert current_plan(token_response('Basic').json()) == 'Basic'


def test_token_without_plan_does_not_guess_from_offers():
    assert current_plan(token_response().json()) is None


def test_unicode_plan_is_not_corrupted_or_guessed_from_hd():
    assert normalize_plan('พรีเมียม') == 'Premium'
    assert normalize_plan('Basic HD') == 'Basic'
    assert normalize_plan('Not a Premium plan') is None


def test_formatted_account_metadata_preserves_basic():
    html='<script>account = {"membershipStatus":"CURRENT_MEMBER", "planName": {"fieldType": "String", "value": "Basic"}, "offers":["Premium"]};</script><p>Upgrade to Premium plan</p>'
    assert html_plan(html) == 'Basic'


def test_web_upgrade_without_current_plan_keeps_plan_unknown():
    html='<script>account={"membershipStatus":"CURRENT_MEMBER","offers":[{"planName":"Premium"}]};</script><p>Upgrade to Premium plan</p>'
    assert html_plan(html) is None


def test_visible_upgrade_labels_never_supply_current_plan():
    from app.services.plan_parser import html_plan
    for advert in ('Upgrade your plan: Premium','Recommended plan: Premium','plan: Premium'):
        assert html_plan('<script>account={"membershipStatus":"CURRENT_MEMBER"};</script><p>'+advert+'</p>') is None
