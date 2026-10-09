BEGIN;
SET LOCAL lock_timeout='5s';
ALTER TABLE public.inventory_runs DROP CONSTRAINT inventory_runs_kind_check;
ALTER TABLE public.inventory_runs ADD CONSTRAINT inventory_runs_kind_check CHECK(kind IN ('full_scan','payment_scan','missing_plans','duplicates','import','cleanup'));
CREATE OR REPLACE FUNCTION public.inventory_enqueue(p_id text,p_kind text,p_records jsonb DEFAULT '[]'::jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE active text; n integer;
BEGIN
 IF p_kind NOT IN ('full_scan','payment_scan','missing_plans','duplicates','import','cleanup') THEN RAISE EXCEPTION 'Invalid task'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('inventory_jobs',0));
 SELECT id INTO active FROM public.inventory_runs WHERE status='running' ORDER BY created_at LIMIT 1;
 IF active IS NOT NULL THEN RETURN jsonb_build_object('id',active,'existing',true); END IF;
 INSERT INTO public.inventory_runs(id,kind,status) VALUES(p_id,p_kind,'running');
 IF p_kind='import' THEN
   IF jsonb_typeof(p_records)<>'array' OR jsonb_array_length(p_records)>5000 THEN RAISE EXCEPTION 'Invalid import'; END IF;
   INSERT INTO public.inventory_items(run_id,email,payload)
   SELECT p_id,x->>'email',x FROM jsonb_array_elements(p_records) x
   WHERE COALESCE(x->>'email','')<>'' AND COALESCE(x->>'netflix_id','')<>'' ON CONFLICT(run_id,email) DO NOTHING;
 ELSE
 INSERT INTO public.inventory_items(run_id,email)
 SELECT p_id,email FROM public.netflix_accounts
 WHERE (p_kind<>'missing_plans' OR COALESCE(trim(plan),'') IN ('','Unknown','UNKNOWN','VALID'))
 AND (p_kind<>'cleanup' OR status IN ('needs_review','dead','expired')) ORDER BY email;
 END IF;
 SELECT count(*) INTO n FROM public.inventory_items WHERE run_id=p_id;
 UPDATE public.inventory_runs SET total=n,status=CASE WHEN n=0 THEN 'completed' ELSE 'running' END WHERE id=p_id;
 RETURN jsonb_build_object('id',p_id,'existing',false);
END; $$;


