-- =============================================================================
-- Migration: 20261005000001_authoritative_schema.sql
-- Goal: Establish PostgreSQL as authoritative source of truth with strong foreign
-- keys, capacity constraints, idempotency records, and outbox tables.
-- =============================================================================

-- 1. Accounts Table with status and assignment_version
CREATE TABLE IF NOT EXISTS netflix_accounts (
    email TEXT PRIMARY KEY,
    expire_date TEXT,
    netflix_id TEXT,
    secure_netflix_id TEXT,
    plan TEXT DEFAULT 'Premium',
    status TEXT DEFAULT 'usable' CHECK (status IN ('usable', 'needs_review', 'blocked_for_new_assignments')),
    assignment_version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Ensure columns exist if table was created previously
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='netflix_accounts' AND column_name='status') THEN
        ALTER TABLE netflix_accounts ADD COLUMN status TEXT DEFAULT 'usable';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='netflix_accounts' AND column_name='assignment_version') THEN
        ALTER TABLE netflix_accounts ADD COLUMN assignment_version INTEGER DEFAULT 1;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='netflix_accounts' AND column_name='plan') THEN
        ALTER TABLE netflix_accounts ADD COLUMN plan TEXT DEFAULT 'Premium';
    END IF;
END $$;

-- 2. Access Keys Table with plan and foreign key integrity
CREATE TABLE IF NOT EXISTS access_keys (
    code TEXT PRIMARY KEY,
    assigned_email TEXT REFERENCES netflix_accounts(email) ON UPDATE CASCADE ON DELETE RESTRICT,
    plan TEXT DEFAULT 'Premium',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    expire_at TEXT
);

DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='access_keys' AND column_name='plan') THEN
        ALTER TABLE access_keys ADD COLUMN plan TEXT DEFAULT 'Premium';
    END IF;
END $$;

-- 3. Warranty Requests Table with blocked_reason
CREATE TABLE IF NOT EXISTS requests (
    id BIGSERIAL PRIMARY KEY,
    code TEXT REFERENCES access_keys(code) ON UPDATE CASCADE ON DELETE SET NULL,
    u7buy_order_id TEXT,
    image_url TEXT,
    reason TEXT,
    status TEXT DEFAULT 'pending',
    blocked_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='requests' AND column_name='blocked_reason') THEN
        ALTER TABLE requests ADD COLUMN blocked_reason TEXT;
    END IF;
END $$;

-- 4. Idempotent Operations Table
CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    assigned_email TEXT,
    detail_code TEXT,
    payload_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 5. Outbox Events Table for reliable post-commit notifications
CREATE TABLE IF NOT EXISTS events_outbox (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'failed')),
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMPTZ
);

-- 6. Rotation Events Table
CREATE TABLE IF NOT EXISTS rotation_events (
    id BIGSERIAL PRIMARY KEY,
    code TEXT REFERENCES access_keys(code) ON UPDATE CASCADE ON DELETE SET NULL,
    old_email TEXT,
    new_email TEXT,
    actor TEXT,
    reason TEXT,
    request_id TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 7. Orders Table
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    code TEXT UNIQUE REFERENCES access_keys(code) ON UPDATE CASCADE ON DELETE SET NULL,
    status TEXT DEFAULT 'unverified' CHECK (status IN ('verified', 'unverified', 'cancelled')),
    verified_by TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 8. Order Audit Log
CREATE TABLE IF NOT EXISTS order_audit_log (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT,
    action TEXT,
    actor TEXT,
    old_code TEXT,
    new_code TEXT,
    old_status TEXT,
    new_status TEXT,
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 9. System Configuration Table
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- 7. Backfill legacy access keys plans based on code length invariants
UPDATE access_keys SET plan = 'Premium' WHERE (plan IS NULL OR plan = '') AND LENGTH(code) = 15;
UPDATE access_keys SET plan = 'Standard' WHERE (plan IS NULL OR plan = '') AND LENGTH(code) = 10;
UPDATE access_keys SET plan = 'Standard_Ads' WHERE (plan IS NULL OR plan = '') AND LENGTH(code) = 8;
UPDATE access_keys SET plan = 'Basic' WHERE (plan IS NULL OR plan = '') AND LENGTH(code) = 5;
UPDATE access_keys SET plan = 'Premium' WHERE plan IS NULL OR plan = '';
