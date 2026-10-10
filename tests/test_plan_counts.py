from unittest.mock import patch, Mock
from app.services.admin_inventory_service import inventory_summary
from app.services.admin_inventory_service import count_plan_groups


def test_counts_normalize_plans_and_do_not_inflate_premium(test_app):
    import database
    conn=database.get_sqlite_conn()
    plans=['Premium','พรีเมียม','Standardowy','Standard with Ads','Standard_Ads','Básico','Unknown',None]
    for i,plan in enumerate(plans):
        conn.execute("INSERT INTO netflix_accounts(email,plan) VALUES(?,?)",(f'count{i}@test.invalid',plan))
    conn.execute("INSERT INTO access_keys(code,assigned_email,plan) VALUES('STANDARDKEY16ABC','count2@test.invalid','Standard')")
    conn.commit();conn.close()
    stats=inventory_summary()
    assert stats['accounts']=={'total':8,'Premium':2,'Standard':1,'Standard_Ads':2,'Basic':1,'Unknown':2}
    assert stats['codes']['Standard']==1 and stats['codes']['Premium']==0


def test_cloud_counting_uses_same_rules_without_reading_credentials(test_app):
    cloud=Mock()
    cloud.rpc.return_value.execute.return_value.data={'accounts':[{'plan':'Standard with ads','quantity':1234},{'plan':'Unknown','quantity':9}], 'codes':[{'plan':'Standard','length':16,'quantity':3}], 'health':{'live':1234}}
    with patch('database.SUPABASE_KEY','synthetic'),patch('database.get_supabase',return_value=cloud):
        stats=inventory_summary()
    cloud.rpc.assert_called_once_with('admin_plan_counts',{})
    assert stats['accounts']['Standard_Ads']==1234
    assert stats['accounts']['Premium']==0 and stats['accounts']['Unknown']==9
    assert stats['accounts']['total']==1243 and stats['codes']['Standard']==3


def test_japanese_and_korean_names_survive_unicode_normalization():
    groups=[{'plan':plan,'quantity':1} for plan in ['プレミアム','프리미엄','ベーシック','スタンダード','スンダードではない','広告つきスタンダード']]
    assert count_plan_groups(groups)=={'total':6,'Premium':2,'Basic':1,'Standard':1,'Standard_Ads':1,'Unknown':1}
