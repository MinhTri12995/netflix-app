BEGIN;
SET LOCAL lock_timeout='5s';
CREATE OR REPLACE FUNCTION public.activation_capacity(p_plan text) RETURNS integer
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT CASE WHEN lower(COALESCE((SELECT value FROM public.system_config WHERE key='SHARE_MODE_ENABLED'),'false'))<>'true'
 THEN 1 ELSE 2 END;
$$;
REVOKE ALL ON FUNCTION public.activation_capacity(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.activation_capacity(text) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
