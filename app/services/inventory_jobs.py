"""Durable inventory tasks; network checks run outside leased transactions."""
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
import database

KINDS = {'full_scan', 'payment_scan', 'missing_plans', 'duplicates', 'import', 'cleanup'}
log = logging.getLogger(__name__)
_workers = []
_worker_lock = threading.Lock()


def _rpc(name, params):
    return database.get_supabase().rpc('inventory_' + name, params).execute().data


def _conn():
    conn = database.get_sqlite_conn()
    conn.row_factory = sqlite3.Row
    conn.executescript('''CREATE TABLE IF NOT EXISTS inventory_runs (
      id TEXT PRIMARY KEY,kind TEXT,status TEXT,total INTEGER DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS inventory_items (
      id INTEGER PRIMARY KEY,run_id TEXT,email TEXT,status TEXT DEFAULT 'pending',
      attempts INTEGER DEFAULT 0,lease_token TEXT,lease_until REAL,fingerprint TEXT,
      payload TEXT,result TEXT,plan TEXT,finished_at TEXT,UNIQUE(run_id,email));''')
    return conn


def _fingerprint(a):
    return hashlib.sha256(((a['netflix_id'] or '') + chr(31) + (a['secure_netflix_id'] or '')).encode()).hexdigest()


def enqueue(kind, records=None):
    if kind not in KINDS: raise ValueError('Invalid inventory task')
    if kind == 'import':
        if not isinstance(records, list) or not 0 < len(records) <= 5000:
            raise ValueError('Chọn từ 1 đến 5000 tài khoản mỗi lần nhập.')
        clean = {}
        for record in records:
            if not isinstance(record, dict): raise ValueError('Tài khoản không hợp lệ.')
            nid = record.get('netflix_id')
            if not isinstance(nid, str) or not nid.strip() or len(nid) > 20000:
                raise ValueError('Cookie không hợp lệ.')
            email = record.get('email') or ('auto_' + hashlib.sha256(nid.encode()).hexdigest()[:20] + '@netflix.com')
            if not isinstance(email, str) or len(email) > 254 or '@' not in email:
                raise ValueError('Email không hợp lệ.')
            snid = record.get('secure_netflix_id') or ''
            if not isinstance(snid, str) or len(snid) > 20000:
                raise ValueError('Cookie không hợp lệ.')
            email = email.strip().lower()
            clean[email] = {'email': email, 'netflix_id': nid, 'secure_netflix_id': snid}
        records = list(clean.values())
    run_id = uuid.uuid4().hex
    if database.SUPABASE_KEY:
        return _rpc('enqueue', {'p_id': run_id, 'p_kind': kind, 'p_records': records or []})
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        active = conn.execute("SELECT id FROM inventory_runs WHERE status='running' ORDER BY created_at LIMIT 1").fetchone()
        if active: return {'id': active['id'], 'existing': True}
        conn.execute("INSERT INTO inventory_runs(id,kind,status) VALUES(?,?,'running')", (run_id, kind))
        if kind == 'import':
            conn.executemany('INSERT INTO inventory_items(run_id,email,payload) VALUES(?,?,?)', [(run_id, r['email'], json.dumps(r)) for r in records])
        else:
            cond = " WHERE COALESCE(trim(plan),'') IN ('','Unknown','UNKNOWN','VALID')" if kind == 'missing_plans' else ''
            if kind == 'cleanup': cond = " WHERE status IN ('needs_review','dead','expired')"
            conn.execute('INSERT INTO inventory_items(run_id,email) SELECT ?,email FROM netflix_accounts' + cond + ' ORDER BY email', (run_id,))
        n = conn.execute('SELECT count(*) FROM inventory_items WHERE run_id=?', (run_id,)).fetchone()[0]
        conn.execute('UPDATE inventory_runs SET total=?,status=? WHERE id=?', (n, 'running' if n else 'completed', run_id))
        conn.commit()
        return {'id': run_id, 'existing': False}
    finally: conn.close()


