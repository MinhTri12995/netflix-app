import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
const require=createRequire(resolve(process.argv[2],'package.json'));
const {PGlite}=require('@electric-sql/pglite');
const db=new PGlite();
const sql=await readFile(new URL('../../supabase/migrations/20261009085619_activation_recovery_admin.sql',import.meta.url),'utf8');
await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
CREATE TABLE netflix_accounts(email text PRIMARY KEY,expire_date text,netflix_id text,secure_netflix_id text,created_at timestamptz DEFAULT now(),plan text,status text DEFAULT 'usable' CHECK(status IN ('usable','needs_review','blocked_for_new_assignments')));
CREATE TABLE access_keys(code text PRIMARY KEY,assigned_email text,created_at timestamptz DEFAULT now(),expire_at text);
CREATE TABLE events_outbox(id bigserial PRIMARY KEY,event_type text,payload jsonb,status text DEFAULT 'pending',created_at timestamptz DEFAULT now());
INSERT INTO netflix_accounts(email,netflix_id,plan) VALUES('old','n1','Premium'),('new','n2','Premium'),('standard','n3','Standard');
INSERT INTO access_keys(code,assigned_email,expire_at) VALUES('KEY0000000000001','old','2099-12-31');`);
// The earlier activation migration upgrades the authoritative legacy CHECK.
await db.exec(await readFile(new URL('../../supabase/migrations/20261009052917_portal_activation_schema.sql',import.meta.url),'utf8'));
await db.exec(sql); await db.exec(sql);
assert.equal((await db.query("SELECT plan FROM access_keys")).rows[0].plan,'Premium');
for(const role of ['anon','authenticated']) {
 await db.exec(`SET ROLE ${role}`);
 await assert.rejects(db.query('SELECT admin_inventory_summary()'),/permission denied/);
 await db.exec('RESET ROLE');
}
let candidate=(await db.query("SELECT email FROM activation_candidate('Premium',ARRAY['old'],1)")).rows;
assert.equal(candidate[0].email,'new');
let result=(await db.query("SELECT commit_activation_recovery('KEY0000000000001','old','standard','Premium',1) AS r")).rows[0].r;
assert.equal(result.status,'out_of_stock');
assert.equal((await db.query('SELECT assigned_email FROM access_keys')).rows[0].assigned_email,'old');
result=(await db.query("SELECT commit_activation_recovery('KEY0000000000001','old','new','Premium',1) AS r")).rows[0].r;
assert.equal(result.status,'success');
for(let i=0;i<20;i++) {
 result=(await db.query("SELECT commit_activation_recovery('KEY0000000000001','old','new','Premium',1) AS r")).rows[0].r;
 assert.equal(result.status,'already_processed');
}
assert.equal((await db.query('SELECT count(*)::int n FROM events_outbox')).rows[0].n,1);
assert.equal((await db.query('SELECT assignment_version FROM access_keys')).rows[0].assignment_version,2);
await db.exec("INSERT INTO access_keys(code,assigned_email,expire_at,plan) VALUES('ANOTHERKEY0000001','old','2099-12-31','Premium')");
result=(await db.query("SELECT commit_activation_recovery('ANOTHERKEY0000001','old','new','Premium',1) AS r")).rows[0].r;
assert.equal(result.status,'out_of_stock');
const summary=(await db.query('SELECT admin_inventory_summary() AS r')).rows[0].r;
assert.equal(summary.codes.Premium,2);
assert.equal(summary.health.dangling,0);
// Legacy INSERT/UPDATE writers must share the same admission guard as recovery.
for (let i=0;i<3;i++) await db.exec(`INSERT INTO access_keys(code,assigned_email,plan) VALUES('FILL${i}','new','Premium')`);
await assert.rejects(db.exec("INSERT INTO access_keys(code,assigned_email,plan) VALUES('OVERFLOW','new','Premium')"),/capacity/i);
await assert.rejects(db.exec("UPDATE access_keys SET assigned_email='new' WHERE code='ANOTHERKEY0000001'"),/capacity/i);
await db.exec("UPDATE access_keys SET expire_at='2099-12-31' WHERE assigned_email='new'");
assert.equal((await db.query("SELECT count(*)::int n FROM access_keys WHERE assigned_email='new'")).rows[0].n,4);
console.log('PASS legacy backfill, repeat migration, restricted RPCs, plan protection, capacity, retry idempotency, one event, summary');
{
 const legacySql=await readFile(new URL('../../supabase/migrations/20261009093237_restore_legacy_dashboard_counter.sql',import.meta.url),'utf8');
 await db.exec(legacySql); await db.exec(legacySql);
 await db.exec("INSERT INTO netflix_accounts(email,netflix_id,plan) VALUES('ads','n4','Standard with Ads'),('basic','n5',' Basic ')");
 await db.exec("INSERT INTO access_keys(code,assigned_email,plan) VALUES('NEWSTANDARDKEY16','standard','Standard')");
 const restored=(await db.query('SELECT admin_inventory_summary() AS r')).rows[0].r;
 assert.equal(restored.accounts.Premium,3);
 assert.equal(restored.accounts.Standard_Ads,0);
 assert.equal(restored.accounts.Basic,1);
 assert.equal(restored.codes.Standard,0);
 assert.equal(restored.codes.Premium,3);
 assert.equal(restored.codes.Basic,3);
 assert.equal((await db.query("SELECT plan FROM access_keys WHERE code='NEWSTANDARDKEY16'")).rows[0].plan,'Standard');
 for(const role of ['anon','authenticated']) {
  await db.exec(`SET ROLE ${role}`);
  await assert.rejects(db.query('SELECT admin_inventory_summary()'),/permission denied/);
  await db.exec('RESET ROLE');
 }
 console.log('PASS legacy counter restored without changing business plans or RPC permissions');
}
if(process.argv[3]) {
 await db.exec(await readFile(resolve(process.argv[3]),'utf8'));
 assert.equal((await db.query("SELECT activation_capacity('Premium') AS n")).rows[0].n,2);
 assert.equal((await db.query("SELECT count(*)::int AS n FROM access_keys WHERE assigned_email='new'")).rows[0].n,4);
 await db.exec("UPDATE access_keys SET expire_at='2099-12-31' WHERE assigned_email='new'");
 await assert.rejects(db.exec("INSERT INTO access_keys(code,assigned_email,plan) VALUES('EXTRA','new','Premium')"),/capacity/i);
 await db.exec("INSERT INTO netflix_accounts(email,netflix_id,plan) VALUES('fresh','nfresh','Premium')");
 await db.exec("INSERT INTO access_keys(code,assigned_email,plan) VALUES('FRESH1','fresh','Premium'),('FRESH2','fresh','Premium')");
 await assert.rejects(db.exec("INSERT INTO access_keys(code,assigned_email,plan) VALUES('FRESH3','fresh','Premium')"),/capacity/i);
 assert.equal((await db.query("SELECT count(*)::int AS n FROM access_keys WHERE assigned_email='fresh'")).rows[0].n,2);
 console.log('PASS Premium two-code capacity and preservation of existing four-code assignments');
}
await db.close();
