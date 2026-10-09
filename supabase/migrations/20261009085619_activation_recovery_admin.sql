-- Applied migration version matches Supabase history.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
ALTER TABLE public.access_keys ADD COLUMN IF NOT EXISTS plan text;
ALTER TABLE public.access_keys ADD COLUMN IF NOT EXISTS assignment_version bigint NOT NULL DEFAULT 1;
UPDATE public.access_keys k SET plan=COALESCE(
    CASE length(k.code) WHEN 15 THEN 'Premium' WHEN 10 THEN 'Standard' WHEN 8 THEN 'Standard_Ads' WHEN 5 THEN 'Basic' END,
    (SELECT a.plan FROM public.netflix_accounts a WHERE a.email=k.assigned_email), 'Premium') WHERE k.plan IS NULL;

CREATE OR REPLACE FUNCTION public.activation_plan(p text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,public AS $$
 SELECT CASE WHEN lower(p) LIKE '%standard%' AND lower(p) LIKE '%ad%' THEN 'Standard_Ads'
 WHEN lower(p) LIKE '%premium%' THEN 'Premium' WHEN lower(p) LIKE '%standard%' THEN 'Standard'
 WHEN lower(p) LIKE '%basic%' THEN 'Basic' ELSE p END;
$$;

CREATE TABLE IF NOT EXISTS public.system_config(key text PRIMARY KEY,value text);
INSERT INTO public.system_config(key,value) VALUES('SHARE_MODE_ENABLED','True') ON CONFLICT(key) DO NOTHING;
ALTER TABLE public.system_config ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.system_config FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.system_config TO service_role;

CREATE OR REPLACE FUNCTION public.activation_capacity(p_plan text) RETURNS integer
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT CASE WHEN lower(COALESCE((SELECT value FROM public.system_config WHERE key='SHARE_MODE_ENABLED'),'false'))<>'true'
 THEN 1 WHEN public.activation_plan(p_plan)='Premium' THEN 4 ELSE 2 END;
$$;

CREATE OR REPLACE FUNCTION public.guard_activation_admission() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE a public.netflix_accounts%ROWTYPE; capacity integer;
BEGIN
 IF TG_OP='UPDATE' AND NEW.assigned_email IS NOT DISTINCT FROM OLD.assigned_email
    AND NEW.plan IS NOT DISTINCT FROM OLD.plan THEN RETURN NEW; END IF;
 -- Existing over-capacity customers are preserved; only new admissions are checked.
 PERFORM pg_advisory_xact_lock(hashtextextended('activation_recovery',0));
 SELECT * INTO a FROM public.netflix_accounts WHERE email=NEW.assigned_email FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Assigned account missing'; END IF;
 NEW.plan=COALESCE(NEW.plan,a.plan);
 IF COALESCE(a.status,'usable') NOT IN ('live','usable') THEN RAISE EXCEPTION 'Assigned account unavailable'; END IF;
 IF public.activation_plan(a.plan) IS DISTINCT FROM public.activation_plan(NEW.plan) THEN RAISE EXCEPTION 'Account plan mismatch'; END IF;
 capacity=public.activation_capacity(NEW.plan);
 IF (SELECT count(*) FROM public.access_keys WHERE assigned_email=NEW.assigned_email AND code<>NEW.code)>=capacity
 THEN RAISE EXCEPTION 'Account capacity exceeded'; END IF;
 RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER access_keys_admission_guard BEFORE INSERT OR UPDATE OF assigned_email,plan ON public.access_keys
 FOR EACH ROW EXECUTE FUNCTION public.guard_activation_admission();

CREATE OR REPLACE FUNCTION public.activation_candidate(p_plan text,p_excluded text[],p_capacity integer)
RETURNS SETOF public.netflix_accounts LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT a.* FROM public.netflix_accounts a
 WHERE p_capacity IN (1,2,4) AND public.activation_plan(a.plan)=public.activation_plan(p_plan)
 AND COALESCE(a.status,'usable') IN ('usable','live')
 AND NOT (lower(a.email)=ANY(p_excluded)) AND COALESCE(a.netflix_id,'')<>''
 AND (SELECT count(*) FROM public.access_keys k WHERE k.assigned_email=a.email)<LEAST(p_capacity,public.activation_capacity(p_plan))
 ORDER BY CASE WHEN a.status='live' THEN 0 ELSE 1 END,
 (SELECT count(*) FROM public.access_keys k WHERE k.assigned_email=a.email),a.email LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION public.commit_activation_recovery(p_code text,p_old_email text,p_new_email text,p_plan text,p_capacity integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE k public.access_keys%ROWTYPE; a public.netflix_accounts%ROWTYPE;
BEGIN
 IF p_capacity NOT IN (1,2,4) THEN RETURN jsonb_build_object('status','invalid_input'); END IF;
 -- No external network calls while this transaction holds locks.
 PERFORM pg_advisory_xact_lock(hashtextextended('activation_recovery',0));
 SELECT * INTO k FROM public.access_keys WHERE code=p_code FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('status','invalid_input'); END IF;
 IF k.assigned_email IS DISTINCT FROM p_old_email THEN
   RETURN jsonb_build_object('status','already_processed','assigned_email',k.assigned_email);
 END IF;
 IF k.expire_at IS NOT NULL AND k.expire_at::date<CURRENT_DATE THEN RETURN jsonb_build_object('status','invalid_input'); END IF;
 SELECT * INTO a FROM public.netflix_accounts WHERE email=p_new_email FOR UPDATE;
 IF NOT FOUND OR p_new_email IS NOT DISTINCT FROM p_old_email OR COALESCE(a.status,'usable') NOT IN ('live','usable')
 OR public.activation_plan(a.plan) IS DISTINCT FROM public.activation_plan(p_plan)
 OR public.activation_plan(k.plan) IS DISTINCT FROM public.activation_plan(p_plan)
 OR (SELECT count(*) FROM public.access_keys WHERE assigned_email=p_new_email)>=LEAST(p_capacity,public.activation_capacity(p_plan)) THEN
   RETURN jsonb_build_object('status','out_of_stock');
 END IF;
 UPDATE public.access_keys SET assigned_email=p_new_email,assignment_version=assignment_version+1 WHERE code=p_code;
 UPDATE public.netflix_accounts SET status='live' WHERE email=p_new_email;
 INSERT INTO public.events_outbox(event_type,payload) VALUES('account_replaced',jsonb_build_object(
   'code',p_code,'old_email',p_old_email,'new_email',p_new_email,'actor','system:activation','reason','verified recovery'));
 RETURN jsonb_build_object('status','success','assigned_email',p_new_email);
END;
$$;

CREATE OR REPLACE FUNCTION public.admin_inventory_summary() RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT jsonb_build_object('accounts',jsonb_build_object('total',(SELECT count(*) FROM public.netflix_accounts),
   'Premium',(SELECT count(*) FROM public.netflix_accounts WHERE public.activation_plan(plan)='Premium'),
   'Standard',(SELECT count(*) FROM public.netflix_accounts WHERE public.activation_plan(plan)='Standard'),
   'Standard_Ads',(SELECT count(*) FROM public.netflix_accounts WHERE public.activation_plan(plan)='Standard_Ads'),
   'Basic',(SELECT count(*) FROM public.netflix_accounts WHERE public.activation_plan(plan)='Basic')),
 'codes',jsonb_build_object('total',(SELECT count(*) FROM public.access_keys),
   'Premium',(SELECT count(*) FROM public.access_keys WHERE public.activation_plan(plan)='Premium'),
   'Standard',(SELECT count(*) FROM public.access_keys WHERE public.activation_plan(plan)='Standard'),
   'Standard_Ads',(SELECT count(*) FROM public.access_keys WHERE public.activation_plan(plan)='Standard_Ads'),
   'Basic',(SELECT count(*) FROM public.access_keys WHERE public.activation_plan(plan)='Basic')),
 'health',COALESCE((SELECT jsonb_object_agg(status,n) FROM (SELECT COALESCE(status,'unknown') status,count(*) n FROM public.netflix_accounts GROUP BY status) s),'{}'::jsonb)
   ||jsonb_build_object('dangling',(SELECT count(*) FROM public.access_keys k LEFT JOIN public.netflix_accounts a ON a.email=k.assigned_email WHERE a.email IS NULL)));
$$;
CREATE INDEX IF NOT EXISTS accounts_admin_status_email_idx ON public.netflix_accounts(status,email);
CREATE INDEX IF NOT EXISTS access_keys_assigned_email_idx ON public.access_keys(assigned_email);
REVOKE ALL ON FUNCTION public.activation_capacity(text),public.guard_activation_admission(),public.activation_plan(text),public.activation_candidate(text,text[],integer),public.commit_activation_recovery(text,text,text,text,integer),public.admin_inventory_summary() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.activation_capacity(text),public.guard_activation_admission(),public.activation_plan(text),public.activation_candidate(text,text[],integer),public.commit_activation_recovery(text,text,text,text,integer),public.admin_inventory_summary() TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
