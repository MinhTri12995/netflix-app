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


def test_real_current_plan_paths_from_demo_ignore_offers():
    data = {'models': {
        'signupContext': {'data': {'flow': {'fields': {
            'currentPlan': {'fields': {'localizedPlanName': 'Basic HD'}},
            'offers': [{'localizedPlanName': 'Premium'}],
        }}}},
        'flow': {'data': {'fields': {
            'currentPlan': {'fields': {'localizedPlanName': 'Basic HD'}}
        }}},
    }}
    import json
    assert current_plan(data) == 'Basic'
    assert html_plan('<script>netflix.reactContext = '+json.dumps(data)+';</script>') == 'Basic'


def test_conflicting_current_plan_sources_remain_unknown():
    data = {'models': {
        'signupContext': {'data': {'flow': {'fields': {'currentPlan': {'fields': {'localizedPlanName': 'Basic'}}}}}},
        'flow': {'data': {'fields': {'currentPlan': {'fields': {'localizedPlanName': 'Premium'}}}}},
    }}
    assert current_plan(data) is None


def test_window_prefixed_account_context_is_supported():
    assert html_plan('<script>window.netflix.reactContext={"account":{"planName":"Basic"}};</script>') == 'Basic'


def test_italian_base_from_actual_account_metadata():
    assert normalize_plan('Base') == 'Basic'
    assert html_plan('<script>netflix.reactContext={"models":{"flow":{"data":{"fields":{"currentPlan":{"fields":{"localizedPlanName":"Base"}}}}}}};</script>') == 'Basic'
    assert normalize_plan('Base con pubblicità') is None