def claim():
    token = uuid.uuid4().hex
    if database.SUPABASE_KEY: return _rpc('claim', {'p_token': token})
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE'); now = time.time()
        conn.execute("UPDATE inventory_items SET status='done',result='ERROR',payload=NULL,finished_at=CURRENT_TIMESTAMP WHERE status='processing' AND lease_until<=? AND attempts>=3", (now,))
        conn.execute("UPDATE inventory_runs SET status='completed' WHERE status='running' AND NOT EXISTS(SELECT 1 FROM inventory_items i WHERE i.run_id=inventory_runs.id AND i.status<>'done')")
        if conn.execute("SELECT count(*) FROM inventory_items WHERE status='processing' AND lease_until>?", (now,)).fetchone()[0] >= 3:
            conn.commit(); return None
        item = conn.execute("SELECT i.*,r.kind FROM inventory_items i JOIN inventory_runs r ON r.id=i.run_id WHERE attempts<3 AND ((i.status='pending' AND (lease_until IS NULL OR lease_until<=?)) OR (i.status='processing' AND lease_until<=?)) ORDER BY i.id LIMIT 1", (now, now)).fetchone()
        if not item: conn.commit(); return None
        a = conn.execute('SELECT * FROM netflix_accounts WHERE email=?', (item['email'],)).fetchone()
        conn.execute("UPDATE inventory_items SET status='processing',attempts=attempts+1,lease_token=?,lease_until=?,fingerprint=? WHERE id=?", (token, now + 180, _fingerprint(a) if a else '', item['id']))
        conn.commit(); payload = json.loads(item['payload']) if item['payload'] else {}
        return {'id': item['id'], 'run_id': item['run_id'], 'email': item['email'], 'kind': item['kind'],
                'netflix_id': payload.get('netflix_id') if item['kind'] == 'import' else a['netflix_id'] if a else None,
                'secure_netflix_id': payload.get('secure_netflix_id') if item['kind'] == 'import' else a['secure_netflix_id'] if a else None, 'lease_token': token}
    finally: conn.close()


def finish(item, result, plan=None):
    if database.SUPABASE_KEY:
        return _rpc('finish', {'p_item': item['id'], 'p_token': item['lease_token'], 'p_result': result, 'p_plan': plan})
    conn = _conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        lease = conn.execute('SELECT * FROM inventory_items WHERE id=?', (item['id'],)).fetchone()
        if not lease or lease['status'] != 'processing' or lease['lease_token'] != item['lease_token'] or lease['lease_until'] <= time.time(): return False
        a = conn.execute('SELECT * FROM netflix_accounts WHERE email=?', (lease['email'],)).fetchone()
        if item['kind'] == 'import':
            payload = json.loads(lease['payload'])
            if result == 'LIVE' and plan in ('Premium','Standard','Standard with Ads','Basic'):
                keeper = conn.execute('SELECT email FROM netflix_accounts WHERE netflix_id=? ORDER BY email LIMIT 1', (payload['netflix_id'],)).fetchone()
                if a and lease['fingerprint'] != _fingerprint(a): result = 'CHANGED'
                elif keeper and keeper['email'] != lease['email']: result = 'KEPT'
                else:
                    conn.execute("INSERT INTO netflix_accounts(email,netflix_id,secure_netflix_id,plan,status) VALUES(?,?,?,?,'live') ON CONFLICT(email) DO UPDATE SET netflix_id=excluded.netflix_id,secure_netflix_id=excluded.secure_netflix_id,plan=excluded.plan,status=CASE WHEN netflix_accounts.status='blocked_for_new_assignments' THEN netflix_accounts.status ELSE 'live' END", (lease['email'], payload['netflix_id'], payload['secure_netflix_id'], plan))
            elif result == 'LIVE': result = 'UNKNOWN'
            elif result not in ('DIE','UNKNOWN','ERROR'): raise ValueError('Invalid result')
        elif not a: result = 'MISSING'
        elif lease['fingerprint'] != _fingerprint(a): result = 'CHANGED'
        elif item['kind'] == 'duplicates':
            keeper = conn.execute("SELECT email FROM netflix_accounts a WHERE netflix_id=? AND COALESCE(netflix_id,'')<>'' ORDER BY EXISTS(SELECT 1 FROM access_keys k WHERE instr(','||replace(k.assigned_email,' ','')||',',','||a.email||',')>0) DESC,(COALESCE(plan,'')<>'') DESC,email LIMIT 1", (a['netflix_id'],)).fetchone()
            if not keeper or keeper['email'] == lease['email']: result = 'KEPT'
            elif conn.execute("SELECT 1 FROM access_keys WHERE instr(','||replace(assigned_email,' ','')||',',','||?||',')>0 LIMIT 1", (lease['email'],)).fetchone(): result = 'PROTECTED'
            else: conn.execute('DELETE FROM netflix_accounts WHERE email=?', (lease['email'],)); result = 'DELETED'
        elif item['kind'] == 'cleanup' and result == 'DIE_CONFIRMED':
            if a['status'] not in ('needs_review','dead','expired'): result = 'CHANGED'
            elif conn.execute("SELECT 1 FROM access_keys WHERE instr(','||replace(assigned_email,' ','')||',',','||?||',')>0 LIMIT 1", (lease['email'],)).fetchone(): result = 'PROTECTED'
            else:
                conn.execute('DELETE FROM netflix_accounts WHERE email=?', (lease['email'],)); result = 'DELETED'
        elif result == 'LIVE':
            conn.execute("UPDATE netflix_accounts SET status=CASE WHEN status='blocked_for_new_assignments' THEN status ELSE 'live' END WHERE email=?", (lease['email'],))
            if plan in ('Premium','Standard','Standard with Ads','Basic') and item['kind'] not in ('payment_scan','cleanup'):
                conn.execute('UPDATE netflix_accounts SET plan=? WHERE email=?', (plan, lease['email']))
        elif result == 'DIE':
            conn.execute("UPDATE netflix_accounts SET status=CASE WHEN status='blocked_for_new_assignments' THEN status ELSE 'needs_review' END WHERE email=?", (lease['email'],))
        elif result not in ('UNKNOWN','ERROR','MISSING'): raise ValueError('Invalid result')
        if result in ('UNKNOWN','ERROR') and lease['attempts']<3:
            conn.execute("UPDATE inventory_items SET status='pending',result=NULL,lease_token=NULL,lease_until=? WHERE id=?",(time.time()+15,item['id']))
            conn.commit(); return True
        conn.execute("UPDATE inventory_items SET status='done',result=?,plan=?,payload=NULL,finished_at=CURRENT_TIMESTAMP,lease_token=NULL,lease_until=NULL WHERE id=?", (result, plan, item['id']))
        conn.execute("UPDATE inventory_runs SET updated_at=CURRENT_TIMESTAMP,status=CASE WHEN EXISTS(SELECT 1 FROM inventory_items WHERE run_id=? AND status<>'done') THEN 'running' ELSE 'completed' END WHERE id=?", (lease['run_id'], lease['run_id']))
        conn.commit(); return True
    finally: conn.close()


