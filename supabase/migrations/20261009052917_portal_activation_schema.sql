-- Applied via Supabase migration API; version aligned with its migration history.
-- Run preflight in docs/portal-activation-repair.md before applying elsewhere.
-- This patch can be applied directly to the legacy production schema; it does
-- not require replaying the broader 20261005000001 migration.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

DO $migration$
BEGIN
    IF to_regclass('public.netflix_accounts') IS NULL THEN
        RAISE EXCEPTION 'public.netflix_accounts is absent; reconcile the target database first';
    END IF;
END
$migration$;

ALTER TABLE public.netflix_accounts
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'usable';

DO $migration$
DECLARE
    status_attnum SMALLINT;
    status_type TEXT;
    status_constraint RECORD;
BEGIN
    SELECT attnum, format_type(atttypid, atttypmod)
      INTO status_attnum, status_type
      FROM pg_attribute
     WHERE attrelid = 'public.netflix_accounts'::regclass
       AND attname = 'status' AND NOT attisdropped;
    IF status_type <> 'text' AND status_type NOT LIKE 'character varying%' THEN
        RAISE EXCEPTION 'Unsupported netflix_accounts.status type: %', status_type;
    END IF;

    -- Replace only the exact constraint shipped in the previous migration.
    -- Custom constraints need explicit review instead of being silently dropped.
    FOR status_constraint IN
        SELECT conname, pg_get_constraintdef(oid) AS definition
          FROM pg_constraint
         WHERE conrelid = 'public.netflix_accounts'::regclass
           AND contype = 'c' AND conkey = ARRAY[status_attnum]
    LOOP
        IF status_constraint.conname = 'netflix_accounts_status_check'
           AND status_constraint.definition =
               $$CHECK ((status = ANY (ARRAY['usable'::text, 'needs_review'::text, 'blocked_for_new_assignments'::text])))$$ THEN
            ALTER TABLE public.netflix_accounts DROP CONSTRAINT netflix_accounts_status_check;
        ELSIF status_constraint.conname <> 'netflix_accounts_activation_status_check' THEN
            RAISE EXCEPTION 'Review custom status constraint before migration: %', status_constraint.conname;
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1 FROM public.netflix_accounts
         WHERE status IS NOT NULL AND lower(btrim(status)) NOT IN (
             '', 'usable', 'live', 'needs_review', 'dead', 'die', 'expired',
             'pending_review', 'inactive', 'blocked_for_new_assignments')
    ) THEN
        RAISE EXCEPTION 'Unknown account statuses detected; reconcile before migration';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'public.netflix_accounts'::regclass
           AND conname = 'netflix_accounts_activation_status_check'
    ) THEN
        ALTER TABLE public.netflix_accounts
            ADD CONSTRAINT netflix_accounts_activation_status_check
            CHECK (status IS NULL OR lower(btrim(status)) IN (
                '', 'usable', 'live', 'needs_review', 'dead', 'die', 'expired',
                'pending_review', 'inactive', 'blocked_for_new_assignments'));
    END IF;
END
$migration$;

CREATE TABLE IF NOT EXISTS public.events_outbox (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'failed')),
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMPTZ
);

ALTER TABLE public.events_outbox
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ;

DO $migration$
DECLARE
    expected RECORD;
    actual_type TEXT;
    outbox_sequence TEXT;
BEGIN
    -- Reject an incompatible existing outbox instead of coercing stored data.
    FOR expected IN SELECT * FROM (VALUES
        ('id', ARRAY['int8', 'int4']),
        ('event_type', ARRAY['text', 'varchar']),
        ('payload', ARRAY['jsonb', 'json']),
        ('status', ARRAY['text', 'varchar']),
        ('retry_count', ARRAY['int4', 'int8']),
        ('created_at', ARRAY['timestamptz', 'timestamp']),
        ('delivered_at', ARRAY['timestamptz', 'timestamp'])
    ) AS requirements(column_name, allowed_types)
    LOOP
        SELECT udt_name INTO actual_type FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name = 'events_outbox'
           AND column_name = expected.column_name;
        IF actual_type IS NULL OR NOT actual_type = ANY(expected.allowed_types) THEN
            RAISE EXCEPTION 'Incompatible events_outbox column: % (%)', expected.column_name, actual_type;
        END IF;
    END LOOP;

    ALTER TABLE public.events_outbox ENABLE ROW LEVEL SECURITY;
    REVOKE ALL ON TABLE public.events_outbox FROM PUBLIC, anon, authenticated;
    GRANT SELECT, INSERT, UPDATE ON TABLE public.events_outbox TO service_role;
    outbox_sequence := pg_get_serial_sequence('public.events_outbox', 'id');
    IF outbox_sequence IS NOT NULL THEN
        EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC, anon, authenticated', outbox_sequence);
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO service_role', outbox_sequence);
    END IF;
END
$migration$;

-- Reload happens at commit; no notification is delivered if the migration fails.
NOTIFY pgrst, 'reload schema';
COMMIT;
