BEGIN;
SET LOCAL lock_timeout='5s';
CREATE OR REPLACE FUNCTION public.admin_plan_counts() RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT jsonb_build_object(
 'accounts',COALESCE((SELECT jsonb_agg(to_jsonb(x)) FROM
   (SELECT plan,count(*) AS quantity FROM public.netflix_accounts GROUP BY plan) x),'[]'::jsonb),
 'codes',COALESCE((SELECT jsonb_agg(to_jsonb(x)) FROM
   (SELECT plan,length(code) AS length,count(*) AS quantity FROM public.access_keys GROUP BY plan,length(code)) x),'[]'::jsonb),
 'health',public.admin_inventory_summary()->'health');
$$;
REVOKE ALL ON FUNCTION public.admin_plan_counts() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.admin_plan_counts() TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
