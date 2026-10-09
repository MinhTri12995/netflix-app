BEGIN;
SET LOCAL lock_timeout='5s';
CREATE TABLE IF NOT EXISTS public.inventory_runs (
 id text PRIMARY KEY, kind text NOT NULL CHECK(kind IN ('full_scan','payment_scan','missing_plans','duplicates','import')),
 status text NOT NULL CHECK(status IN ('running','completed')), total integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.inventory_items (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, run_id text NOT NULL REFERENCES public.inventory_runs(id),
 email text NOT NULL, status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','done')),
 attempts integer NOT NULL DEFAULT 0, lease_token text, lease_until timestamptz,
 payload jsonb, fingerprint text, result text, plan text, finished_at timestamptz, UNIQUE(run_id,email)
);
CREATE INDEX IF NOT EXISTS inventory_items_claim_idx ON public.inventory_items(status,lease_until,id);
CREATE INDEX IF NOT EXISTS inventory_items_run_idx ON public.inventory_items(run_id,id);
ALTER TABLE public.inventory_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.inventory_runs,public.inventory_items FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.inventory_runs,public.inventory_items TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.inventory_items_id_seq TO service_role;

CREATE OR REPLACE FUNCTION public.inventory_enqueue(p_id text,p_kind text,p_records jsonb DEFAULT '[]'::jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE active text; n integer;
BEGIN
 IF p_kind NOT IN ('full_scan','payment_scan','missing_plans','duplicates','import') THEN RAISE EXCEPTION 'Invalid task'; END IF;
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
 WHERE p_kind<>'missing_plans' OR COALESCE(trim(plan),'') IN ('','Unknown','UNKNOWN','VALID') ORDER BY email;
 END IF;
 SELECT count(*) INTO n FROM public.inventory_items WHERE run_id=p_id;
 UPDATE public.inventory_runs SET total=n,status=CASE WHEN n=0 THEN 'completed' ELSE 'running' END WHERE id=p_id;
 RETURN jsonb_build_object('id',p_id,'existing',false);
END; $$;

CREATE OR REPLACE FUNCTION public.inventory_claim(p_token text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE item public.inventory_items%ROWTYPE; a public.netflix_accounts%ROWTYPE; kind text;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('inventory_jobs',0));
 UPDATE public.inventory_items SET status='done',result='ERROR',payload=NULL,finished_at=now()
 WHERE status='processing' AND lease_until<=now() AND attempts>=3;
 UPDATE public.inventory_runs r SET status='completed',updated_at=now()
 WHERE status='running' AND NOT EXISTS(SELECT 1 FROM public.inventory_items i WHERE i.run_id=r.id AND i.status<>'done');
 IF (SELECT count(*) FROM public.inventory_items WHERE status='processing' AND lease_until>now())>=3 THEN RETURN NULL; END IF;
 SELECT * INTO item FROM public.inventory_items WHERE attempts<3 AND
 ((status='pending' AND (lease_until IS NULL OR lease_until<=now())) OR (status='processing' AND lease_until<=now())) ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO a FROM public.netflix_accounts WHERE email=item.email;
 SELECT r.kind INTO kind FROM public.inventory_runs r WHERE r.id=item.run_id;
 UPDATE public.inventory_items SET status='processing',attempts=attempts+1,lease_token=p_token,
 lease_until=now()+interval '180 seconds',fingerprint=encode(sha256(convert_to(COALESCE(a.netflix_id,'')||chr(31)||COALESCE(a.secure_netflix_id,''),'UTF8')),'hex') WHERE id=item.id;
 -- Credential values stay server-side and are never returned by the progress endpoint.
 RETURN jsonb_build_object('id',item.id,'run_id',item.run_id,'email',item.email,'kind',kind,
 'netflix_id',CASE WHEN kind='import' THEN item.payload->>'netflix_id' ELSE a.netflix_id END,
 'secure_netflix_id',CASE WHEN kind='import' THEN item.payload->>'secure_netflix_id' ELSE a.secure_netflix_id END,'lease_token',p_token);
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
 ELSIF p_result='LIVE' THEN
   UPDATE public.netflix_accounts SET status=CASE WHEN status='blocked_for_new_assignments' THEN status ELSE 'live' END,
     plan=CASE WHEN p_plan IN ('Premium','Standard','Standard with Ads','Basic') AND kind<>'payment_scan' THEN p_plan ELSE plan END WHERE email=item.email;
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

CREATE OR REPLACE FUNCTION public.inventory_progress(p_id text DEFAULT NULL) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,public AS $$
 SELECT jsonb_build_object('run',to_jsonb(r),'processed',(SELECT count(*) FROM public.inventory_items WHERE run_id=r.id AND status='done'),
 'counts',COALESCE((SELECT jsonb_object_agg(result,n) FROM (SELECT result,count(*) n FROM public.inventory_items WHERE run_id=r.id AND status='done' GROUP BY result) x),'{}'::jsonb),
 'recent',COALESCE((SELECT jsonb_agg(to_jsonb(x)) FROM (SELECT email,result,plan,finished_at FROM public.inventory_items WHERE run_id=r.id AND status='done' ORDER BY finished_at DESC,id DESC LIMIT 20) x),'[]'::jsonb),
 'processing',COALESCE((SELECT jsonb_agg(email) FROM public.inventory_items WHERE run_id=r.id AND status='processing' AND lease_until>now()),'[]'::jsonb),
 'history',COALESCE((SELECT jsonb_agg(to_jsonb(x)) FROM (SELECT id,kind,status,total,created_at FROM public.inventory_runs ORDER BY created_at DESC LIMIT 10) x),'[]'::jsonb))
 FROM public.inventory_runs r WHERE p_id IS NULL OR r.id=p_id ORDER BY r.created_at DESC LIMIT 1;
$$;
REVOKE ALL ON FUNCTION public.inventory_enqueue(text,text,jsonb),public.inventory_claim(text),public.inventory_finish(bigint,text,text,text),public.inventory_progress(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.inventory_enqueue(text,text,jsonb),public.inventory_claim(text),public.inventory_finish(bigint,text,text,text),public.inventory_progress(text) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
