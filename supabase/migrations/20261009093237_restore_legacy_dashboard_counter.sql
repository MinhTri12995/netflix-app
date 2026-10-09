BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
-- Restore display counters only. Allocation and verification keep explicit plans.
CREATE OR REPLACE FUNCTION public.admin_inventory_summary() RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 WITH a AS (
   SELECT CASE WHEN btrim(plan) IN ('Premium','Standard','Standard_Ads','Basic')
     THEN btrim(plan) ELSE 'Premium' END label FROM public.netflix_accounts
 ), k AS (
   SELECT CASE length(code) WHEN 15 THEN 'Premium' WHEN 10 THEN 'Standard'
     WHEN 8 THEN 'Standard_Ads' WHEN 5 THEN 'Basic' ELSE 'Premium' END label FROM public.access_keys
 )
 SELECT jsonb_build_object('accounts',jsonb_build_object('total',(SELECT count(*) FROM a),
   'Premium',(SELECT count(*) FROM a WHERE label='Premium'),
   'Standard',(SELECT count(*) FROM a WHERE label='Standard'),
   'Standard_Ads',(SELECT count(*) FROM a WHERE label='Standard_Ads'),
   'Basic',(SELECT count(*) FROM a WHERE label='Basic')),
 'codes',jsonb_build_object('total',(SELECT count(*) FROM k),
   'Premium',(SELECT count(*) FROM k WHERE label='Premium'),
   'Standard',(SELECT count(*) FROM k WHERE label='Standard'),
   'Standard_Ads',(SELECT count(*) FROM k WHERE label='Standard_Ads'),
   'Basic',(SELECT count(*) FROM k WHERE label='Basic')),
 'health',COALESCE((SELECT jsonb_object_agg(status,n) FROM (SELECT COALESCE(status,'unknown') status,count(*) n FROM public.netflix_accounts GROUP BY status) s),'{}'::jsonb)
   ||jsonb_build_object('dangling',(SELECT count(*) FROM public.access_keys k LEFT JOIN public.netflix_accounts a ON a.email=k.assigned_email WHERE a.email IS NULL)));
$$;
REVOKE ALL ON FUNCTION public.admin_inventory_summary() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.admin_inventory_summary() TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