def progress(run_id=None):
    if database.SUPABASE_KEY: return _rpc('progress', {'p_id': run_id})
    conn = _conn()
    try:
        run = conn.execute('SELECT * FROM inventory_runs WHERE id=?' if run_id else 'SELECT * FROM inventory_runs ORDER BY rowid DESC LIMIT 1', (run_id,) if run_id else ()).fetchone()
        if not run: return None
        run_id = run['id']
        counts = dict(conn.execute("SELECT result,count(*) FROM inventory_items WHERE run_id=? AND status='done' GROUP BY result", (run_id,)).fetchall())
        recent = conn.execute("SELECT email,result,plan,finished_at FROM inventory_items WHERE run_id=? AND status='done' ORDER BY id DESC LIMIT 20", (run_id,)).fetchall()
        processing = conn.execute("SELECT email FROM inventory_items WHERE run_id=? AND status='processing' AND lease_until>?", (run_id, time.time())).fetchall()
        return {'run':dict(run),'processed':sum(counts.values()),'counts':counts,'recent':[dict(x) for x in recent],
                'processing':[x['email'] for x in processing],'history':[dict(x) for x in conn.execute('SELECT * FROM inventory_runs ORDER BY rowid DESC LIMIT 10')]}
    finally: conn.close()


def work_once():
    item = claim()
    if not item: return False
    if item['kind'] == 'duplicates': finish(item,'KEPT'); return True
    if not item['netflix_id']: finish(item,'MISSING'); return True
    import checker
    try:
        result,plan = checker.check_account_live(item['netflix_id'],item['secure_netflix_id'] or '',check_payment=True)
    except Exception as exc:
        log.warning('Inventory check failed run=%s item=%s type=%s',item['run_id'],item['id'],type(exc).__name__)
        result,plan='ERROR',None
    if item['kind'] == 'cleanup' and result == 'DIE':
        time.sleep(5)
        try:
            second, second_plan = checker.check_account_live(item['netflix_id'],item['secure_netflix_id'] or '',check_payment=True)
            if second == 'DIE': result,plan = 'DIE_CONFIRMED',None
            else: result,plan = second,second_plan
        except Exception as exc:
            log.warning('Inventory confirmation failed run=%s item=%s type=%s',item['run_id'],item['id'],type(exc).__name__)
            result,plan = 'ERROR',None
    finish(item,result,plan); return True


def start_worker(app):
    if app.testing or os.environ.get('DISABLE_ADMIN_WORKER')=='1': return
    def run():
        with app.app_context():
            while True:
                try:
                    if not work_once(): time.sleep(3)
                except Exception as exc:
                    log.warning('Inventory worker unavailable (%s)',type(exc).__name__)
                    time.sleep(10)
    with _worker_lock:
        if any(worker.is_alive() for worker in _workers): return
        _workers.clear()
        for index in range(3):
            worker=threading.Thread(target=run,daemon=True,name=f'inventory-worker-{index}')
            _workers.append(worker); worker.start()