CREATE OR REPLACE FUNCTION public.inventory_finish(p_item bigint,p_token text,p_result text,p_plan text) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE item public.inventory_items%ROWTYPE; a public.netflix_accounts%ROWTYPE; kind text; outcome text:=p_result; keeper text;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('inventory_jobs',0));
 -- Use the same admission lock before duplicate deletion; never delete referenced accounts.
 PERFORM pg_advisory_xact_lock(hashtextextended('activation_recovery',0));
 SELECT * INTO item FROM public.inventory_items WHERE id=p_item FOR UPDATE;
 IF NOT FOUND OR item.status<>'processing' OR item.lease_token IS DISTINCT FROM p_token OR item.lease_until<=now() THEN RETURN false; END IF;
 SELECT * INTO a FROM public.netflix_accounts WHERE email=item.email FOR UPDATE;
 SELECT r.kind INTO kind FROM public.inventory_runs r WHERE r.id=item.run_id;
 IF kind='import' THEN
   IF p_result='LIVE' AND p_plan IN ('Premium','Standard','Standard with Ads','Basic') THEN
     -- Keep any existing identity for this cookie; no duplicate synthetic email.
     SELECT x.email INTO keeper FROM public.netflix_accounts x WHERE x.netflix_id=item.payload->>'netflix_id' ORDER BY x.email LIMIT 1;
     IF a.email IS NOT NULL AND item.fingerprint IS DISTINCT FROM encode(sha256(convert_to(COALESCE(a.netflix_id,'')||chr(31)||COALESCE(a.secure_netflix_id,''),'UTF8')),'hex') THEN outcome='CHANGED';
     ELSIF keeper IS NOT NULL AND keeper<>item.email THEN outcome='KEPT';
     ELSE
       INSERT INTO public.netflix_accounts(email,netflix_id,secure_netflix_id,plan,status)
       VALUES(item.email,item.payload->>'netflix_id',COALESCE(item.payload->>'secure_netflix_id',''),p_plan,'live')
       ON CONFLICT(email) DO UPDATE SET netflix_id=EXCLUDED.netflix_id,secure_netflix_id=EXCLUDED.secure_netflix_id,plan=EXCLUDED.plan,
       status=CASE WHEN netflix_accounts.status='blocked_for_new_assignments' THEN netflix_accounts.status ELSE 'live' END;
     END IF;
   ELSIF p_result='LIVE' THEN outcome='UNKNOWN';
   ELSIF p_result NOT IN ('DIE','UNKNOWN','ERROR') THEN RAISE EXCEPTION 'Invalid result'; END IF;
 ELSIF NOT FOUND OR a.email IS NULL THEN outcome='MISSING';
 ELSIF item.fingerprint IS DISTINCT FROM encode(sha256(convert_to(COALESCE(a.netflix_id,'')||chr(31)||COALESCE(a.secure_netflix_id,''),'UTF8')),'hex') THEN outcome='CHANGED';
 ELSIF kind='duplicates' THEN
   SELECT x.email INTO keeper FROM public.netflix_accounts x WHERE x.netflix_id=a.netflix_id AND COALESCE(x.netflix_id,'')<>''
   ORDER BY EXISTS(SELECT 1 FROM public.access_keys k WHERE x.email=ANY(regexp_split_to_array(trim(k.assigned_email),'\s*,\s*'))) DESC,
            (COALESCE(x.plan,'')<>'') DESC,x.email LIMIT 1;
   IF keeper IS NULL OR keeper=item.email THEN outcome='KEPT';
   ELSIF EXISTS(SELECT 1 FROM public.access_keys k WHERE item.email=ANY(regexp_split_to_array(trim(k.assigned_email),'\s*,\s*'))) THEN outcome='PROTECTED';
   ELSE DELETE FROM public.netflix_accounts WHERE email=item.email; outcome='DELETED'; END IF;
 ELSIF kind='cleanup' AND p_result='DIE_CONFIRMED' THEN
   IF (a.status IN ('needs_review','dead','expired')) IS NOT TRUE THEN outcome='CHANGED';
   ELSIF EXISTS(SELECT 1 FROM public.access_keys k WHERE item.email=ANY(regexp_split_to_array(trim(k.assigned_email),'\s*,\s*'))) THEN outcome='PROTECTED';
   ELSE DELETE FROM public.netflix_accounts WHERE email=item.email; outcome='DELETED'; END IF;
 ELSIF p_result='LIVE' THEN
   UPDATE public.netflix_accounts SET status=CASE WHEN status='blocked_for_new_assignments' THEN status ELSE 'live' END,
     plan=CASE WHEN p_plan IN ('Premium','Standard','Standard with Ads','Basic') AND kind NOT IN ('payment_scan','cleanup') THEN p_plan ELSE plan END WHERE email=item.email;
 ELSIF p_result='DIE' THEN
   UPDATE public.netflix_accounts SET status=CASE WHEN status='blocked_for_new_assignments' THEN status ELSE 'needs_review' END WHERE email=item.email;
 ELSIF p_result NOT IN ('UNKNOWN','ERROR','MISSING') THEN RAISE EXCEPTION 'Invalid result';
 END IF;
 IF outcome IN ('UNKNOWN','ERROR') AND item.attempts<3 THEN
   UPDATE public.inventory_items SET status='pending',result=NULL,lease_token=NULL,lease_until=now()+interval '15 seconds' WHERE id=p_item;
   RETURN true;
 END IF;
 UPDATE public.inventory_items SET status='done',result=outcome,plan=p_plan,payload=NULL,finished_at=now(),lease_token=NULL,lease_until=NULL WHERE id=p_item;
 UPDATE public.inventory_runs r SET updated_at=now(),status=CASE WHEN EXISTS(SELECT 1 FROM public.inventory_items i WHERE i.run_id=r.id AND i.status<>'done') THEN 'running' ELSE 'completed' END WHERE r.id=item.run_id;
 RETURN true;
END; $$;

NOTIFY pgrst,'reload schema';
COMMIT;
