// Run on disposable PostgreSQL (PGlite); no URLs, credentials or external calls.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';

const require = createRequire(resolve(process.argv[2], 'package.json'));
const { PGlite } = require('@electric-sql/pglite');
const migration = await readFile(new URL('../../supabase/migrations/20261009052917_portal_activation_schema.sql', import.meta.url), 'utf8');
const legacy = `CREATE TABLE public.netflix_accounts (
    email TEXT PRIMARY KEY, netflix_id TEXT, plan TEXT
); INSERT INTO public.netflix_accounts VALUES ('local@example.test', 'fixture-cookie', 'Premium');`;
const oldStatus = `ALTER TABLE public.netflix_accounts ADD COLUMN status TEXT DEFAULT 'usable'
    CHECK (status IN ('usable', 'needs_review', 'blocked_for_new_assignments'));`;

async function scenario(name, setup, check) {
    const db = new PGlite();
    try {
        await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;');
        await db.exec(legacy + setup);
        await check(db);
        console.log(`PASS ${name}`);
    } finally {
        await db.close();
    }
}

async function apply(db) {
    await db.exec(migration);
}

async function expectRollback(db, message) {
    await assert.rejects(apply(db), message);
    // Failed explicit transaction must be rolled back before reading evidence.
    await db.exec('ROLLBACK');
}

await scenario('legacy schema, idempotency, preserved accounts, restricted outbox', '', async db => {
    await apply(db);
    await apply(db);
    assert.deepEqual((await db.query('SELECT email, netflix_id, plan, status FROM public.netflix_accounts')).rows,
        [{ email: 'local@example.test', netflix_id: 'fixture-cookie', plan: 'Premium', status: 'usable' }]);
    assert.equal((await db.query("SELECT relrowsecurity FROM pg_class WHERE oid='public.events_outbox'::regclass")).rows[0].relrowsecurity, true);
    for (const role of ['anon', 'authenticated']) {
        await db.exec(`SET ROLE ${role}`);
        try {
            await assert.rejects(db.query('SELECT * FROM public.events_outbox'), /permission denied/);
        } finally {
            await db.exec('RESET ROLE');
        }
    }
    await db.exec('SET ROLE service_role');
    const inserted = await db.query("INSERT INTO public.events_outbox (event_type,payload) VALUES ('telegram_alert', '{\"message\":\"fixture\"}') RETURNING id");
    await db.query("UPDATE public.events_outbox SET status='delivered',delivered_at=now() WHERE id=$1", [inserted.rows[0].id]);
    assert.equal((await db.query('SELECT status FROM public.events_outbox')).rows[0].status, 'delivered');
    await db.exec('RESET ROLE');
});

await scenario('previous migration constraint accepts live after repair', oldStatus, async db => {
    await apply(db);
    await db.exec("UPDATE public.netflix_accounts SET status='live'");
    assert.equal((await db.query('SELECT status FROM public.netflix_accounts')).rows[0].status, 'live');
});

await scenario('known legacy statuses are preserved exactly', `ALTER TABLE public.netflix_accounts ADD COLUMN status TEXT;
    INSERT INTO public.netflix_accounts (email,status) VALUES
    ('review@example.test','needs_review'), ('dead@example.test','dead'),
    ('live@example.test',' LIVE '), ('empty@example.test',''), ('null@example.test',NULL);`, async db => {
    const before = (await db.query('SELECT * FROM public.netflix_accounts ORDER BY email')).rows;
    await apply(db);
    assert.deepEqual((await db.query('SELECT * FROM public.netflix_accounts ORDER BY email')).rows, before);
});

await scenario('existing outbox payload and retry history are preserved', oldStatus + `
    CREATE TABLE public.events_outbox (
        id BIGSERIAL PRIMARY KEY, event_type TEXT NOT NULL, payload JSONB NOT NULL,
        status TEXT DEFAULT 'pending', retry_count INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now(), delivered_at TIMESTAMPTZ
    ); INSERT INTO public.events_outbox (event_type,payload,status,retry_count)
      VALUES ('telegram_alert','{"message":"fixture"}','failed',3);`, async db => {
    const before = (await db.query('SELECT * FROM public.events_outbox')).rows;
    await apply(db);
    await apply(db);
    assert.deepEqual((await db.query('SELECT * FROM public.events_outbox')).rows, before);
});

await scenario('unknown statuses abort without rewriting data', `
    ALTER TABLE public.netflix_accounts ADD COLUMN status TEXT DEFAULT 'custom_state';`, async db => {
    await expectRollback(db, /Unknown account statuses/);
    assert.equal((await db.query('SELECT status FROM public.netflix_accounts')).rows[0].status, 'custom_state');
    assert.equal((await db.query("SELECT to_regclass('public.events_outbox') AS relation")).rows[0].relation, null);
});

await scenario('custom status constraints require review', `
    ALTER TABLE public.netflix_accounts ADD COLUMN status TEXT DEFAULT 'usable';
    ALTER TABLE public.netflix_accounts ADD CONSTRAINT custom_status_rule CHECK(status IN ('usable','dead'));`, async db => {
    await expectRollback(db, /Review custom status constraint/);
    assert.equal((await db.query("SELECT count(*)::int AS count FROM pg_constraint WHERE conname='custom_status_rule'")).rows[0].count, 1);
});

await scenario('incompatible outbox aborts and restores original status constraint', oldStatus + `
    CREATE TABLE public.events_outbox (id BIGSERIAL PRIMARY KEY, event_type TEXT, payload TEXT);
    INSERT INTO public.events_outbox (event_type,payload) VALUES ('legacy','preserve me');`, async db => {
    await expectRollback(db, /Incompatible events_outbox column/);
    assert.equal((await db.query('SELECT payload FROM public.events_outbox')).rows[0].payload, 'preserve me');
    await assert.rejects(db.exec("UPDATE public.netflix_accounts SET status='live'"), /violates check constraint/);
});

console.log('7 migration scenarios passed; production database untouched.');
