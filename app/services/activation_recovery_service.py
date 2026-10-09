"""Verify replacement outside transactions; commit only a verified assignment."""
import json
import database as db
from app.services.allocation_service import get_max_capacity, match_plan, is_account_usable
from app.services.business_result import OperationResult


def candidate(plan, excluded):
    excluded = {str(email or '').casefold() for email in excluded}
    capacity = get_max_capacity(plan)
    if db.SUPABASE_KEY:
        # A backend-only RPC performs filtering and usage counts in PostgreSQL.
        result = db.get_supabase().rpc('activation_candidate', {
            'p_plan': plan, 'p_excluded': sorted(excluded), 'p_capacity': capacity}).execute()
        rows = result.data or []
        if not rows:
            return None
        row = rows[0]
        return (row['email'], row.get('expire_date'), row['netflix_id'], row.get('secure_netflix_id'),
                row.get('created_at'), row.get('plan'), row.get('status'))
    conn = db.get_sqlite_conn()
    try:
        rows = conn.execute("""SELECT a.email,a.expire_date,a.netflix_id,a.secure_netflix_id,a.created_at,a.plan,a.status,
                    (SELECT COUNT(*) FROM access_keys k WHERE k.assigned_email=a.email) AS used
                FROM netflix_accounts a ORDER BY CASE WHEN a.status='live' THEN 0 ELSE 1 END, used, a.email""").fetchall()
        return next((row[:7] for row in rows if row[0].casefold() not in excluded
                     and match_plan(row[5], plan) and is_account_usable(row[6]) and row[7] < capacity), None)
    finally:
        conn.close()


def commit_verified(code, old_email, new_email, plan):
    """Recheck capacity and original assignment under a short transaction."""
    capacity = get_max_capacity(plan)
    if db.SUPABASE_KEY:
        try:
            result = db.get_supabase().rpc('commit_activation_recovery', {
                'p_code':code, 'p_old_email':old_email, 'p_new_email':new_email,
                'p_plan':plan, 'p_capacity':capacity}).execute()
            row = result.data
            if isinstance(row,list):
                row = row[0] if row else {}
            return OperationResult(status=row.get('status','temporarily_unavailable'),
                assigned_email=row.get('assigned_email'), retryable=row.get('status') != 'success')
        except Exception:
            # Unknown RPC outcome: inspect the same code; never choose another account blindly.
            try:
                result = db.get_supabase().table('access_keys').select('assigned_email').eq('code',code).execute()
                if result.data and result.data[0]['assigned_email'] == new_email:
                    return OperationResult(status='success', assigned_email=new_email)
            except Exception:
                pass
            return OperationResult(status='temporarily_unavailable', retryable=True)
    conn = db.get_sqlite_conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT assigned_email,expire_at FROM access_keys WHERE code=?',(code,)).fetchone()
        if not row or row[0] != old_email:
            return OperationResult(status='already_processed',assigned_email=row[0] if row else None)
        from datetime import date
        if row[1] and date.fromisoformat(row[1]) < date.today():
            return OperationResult(status='invalid_input')
        account = conn.execute('SELECT plan,status FROM netflix_accounts WHERE email=?',(new_email,)).fetchone()
        count = conn.execute('SELECT COUNT(*) FROM access_keys WHERE assigned_email=?',(new_email,)).fetchone()[0]
        if not account or not match_plan(account[0],plan) or not is_account_usable(account[1]) or count >= capacity:
            return OperationResult(status='out_of_stock')
        columns = {r[1] for r in conn.execute('PRAGMA table_info(access_keys)')}
        version = ',assignment_version=COALESCE(assignment_version,1)+1' if 'assignment_version' in columns else ''
        conn.execute(f'UPDATE access_keys SET assigned_email=?{version} WHERE code=?',(new_email,code))
        conn.execute("UPDATE netflix_accounts SET status='live' WHERE email=?",(new_email,))
        conn.execute('CREATE TABLE IF NOT EXISTS rotation_events (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, old_email TEXT, new_email TEXT, actor TEXT, reason TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        conn.execute("INSERT INTO rotation_events(code,old_email,new_email,actor,reason) VALUES(?,?,?,'system:activation','verified recovery')",(code,old_email,new_email))
        from app.services.outbox_service import record_outbox_event
        if record_outbox_event('account_replaced',{'code':code,'old_email':old_email,'new_email':new_email,'actor':'system:activation'},conn=conn) is None:
            raise RuntimeError('Event not saved')
        conn.commit()
        return OperationResult(status='success',assigned_email=new_email)
    except Exception:
        conn.rollback()
        return OperationResult(status='temporarily_unavailable',retryable=True)
    finally:
        conn.close()
