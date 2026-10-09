BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
INSERT INTO public.system_config(key,value) VALUES('MIX_PREMIUM_STANDARD','False') ON CONFLICT(key) DO NOTHING;
CREATE OR REPLACE FUNCTION public.activation_assignment_allowed(p_account_plan text,p_key_plan text,p_code text) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT COALESCE(public.activation_plan(p_account_plan)=public.activation_plan(p_key_plan),false)
 OR (length(p_code)=15 AND public.activation_plan(p_key_plan)='Premium' AND public.activation_plan(p_account_plan)='Standard'
 AND lower(COALESCE((SELECT value FROM public.system_config WHERE key='MIX_PREMIUM_STANDARD'),'false'))='true');
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
 IF NOT public.activation_assignment_allowed(a.plan,NEW.plan,NEW.code) THEN RAISE EXCEPTION 'Account plan mismatch'; END IF;
 capacity=public.activation_capacity(NEW.plan);
 IF (SELECT count(*) FROM public.access_keys WHERE assigned_email=NEW.assigned_email AND code<>NEW.code)>=capacity
 THEN RAISE EXCEPTION 'Account capacity exceeded'; END IF;
 RETURN NEW;
END;
$$;
CREATE OR REPLACE TRIGGER access_keys_admission_guard BEFORE INSERT OR UPDATE OF assigned_email,plan ON public.access_keys
 FOR EACH ROW EXECUTE FUNCTION public.guard_activation_admission();


CREATE OR REPLACE FUNCTION public.activation_candidate_for_code(p_code text,p_plan text,p_excluded text[],p_capacity integer)
RETURNS SETOF public.netflix_accounts LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT a.* FROM public.netflix_accounts a
 WHERE p_capacity IN (1,2,4) AND public.activation_assignment_allowed(a.plan,p_plan,p_code)
 AND COALESCE(a.status,'usable') IN ('usable','live')
 AND NOT (lower(a.email)=ANY(p_excluded)) AND COALESCE(a.netflix_id,'')<>''
 AND (SELECT count(*) FROM public.access_keys k WHERE k.assigned_email=a.email)<LEAST(p_capacity,public.activation_capacity(a.plan))
 ORDER BY CASE WHEN public.activation_plan(a.plan)=public.activation_plan(p_plan) THEN 0 ELSE 1 END,
 CASE WHEN a.status='live' THEN 0 ELSE 1 END,
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
 OR NOT public.activation_assignment_allowed(a.plan,p_plan,p_code)
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

REVOKE ALL ON FUNCTION public.activation_assignment_allowed(text,text,text),public.activation_candidate_for_code(text,text,text[],integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.activation_assignment_allowed(text,text,text),public.activation_candidate_for_code(text,text,text[],integer) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
